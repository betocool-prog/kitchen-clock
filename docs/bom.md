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
| Micro-USB → VBUS/GND breakout PCB (Adafruit PID 1833) | Core Electronics / Adafruit | 1 | 8 | 8 |
| JST-style 2-pin inline DC socket (plug + receptacle), AWG22 pigtails | Altronics P7831A (already on hand) | 1 | 0 | 0 |
| Hookup wire, red + black, AWG22, ~1 m (Y-split inside frame) | Altronics / generic | 1 | 3 | 3 |
| Cable gland (PG7 or M12) | Altronics | 1 | 3 | 3 |
| microSD card, 16 GB, A1-rated | generic | 1 | 12 | 12 |
| 3D-printed frame (PLA/PETG) | local print | 1 | 25 | 25 |

**Main unit subtotal: ~A$196**

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

**Total project: ~A$321–341**

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
- Power topology is **custom harness** (no off-the-shelf splitter PCB):
  the official Raspberry Pi 5.1 V / 3 A micro-USB PSU's captive
  micro-USB plug enters the frame through a PG7 cable gland and lands
  on an **Adafruit PID 1833** Micro-B USB → VBUS/GND breakout PCB
  (input = micro-B female receptacle; output = plated through-holes
  for VBUS and GND). AWG22 wires are soldered directly to those pads:
  - One pair feeds a **JST-style 2-pin inline DC socket** (Altronics
    P7831A, plug on the harness side, receptacle mounted to the
    chassis). This is the single service-disconnect point at the
    frame boundary.
  - The receptacle's wires enter the frame and **Y-split** into two
    AWG22 pairs at a soldered splice + heatshrink (a Wago 221-415
    lever-nut is a reversible alternative): one branch to the Pi's
    GPIO header (pin 4 = 5 V, pin 6 = GND), one branch to the panel
    driver board's `5 V / GND` screw terminal (red +, black −).
  Net effect: panel current does **not** cross the Pi's polyfuse,
  and the entire power path is soldered with one pluggable service
  disconnect. No inline slow-blow fuses; protection is delegated to
  the PSU's own 3 A foldback current limit.
- Breakout-location flexibility: the Adafruit PID 1833 board is small
  enough (20 × 10 mm) to live just inside or just outside the back
  cover. Placement is open until frame layout is finalised.
- Sensor-unit battery load: both XIAO + BME280 nodes ship with 2× AA
  alkaline cells per unit. No lithium, no boost stage.
- Indoor and outdoor sensor units are **identical** firmware and
  hardware. They share the same BOM line item (qty 2). The role one
  each plays is assigned on the Pi side via
  `/etc/kitchen-clock/config.toml`; no firmware difference between
  them. Swap roles later = edit one line in the config.
- Physical differentiation at deployment: stick a small label (e.g.
  "A" / "B", or "In" / "Out") on each sensor enclosure so the user
  can record which MAC corresponds to which physical location before
  copying addresses into the config.
