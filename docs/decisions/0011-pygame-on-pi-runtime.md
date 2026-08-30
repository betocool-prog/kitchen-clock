# 11. PyGame on the Pi runtime (Path A)

Date: 2026-08-30

## Status

Accepted.

Supersedes the "Renderer strategy" section of ADR 0005 (Path C
adopted on the same date but retired without ever shipping a wheel).

## Context

ADR 0005 picked Path C (host = PyGame, Pi = LVGL) because the
`lvgl` package on PyPI was broken on Linux (`lvgl-0.1.1b0` imports
a missing `builder/` module) and the maintainer's
`lv_cpython@develop` fork caps at Python ≤ 3.11 — the last three
issues stack up to make the LVGL wheel a brittle dependency.

The Pi Zero W's actual workload is much smaller than the LVGL
toolsets assume: a *clock* that updates temperature / humidity /
battery every quarter-second, with a static layout for the lifetime
of the device. The user has stated the target ceiling is ~4 fps:
"2-4 fps on the screen, at worst. It's a clock, nothing will move
much."

That's a poor match for what LVGL is built to do (full embedded GUI
with widgets, scrolling, animations at 60 fps). PyGame on the same
panels hits 2-3 fps full-frame without scrolling or animations, and
the simplicity of having **one renderer** instead of two is a bigger
design win than the marginal smoothness we get from LVGL.

## Decision

PyGame is the **only** renderer on host dev and on the Pi runtime.

- `kitchen_clock/ui/window.py` returns `PygameRunner`. Any value
  other than `pygame` for `KITCHEN_CLOCK_RENDERER` raises
  `ValueError` pointing at this ADR.
- `kitchen_clock/ui/lvgl_window.py` is **deleted**. There is no
  deprecation alias. There is no Path C backstop.
- `pyproject.toml` describes the package as PyGame-only; the
  `dependencies` list is unchanged (`pygame`, `dbus-python`, `bleak`).
- `__main__.py` default `--period` is **0.25** (= 4 fps).

### Pi runtime image (Path A wiring)

`docker/pi-overlay/stage2/00-kclock-runtime/`:

- apt: `python3-pygame python3-pil libsdl2-image-2.0-0
  libsdl2-ttf-2.0-0 libfreetype6 bluez python3-freetype`
- A venv at `/opt/kitchen-clock-venv` with
  `pip install` of `firmware/main-unit/` plus `dbus-python`, `bleak`
  (apt has no `bleak` for Trixie).
- A systemd unit `kitchen-clock.service`:
  - `Environment=SDL_VIDEODRIVER=kmsdrm` (preferred on Trixie's KMS).
  - `WorkingDirectory=/opt/kitchen-clock`.
  - `ExecStart=/opt/kitchen-clock-venv/bin/python -m kitchen_clock`.
  - `User=betocool` (matches the user account on the prepped SD card).
  - `Restart=on-failure`.
  - `After=bluetooth.target network-online.target`,
    `WantedBy=multi-user.target`.
- The HDMI console text on Trixie (the boot kernel's printk) is
  redacted to `loglevel=3 console=tty3` in `scripts/prep-sdcard.sh`
  so the kernel doesn't repaint the same framebuffer that PyGame is
  using for the clock face.
- A `kitchen-clock-suppressor.service` runs `systemd-inhibit
  --what=idle:sleep:handle-lid-switch --who=kitchen-clock
  --why=kitchen-clock-quiet-mode sleep 86400 &` holding the screen
  blanker off for one day.

## Consequences

- **One renderer**, one set of widgets. Visual divergence between
  host dev and Pi runtime is impossible by construction.
- **No LVGL wheel bake** required in the pi-gen image. pi-gen
  becomes a single-purpose image assembler (no `lv_cpython`
  toolchain, no fiddling with `libsdl2-dev libudev-dev` for a wheel
  that may break upstream).
- **Lighter image**: ~140 MB smaller without the LVGL build
  artefacts (wheel + intermediate `.so`).
- **Hot-iteration cost to Pi is zero**: edit on the host, `rsync`,
  `systemctl restart kitchen-clock.service`. No image rebuild, no
  wheel rebuild.
- **Frame rate is capped at ~3 fps** on Pi Zero W. That is the
  primary trade-off; for a clock, this is fine. If we ever need
  smooth animation (e.g., a wind-compass dial), this is the metric
  to revisit.
- **Future contracts**: if we ever want a more elaborate UI, the
  failure mode of Path A is "add features to PyGame," not "swap a
  renderer." Sticking to one tool is cheaper than tracing two.

## What we lose

- LVGL widget trees (label, button, animated icon, scrolling list).
  Custom-build needed if we want anything outside the current
  rect/label/colour/grid model.
- Threaded PAINT/resize events on the Pi. PyGame is single-threaded
  on the UI side (we let `asyncio.gather` schedule the BLE side).
- The community-built widgets in lvgl's examples repo.

## What we keep

- Everything in ADR 0005's host dev recipe (conda env, system apt
  packages, `script/build-sensor.sh`, `script/build-image.sh`).
- The Zephyr 3.7 LTS pin, the pie-sensor service, the SD-card
  provisioning path, the structured-bonded-peer BLE workflow.

## Migration

Already executed in this commit:

- `kitchen_clock/ui/window.py` — only `pygame` arm remains.
- `kitchen_clock/ui/lvgl_window.py` — deleted.
- `kitchen_clock/__main__.py` — `--period` default = `0.25`.
- `pyproject.toml` — description reflects Path A.
- `firmware/main-unit/README.md` — Path A; new `SDL_VIDEODRIVER` row.
- `tests/test_ble_decode.py` — `TestRendererDispatch` flipped
  (`"lvgl"` raises, `lvgl_window` import raises `ImportError`).
- `scripts/setup-host.sh` — header comment updated.
- `docs/decisions/0005-dev-environment.md` — renderer-strategy
  section marked **SUPERSEDED**, status header updated.
- `docker/pi-overlay/stage2/00-kclock-runtime/` — added.

## Open items (queue)

- Continue writing the kitchen-clock app — clock face, sensor tile
  layout, scrolling text — entirely in PyGame.
- Add `Open-Meteo` fetch (TBD; see ADR 0002).
- Add a `kitchen-clock-suppressor.service` overlay script.
- Pi Zero W validation: capture a screenshot of the running clock
  face via `raspi2png`/`scrot`/`grim` to confirm the layout.
- Doc drift cleanup (Pi Zero 2 W → Pi Zero W; Bookworm → Trixie)
  across the rest of the repo (separate pass).
