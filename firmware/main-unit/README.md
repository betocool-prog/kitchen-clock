# Main unit — firmware (Pi app)

Python 3.13 + Pillow on the Pi, PyGame on host dev. Path A — renderers
split by Environment at runtime so we don't carry the SDL dependency on
the small armv6 Pi. See `docs/decisions/0011-pygame-on-pi-runtime.md`,
specifically the "fbdev fork" paragraph.

## Layout

```
firmware/main-unit/
├── pyproject.toml
├── README.md                                   (this file)
├── kitchen_clock/
│   ├── __init__.py
│   ├── __main__.py                             (entry: `python -m kitchen_clock`)
│   ├── config/
│   │   ├── __init__.py
│   │   └── sensors.py                          (bonded peer registry; kclock-d0/d3)
│   ├── ble/
│   │   ├── __init__.py
│   │   └── bleak_client.py                     (decode + RealBleakClient + MockBleakClient)
│   ├── runner.py                               (BaseRunner + concurrent reads + client cache)
│   └── ui/
│       ├── __init__.py
│       ├── window.py                           (dispatcher: 'pygame' or 'fbdev')
│       ├── pygame_window.py                    (host dev: SDL2 window)
│       └── fbdev_window.py                     (Pi runtime: /dev/fb0 mmap + PIL)
└── tests/
    ├── __init__.py
    └── test_ble_decode.py                      (pure-python unit tests)
```

## Env vars

| Var                            | Value              | Effect                                                       |
| ------------------------------ | ------------------ | ------------------------------------------------------------ |
| `KITCHEN_CLOCK_RENDERER`       | `fbdev` (Pi default)| Direct `/dev/fb0` blit via mmap + Pillow. Bypasses SDL.      |
|                                | `pygame`           | SDL2 window — host dev only.                                  |
|                                | anything else      | Raises `ValueError`.                                         |
| `KITCHEN_CLOCK_BLE`            | `mock` (default)   | `MockBleakClient` — synthetic readings, no bluetooth.        |
|                                | `live`             | `RealBleakClient` — uses host `hci0` over bleak.             |

CLI flags `--mock`, `--sensor {outdoor|indoor|all}`, `--period <sec>`
override defaults on the command line. `--period` defaults to `0.25`
(= 4 fps).

## Why split renderers

The Pi Zero W Trixie armv6 + pygame 2.6.1 SDL 2.32 wheel lands in
this state:

| SDL driver | Status |
| --- | --- |
| `kmsdrm` | EGL fails — Pi Zero W has no GPU. |
| `fbcon` | Not compiled into the SDL 2.32 armv6 multi-arch build. |
| `x11` | No X server. |
| `directfb` | No DirectFB. |
| `dummy` | OK (but doesn't render). |

We therefore bypass SDL on the Pi and render directly to the
framebuffer. The host dev loop keeps PyGame so iteration speed is
maximised.

## Running on the host

```sh
conda activate kitchen-clock

# PyGame window on the host laptop (SDL2 backend).
PYTHONPATH=firmware/main-unit \
  KITCHEN_CLOCK_RENDERER=pygame \
    python -m kitchen_clock --mock --period 0.25

# Probe the wired kclock-d0 unit via BLE.
PYTHONPATH=firmware/main-unit \
  python -m kitchen_clock --sensor outdoor --period 0.5
```

## Running on the Pi

```sh
ssh betocool@192.168.0.49
ls /dev/fb0 /sys/class/graphics/fb0
# expected: /dev/fb0 present, virtual_size readable.
```

`scripts/probe-pygame-video-drivers.py` is the diagnostic you run on
the Pi **before** rebuilding the venv — see ADR 0011 for the
rationale of stepping away from `fbcon`.

The image-level wiring is in
`docker/pi-overlay/stage2/00-kclock-runtime/`:

- apt: `python3-pil python3-pygame python3-bluez` (Pillow is the
  renderer dep; pygame stays for occasional SDL-style probing).
- A venv at `/opt/kitchen-clock-venv` with `pip install` of
  `firmware/main-unit/` plus `dbus-python`, `bleak`.
- `kitchen-clock.service` running that venv's Python as
  `User=betocool`, with `Environment=KITCHEN_CLOCK_RENDERER=fbdev`,
  `Restart=on-failure`, `WantedBy=multi-user.target`.

## Testing

```sh
PYTHONPATH=firmware/main-unit python -m unittest discover \
  -s firmware/main-unit/tests -p "test_*.py" -v
```

Pure-python tests; no bluetooth or framebuffer required.

## ADR

Detailed rationale is at `docs/decisions/0011-pygame-on-pi-runtime.md`.
