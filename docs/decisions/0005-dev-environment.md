# 5. Dev environment

Date: 2026-08-22

## Status

Superseded by `0011-pygame-on-pi-runtime.md` for **renderer strategy** (2026-08-30).

The original 2026-08-22 acceptance covered the host dev recipe
(miniconda + SDL2 stack + APK packages). The 2026-08-30 revision
introduced Path C (PyGame host, LVGL Pi runtime) which was then
replaced on the same date by Path A (PyGame on both) — see ADR 0011.

The host dev recipe below is unchanged for ADR 0011 and remains
correct.

## Context

Two firmware targets:

1. Pi app (Python + LVGL).
2. Outdoor sensor (C, Zephyr, nRF52840).

Goals: reproducible builds, minimal host pollution, a fast visible-editor
loop. The host OS is **Zorin OS** (Ubuntu-based), with Python (via
**Miniconda**), GTK, git and SSH natively available.

## Renderer strategy (revised 2026-08-30)

> **SUPERSEDED 2026-08-30 by `0011-pygame-on-pi-runtime.md`.** This
> section is retained for historical context only. The Path A
> decision (PyGame on both host dev and Pi runtime) replaced Path C
> (which we previously kept here). Use ADR 0011 for current renderer
> strategy.

A binding layer underneath LVGL's Python package currently has a
broken sdist on Linux: `lvgl-0.1.1b0` on PyPI imports a `builder/`
module that isn't shipped in the tarball, so `pip install lvgl` fails
with `ModuleNotFoundError: No module named 'builder'` on every Linux
distribution. The maintainer (`kdschlosser`) has a working
replacement in `lv_cpython@develop`, but it lags behind, supports
Python ≤ 3.11, and is a single-maintainer fork.

We adopt **Path C** for the dev loop:

- **Host dev uses PyGame** as the windowed renderer. PyGame ships
  binary wheels for cp312 on every platform; no compilation, no
  upstream risk.
- **The Pi runtime uses LVGL** for the EastRising framebuffer. The
  binding compile is hosted by the **pi-gen image** (debian bookworm
  / Trixie + Python 3.11 + `make gcc libsdl2-dev libudev-dev` + build
  `kdschlosser/lv_cpython@develop` or upstream `lvgl@0.2.x` once it's
  republished). It is one-shot per release, not per dev iteration.

The widget tree is identical regardless of which renderer is bound —
the same widgets / layouts / data flows render in either backend.
`kitchen_clock/ui/window.py` selects the renderer via a
`KITCHEN_CLOCK_RENDERER` env var (`pygame` on host, `lvgl` on Pi).

## Decision

**Container does the heavy lifting; the host runs the visible work.**

`docker/Dockerfile` (debian:bookworm-slim):

- Zephyr Python tooling in `/opt/zephyr-venv` (`west`, `pyelftools`).
- Zephyr SDK **0.16.x line** at `/opt/zephyr-sdk`, SHA-pinned
  (currently `0.16.9`).
- pi-gen at `/opt/pi-gen` to assemble the Raspberry Pi OS image
  with our overlay.
- LVGL Python-build toolchain (`gcc make libsdl2-dev libudev-dev`,
  Python 3.11 venv) sufficient to compile a working `lvgl`
  wheel for cp311 on Linux, exactly once per pi-gen run.
- No ARM cross-toolchain: the Pi app runs on the Pi's own Python
  interpreter; the container assembles the image but does not need
  to cross-compile Python.
- Quality-of-life: `qemu-user-static` + `binfmt-support` to smoke-test
  ARM binaries.

Two thin entrypoints mounted from the host repo:

- `scripts/build-sensor.sh`: `west build -b xiao_ble
  firmware/outdoor-sensor`, copies `build/zephyr/zephyr.uf2` to
  `dist/`.
- `scripts/build-image.sh`: runs `./build.sh` from pi-gen with our
  overlay under `docker/pi-overlay/` (installs the Pi app, enables
  the systemd unit, drops the `wpa_supplicant.conf` template).
  This is also where the LVGL wheel is built and dropped into the
  image.

Host loop:

- Pi app: edit on host, run with `python -m app.main` (PyGame
  backend → SDL2 window on the laptop display). Sync to the Pi
  via ssh + rsync or re-flash.
- Sensor: edit on host, `west build -b xiao_ble -p auto`. Once
  clean, `./scripts/build-sensor.sh` produces the reproducible
  container-built UF2; drag-drop onto the dev kit.

Host dependencies required:

- **Miniconda** (already installed on the host). A dedicated conda
  environment `kitchen-clock` is created once with
  `conda create -n kitchen-clock python=3.12`. PyGame, dbus-python,
  and bleak are installed inside it (no LVGL on host).
- System-level apt packages: `libsdl2-dev`, `libgtk-3-dev`,
  `git`, `openssh-client`, `rsync`. (`libsdl2-dev` typically
  needs an explicit install; the others are pre-installed on a
  default Zorin desktop.)
- Conda env activation: `conda activate kitchen-clock` before
  any `python -m …` invocation.

## Consequences

- One Dockerfile pins Zephyr SDK, the LVGL build env, and pi-gen;
  reproducible across any Zorin host **for both firmware targets**.
- First-time image build is slow (~15 min for pi-gen + LVGL
  wheel-bake); subsequent iterations use cached layers.
- Host dev has **no LLVM / LVGL dependency**. The dev loop is fast
  and resilient to upstream LVGL churn.
- On the Pi, the same `kitchen_clock` Python package renders
  via LVGL — portability is preserved for the Bookworm /
  Trixie lifetime (~3 years of updates).
- `KITCHEN_CLOCK_RENDERER` env var decides which backend drives
  the window; testing both paths is easy from the host shell.
- A fresh conda env keeps the host's `base` environment
  uncluttered and makes it trivial to delete / rebuild the
  project's Python world (`conda env remove -n kitchen-clock`).
- WSL/headless hosts would need X forwarding for the SDL2 window.
  Zorin laptop with a desktop session is fine.
