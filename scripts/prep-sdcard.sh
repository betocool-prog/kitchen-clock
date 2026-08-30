#!/usr/bin/env bash
#
# scripts/prep-sdcard.sh
#   Writes the SD-card provisioning bundle (built by
#   scripts/build-sd-bundle.sh) onto a freshly flashed Raspberry Pi
#   OS Lite Bookworm 64-bit SD card. Takes a single argument: the
#   block device of the SD card (e.g. /dev/sdc).
#
# Usage:
#   scripts/build-sd-bundle.sh
#   sudo scripts/prep-sdcard.sh /dev/sdc

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="${PROJECT_ROOT}/build/sd"

# ---------------------------------------------------------------------------
# Pre-flight

if [[ $# -lt 1 ]]; then
    cat >&2 <<'EOF'
usage: sudo prep-sdcard.sh <block-device> [--dry-run]

  e.g. sudo prep-sdcard.sh /dev/sdc

EOF
    exit 64
fi

DRY_RUN=0
if [[ "${2:-}" == "--dry-run" ]]; then
    DRY_RUN=1
fi

if [[ $EUID -ne 0 ]]; then
    echo "ERROR: re-run as root (sudo)." >&2
    exit 1
fi

SD_DEV="$1"
if [[ ! -b "${SD_DEV}" ]]; then
    # Allow /dev/mmcblk0 → /dev/mmcblk0p1 expansion below.
    if [[ ! -e "${SD_DEV}p1" ]]; then
        echo "ERROR: ${SD_DEV} is not a block device." >&2
        exit 1
    fi
fi

if [[ ! -d "${BUILD_DIR}" ]]; then
    echo "ERROR: ${BUILD_DIR} not found — run scripts/build-sd-bundle.sh first." >&2
    exit 1
fi

# shellcheck disable=SC1091
set -a; source "${PROJECT_ROOT}/secrets.env"; set +a

# ---------------------------------------------------------------------------
# Partition layout

# Two layouts are common in the wild:
#   - /dev/sdX with /dev/sdX1, /dev/sdX2 (USB card readers)
#   - /dev/mmcblkN with /dev/mmcblkNp1, /dev/mmcblkNp2 (built-in eMMC)
# Resolve the *p1 / *p2 paths from the input device.

case "${SD_DEV}" in
    /dev/mmcblk*)
        BOOT_DEV="${SD_DEV}p1"
        ROOT_DEV="${SD_DEV}p2"
        ;;
    *)
        BOOT_DEV="${SD_DEV}1"
        ROOT_DEV="${SD_DEV}2"
        ;;
esac

if [[ ! -b "${BOOT_DEV}" || ! -b "${ROOT_DEV}" ]]; then
    echo "ERROR: expected ${BOOT_DEV} (FAT32) and ${ROOT_DEV} (ext4) on ${SD_DEV}." >&2
    echo "       Did you flash Pi OS Lite Bookworm 64-bit to the card?" >&2
    exit 1
fi

# Confirm the partitions carry the right fstypes. We tolerate re-format
# but bail if they look like something exotic.
boot_fs="$(blkid -o value -s TYPE "${BOOT_DEV}" 2>/dev/null || true)"
root_fs="$(blkid -o value -s TYPE "${ROOT_DEV}" 2>/dev/null || true)"
if [[ "${boot_fs}" != "vfat" && "${boot_fs}" != "FAT32" && -n "${boot_fs}" ]]; then
    echo "ERROR: ${BOOT_DEV} is ${boot_fs}, expected vfat (FAT32)." >&2
    exit 1
fi
if [[ "${root_fs}" != "ext4" && -n "${root_fs}" ]]; then
    echo "ERROR: ${ROOT_DEV} is ${root_fs}, expected ext4." >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Mount + install

MNT_BOOT="$(mktemp -d --tmpdir=/mnt kclock-boot-XXXXXX)"
MNT_ROOT="$(mktemp -d --tmpdir=/mnt kclock-root-XXXXXX)"

cleanup() {
    set +e
    umount "${MNT_BOOT}" 2>/dev/null
    umount "${MNT_ROOT}" 2>/dev/null
    rmdir  "${MNT_BOOT}"  2>/dev/null
    rmdir  "${MNT_ROOT}"  2>/dev/null
}
trap cleanup EXIT

mount -t vfat -o rw "${BOOT_DEV}"  "${MNT_BOOT}"
mount -t ext4 -o rw "${ROOT_DEV}" "${MNT_ROOT}"

run() {
    if [[ ${DRY_RUN} -eq 1 ]]; then
        echo "DRY: $*"
    else
        "$@"
    fi
}

