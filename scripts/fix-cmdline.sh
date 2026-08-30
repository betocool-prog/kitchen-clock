#!/usr/bin/env bash
#
# scripts/fix-cmdline.sh
#
# Re-write the boot partition's `cmdline.txt` with a complete
# kernel command line, given an SD card block device. It auto-
# detects the rootfs PARTUUID from the second partition.
#
# Usage:
#   sudo scripts/fix-cmdline.sh /dev/sdX
#   sudo scripts/fix-cmdline.sh /dev/mmcblk0
#
# What it does:
#   1. Resolves boot + root partition block devices.
#   2. Reads the EXT4 rootfs's PARTUUID via blkid.
#   3. Backs up any existing cmdline.txt to cmdline.txt.bak-cli.
#   4. Writes a Pi-Zero-W compatible kernel command line with the
#      right root= token, console left at the value we currently
#      see on this Trixie image (ttyS0 = PL011 = GPIO 14/15 on
#      kernel 6.18/BCM2835).

set -euo pipefail

if [[ $# -lt 1 ]]; then
    cat >&2 <<'EOF'
usage: sudo scripts/fix-cmdline.sh <block-device>

  e.g. sudo scripts/fix-cmdline.sh /dev/sdc

EOF
    exit 64
fi

if [[ $EUID -ne 0 ]]; then
    echo "ERROR: re-run as root (sudo)." >&2
    exit 1
fi

SD_DEV="$1"
case "${SD_DEV}" in
    /dev/mmcblk*) BOOT_DEV="${SD_DEV}p1"; ROOT_DEV="${SD_DEV}p2" ;;
    *)             BOOT_DEV="${SD_DEV}1";  ROOT_DEV="${SD_DEV}2"  ;;
esac

if [[ ! -b "${BOOT_DEV}" || ! -b "${ROOT_DEV}" ]]; then
    echo "ERROR: expected ${BOOT_DEV} (vfat) and ${ROOT_DEV} (ext4) on ${SD_DEV}." >&2
    exit 1
fi

# Sanity: rootfs must have an ext4 filesystem with a PARTUUID.
root_fs="$(blkid -o value -s TYPE  "${ROOT_DEV}" 2>/dev/null || true)"
boot_fs="$(blkid -o value -s TYPE  "${BOOT_DEV}" 2>/dev/null || true)"
ROOT_PARTUUID="$(blkid -o value -s PARTUUID "${ROOT_DEV}" 2>/dev/null || true)"
if [[ -z "${ROOT_PARTUUID}" ]]; then
    echo "ERROR: ${ROOT_DEV} has no PARTUUID; cannot write cmdline.txt." >&2
    exit 1
fi
if [[ -n "${root_fs}" && "${root_fs}" != "ext4" ]]; then
    echo "WARN: ${ROOT_DEV} is ${root_fs}, not ext4. PARTUUID still used." >&2
fi

# Mount the boot partition.
MNT_BOOT="$(mktemp -d --tmpdir=/mnt kclock-boot-XXXXXX)"
cleanup() {
    set +e
    umount "${MNT_BOOT}" 2>/dev/null
    rmdir  "${MNT_BOOT}" 2>/dev/null
}
trap cleanup EXIT
mount -t vfat -o rw "${BOOT_DEV}" "${MNT_BOOT}"

# Preserve any existing cmdline.txt once.
[[ ! -f "${MNT_BOOT}/cmdline.txt.bak-cli" ]] \
    && cp "${MNT_BOOT}/cmdline.txt" "${MNT_BOOT}/cmdline.txt.bak-cli"

# Compose a complete kernel command line for the BCM2835 / Pi Zero
# W. On Trixie kernel 6.18, the 8250 driver drag the PL011 in as
# ttyS0; that's the UART on GPIO 14/15.
NEW_CMDLINE="console=ttyS0,115200 console=tty1 root=PARTUUID=${ROOT_PARTUUID} rootfstype=ext4 fsck.repair=yes rootwait cfg80211.ieee80211_regdom=AU"
printf '%s\n' "${NEW_CMDLINE}" > "${MNT_BOOT}/cmdline.txt"
sync

echo "wrote cmdline.txt to ${BOOT_DEV}:"
printf '  %s\n' "${NEW_CMDLINE}"
echo
echo "previous content saved at ${BOOT_DEV}:cmdline.txt.bak-cli"
echo "(run 'head /media/<...>/cmdline.txt.bak-cli' before unmount to recover if needed)"
