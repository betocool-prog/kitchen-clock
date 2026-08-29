#!/usr/bin/env bash
#
# scripts/build-sensor.sh
#   Containerised build of the outdoor-sensor firmware.
#
# Produces `dist/outdoor-sensor.uf2` from `firmware/outdoor-sensor/app`
# using the Zephyr 3.7 LTS image (defined in `docker/Dockerfile`).
#
# Requires:
#   - docker
#   - The image `kitchen-clock-build:latest` (built once via
#     `docker build -t kitchen-clock-build:latest -f docker/Dockerfile .`).

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOCKER_IMAGE="${KITCHEN_CLOCK_IMAGE:-kitchen-clock-build:latest}"
DIST_DIR="${PROJECT_ROOT}/dist"

mkdir -p "$DIST_DIR"

docker run --rm \
  -v "${PROJECT_ROOT}:/work" \
  -v "${DIST_DIR}:/dist" \
  -e ZEPHYR_TOOLCHAIN_PATH=/opt/zephyr-sdk \
  "$DOCKER_IMAGE" \
  bash -lc '
    set -euo pipefail
    source /opt/zephyr-venv/bin/activate
    west build -b xiao_ble /work/firmware/outdoor-sensor/app
    cp build/zephyr/zephyr.uf2 /dist/outdoor-sensor.uf2
    echo "Built: /dist/outdoor-sensor.uf2"
  '
