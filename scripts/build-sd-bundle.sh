#!/usr/bin/env bash
#
# scripts/build-sd-bundle.sh
#   Render the SD-card provisioning bundle from
#   scripts/templates/sd/ into ./build/sd/, using values from
#   secrets.env. The output of this script is consumed by
#   scripts/prep-sdcard.sh on the SD card device.

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEMPLATE_DIR="${PROJECT_ROOT}/scripts/templates/sd"
BUILD_DIR="${PROJECT_ROOT}/build/sd"

if [[ ! -f "${PROJECT_ROOT}/secrets.env" ]]; then
    cat >&2 <<'EOF'
ERROR: secrets.env not found.

  1. Copy secrets.env.example to secrets.env.
  2. Fill in the values that apply to your deployment.
  3. Re-run this script.

EOF
    exit 1
fi

# shellcheck disable=SC1091
set -a; source "${PROJECT_ROOT}/secrets.env"; set +a

# Required values (build fails fast if any are empty).
required=(
    WIFI_SSID WIFI_PSK_HEX WIFI_COUNTRY
    HOSTNAME
    STATIC_IP GATEWAY DNS_SERVERS
    LOCALE_PRIMARY LOCALE_SECONDARY TIMEZONE
    USER_NAME USER_PASS_HASH
    SSH_PUBKEY
)
for v in "${required[@]}"; do
    if [[ -z "${!v:-}" ]]; then
        echo "ERROR: variable ${v} is empty in secrets.env" >&2
        exit 1
    fi
done

rm -rf "${BUILD_DIR}"
mkdir -p "${BUILD_DIR}"

render_template() {
    # Usage: render_template <name> [<extra_chmod>]
    local name="$1"
    local src="${TEMPLATE_DIR}/${name}.tpl"
    local dst="${BUILD_DIR}/${name}"
    if [[ ! -f "${src}" ]]; then
        echo "ERROR: missing template ${src}" >&2
        exit 1
    fi
    envsubst < "${src}" > "${dst}"
}

# --- Boot partition (FAT32) ---

# userconf.txt — username:hash
render_template userconf.txt
chmod 0644 "${BUILD_DIR}/userconf.txt"

# ssh — empty flag file
: > "${BUILD_DIR}/ssh"
chmod 0644 "${BUILD_DIR}/ssh"

# hostname marker — empty file, but its NAME is the hostname.
# A second copy named after ${HOSTNAME} will be installed by prep-sdcard.sh.
: > "${BUILD_DIR}/hostname_marker"
chmod 0644 "${BUILD_DIR}/hostname_marker"

# locale.txt
render_template locale.txt
chmod 0644 "${BUILD_DIR}/locale.txt"

# timezone
render_template timezone
chmod 0644 "${BUILD_DIR}/timezone"

# wpa_supplicant.conf
render_template wpa_supplicant.conf
chmod 0600 "${BUILD_DIR}/wpa_supplicant.conf"

# --- Rootfs ---

# NM connection profile
render_template homewifi.nmconnection
chmod 0600 "${BUILD_DIR}/homewifi.nmconnection"

# NM managed-mode drop-in
cp "${TEMPLATE_DIR}/10-kclock-wifi-managed.conf" "${BUILD_DIR}/"
chmod 0644 "${BUILD_DIR}/10-kclock-wifi-managed.conf"

# sshd drop-in
cp "${TEMPLATE_DIR}/02-kclock-sshd.conf" "${BUILD_DIR}/"
chmod 0644 "${BUILD_DIR}/02-kclock-sshd.conf"

# SSH banner drop-in (sshd reads Banner /etc/issue.net)
cp "${TEMPLATE_DIR}/99-kclock-banner-ssh.conf" "${BUILD_DIR}/"
chmod 0644 "${BUILD_DIR}/99-kclock-banner-ssh.conf"

# /etc/issue.net — banner text
cp "${TEMPLATE_DIR}/issue.net" "${BUILD_DIR}/"
chmod 0644 "${BUILD_DIR}/issue.net"

# authorized_keys for betocool
render_template authorized_keys
chmod 0600 "${BUILD_DIR}/authorized_keys"

# Trixie-specific: a systemd one-shot that re-clears the rfkill
# block AND flips WirelessEnabled=true just before NM comes up.
# Trixie firstboot keeps re-writing both to "blocked", so we
# schedule the cleanup reactively at every reboot.
cp "${TEMPLATE_DIR}/kclock-wifi-unblock.service" "${BUILD_DIR}/"
chmod 0644 "${BUILD_DIR}/kclock-wifi-unblock.service"

ls -la "${BUILD_DIR}" >&2

echo "Built: ${BUILD_DIR}" >&2