echo "Installing SD bundle onto ${SD_DEV} (${BOOT_DEV}, ${ROOT_DEV})" >&2

# --- Boot partition (FAT32) ---

run install -m 0644 "${BUILD_DIR}/userconf.txt"            "${MNT_BOOT}/userconf.txt"
run install -m 0644 "${BUILD_DIR}/ssh"                    "${MNT_BOOT}/ssh"
run install -m 0644 "${BUILD_DIR}/hostname_marker"        "${MNT_BOOT}/${HOSTNAME}"
run install -m 0644 "${BUILD_DIR}/locale.txt"             "${MNT_BOOT}/locale.txt"
run install -m 0644 "${BUILD_DIR}/timezone"               "${MNT_BOOT}/timezone"
run install -m 0600 "${BUILD_DIR}/wpa_supplicant.conf"    "${MNT_BOOT}/wpa_supplicant.conf"

# Direct UART serial console: enable UART0 (ttyAMA0 = serial0) at
# 115 200 baud 8N1 on GPIO 14 (TX) / GPIO 15 (RX).  We wire a
# 3.3 V USB-TTL adapter onto those pads. The Linux kernel command
# line is left as the image shipped it — recent Pi OS (Trixie)
# images default `console=ttyS0,...` and we don't override that.
SDK_FILE="${MNT_BOOT}/config.txt"
[[ ! -f "${SDK_FILE}.bak-prep" ]] && cp "${SDK_FILE}" "${SDK_FILE}.bak-prep"
if grep -qE '^[[:space:]]*enable_uart[[:space:]]*=' "${SDK_FILE}" 2>/dev/null; then
    printf 'config.txt: enable_uart already present, no edit\n' >&2
else
    printf '\n# UART serial console over GPIO 14/15 (kitchen-clock prep)\nenable_uart=1\n' \
        >> "${SDK_FILE}"
    echo "appended enable_uart=1 to config.txt" >&2
fi

# cmdline.txt: read-modify-write with shell primitives instead of
# sed -i. We never *prepend* console tokens (those are image-defined
# on Trixie and Bookworm); we only *append* tokens that the image
# shipped without. Specifically: root=PARTUUID=… (so the kernel can
# find the rootfs) and cfg80211.ieee80211_regdom=<alpha-2 country>
# (so CRDA unblocks wifi at boot — without it, the kernel keeps
# the radio soft-blocked via rfkill until something else sets the
# regdomain). Below + :regdom key both forms so the kernel picks
# whichever it recognises on the running version.
CMD_FILE="${MNT_BOOT}/cmdline.txt"
[[ ! -f "${CMD_FILE}.bak-prep" ]] && cp "${CMD_FILE}" "${CMD_FILE}.bak-prep"
content="$(cat "${CMD_FILE}" 2>/dev/null || true)"
if [[ -z "$content" ]]; then
    printf 'cmdline.txt: empty; cannot inject tokens automatically.\n' >&2
    printf '            run scripts/fix-cmdline.sh /dev/sdX on the host to recover.\n' >&2
else
    ROOT_PARTUUID="$(blkid -o value -s PARTUUID "${ROOT_DEV}" 2>/dev/null || true)"
    APPENDED=0

    if ! printf '%s' "$content" | grep -qE '(^|[[:space:]])root='; then
        if [[ -n "$ROOT_PARTUUID" ]]; then
            content="${content} root=PARTUUID=${ROOT_PARTUUID} cfg80211.ieee80211_regdom=${WIFI_COUNTRY}"
            APPENDED=1
            printf 'cmdline.txt: appended root=PARTUUID=%s + cfg80211.ieee80211_regdom=%s\n' \
                "${ROOT_PARTUUID}" "${WIFI_COUNTRY}" >&2
        else
            printf 'cmdline.txt: could not read PARTUUID of %s; root= NOT added.\n' "${ROOT_DEV}" >&2
        fi
    else
        # root= is already there — top up only the reg-dom hint(s).
        if ! printf '%s' "$content" | grep -qE 'ieee80211_regdom|80211\.regdom'; then
            content="${content} cfg80211.ieee80211_regdom=${WIFI_COUNTRY}"
            APPENDED=1
            printf 'cmdline.txt: appended cfg80211.ieee80211_regdom=%s\n' "${WIFI_COUNTRY}" >&2
        fi
    fi

    if [[ $APPENDED -eq 1 ]]; then
        printf '%s\n' "$content" > "${CMD_FILE}"
    else
        printf 'cmdline.txt: root= and regulatory domain already set, no edit\n' >&2
    fi
fi

# --- Rootfs (ext4) ---

