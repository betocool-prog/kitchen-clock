# 5. Dev environment

Date: 2026-08-22

## Status

Accepted.

## Context

Two firmware targets:

1. Pi app (Python + LVGL).
2. Outdoor sensor (C, Zephyr, nRF52840).

Goals: reproducible builds, minimal host pollution, a fast visible-editor
loop. The host OS is **Zorin OS** (Ubuntu-based), with Python (via
**Miniconda**), GTK, git and SSH natively available.

## Decision

**Container does the heavy lifting; the host runs the visible work.**

`docker/Dockerfile` (debian:bookworm-slim):

- Zephyr Python tooling in `/opt/zephyr-venv` (`west`, `pyelftools`).
- Zephyr SDK 0.17.x at `/opt/zephyr-sdk`, SHA-pinned.
- `pi-gen` at `/opt/pi-gen` to assemble the Raspberry Pi OS image with
  our overlay.
- No ARM cross-toolchain: the Pi app runs on the Pi's own Python
  interpreter; the container assembles the image but does not need to
  cross-compile Python.
- Quality-of-life: `qemu-user-static` + `binfmt-support` to smoke-test
  ARM binaries.

Two thin entrypoints mounted from the host repo:

- `scripts/build-sensor.sh`: `west build -b xiao_nrf52840
  firmware/outdoor-sensor`, copies `build/zephyr/zephyr.uf2` to `dist/`.
- `scripts/build-image.sh`: runs `./build.sh` from `pi-gen` with our
  overlay under `docker/pi-overlay/` (installs the Pi app, enables the
  systemd unit, drops the `wpa_supplicant.conf` template).

Host loop:

- Pi app: edit on host, run with `LVGL_SDL2=1 python -m app.main` →
  appears in an SDL2 window at 1024×600. Sync to the Pi via ssh + rsync or
  re-flash.
- Sensor: edit on host, `west build -b xiao_nrf52840 -p auto`. Once the
  build is clean, `./scripts/build-sensor.sh` produces the reproducible
  container-built UF2; drag-drop onto the dev kit.

Host dependencies required:

- **Miniconda** (already installed on the host). A dedicated conda
  environment `kitchen-clock` is created once with `conda create -n
  kitchen-clock python=3.12`; LVGL Python bindings are installed inside it
  via `pip install lvgl`. Avoids polluting the `base` environment and
  keeps other host Python projects insulated from LVGL version bumps.
- System-level apt packages: `libsdl2-dev`, `libgtk-3-dev`, `git`,
  `openssh-client`, `rsync` (most are pre-installed on a standard Zorin
  desktop; `libsdl2-dev` typically needs an explicit install).
- Conda env activation: `conda activate kitchen-clock` before any
  `python -m …` invocation.

## Consequences

- One Dockerfile pins Zephyr SDK and SDK tooling; reproducible across any
  Zorin host.
- First-time image build is slow (~15 min for pi-gen); subsequent
  iterations use cached layers.
- On the Pi, Python + LVGL stays portable across the Bookworm lifetime
  (~3 years of updates).
- No closed-source drivers added; everything stays under standard OSS
  licences.
- A fresh conda env keeps the host's `base` environment uncluttered and
  makes it trivial to delete / rebuild the project's Python world (`conda
  env remove -n kitchen-clock`).
- WSL/headless hosts would need X forwarding for the SDL2 window. Zorin
  laptop with a desktop session is fine.
