# Main unit — firmware (Pi app)

Python 3.12 + PyGame. Path A — same code on host dev and Pi runtime.
See `docs/decisions/0011-pygame-on-pi-runtime.md`.

## Layout

```
firmware/main-unit/
├── pyproject.toml
├── README.md                                (this file)
├── kitchen_clock/
│   ├── __init__.py
│   ├── __main__.py                          (entry: `python -m kitchen_clock`)
│   ├── config/
│   │   ├── __init__.py
│   │   └── sensors.py                       (bonded peer registry; kclock-d0/d3)
│   ├── ble/
│   │   ├── __init__.py
│   │   └── bleak_client.py                  (decode + RealBleakClient + MockBleakClient)
│   ├── runner.py                            (BaseRunner + concurrent reads + client cache)
│   └── ui/
│       ├── __init__.py
│       ├── window.py                        (Path A: always PyGame)
│       └── pygame_window.py                 (host dev runner = Pi runner)
└── tests/
    ├── __init__.py
    └── test_ble_decode.py                   (pure-python unit tests)
```

## Env vars

| Var                            | Value              | Effect                                                  |
| ------------------------------ | ------------------ | ------------------------------------------------------- |
| `KITCHEN_CLOCK_RENDERER`       | `pygame` (default) | PyGame SDL2 window on host and Pi.                      |
|                                | anything else      | Raises `ValueError` — Path A has only one renderer.    |
| `KITCHEN_CLOCK_BLE`            | `mock` (default)   | `MockBleakClient` — synthetic readings, no bluetooth.   |
|                                | `live`             | `RealBleakClient` — uses host `hci0` over bleak.        |
| `SDL_VIDEODRIVER`              | `kmsdrm` (Pi)      | Default on Trixie. Pi-only; not needed on the laptop.   |

CLI flags `--mock`, `--sensor {outdoor|indoor|all}`, `--period <sec>`
override defaults on the command line. `--period` defaults to
`0.25` (= 4 fps).

## Running on the host

```sh
conda activate kitchen-clock

# iterate with synthetic data; opens a PyGame SDL2 window
PYTHONPATH=firmware/main-unit python -m kitchen_clock --mock --period 0.25

# probe the wired kclock-d0 unit via BLE
PYTHONPATH=firmware/main-unit python -m kitchen_clock --sensor outdoor --period 0.5

# one-shot GATT probe (separate CLI; prints decoded + succeeds-per-characteristic)
PYTHONPATH=firmware/main-unit python scripts/probe-ble-gatt.py --sensor outdoor --ticks 1
```

## Running on the Pi

The Pi runs the **same** PyGame renderer, against the **same**
`kitchen_clock` package. The image-level wiring is in
`docker/pi-overlay/stage2/00-kclock-runtime/`:

- apt: `python3-pygame python3-pil libsdl2-image-2.0-0 libsdl2-ttf-2.0-0 libfreetype6 bluez`
- A venv at `/opt/kitchen-clock-venv` with `pip install dpkg` of this folder + `dbus-python bleak`.
- `kitchen-clock.service` unit running that venv's Python as `User=betocool`,
  with `Environment=SDL_VIDEODRIVER=kmsdrm` and `WantedBy=multi-user.target`
  (`After=bluetooth.target network-online.target`).

## Testing

```sh
PYTHONPATH=firmware/main-unit python -m unittest discover -s firmware/main-unit/tests -p "test_*.py" -v
```

Pure-python tests; no bluetooth required.

## Path A

PyGame on host and Pi. The same `kitchen_clock` package renders
either target's display. There is no LVGL wheel build in this
project. Detailed rationale: `docs/decisions/0011-pygame-on-pi-runtime.md`.
