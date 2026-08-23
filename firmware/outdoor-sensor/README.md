# Sensor unit — firmware (Zephyr / nRF52)

_Zephyr 3.7 LTS application, board `xiao_nrf52840`._

**One binary, two deployments.** The same firmware image ships to both
the indoor and the outdoor sensor node. The firmware does **not** know
or persist which role it is playing; that decision lives on the Pi in
`/etc/kitchen-clock/config.toml` and is matched against the unit's
bonded MAC.

The directory is named `firmware/outdoorsensor/` for historical
reasons and is referenced by `scripts/build-sensor.sh` and the ADRs;
**the contents describe a generic sensor unit** that gets deployed
twice.

Planned layout:

- `app/prj.conf` — Zephyr config.
- `app/src/main.c` — entry point.
- `app/src/sensor.c` — BME280 read, build the GATT characteristic
  payload.
- `app/src/ble.c` — advertise, expose the custom GATT service with
  temperature / humidity / battery characteristics.
- `app/src/power.c` — deep-sleep cadence between advertisements.
- `app/src/mac.c` — print the device's last-two-bytes BLE address to
  the USB serial console for ~5 s at boot (deployment-time marker).
- `app/boards/xiao_nrf52840.overlay` — pin mux for BME280 I²C.

## Building

```sh
# Host build (fast iteration).
west build -b xiao_nrf52840 firmware/outdoor-sensor/app

# Container build (reproducible; requires `docker/Dockerfile`).
./scripts/build-sensor.sh
```
