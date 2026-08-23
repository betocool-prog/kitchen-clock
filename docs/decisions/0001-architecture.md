# 1. Architecture

Date: 2026-08-22

## Status

Accepted.

## Context

A kitchen clock with weather: an indoor display unit and two battery-powered
sensor nodes, one deployed indoors and one outdoors, both reporting
temperature, humidity and battery voltage over BLE. Constraints:

- 9" colour display (no touch), split-pane UI (time | weather).
- Two temperature sources (indoor + outdoor), each with 24 h min/max.
- No battery backup on the main unit; mains-or-nothing.
- Open-source stack wherever possible.
- Single developer; reproducibility of the build is a quality bar.
- Total BOM target ~A$300–350.

## Decision

**Main unit:** Raspberry Pi Zero 2 W driving a **EastRising
ER-TFT090-3-3938** 9" IPS HDMI panel (1024×600, 5 V, no touch), held in an
OpenSCAD-designed 3D-printed bench frame. Powered by the **official
Raspberry Pi 5.1 V / 3 A micro-USB PSU** routed through a **passive USB
Power Splitter PCB** (one micro-USB input → 2× USB-A outputs). One branch
drives the Pi's `micro-USB PWR IN`; the other drives the panel driver
board's 5 V / GND screw terminal via a USB-A → bare-wire pigtail. The Pi's
polyfuse sees only the Pi's current.

**Sensor units (×2, firmware-identical):** **Seeed XIAO nRF52840** +
**BME280** breakout, powered **directly** by 2× AA alkaline cells in series
(no boost stage — both parts operate from ~1.7 V up). Each unit is a BLE
peripheral: advertises measurements and exposes a small GATT service.
Deep-sleep between advertisements. The two units run the **same Zephyr
application**; *role* ("indoor" / "outdoor" / any custom name) is decided
on the Pi side only.

**Mechanical:** Same 3D-printed IP54-class enclosure under
`hardware/sensor-unit/` used for both sensor units.

**Firmware:**

- Pi app: Python + **LVGL** (SDL2 backend for host development, Linux
  DRM/KMS for the Pi).
- Sensor units: **Zephyr 3.7 LTS** with the **Zephyr SDK 0.17.x** line;
  one binary, deployed to both nodes.

## Consequences

- Single PSU + splitter PCB keeps the main unit on one mains lead. Cable
  assembly lives inside the 3D-printed frame.
- Pi Zero 2 W's BLE and Wi-Fi share an antenna; two persistent peripheral
  connections plus Wi-Fi traffic reduce airtime headroom. Staggered
  advertisement intervals (random initial delay per node, 2–5 s base
  interval) and short scan windows keep dropouts rare.
- No battery backup → on a power return, the Pi re-NTPs and re-fetches
  weather; time may be wrong for a few seconds before sync arrives.
- Two identical sensor units cut firmware and BOM complexity at the price
  of one extra cell-replacement cadence (each unit lasts months on 2× AA,
  but the household replaces cells twice as often).
- All sources (firmware, KiCad, OpenSCAD, Docker) live in this repo.
