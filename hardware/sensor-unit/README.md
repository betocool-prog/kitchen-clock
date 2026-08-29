# Sensor unit — hardware

Both the indoor and outdoor sensor nodes use the **same hardware** and
the **same Zephyr firmware image**, deployed twice. Role
("indoor" / "outdoor" / any custom label) is set on the Pi side in
`/etc/kitchen-clock/config.toml`, not in firmware.

## Components

- **Seeed XIAO nRF52840** (Pre-Soldered headers) running Zephyr 3.7 LTS.
- **Adafruit BME280 breakout** (I²C, STEMMA QT). The STEMMA QT
  regulator is **bypassed**; the BME280 VDD is fed from the XIAO's
  `3V3` pin instead.
- **1× 26650 Li-Ion cell** (4.2 V full → 3.0 V cut-off, ~5000 mAh,
  user-supplied) in a 26650 holder (user-supplied).
- **3D-printed enclosure**, designed in **Onshape** by the user (see
  [ADR 0006](../decisions/0006-cad-tooling.md)). The Onshape document
  URL will be added to this README when the user has the document
  live. The enclosure must allow: USB-C access for charging at the
  side or bottom; a small vent hole for humidity equilibrium;
  ventilation for self-heating when the cell is fast-charging;
  sufficient internal volume for the cell holder and the wiring
  loom.

## Wiring (point-to-point, no PCB)

AWG22 (or AWG24) hook-up wire is soldered between:

1. **26650 cell (+) → XIAO `BAT` pad** (no polarity protection — the
   cell holder's polarity keying or a series Schottky is recommended
   if the user wants reverse-polarity protection).
2. **26650 cell (−) → XIAO `GND`**.
3. **XIAO `3V3` → BME280 VDD** (bypass the STEMMA QT regulator's
   input — wire straight to the BME280's `3V3` pin or the breakout's
   `VCC`/`VIN` if you want the regulator in the path; default is
   direct to `3V3`).
4. **XIAO D4 (SDA) → BME280 SDA**.
5. **XIAO D5 (SCL) → BME280 SCL**.
6. **XIAO GND → BME280 GND** (common ground reference).

(D4 / D5 are Zephyr's default I²C pins on `xiao_ble`; the
`xiao_ble.overlay` in `firmware/outdoor-sensor/app/boards/` pins
the bus to these pads.)

## Charging

The XIAO nRF52840 has an onboard **BQ25101** charger. Plug a USB-C
cable into the XIAO's USB-C port to charge the 26650 cell attached at
`BAT` / `GND`.

The charger is configured at **100 mA** by default (Seeed D13
default). At ~5000 mAh, a full empty-to-full cycle is roughly 50 hours.
Adequate for a sensor that gets recharged every few months.

## Deployment

Two units per project. One indoors, one outdoors. After first flash,
each unit prints its **last two bytes of public BLE address** to USB
serial for ~5 s at boot. The deployer records those bytes per unit
into `/etc/kitchen-clock/config.toml` along with the role each one is
playing. Reboot the Pi once; both sensors come up bonded and the
clock UI shows both at the assigned labels.
