# 1. Architecture

Date: 2026-08-22

## Status

Accepted.

## Context

Two physical units — an indoor display clock and a battery-powered outdoor
temperature/humidity sensor — need to be designed and built together.
Constraints:

- 9" colour display (no touch), split-pane UI (time | weather).
- Indoor + outdoor temperatures, each with 24 h min/max.
- No battery backup on the main unit; mains-or-nothing.
- Open-source stack wherever possible.
- Single developer; reproduction of the build is a quality bar.

## Decision

**Main unit:** Raspberry Pi Zero 2 W driving a **EastRising
ER-TFT090-3-3938** 9" IPS HDMI panel (1024×600, 5 V, no touch), held in an
OpenSCAD-designed 3D-printed bench frame. Powered by the official Raspberry
Pi **5.1 V / 3 A micro-USB PSU**; the panel shares the same 5 V rail.

**Indoor sensor:** Bosch **BME280** breakout on a JST-SH pigtail (~0.5–1 m),
I²C to the Pi GPIO header, mounted in the frame's ventilation slot away from
the warm bias of the Pi and panel.

**Outdoor sensor:** **Seeed XIAO nRF52840** + **BME280** breakout, powered
**directly** by 2× AA alkaline cells in series (no boost stage — both parts
operate from ~1.7 V up). BLE peripheral, advertises measurements and exposes
a small GATT service. Deep-sleep between advertisements.

**Firmware:**

- Pi app: Python + **LVGL** (SDL2 backend for host development, Linux
  DRM/KMS for the Pi).
- Outdoor sensor: **Zephyr 3.7 LTS** with the **Zephyr SDK 0.17.x** line.

## Consequences

- Single PSU for the whole main unit (5.1 V / 3 A micro-USB). No mains
  brick, no UPS.
- Pi Zero 2 W's BLE and Wi-Fi share an antenna; outdoor advertisements are
  tuned to be sparse (every 2–5 s, not continuous).
- No battery backup → on a power return, the Pi re-NTPs; time may be wrong
  for the few seconds before sync arrives.
- Panel + Pi on a shared 5 V rail risks under-voltage at peak; mitigated by
  the official 5.1 V / 3 A PSU and by avoiding cheap no-name bricks.
- All sources (firmware, KiCad, OpenSCAD, Docker) live in this repo.
