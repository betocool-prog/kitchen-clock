# Main unit — firmware (Pi app)

Python 3.12 + LVGL Python bindings.

Planned layout:

- `kitchen_clock/`
  - `__init__.py`
  - `__main__.py` — entry point for `python -m kitchen_clock`.
  - `ui/` — LVGL widgets (split-pane, time, weather, indoor/outdoor
    readouts).
  - `data/` — sources for clock, indoor sensor (I²C), outdoor sensor
    (BLE GATT client), Open-Meteo (HTTPS).
  - `history.py` — 24 h rolling min/max ring buffer per sensor.
  - `config.py` — load `/etc/kitchen-clock/config.toml`.
- `pyproject.toml`
- `tests/`

## Running on the host (for development)

```sh
conda activate kitchen-clock
LVGL_SDL2=1 python -m kitchen_clock
```
