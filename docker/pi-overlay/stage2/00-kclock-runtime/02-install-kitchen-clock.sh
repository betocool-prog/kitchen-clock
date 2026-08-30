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

# Render-system dependency: wlfre work / kmsdrm support. SDL2's
# `kmsdrm` backend is the default on Trixie.
"${VENV}/bin/python" - <<'PY'
import pygame
import dbus         # noqa: F401
import bleak        # noqa: F401
print("pygame", pygame.__version__, "OK")
PY
