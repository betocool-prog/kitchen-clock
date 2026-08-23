# Indoor sensor — hardware

BME280 breakout board on a JST-SH 4-wire pigtail:

- Red: 3V3 (Pi GPIO header pin 1)
- Black: GND (pin 6)
- Yellow: SDA (pin 3, I²C1)
- Green: SCL (pin 5, I²C1)

Cable length 0.5–1 m so the sensor can be parked away from the warm
bias of the Pi and the panel backlight.

A small 3D-printed sensor enclosure (vented, ~30 × 20 × 10 mm) clips
onto a kitchen cabinet door or sits on a shelf. OpenSCAD sources
under this directory when added.
