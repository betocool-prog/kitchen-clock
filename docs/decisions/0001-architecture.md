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

**Main unit:** Raspberry Pi Zero 2 W (with pre-soldered headers, so the
5 V / GND pair can be soldered directly to GPIO pins 4 / 6) driving a
**EastRising ER-TFT090-3-3938** 9" IPS HDMI panel (1024×600, 5 V, no
touch), held in an OpenSCAD-designed 3D-printed bench frame. Powered by
the **official Raspberry Pi 5.1 V / 2.5 A (12.5 W) micro-USB PSU** routed
through a **custom soldered harness**: PSU's captive micro-USB plug
enters the frame through a PG7 cable gland and lands on an
**Adafruit PID 1833** micro-B USB → VBUS / GND breakout PCB (input =
micro-B female receptacle; output = plated through-holes for VBUS and
GND). AWG22 wires are soldered directly to those pads and crimped onto
a **JST-style 2-pin inline DC socket** (Altronics P7831A) mounted to the
frame. The mating plug on the harness side is the single service
disconnect at the frame boundary. Inside the frame, the receptacle's
wires Y-split at a soldered splice (with heatshrink) into two AWG22
pairs: one to the Pi's GPIO header (pin 4 = 5 V, pin 6 = GND), one to
the panel driver board's `5 V / GND` screw terminal (red +, black −).
The Pi's micro-USB polyfuse is bypassed entirely; fault current is
limited by the PSU's 2.5 A foldback.

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

- Single PSU + custom harness keeps the main unit on one mains lead. The
  harness has exactly one pluggable service disconnect (the inline JST
  pair mounted at the frame boundary). Repair or replacement of the
  harness is reversible end-to-end.
- The Pi's micro-USB polyfuse is bypassed; fault current is bounded by
  the PSU's 2.5 A foldback only. A wiring short on either branch will
  cause the PSU to throttle. No inline slow-blow fuses — see the
  "Power topology" bullet in `docs/bom.md` for the rationale.
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
