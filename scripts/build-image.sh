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
#   - An overlay wired into pi-gen (created in step 3).

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOCKER_IMAGE="${KITCHEN_CLOCK_IMAGE:-kitchen-clock-build:latest}"
DIST_DIR="${PROJECT_ROOT}/dist"

mkdir -p "$DIST_DIR"

docker run --rm \
  -v "${PROJECT_ROOT}:/work" \
  -v "${DIST_DIR}:/out" \
  "$DOCKER_IMAGE" \
  bash -lc '
    set -euo pipefail
    cd /opt/pi-gen
    ./build.sh
    cp deploy/*.img /out/kitchen-clock.img
    echo "Built: /out/kitchen-clock.img"
  '
