# Bill of materials

Frozen at project start. Update this file when a part is substituted;
record the reasoning inline.

All prices in A$ approximate, end-2026 retail, intended as planning
budget, not quotes.

## Main unit (indoor)

| Item | Source | Qty | ~A$ each | Subtotal |
| --- | --- | --- | --- | --- |
| Raspberry Pi Zero 2 W | Core Electronics / element14 | 1 | 25 | 25 |
| EastRising ER-TFT090-3-3938 (9″ IPS HDMI panel, 5 V, no touch) | buydisplay.com | 1 | 90 | 90 |
| mini-HDMI → HDMI cable (Type C → Type A), 0.5 m | Core Electronics | 1 | 12 | 12 |
| Raspberry Pi official 5.1 V / 3 A micro-USB PSU | Core Electronics / element14 | 1 | 18 | 18 |
| USB Power Splitter PCB (micro-USB in → 2× USB-A out, 5 V) | Pi Hut / Lectronz (`8086 Consultancy`) | 1 | 15 | 15 |
| USB-A → micro-USB cable, 0.3 m (Pi feed) | AliExpress / Core Electronics | 1 | 4 | 4 |
| USB-A → bare-wire pigtail, 0.3 m (panel feed, red +, black −) | AliExpress | 1 | 3 | 3 |
| microSD card, 16 GB, A1-rated | generic | 1 | 12 | 12 |
| 3D-printed frame (PLA/PETG) | local print | 1 | 25 | 25 |

**Main unit subtotal: ~A$200**

## Sensor units (×2, firmware-identical)

Both the indoor and outdoor sensor nodes run the same Zephyr image on the
same XIAO+BME280+AA hardware, packaged in the same enclosure. The role
("indoor" / "outdoor" / any custom label) is set on the Pi side via
`/etc/kitchen-clock/config.toml` and is not encoded in firmware.

| Item | Source | Qty | ~A$ each | Subtotal |
| --- | --- | --- | --- | --- |
| Seeed XIAO nRF52840 (with headers) | Core Electronics / Seeed | 2 | 30 | 60 |
| BME280 breakout (I²C, 3.3 V) | Core Electronics / AliExpress | 2 | 12 | 24 |
| 2× AA battery holder, wire leads | Jaycar / AliExpress | 2 | 4 | 8 |
| 3D-printed enclosure (PETG, IP54-class) | local print | 2 | 8 | 16 |

**Sensor units subtotal: ~A$108**

## Scaffolding / freight

- Jumper wires, headers, M2.5 standoffs: A$5–10 (incl. freight).
- AA alkaline cells, two pairs (one per sensor unit): A$10.

**Total project: ~A$325–345**

## Notes

- Panel source: `buydisplay.com` is the cheapest path in AU; local
  distributors markup ~30 %.
- Pi Zero 2 W stock has historically been tight; element14 and Core
  Electronics are the most reliable for AU.
- For the Seeed XIAO nRF52840, ensure the variant ordered is the
  plain nRF52840 (no onboard sensors); "Sense" variant adds an
  extra BOM line without benefit for this project.
- HDMI cable is **mini-HDMI (Type C) → HDMI (Type A)**, not micro-HDMI.
  Pi Zero 2 W has a slim mini-HDMI receptacle; ordered wrong is the #1
  "blank panel" gotcha.
- Power topology is **Option C**: the official Raspberry Pi 5.1 V / 3 A
  micro-USB PSU plugs into the splitter PCB's micro-USB input. Outputs:
  - Branch 1 — USB-A → micro-USB cable → Pi's `micro-USB PWR IN`.
  - Branch 2 — USB-A → bare-wire pigtail → panel driver board's `5 V /
    GND` screw terminal (red = +5 V, black = GND).
  The splitter lives inside the 3D-printed frame; both branches share a
  common GND via the PSU return path. Net effect: panel current does
  **not** cross the Pi's polyfuse.
- Splitter PCB alternatives considered (kept here for procurement
  flexibility):
  - **Adafruit Micro B USB 2-Way Y Splitter Cable (PID 3030)** — a
    pre-built cable, ~US$8, splits a micro-USB input into one
    data+power micro-USB and one power-only micro-USB. Slightly tidier
    inside the frame, no PCB to mount, but only two micro-USB outputs
    so you'd still need a micro-USB → bare-wire pigtail for the panel
    feed.
  - AliExpress "Micro USB Power Splitter" PCBs — functionally identical
    to the Pi Hut board; lower cost (A$3–6) but slower AU shipping and
    variable build quality.
- Indoor and outdoor sensor units are **identical** firmware and
  hardware. They share the same BOM line item (qty 2). The role one
  each plays is assigned on the Pi side via
  `/etc/kitchen-clock/config.toml`; no firmware difference between
  them. Swap roles later = edit one line in the config.
- Physical differentiation at deployment: stick a small label (e.g.
  "A" / "B", or "In" / "Out") on each sensor enclosure so the user
  can record which MAC corresponds to which physical location before
  copying addresses into the config.
