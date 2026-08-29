# Main unit — hardware

The indoor kitchen-clock unit:

- **Electronics**: Raspberry Pi Zero 2 W (with pre-soldered headers;
  GPIO pins 4 and 6 used for the harness) and the EastRising
  ER-TFT090-3-3938 9″ IPS HDMI panel driver board.
- **Mechanical**: bench frame, designed in **Onshape** by the user
  (see [ADR 0006](../decisions/0006-cad-tooling.md)). The Pi and
  panel driver board are mounted inside the back of the frame. The
  PG7 cable gland is fitted at the rear, with the harness's inline
  JST socket nearby. The Onshape document URL will be added to this
  README when the user has the document live.

## Harness routing inside the frame

The PSU's micro-USB cable enters the frame through the PG7 cable
gland and lands on the Adafruit PID 1833 breakout mounted on the
inside of the back cover. From the breakout, AWG22 wires go to the
inline JST pair (mounted at the frame boundary), and inside the
frame the receptacle side splits to:

- Pi's GPIO header (pin 4 = 5 V, pin 6 = GND), short AWG22 pigtails.
- Panel driver board's `5 V / GND` screw terminal (red +, black −),
  short AWG22 pigtails, with heatshrink over the splice.

There are no PCBs in this unit beyond the off-the-shelf breakouts
listed in `docs/bom.md` — see ADR 0006.