run install -d -m 0755 \
    "${MNT_ROOT}/etc/NetworkManager/system-connections"
run install -m 0600 "${BUILD_DIR}/homewifi.nmconnection" \
    "${MNT_ROOT}/etc/NetworkManager/system-connections/homewifi.nmconnection"

run install -d -m 0755 "${MNT_ROOT}/etc/NetworkManager/conf.d"
run install -m 0644 "${BUILD_DIR}/10-kclock-wifi-managed.conf" \
    "${MNT_ROOT}/etc/NetworkManager/conf.d/10-kclock-wifi-managed.conf"

run install -d -m 0755 "${MNT_ROOT}/etc/ssh/sshd_config.d"
run install -m 0644 "${BUILD_DIR}/02-kclock-sshd.conf" \
    "${MNT_ROOT}/etc/ssh/sshd_config.d/02-kclock-sshd.conf"
run install -m 0644 "${BUILD_DIR}/99-kclock-banner-ssh.conf" \
    "${MNT_ROOT}/etc/ssh/sshd_config.d/99-kclock-banner-ssh.conf"
run install -m 0644 "${BUILD_DIR}/issue.net" \
    "${MNT_ROOT}/etc/issue.net"

# userconf.txt is consumed before /home/<user> exists; we put the SSH
# keys alongside the home directory using UID 1000 so that the user
# become-owner when first boot completes.
run install -d -m 0700 -o 1000 -g 1000 \
    "${MNT_ROOT}/home/${USER_NAME}/.ssh"
run install -m 0600 -o 1000 -g 1000 \
    "${BUILD_DIR}/authorized_keys" \
    "${MNT_ROOT}/home/${USER_NAME}/.ssh/authorized_keys"

# Hostname: write /etc/hostname directly. Trixie ignores the
# /boot/firmware/<hostname> empty-file marker (the Bookworm-era
# rpi-bookworm-init hook was deprecated upstream); only editing
# /etc/hostname is durable across current Pi OS flavours. The
# bootfs marker file is still dropped (kept) for completeness on
# Bookworm and older images that may keep using it.
if [[ -n "${HOSTNAME}" ]]; then
    printf '%s\n' "${HOSTNAME}" > "${MNT_ROOT}/etc/hostname"
    chmod 0644 "${MNT_ROOT}/etc/hostname"

    # Also place the hostname in /etc/hosts so local-resolve works
    # (otherwise sudo's NSS goes through other resolvers and prints
    # "unable to resolve host kclock: …" on every shell — cosmetic
    # but annoying).
    if [[ -f "${MNT_ROOT}/etc/hosts" ]]; then
        if ! grep -qE "[[:space:]]${HOSTNAME}(\$|[[:space:]])" "${MNT_ROOT}/etc/hosts" 2>/dev/null; then
            # Append the host on the existing 127.0.0.1 line; if
            # none has space for it, append a fresh alias line.
            if grep -qE '^127\.0\.0\.1[[:space:]]+' "${MNT_ROOT}/etc/hosts"; then
                sed -i "/^127\.0\.0\.1[[:space:]]/ s/\$/ ${HOSTNAME}/" "${MNT_ROOT}/etc/hosts"
            else
                printf '127.0.0.1 %s\n' "${HOSTNAME}" >> "${MNT_ROOT}/etc/hosts"
            fi
        fi
    else
        printf '127.0.0.1 localhost %s\n::1 localhost ip6-localhost ip6-loopback\nff02::1 ip6-allnodes\nff02::2 ip6-allrouters\n' \
            "${HOSTNAME}" >> "${MNT_ROOT}/etc/hosts"
    fi
    printf 'rootfs: /etc/hostname = %s\n' "${HOSTNAME}" >&2
fi

# Direct UART console: drop a serial-getty@ttyAMA0.service
# symlink under getty.target.wants so systemd runs a login
# prompt on /dev/ttyAMA0 (the Pi UART0 = serial0). ttyAMA0 is
# the natural choice for the BCM2835 / Pi Zero W.

# Trixie-specific rebooted boot: a one-shot systemd unit that
# runs a few microseconds before NetworkManager and undoes what
# the Trixie firstboot persistently writes to the rfkill state
# file and NetworkManager.state. Symlink it into NM's requires/
# directory so it's guaranteed to run first.
NM_REQUIRES_DIR="${MNT_ROOT}/etc/systemd/system/NetworkManager.service.requires"
run install -d -m 0755 "${NM_REQUIRES_DIR}"
run install -m 0644 "${BUILD_DIR}/kclock-wifi-unblock.service" \
    "${MNT_ROOT}/etc/systemd/system/kclock-wifi-unblock.service"
