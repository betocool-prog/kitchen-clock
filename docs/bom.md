# Bill of materials

Frozen at project start. Update this file when a part is substituted;
record the reasoning inline.

All prices in A$ approximate, end-2026 retail, intended as planning
budget, not quotes. Click any Source link to open the product page.

Locally-printed parts (3D-printed frame, sensor enclosures) and the
generic hookup wire are listed without buyer links.

## Main unit (indoor)

| Item | Source | Qty | ~A$ each | Subtotal |
| --- | --- | --- | --- | --- |
| Raspberry Pi Zero 2 W (with pre-soldered headers) | [Core CE09937](https://core-electronics.com.au/raspberry-pi-zero-2-w-wireless-soldered-male-headers.html) | 1 | 25 | 25 |
| EastRising ER-TFT090-3-3938 (9″ IPS HDMI panel, 5 V, no touch) | [buydisplay.com](https://www.buydisplay.com/9-inch-ips-1024x600-tft-lcd-display-with-hdmi-driver-board-for-raspberry-pi) | 1 | 90 | 90 |
| mini-HDMI → HDMI cable (Type C → Type A), 1.5 m | [Core FIT0543](https://core-electronics.com.au/mini-hdmi-to-hdmi-cable.html) | 1 | 11 | 11 |
| Official Raspberry Pi **5.1 V / 2.5 A (12.5 W)** micro-USB PSU | [Core CE08324](https://core-electronics.com.au/official-raspberry-pi-12-5w-micro-usb-power-supply.html) | 1 | 14 | 14 |
| USB Micro-B breakout PCB (Adafruit PID 1833, all 5 pins to through-holes) | [Core ADA1833](https://core-electronics.com.au/usb-micro-b-breakout-board.html) | 1 | 10 | 10 |
| JST-style 2-pin inline DC socket (plug + receptacle), AWG22 pigtails | [Altronics P7831A](https://www.altronics.com.au/product/p7831a-jst-style-2-way-13mm-crimp-dc-socket) | 1 | 0 | 0 |
| Hookup wire, red + black, AWG22, ~1 m (Y-split inside frame) | generic (already on hand) | 1 | 0 | 0 |
| PG7 metal cable gland, IP68 (3–6.5 mm clamping range) | [Altronics H4334](https://www.altronics.com.au/p/h4334-3-6.5mm-eg7-pg7-ip68-metal-cable-gland/) | 1 | 4 | 4 |
| microSD card, 16 GB, Class 10 | [Core CE04628](https://core-electronics.com.au/sd-microsd-memory-card-16gb-class-10.html) | 1 | 20 | 20 |
| 3D-printed frame (PLA/PETG) | local print | 1 | 25 | 25 |

**Main unit subtotal: ~A$199**

## Sensor units (×2, firmware-identical)

Both the indoor and outdoor sensor nodes run the same Zephyr image on
the same XIAO+BME280+AA hardware, packaged in the same enclosure. The
role ("indoor" / "outdoor" / any custom label) is set on the Pi side via
`/etc/kitchen-clock/config.toml` and is not encoded in firmware.

| Item | Source | Qty | ~A$ each | Subtotal |
| --- | --- | --- | --- | --- |
| Seeed XIAO nRF52840 (Pre-Soldered) | [Core SS102010631](https://core-electronics.com.au/seeed-studio-xiao-nrf52840-pre-soldered-bluetooth-5-0-ble-wireless-iot-microcontroller-board.html) | 2 | 19.25 | 38.50 |
| Adafruit BME280 (I²C/SPI, STEMMA QT, ±1 °C / ±3 %RH) | [Core ADA2652](https://core-electronics.com.au/adafruit-bme280-i2c-or-spi-temperature-humidity-pressure-sensor.html) | 2 | 18 | 36 |
| 2× AA switched battery holder (Jaycar PH9280) | [Jaycar PH9280](https://www.jaycar.com.au/2aa-switched-battery-enclosure/p/PH9280) | 2 | 4 | 8 |
| 3D-printed enclosure (PETG, IP54-class) | local print | 2 | 8 | 16 |

**Sensor units subtotal: ~A$98.50**

## Scaffolding / freight

- Jumper wires, M2.5 standoffs, heatshrink: A$5–10 (incl. freight).
- AA alkaline cells, two pairs (one per sensor unit): A$10.

**Total project: ~A$307–327**

## Notes

- Panel source: `buydisplay.com` is the cheapest path in AU; local
  distributors markup ~30 %. The exact SKU ordered must be the
  **no-touch** option (no `-32XX`/`-33XX` touch suffix) for our
  panel-only frame.
- Pi Zero 2 W stock has historically been tight; element14 and Core
  Electronics are the most reliable for AU. We've specced the
  **pre-soldered male headers** SKU (CE09937) because the harness
  uses the GPIO header pins 4 (5 V) and 6 (GND) directly.
- For the Seeed XIAO nRF52840, ensure the variant ordered is the
  **Pre-Soldered** SS102010631 (no `Sense` suffix). The `Sense` variant
  adds an extra microphone + IMU without benefit for this project.
- HDMI cable is **mini-HDMI (Type C) → HDMI (Type A)**, not micro-HDMI.
  Pi Zero 2 W has a slim mini-HDMI receptacle; ordered wrong is the #1
  "blank panel" gotcha.
- Power topology is **custom harness**: the official **5.1 V / 2.5 A
  (12.5 W)** Raspberry Pi PSU's captive micro-USB plug enters the frame
  through a PG7 cable gland and lands on an **Adafruit PID 1833**
  Micro-B USB breakout PCB. AWG22 wires are soldered directly to the
  breakout's VBUS / GND pads and crimped onto a **JST-style 2-pin
  inline DC socket** (Altronics P7831A) mounted to the frame.
  The mating plug on the harness side is the single service disconnect
  at the frame boundary. Inside the frame, the receptacle's wires
  Y-split at a soldered splice + heatshrink (a Wago 221-415 lever-nut
  is a reversible alternative): one branch to the Pi's GPIO header
  (pin 4 = 5 V, pin 6 = GND), one branch to the panel driver board's
  5 V / GND screw terminal (red +, black −). Net effect: panel current
  does **not** cross the Pi's polyfuse, and the only current limit on
  a fault is the PSU's 2.5 A foldback.
- Breakout-location flexibility: the Adafruit PID 1833 board is small
  enough (20 × 10 mm) to live just inside or just outside the back
  cover. Placement is open until frame layout is finalised.
- Lower-cost micro-USB breakout alternative: **Core Electronics CE09239**
  (their own-brand clone, $2.62 inc GST) — same micro-B receptacle with
  5 pins brought to a 5-pin header; works, but lacks the through-hole
  pads that the harness needs for direct AWG22 soldering.
- Indoor and outdoor sensor units are **identical** firmware and
  hardware. They share the same BOM line items (qty 2). The role each
  one plays is assigned on the Pi side via
  `/etc/kitchen-clock/config.toml`; no firmware difference between
  them. Swap roles later = edit one line in the config.
- Physical differentiation at deployment: stick a small label (e.g.
  "A" / "B", or "In" / "Out") on each sensor enclosure so the user
  can record which MAC corresponds to which physical location before
  copying addresses into the config.
