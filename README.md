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
| Architecture | done | ADRs 0001–0009 in `docs/decisions/` |
| Hardware selection | done | see [`docs/bom.md`](./docs/bom.md) |
| Dev environment (Docker) | queued | Dockerfile + scripts |
| Sensor firmware (Zephyr BLE peripheral) | done | builds and ships on nRF52; verified on nRF Connect; UART P1.11/P1.12 debug link |
| Pi SD-card provisioning | **done** | Trixie 32-bit + `prep-sdcard.sh` brings the Pi up on `192.168.0.49/24` over `TelstraD87381-24`, hostname `kclock`, SSH active. Survives reboot via `kclock-wifi-unblock.service` (see ADR 0008). |
| Bench bring-up | **done** | end-to-end from cold-flash: console login → wifi unblocked → NM associates → static IPv4 → ping WAN. Repeatable across reboots. |
| Pi app skeleton | queued | Python + LVGL split-pane (next) |
| Indoor I²C sensor | dropped | replaced by secondary BLE sensor unit |
| Outdoor BLE client | queued | BlueZ `bluetoothctl` integration, two bonded peers |
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
│   ├── decisions/        # ADRs (0001..0008)
│   ├── checklists/       # 01-pi-on-lan.md, ...
│   └── bom.md
├── hardware/
│   ├── main-unit/        # Pi + panel mount + frame
│   │   └── README.md
│   └── sensor-unit/      # XIAO+BME280+26650 + IP54 enclosure, ×2
├── firmware/
│   ├── main-unit/        # Pi app (Python + LVGL)
│   └── outdoor-sensor/   # Zephyr app (nRF52)
├── docker/
│   ├── Dockerfile
│   └── pi-overlay/       # pi-gen overlay for the SD-card image
├── scripts/
│   ├── setup-host.sh
│   ├── build-sensor.sh
│   ├── build-image.sh
│   ├── build-sd-bundle.sh   # renders templates → build/sd/
│   ├── prep-sdcard.sh       # writes build/sd/ → SD card
│   ├── fix-cmdline.sh       # writes a complete cmdline.txt with
│   │                        #   the right root= PARTUUID
│   └── templates/sd/        # envsubst-templated provisioning files
```

## Build / dev quick reference

```sh
# One-time host setup (creates the conda env, installs system deps).
./scripts/setup-host.sh

# Outdoor sensor firmware (containerised; requires `docker/Dockerfile`).
./scripts/build-sensor.sh

# Pi SD-card image (containerised; requires `docker/Dockerfile`).
./scripts/build-image.sh

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
