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
touch), held in a 3D-printed bench frame (enclosure designed in
Onshape — see ADR 0006). Powered by the **official Raspberry Pi 5.1 V
/ 2.5 A (12.5 W) micro-USB PSU** routed through a **custom soldered
harness**: PSU's captive micro-USB plug enters the frame through a
PG7 cable gland and lands on an **Adafruit PID 1833** micro-B USB →
VBUS / GND breakout PCB (input = micro-B female receptacle; output =
plated through-holes for VBUS and GND). AWG22 wires are soldered
directly to those pads and crimped onto a **JST-style 2-pin inline DC
socket** (Altronics P7831A) mounted to the frame. The mating plug on
the harness side is the single service disconnect at the frame
boundary. Inside the frame, the receptacle's wires Y-split at a
soldered splice (with heatshrink) into two AWG22 pairs: one to the
Pi's GPIO header (pin 4 = 5 V, pin 6 = GND), one to the panel driver
board's `5 V / GND` screw terminal (red +, black −). The Pi's
micro-USB polyfuse is bypassed entirely; fault current is limited by
the PSU's 2.5 A foldback.

**Sensor units (×2, firmware-identical):** Seeed XIAO nRF52840 +
BME280 breakout, each powered by a **single 26650 Li-Ion cell** (4.2 V
full → 3.0 V cut-off, ~5000 mAh) connected directly to the XIAO's
`BAT` pin. The XIAO's onboard 3.3 V regulator feeds the BME280's
`3V3` pin (the STEMMA QT regulator is bypassed). Charging handled by
the XIAO's onboard BQ25101 via USB-C at the Seeed-default 100 mA rate
(D13 default). One firmware image, one Zephyr workspace; the two
units run identical code, role is set on the Pi side.

**Mechanical:** Enclosures for both the main unit and the sensor
units are designed in Onshape (free-tier, public-by-default) by the
user — see ADR 0006. Source-of-truth geometry lives in the user's
Onshape account. This repo holds the BOM and assembly notes, not the
CAD files.

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
- Two identical sensor units cut firmware and BOM complexity. Each
  sensor is rechargeable via USB-C through the XIAO's BQ25101 (100 mA
  default). At ~5000 mAh per 26650, expected runtime on a single
  charge is measured in months; recharge is "occasionally every few
  months" rather than "replace alkaline cells twice as often" as it was
  for the earlier 2× AA topology (per ADR 0001 prior to this revision).
- All source for firmware and the project workflow lives in this repo.
  Mechanical geometry is in the user's Onshape account; not in this
  repo.
