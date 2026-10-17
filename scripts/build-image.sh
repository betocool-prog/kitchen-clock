#!/usr/bin/env bash
#
# scripts/build-image.sh
#   Containerised build of the Raspberry Pi OS SD-card image via
#   pi-gen, with our overlay applied.
#
# Produces `dist/kitchen-clock.img`, ready to flash with balenaEtcher.
#
# Requires:
#   - docker
#   - The image `kitchen-clock-build:latest` (built once via
#     `docker build -t kitchen-clock-build:latest -f docker/Dockerfile .`).
#   - The overlay at <repo>/docker/pi-overlay/ (Path A — see ADR 0011).
#     Specifically, stage2/00-kclock-runtime/ contains:
#       01-install-system-deps.sh   apt installs python3-pygame + SDL2
#       02-install-kitchen-clock.sh venv + pip install of firmware/main-unit
#       files/etc/systemd/system/kitchen-clock.service
#       files/etc/systemd/system/kitchen-clock-suppressor.{service,timer}
#
# Wiring: we symlink the overlay directory into pi-gen stage2
# before invoking ./build.sh. pi-gen walks every NN-name directory
# in stage2 (and other stages) lexically; it runs the *.sh files
# and copies files/. Symlinking is the cheapest way to hook our
# overlay without forking pi-gen or pinning its version.

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOCKER_IMAGE="${KITCHEN_CLOCK_IMAGE:-kitchen-clock-build:latest}"
DIST_DIR="${PROJECT_ROOT}/dist"
OVERLAY_DIR="${PROJECT_ROOT}/docker/pi-overlay"

mkdir -p "$DIST_DIR"

# pi-gen stage walker treats any *.sh at top level of an overlay
# directory as a chroot-run script. chmod +x is required even if a
# developer writes the file from a shell that did not set the bit.
if [ -d "${OVERLAY_DIR}/stage2/00-kclock-runtime" ]; then
    find "${OVERLAY_DIR}/stage2/00-kclock-runtime" -maxdepth 1 -name '*.sh' \
        -exec chmod +x {} +
fi

docker run --rm \
    -v "${PROJECT_ROOT}:/work" \
    -v "${DIST_DIR}:/out" \
    --entrypoint /bin/bash \
    "${DOCKER_IMAGE}" \
    -lc '
        set -euo pipefail
        cd /opt/pi-gen

        # Path A overlay (ADR 0011). Symlink our stage2 hook into
        # pi-gen with -f so we always overwrite on each run.
        ln -sfn /work/docker/pi-overlay/stage2/00-kclock-runtime \
                /opt/pi-gen/stage2/00-kclock-runtime

        # Tear down prior worktree artifacts so the new overlay
        # is honored end-to-end.
        rm -rf /opt/pi-gen/work

        ./build.sh
        cp deploy/*.img /out/kitchen-clock.img
        echo "Built: /out/kitchen-clock.img"
    '
