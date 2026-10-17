# Kitchen Clock

A DIY kitchen clock with weather, built around a 9″ HDMI LCD driven by a
Raspberry Pi Zero W, paired with two battery-powered BLE sensor units
(indoor + outdoor).

See [`PROJECT.md`](./PROJECT.md) for the full specification and
[`docs/decisions/`](./docs/decisions/) for the architecture decision
records (ADRs).

## Status

| Phase | Status | Notes |
| --- | --- | --- |
| Spec | done | PROJECT.md captured |
| Architecture | done | ADRs 0001–0012 in `docs/decisions/` (0010 was never used) |
| Hardware selection | done | see [`docs/bom.md`](./docs/bom.md) |
| Dev environment (Docker) | **done** | image `kitchen-clock-build:latest` (Zephyr SDK 0.16.9 + west + pi-gen, `docker/Dockerfile`); both the sensor-firmware and image builds run inside it |
| Sensor firmware (Zephyr BLE peripheral) | done | v9: T/H/B broadcast in the advertising packet (ESS 0x181A service data + UUID16 list, ADR 0012), 15 s measurement cadence; GATT service kept for debugging; verified on nRF Connect; UART P1.11/P1.12 debug link |
| Pi SD-card provisioning | **done** | Trixie 32-bit + `prep-sdcard.sh` brings the Pi up on `192.168.0.49/24` over `TelstraD87381-24`, hostname `kclock`, SSH active. Survives reboot via `kclock-wifi-unblock.service` (see ADR 0008). |
| Bench bring-up | **done** | end-to-end from cold-flash: console login → wifi unblocked → NM associates → static IPv4 → ping WAN. Repeatable across reboots. |
| Pi app | **done** | `kitchen_clock` Python app (v0.3.0): fbdev renderer on the Pi (ADR 0011), AWST clock + date + two BLE sensor tiles, runs as `kitchen-clock.service`, deployed via `scripts/deploy-to-pi.sh` |
| Indoor I²C sensor | dropped | replaced by secondary BLE sensor unit |
| Outdoor BLE client | done | passive scan (ADR 0012): filtered BleakScanner, no GATT connections; per-field render-cache merge; rate-limited scanner-restart watchdog; verified live on the bench (2026-10-17) |
| Open-Meteo fetch | queued | hourly + daily |
| 24 h min/max history | queued | ring buffer per sensor |
| 3D-printed frame | managed in Onshape | user-designed (see ADR 0006) |

## Repository layout

```
.
├── PROJECT.md
├── README.md
├── secrets.env.example   # checked-in; copy → secrets.env
├── docs/
│   ├── decisions/        # ADRs (0001..0012)
│   ├── checklists/       # 01-pi-on-lan.md, ...
│   └── bom.md
├── hardware/
│   ├── main-unit/        # Pi + panel mount + frame
│   │   └── README.md
│   └── sensor-unit/      # XIAO+BME280+26650 + IP54 enclosure, ×2
├── firmware/
│   ├── main-unit/        # Pi app (Python; fbdev + pygame renderers)
│   └── outdoor-sensor/   # Zephyr app (nRF52)
├── docker/
│   ├── Dockerfile        # kitchen-clock-build:latest build farm
│   └── pi-overlay/       # pi-gen overlay for the SD-card image
└── scripts/
    ├── setup-host.sh        # one-time host (conda env + system deps)
    ├── build-sensor.sh      # containerised Zephyr build → dist/*.uf2
    ├── build-image.sh       # containerised pi-gen image build
    ├── deploy-to-pi.sh       # rsync app → Pi + service restart + snapshot
    ├── build-sd-bundle.sh    # renders templates → build/sd/
    ├── prep-sdcard.sh        # writes build/sd/ → SD card
    ├── fix-cmdline.sh        # rewrites a complete cmdline.txt
    ├── probe-ble-scan.py     # passive-scan smoke test (production hub)
    ├── probe-ble-gatt.py     # one-shot GATT read smoke test (debug)
    ├── probe-ble-devices.py  # bleak discovery smoke test
    ├── ble-poll-debug.py     # manual BLE poller (reconnect diagnosis)
    ├── gatt-walk.py          # walk a peripheral's GATT surface
    ├── sim_wake_loop.py      # Phase-0 timing harness for wake cadence
    └── templates/sd/         # envsubst-templated provisioning files
```

## Build / dev quick reference

```sh
# One-time host setup (creates the conda env, installs system deps).
./scripts/setup-host.sh

# Outdoor sensor firmware (containerised; requires image
# `kitchen-clock-build:latest` from `docker/Dockerfile`).
./scripts/build-sensor.sh

# Pi SD-card image (containerised; requires the same image).
./scripts/build-image.sh

# Deploy the Pi app to the bench Pi (rsync + service restart +
# panel snapshot; interactive, uses sudo on the Pi).
./scripts/deploy-to-pi.sh

# Host-side passive-scan smoke test against the real sensors.
python scripts/probe-ble-scan.py --duration 20

# First-time SD-card provisioning (host-side; does NOT need docker).
cp secrets.env.example secrets.env
# edit secrets.env ...
./scripts/build-sd-bundle.sh
sudo ./scripts/prep-sdcard.sh /dev/sdX
```

## License

All source under this repository is released under the licences listed in
[`LICENSES/`](./LICENSES). Project licensing is finalised before the
first source commit.

## Acknowledgements

- Weather data by [Open-Meteo](https://open-meteo.com/) — CC BY 4.0,
  attribution shown in the UI.
