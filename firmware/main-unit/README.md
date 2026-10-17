# Main unit — Pi app (Python)

_Python ≥3.12 package `kitchen_clock`, version 0.3.0. Runs on the Pi
as `kitchen-clock.service` and on the host for dev._

The app renders the panel (AWST clock + date + two sensor tiles) and
ingests the sensor units' broadcast payloads by **passive scanning**
(ADR 0012) — it never opens a GATT connection. On the Pi it writes
directly to `/dev/fb0` via Pillow + numpy (ADR 0011 — SDL has no
working video driver on Pi Zero W Trixie); on the host it opens a
pygame window of the same layout.

## Layout

```
firmware/main-unit/
├── pyproject.toml            # deps: pygame, Pillow, numpy, bleak
├── kitchen_clock/
│   ├── __main__.py           # entry: python -m kitchen_clock
│   ├── runner.py             # shared gather → merge → draw loop,
│   │                         #   per-field render-cache merge
│   ├── config/sensors.py     # bonded-peer registry (MAC, name, role)
│   ├── time.py               # AWST wall clock + date formatting
│   ├── ble/
│   │   ├── scanner.py        # ScannerHub: filtered passive scan,
│   │   │                     #   ESS 0x181A decode, staleness
│   │   ├── watchdog.py       # rate-limited scanner-restart recovery
│   │   └── bleak_client.py   # decoders + mock client + legacy
│   │                         #   GATT client (debug probes only)
│   └── ui/
│       ├── window.py         # renderer dispatch (env var)
│       ├── fbdev_window.py   # Pi: mmap /dev/fb0 via Pillow
│       └── pygame_window.py  # host: pygame window
└── tests/                    # pure-Python unittests (no hardware)
```

## Running

```sh
python -m kitchen_clock                       # mock BLE, host pygame
KITCHEN_CLOCK_BLE=live python -m kitchen_clock  # live scanner transport
python -m kitchen_clock --sensor outdoor --period 0.5
```

Flags / env vars:

| Setting | Values | Default | Notes |
| --- | --- | --- | --- |
| `--mock` | flag | off | forces `KITCHEN_CLOCK_BLE=mock` |
| `--sensor` | `outdoor`/`indoor`/`all` | `all` | registry filter |
| `--period` | seconds | `0.25` | render period (4 fps) |
| `--timezone` | IANA key | `Australia/Perth` | |
| `--time-format` | `12h`/`24h` | `12h` | |
| `KITCHEN_CLOCK_RENDERER` | `pygame`/`fbdev` | `fbdev` | Pi service uses `fbdev` |
| `KITCHEN_CLOCK_BLE` | `mock`/`live` | `mock` | `live` = scanner hub |

Behaviour worth knowing (ADR 0012):

- Reports update tiles **per field**; a missing battery value keeps the
  last good one. A tile that has never seen data renders `n/a` and
  never blanks once populated.
- The render loop never touches the radio — BLE trouble cannot freeze
  the clock.
- If **no** sensor reports for 90 s the hub's scanner is restarted, at
  most once per 120 s, as a background task. A dead D-Bus is logged and
  retried after the cooldown; a hard wedge needs a reboot, and the
  journal says so.

## Tests

```sh
python -m unittest discover -s firmware/main-unit/tests
```

## Deploy to the bench Pi

```sh
scripts/deploy-to-pi.sh          # rsync + units + restart + snapshot
```

The Pi's venv is an editable install pointing at `/opt/kitchen-clock`,
so the rsync in that script is what actually ships the code; the
restart loads it. Watch it live:

```sh
journalctl -u kitchen-clock.service -f          # on the Pi
python scripts/probe-ble-scan.py --duration 20  # from the host
```