run ln -sf "/etc/systemd/system/kclock-wifi-unblock.service" \
    "${NM_REQUIRES_DIR}/kclock-wifi-unblock.service"
printf 'rootfs: /etc/systemd/system/kclock-wifi-unblock.service + NM requires → symlink\n' >&2

# CRDA / rfkill state. Pi OS firstboot writes `1` to the per-
# platform rfkill flag at /var/lib/systemd/rfkill/platform-…:wlan
# until something sets the regulatory domain. Without the
# cmdline's cfg80211.ieee80211_regdom hint (above) and clearing
# this file, the kernel keeps wifi software-blocked. We write
# `0` here so the rfkill subsystem agrees wifi is unblocked.
RFKILL_DIR="${MNT_ROOT}/var/lib/systemd/rfkill"
if [[ -d "${RFKILL_DIR}" ]]; then
    for f in "${RFKILL_DIR}"/*:wlan; do
        if [[ -e "$f" ]]; then
            printf '0' > "$f"
            printf 'rootfs: rfkill state file %s set to 0\n' "${f##*/}" >&2
        fi
    done
fi

# Supplementary regulatory-domain paths, mirroring what
# `raspi-config nonint do_wifi_country AU` does. Belt-and-braces
# so the boot-time "Use raspi-config to set the country before
# use" notice in the message of the day goes away.
# /etc/default/crda
run install -d -m 0755 "${MNT_ROOT}/etc/default"
run install -m 0644 /dev/stdin "${MNT_ROOT}/etc/default/crda" <<EOF
# Set by kitchen-clock prep scripts.
REGDOMAIN=${WIFI_COUNTRY}
EOF

# /etc/wpa_supplicant/wpa_supplicant.conf
WSUP_DIR="${MNT_ROOT}/etc/wpa_supplicant"
run install -d -m 0755 "${WSUP_DIR}"
if [[ ! -e "${WSUP_DIR}/wpa_supplicant.conf" ]]; then
    run install -m 0644 /dev/stdin "${WSUP_DIR}/wpa_supplicant.conf" <<EOF
ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
update_config=1
country=${WIFI_COUNTRY}
EOF
else
    if ! grep -qE '^[[:space:]]*country[[:space:]]*=' "${WSUP_DIR}/wpa_supplicant.conf"; then
        printf 'country=%s\n' "${WIFI_COUNTRY}" >> "${WSUP_DIR}/wpa_supplicant.conf"
        printf 'rootfs: /etc/wpa_supplicant/wpa_supplicant.conf: appended country=%s\n' "${WIFI_COUNTRY}" >&2
    fi
fi
GETTY_TEMPLATE="${MNT_ROOT}/lib/systemd/system/serial-getty@.service"
[[ ! -e "${GETTY_TEMPLATE}" ]] && GETTY_TEMPLATE="${MNT_ROOT}/usr/lib/systemd/system/serial-getty@.service"
GETTY_LINKDIR="${MNT_ROOT}/etc/systemd/system/getty.target.wants"
run install -d -m 0755 "${GETTY_LINKDIR}"
run ln -sf "/lib/systemd/system/serial-getty@.service" \
    "${GETTY_LINKDIR}/serial-getty@ttyAMA0.service"

# ---------------------------------------------------------------------------
# Summary

echo "" >&2
echo "Boot partition (FAT32): ${BOOT_DEV} → ${MNT_BOOT}" >&2
ls -la "${MNT_BOOT}" | sed -e "s|^|  |" >&2

echo "" >&2
echo "Root filesystem (ext4): ${ROOT_DEV} → ${MNT_ROOT}" >&2
ls -la "${MNT_ROOT}/etc/NetworkManager/system-connections" \
       "${MNT_ROOT}/etc/NetworkManager/conf.d" \
       "${MNT_ROOT}/etc/ssh/sshd_config.d" \
       "${MNT_ROOT}/etc/systemd/system/getty.target.wants" \
       "${MNT_ROOT}/home/${USER_NAME}/.ssh" 2>/dev/null \
   | sed -e "s|^|  |" >&2

echo "" >&2
echo "UART serial console (boot):" >&2
grep -E '^[[:space:]]*enable_uart[[:space:]]*=' "${MNT_BOOT}/config.txt" 2>/dev/null \
   | sed -e "s|^|  |" >&2
head -c 200 "${MNT_BOOT}/cmdline.txt" 2>/dev/null
printf '\n'
printf '  getty link: %s\n' \
   "$(ls -la "${GETTY_LINKDIR}/serial-getty@ttyAMA0.service" 2>/dev/null | awk '{print $11}')" >&2

echo "" >&2
echo "Done. Unmounting…" >&2
