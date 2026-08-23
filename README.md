# Kitchen Clock

A DIY kitchen clock with weather, built around a 9″ HDMI LCD driven by a
Raspberry Pi Zero 2 W, paired with a battery-powered BLE outdoor sensor.

See [`PROJECT.md`](./PROJECT.md) for the full specification and
[`docs/decisions/`](./docs/decisions/) for the architecture decision
records (ADRs).

## Status

| Phase | Status | Notes |
| --- | --- | --- |
| Spec | done | PROJECT.md captured |
| Architecture | done | ADRs 0001–0005 in `docs/decisions/` |
| Hardware selection | done | see [`docs/bom.md`](./docs/bom.md) |
| Dev environment (Docker) | next | Dockerfile + scripts |
| Blinky on outdoor sensor | queued | Zephyr "hello world" on XIAO nRF52840 |
| Pi app skeleton | queued | Python + LVGL split-pane |
| Indoor I²C sensor | dropped | replaced by secondary BLE sensor unit |
| Outdoor BLE client | queued | BlueZ `bluetoothctl` integration, two bonded peers |
| Open-Meteo fetch | queued | hourly + daily |
| 24 h min/max history | queued | ring buffer per sensor |
| 3D-printed frame | queued | OpenSCAD sources |
| Bench bring-up | queued | end-to-end test |

## Repository layout

```
.
├── PROJECT.md
├── README.md
├── docs/
│   ├── decisions/        # ADRs (0001..0005)
│   └── bom.md
├── hardware/
│   ├── main-unit/        # Pi + panel mount + frame
│   │   └── openscad/
│   └── sensor-unit/      # XIAO+BME280+AA in IP54 enclosure, ×2 (indoor + outdoor)
├── firmware/
│   ├── main-unit/        # Pi app (Python + LVGL)
│   └── outdoor-sensor/   # Zephyr app (nRF52)
├── docker/
│   ├── Dockerfile       # created in the next step
│   └── pi-overlay/       # pi-gen overlay for the SD-card image
├── scripts/
│   ├── setup-host.sh
│   ├── build-sensor.sh
│   └── build-image.sh
└── LICENSES/
```

## Build / dev quick reference

(Filled in once the dev environment is up.)

```sh
# One-time host setup (creates the conda env, installs system deps).
./scripts/setup-host.sh

# Outdoor sensor firmware (containerised; requires `docker/Dockerfile`).
./scripts/build-sensor.sh

# Pi SD-card image (containerised; requires `docker/Dockerfile`).
./scripts/build-image.sh
```

## License

All source under this repository is released under the licences listed in
[`LICENSES/`](./LICENSES). Project licensing is finalised before the
first source commit.

## Acknowledgements

- Weather data by [Open-Meteo](https://open-meteo.com/) — CC BY 4.0,
  attribution shown in the UI.
