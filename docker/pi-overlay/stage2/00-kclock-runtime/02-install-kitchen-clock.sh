#!/usr/bin/env bash
#
# docker/pi-overlay/stage2/00-kclock-runtime/02-install-kitchen-clock.sh
#
# Create a venv at /opt/kitchen-clock-venv and install:
#   - the firmware/main-unit/ Python package (from this overlay's
#     sibling repo area mounted at /work),
#   - dbus-python, bleak (apt lacks these for Trixie).
#
# Loaded by pi-gen from the docker build. Runs inside the chroot.
# Re-runs are idempotent: --upgrade is used.

set -euo pipefail

VENV=/opt/kitchen-clock-venv
SRC=/work/firmware/main-unit

if [ ! -d "${SRC}" ]; then
    echo "ERROR: ${SRC} not mounted in chroot" >&2
    exit 1
fi

mkdir -p /opt/kitchen-clock
/usr/bin/python3 -m venv "${VENV}"

# pip in a fresh venv is fine: only built-ins, no PEP 668 issue
# inside `python3 -m venv`.
"${VENV}/bin/pip" install --upgrade pip
"${VENV}/bin/pip" install --upgrade \
    "${SRC}" \
    'dbus-python>=1.3' \
    'bleak>=0.21'

# Render-system dependency: SDL2 must be able to bind a video driver.
# We use `fbcon` (Pi Zero W has no GPU; kmsdrm GLES fails). The
# Pi OS apt's python3-pygame bundles SDL 2.0.14 with fbcon compiled
# in; the venv fallback (when this file is run during pi-gen on
# Bookworm/Trixie) sees this through `--system-site-packages`.
# Nothing further to install at this step — `apt-get install
# python3-pygame` (in 01-install-system-deps.sh) is what registers
# the package on the system path.
"${VENV}/bin/python" - <<'PY'
import pygame
import dbus         # noqa: F401
import bleak        # noqa: F401
print("pygame", pygame.__version__, "OK")
PY

# Path A (ADR 0011) — enable services on boot. stdlib's `ln -sfn`
# does the equivalent of `systemctl enable` without needing a
# running systemd. The `files/etc/systemd/system/*` payload of this
# overlay had already copied the unit/timer files into the chroot.
mkdir -p /etc/systemd/system/multi-user.target.wants
mkdir -p /etc/systemd/system/timers.target.wants
ln -sfn /etc/systemd/system/kitchen-clock.service \
        /etc/systemd/system/multi-user.target.wants/kitchen-clock.service
ln -sfn /etc/systemd/system/kitchen-clock-suppressor.timer \
        /etc/systemd/system/timers.target.wants/kitchen-clock-suppressor.timer
