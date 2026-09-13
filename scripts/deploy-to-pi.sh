#!/usr/bin/env bash
#
# scripts/deploy-to-pi.sh
#
# One-shot deploy of the kitchen-clock Pi app to the bench Pi:
# rsync source, drop systemd units, install helper scripts, enable
# the service, and capture a snapshot PNG.
#
# Run from your interactive shell (sudo can prompt for password):
#
#   scripts/deploy-to-pi.sh                    # default target betocool@192.168.0.49
#   scripts/deploy-to-pi.sh user@host         # custom SSH target
#
# Anything that's piped through stdin can NOT touch sudo — pipe-style
# use needs sudo with the -S flag and a piped password, which we don't
# recommend. The script is interactive on purpose.

set -euo pipefail

TARGET="${1:-betocool@192.168.0.49}"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SNAPSHOT_DIR="/tmp/render-snapshot"
LOCAL_SNAP_DIR="$PROJECT_ROOT/panel-snapshots"

cd "$PROJECT_ROOT"

# 0. Sanity
if ! command -v rsync >/dev/null 2>&1 || ! command -v scp >/dev/null 2>&1; then
    echo "ERROR: rsync + scp required." >&2
    exit 1
fi
if ! [[ -d "$PROJECT_ROOT/firmware/main-unit/kitchen_clock" ]]; then
    echo "ERROR: $PROJECT_ROOT/firmware/main-unit/kitchen_clock missing." >&2
    exit 1
fi

echo "Target: $TARGET"

# 1. Sync source to /opt/kitchen-clock/. `--delete` is fine because the
#    Pi-side editable install points the venv's site-packages here.
echo
echo "==> rsync firmware/main-unit/ ${TARGET}:/opt/kitchen-clock/"
rsync -av --delete \
    --exclude '*.egg-info*' \
    "firmware/main-unit/" \
    "${TARGET}:/opt/kitchen-clock/"

# 2. Drop the systemd units and capture helper into /tmp on the Pi.
echo
echo "==> scp service units + capture helper to $TARGET:/tmp"
scp \
    "scripts/templates/sd/kitchen-clock.service" \
    "scripts/templates/sd/kitchen-clock-suppressor.service" \
    "scripts/templates/sd/kitchen-clock-suppressor.timer" \
    "scripts/capture-fb0-screenshot.py" \
    "${TARGET}:/tmp/"

# 3. Install + enable (sudo runs in your interactive tty, no -S hack).
echo
echo "==> ssh $TARGET  (install + enable + status)"
ssh -o RequestTTY=force "${TARGET}" '
set -euo pipefail

# Drop unit files into /etc/systemd/system/.
sudo install -m 0644 \
    /tmp/kitchen-clock.service \
    /tmp/kitchen-clock-suppressor.service \
    /tmp/kitchen-clock-suppressor.timer \
    /etc/systemd/system/

# Drop the capture helper into /opt/kitchen-clock/.
sudo install -m 0644 \
    /tmp/capture-fb0-screenshot.py \
    /opt/kitchen-clock/capture-fb0-screenshot.py

# Enable via standard vanilla ".wants/" symlinks (no NM dependency).
sudo mkdir -p \
    /etc/systemd/system/multi-user.target.wants \
    /etc/systemd/system/timers.target.wants
sudo ln -sf /etc/systemd/system/kitchen-clock.service \
    /etc/systemd/system/multi-user.target.wants/kitchen-clock.service
sudo ln -sf /etc/systemd/system/kitchen-clock-suppressor.timer \
    /etc/systemd/system/timers.target.wants/kitchen-clock-suppressor.timer

sudo systemctl daemon-reload
sudo systemctl enable --now \
    kitchen-clock.service \
    kitchen-clock-suppressor.timer

# Restart even if already running: `enable --now` only starts when
# the unit is inactive. We always want the latest source loaded.
sudo systemctl restart kitchen-clock.service

sleep 2  # let the panel paint at least one frame.

echo
echo "--- kitchen-clock.service status ---"
systemctl --no-pager status kitchen-clock.service || true
echo
echo "--- journal (last 30 lines) ---"
sudo journalctl -u kitchen-clock.service -n 30 --no-pager || true
'

# 4. Capture PNG of the service-mode panel and pull back here.
echo
echo "==> capturing PNG of the live panel"
ssh "${TARGET}" "
mkdir -p $SNAPSHOT_DIR
/opt/kitchen-clock-venv/bin/python /opt/kitchen-clock/capture-fb0-screenshot.py $SNAPSHOT_DIR/service-mode.png
"

mkdir -p "$LOCAL_SNAP_DIR"
scp "${TARGET}:${SNAPSHOT_DIR}/service-mode.png" "${LOCAL_SNAP_DIR}/service-mode.png"

echo
echo "Done. PNG: $LOCAL_SNAP_DIR/service-mode.png"
