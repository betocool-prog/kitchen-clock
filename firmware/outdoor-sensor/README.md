# Sensor unit — firmware (Zephyr / nRF52)

_Zephyr 3.7 LTS application, board `xiao_nrf52840`._

**One binary, two deployments.** The same firmware image ships to
both the indoor and the outdoor sensor node. The firmware does **not**
know or persist which role it is playing; that decision lives on the
Pi in `/etc/kitchen-clock/config.toml` and is matched against the
unit's bonded MAC.

## Layout

```
firmware/outdoor-sensor/
├── west.yml                  # Zephyr 3.7 LTS manifest
└── app/
    ├── prj.conf              # Kconfig
    ├── CMakeLists.txt        # top-level build script
    ├── boards/
    │   └── xiao_nrf52840.overlay   # I²C enablement + BME280 node
    └── src/
        ├── main.c            # entry; init + idle loop
        ├── ble.c / ble.h     # Local-name "kclock-XX", ESS for
        │                     #   temp/humidity, custom uint16 char
        │                     #   for battery voltage in mV
        ├── sensor.c          # BME280 driver wrapper + battery stub
        ├── power.c           # deep-sleep cadence stub (next step)
        └── mac.c             # prints public BLE address at boot
```

## GATT layout

Two services, recognised by nRF Connect:

- **Environmental Sensing Service** (UUID `0x181A`) for temperature
  (`0x2A6E`) and humidity (`0x2A6F`) — *standard BLE SIG service*.
  Implemented via `CONFIG_BT_ESS=y`, `BT_ES_DEFINE(...)`,
  `bt_es_set_temperature()`, `bt_es_set_humidity()`.
- **A custom service** (UUID `6b63...e0 01`) for **battery voltage
  in millivolts** as a read-only `uint16` characteristic. Plug a
  1:1 voltage divider on the BAT rail to the XIAO's SAADC pin and
  read it via the nRF52 ADC driver; the current `sensor.c`
  stub returns 0 mV until that wiring is in.

Decimal splitting: a temperature GATT value of `23.45 °C` is rendered
as `ess.temperature = (val1 = 23, val2 = 450000)`. Same logic for
humidity.

## Building

**Inside the Docker container** (See `docker/README.md`).

```sh
cd /work/firmware/outdoor-sensor
west update                     # clones Zephyr 3.7 LTS once
west build -b xiao_nrf52840 app
cp build/zephyr/zephyr.uf2 /work/dist/outdoor-sensor.uf2
```

`scripts/build-sensor.sh` is a one-line wrapper for the last three
steps; either path works.

## Flashing (UF2)

1. Plug the XIAO USB-C cable into the host.
2. Double-tap the XIAO's RST button in <0.5 s. The board enumerates
   as a USB mass-storage drive called `XIAO-BOOT` (auto-mounts under
   `/media/$USER/XIAO-BOOT/` on Zorin).
3. `cp dist/outdoor-sensor.uf2 /media/$USER/XIAO-BOOT/`.
4. The board auto-reboots into the new firmware.

## Verifying with nRF Connect

```sh
tio -b 115200 /dev/ttyACM0       # USB-CDC console
```

You should see lines like:

```
kitchen-clock sensor firmware: boot
MAC[0]: AA:BB:CC:DD:EE:XX
BME280 ready
BLE ready: name=kclock-XX
BLE addr[0] = AA:BB:CC:DD:EE:XX
sensor: 23.45 C, 47.20 %RH
kitchen-clock sensor firmware: idle (awaiting BLE events)
```

In **nRF Connect for Mobile** → **Scan** → pick `kclock-XX` →
**Connect**. The ESS Temperature and Humidity characteristics appear
under "Environmental Sensing Service". The custom service shows up
under the UUID; reading it gives battery voltage in mV (0 until the
ADC divider is wired).

## Open follow-ups

- Deep-sleep cadence (`power.c`).
- Real battery-mV reading via SAADC + divider.
- Notification / subscription on characteristics (instead of polled
  read) once the Pi-side GATT client lands.
- Bonding storage on the Pi side per `docs/decisions/0004-ble-pairing.md`.
