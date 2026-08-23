# Main unit — hardware

The indoor kitchen-clock unit:

- **Electronics**: Raspberry Pi Zero 2 W, the EastRising
  ER-TFT090-3-3938 9″ IPS HDMI panel driver board, the BME280 indoor
  sensor on a JST-SH pigtail.
- **Mechanical**: 3D-printed frame, mount for the panel, optional
  ventilation slot for the indoor sensor cable.

Files:

- `openscad/` — OpenSCAD source for the printed frame; exports to
  STL/3MF.

A KiCad PCB project for any custom carriers (panel driver board
adapter, sensor breakout) will live alongside this when needed.
