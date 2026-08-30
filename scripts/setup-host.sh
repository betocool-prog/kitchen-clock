#!/usr/bin/env bash
#
# scripts/setup-host.sh
#   One-time host setup for the kitchen-clock project.
#
# - Verifies miniconda is present.
# - Installs required apt system packages (libsdl2-dev etc.).
# - Creates the conda env `kitchen-clock` if absent.
# - Installs Python deps in that env (PyGame renderer for host-dev,
#   bleak + dbus-python for the BLE GATT client).
#
# Renderer: PyGame on both host dev and the Pi runtime. Path A —
# see ADR 0011. There is no LVGL install on the host or Pi.
# Re-runs are idempotent: missing apt packages are installed; the conda
# env is updated, not recreated.

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_NAME="kitchen-clock"
PY_VERSION="3.12"

APT_PACKAGES=(
  libsdl2-dev
  libgtk-3-dev
  git
  openssh-client
  rsync
  build-essential
)

say() { printf '[setup-host] %s\n' "$*"; }

# 1. verify miniconda
if ! command -v conda >/dev/null 2>&1; then
  say "ERROR: 'conda' not on PATH. Install Miniconda first:"
  say "  https://docs.conda.io/projects/miniconda/en/latest/"
  exit 1
fi
say "Found miniconda: $(conda --version)"

# shellcheck disable=SC1091
source "$(conda info --base)/etc/profile.d/conda.sh"

# 2. system packages
SUDO=""
if [[ $EUID -ne 0 ]]; then
  if command -v sudo >/dev/null 2>&1; then SUDO=sudo; fi
fi

NEEDED=()
for pkg in "${APT_PACKAGES[@]}"; do
  if ! dpkg -s "$pkg" >/dev/null 2>&1; then
    NEEDED+=("$pkg")
  fi
done

if (( ${#NEEDED[@]} )); then
  say "Installing missing apt packages: ${NEEDED[*]}"
  $SUDO apt-get update
  $SUDO apt-get install -y "${NEEDED[@]}"
else
  say "All apt packages already present."
fi

# 3. conda env
if conda env list | awk '{print $1}' | grep -qx "$ENV_NAME"; then
  say "Conda env '$ENV_NAME' already exists. Updating deps."
  conda activate "$ENV_NAME"
  pip install --upgrade pip
  # Renderer for the SDL2 window on host = PyGame (works on cp312
  # without compilation). See ADR 0005 / "Renderer strategy".
  pip install --upgrade 'pygame>=2.5' 'dbus-python>=1.3' 'bleak>=0.21'
else
  say "Creating conda env '$ENV_NAME' (Python ${PY_VERSION})."
  conda create -y -n "$ENV_NAME" "python=${PY_VERSION}"
  conda activate "$ENV_NAME"
  pip install --upgrade pip
  pip install 'pygame>=2.5' 'dbus-python>=1.3' 'bleak>=0.21'
fi

# 4. sanity-check
say "Verifying host renderer + BLE deps."
python - <<'PY'
from importlib.metadata import version, PackageNotFoundError

def v(name):
    try:
        return version(name)
    except PackageNotFoundError:
        return "(not installed)"

print("pygame     ", v("pygame"))
print("dbus-python", v("dbus-python"))
print("bleak      ", v("bleak"))

# Light import smoke test (don't access __version__ — bleak 3.x
# dropped it as a public attribute). We just need to know each lib
# imports cleanly inside this Conda env.
import pygame    # noqa: F401
import dbus      # noqa: F401
import bleak     # noqa: F401
print("imports    pygame ✓ dbus ✓ bleak ✓")
PY

say "Host setup complete. Activate with: conda activate $ENV_NAME"
