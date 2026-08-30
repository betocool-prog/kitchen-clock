#!/usr/bin/env bash
#
# docker/pi-overlay/stage2/00-kclock-runtime/01-install-system-deps.sh
#
# Path A (ADR 0011) — install PyGame / SDL2 runtime deps on the Pi
# via apt. No LVGL, no `lv_cpython` wheel, no pip build.
#
# Loaded by pi-gen from the docker build:
#   - `pi-gen` runs this inside the chroot.
#   - We assume we're running as `root` in the chroot.
#
# Re-runs are idempotent: packages already present are skipped by
# apt. Errors are fatal: this is a build-time step.

set -euo pipefail

APT_PACKAGES=(
    python3-pygame
    python3-pil
    libsdl2-image-2.0-0
    libsdl2-ttf-2.0-0
    libsdl2-mixer-2.0-0
    libsdl2-gfx-1.0-0
    libfreetype6
    bluez
)

# Avoid installing "Recommends:" — we don't need GUI niceties on
# this kiosk.
mkdir -p /etc/apt/apt.conf.d
cat > /etc/apt/apt.conf.d/90-no-recommends <<'EOF'
APT::Install-Recommends "0";
APT::Install-Suggests "0";
EOF

apt-get update
apt-get install -y "${APT_PACKAGES[@]}"

# Sanity check: pygame module imports inside the system Python.
/usr/bin/python3 - <<'PY'
import pygame
import PIL  # noqa: F401
print("pygame", pygame.__version__, "OK")
PY
