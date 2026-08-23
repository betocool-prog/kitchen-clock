# Outdoor sensor — firmware (Zephyr / nRF52)

Zephyr 3.7 LTS application, board `xiao_nrf52840`.

Planned layout:

- `app/prj.conf` — Zephyr config.
- `app/src/main.c` — entry point.
- `app/src/sensor.c` — BME280 read, build the GATT characteristic
  payload.
- `app/src/ble.c` — advertise, expose the custom GATT service with
  temperature / humidity / battery characteristics.
- `app/src/power.c` — deep-sleep cadence between advertisements.
- `app/boards/xiao_nrf52840.overlay` — pin mux for BME280 I²C.

## Building

```sh
# Host build (fast iteration).
west build -b xiao_nrf52840 firmware/outdoor-sensor/app

# Container build (reproducible; requires `docker/Dockerfile`).
./scripts/build-sensor.sh
```
