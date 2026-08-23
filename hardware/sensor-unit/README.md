# Sensor unit — hardware

Both the indoor and outdoor sensor nodes use the **same hardware** and
the **same Zephyr firmware image**, deployed twice. Role
("indoor" / "outdoor" / any custom label) is set on the Pi side in
`/etc/kitchen-clock/config.toml`, not in firmware.

## Components

- **Seeed XIAO nRF52840** (with headers), running Zephyr 3.7 LTS.
- **BME280 breakout** (I²C, 3.3 V) on the XIAO's I²C bus.
- **2× AA battery holder** (wire leads), wired directly to the XIAO's
  `BAT+` / `BAT−` pads. No boost stage — both parts operate from ~1.7 V
  through to fresh-cell ~3.0 V.
- **3D-printed IP54-class enclosure**.
- (Optional, future) small **PCB carrier** that mounts XIAO + BME280 +
  AA holder neatly inside the enclosure. KiCad sources under `kicad/`
  when added.

## Wiring (XIAO ↔ BME280)

Cross-check against the Seeed XIAO nRF52840 pinout card before
soldering:

- **3V3** → BME280 VDD
- **GND** → BME280 GND
- **D4 (SDA)** → BME280 SDA
- **D5 (SCL)** → BME280 SCL

(D4 / D5 are the Zephyr-default I²C pins on `xiao_nrf52840` board.)

## Mechanical

- OpenSCAD source: `openscad/enclosure.scad`.
- Exports: `openscad/enclosure.stl`, `.3mf`.
- IP54-class: gasketed lid, bottom vent for humidity equilibrium,
  strain relief for the AA-holder wires.
- Two small label recesses in the lid so the user can hand-write "A" /
  "B" / a location name at deployment time.

## Deployment

Two units per project. One indoors, one outdoors. After first flash,
each unit prints its **last two bytes of public BLE address** to USB
serial for ~5 s at boot. The deployer records those at units into
`/etc/kitchen-clock/config.toml` along with the role each one is
playing. Reboot the Pi once; both sensors come up bonded and the
clock UI shows both at the assigned labels.
