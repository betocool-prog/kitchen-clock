# Main unit — hardware

The indoor kitchen-clock unit:

- **Electronics**: Raspberry Pi Zero 2 W and the EastRising
  ER-TFT090-3-3938 9″ IPS HDMI panel driver board.
- **Mechanical**: 3D-printed frame, mount for the panel, optional
  cutout for the cable gland that admits the PSU's micro-USB cable.

Files:

- `openscad/` — OpenSCAD source for the printed frame; exports to
  STL/3MF.

The two **sensor units** (indoor + outdoor, identical hardware and
firmware) live under `../sensor-unit/` and are not part of this
unit's assembly.

A KiCad PCB project for any custom carriers (panel driver board
adapter, sensor breakout, custom power-distribution board) will live
alongside this when needed.
