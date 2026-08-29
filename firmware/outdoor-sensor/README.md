# Sensor unit — firmware (Zephyr / nRF52)

_Zephyr 3.7 LTS application, board `xiao_ble`._

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
    │   └── xiao_ble.overlay   # I²C enablement + BME280 node
    └── src/
        ├── main.c            # entry; init + idle loop
        ├── ble.c / ble.h     # Local-name "kclock-XX"; custom
        │                     #   128-bit service hosting the
        │                     #   standard ESS-style char UUIDs
        │                     #   0x2A6E (T) and 0x2A6F (H), plus a
        │                     #   custom uint16 char for battery mV
        ├── sensor.c          # BME280 driver wrapper + battery stub
        ├── power.c           # deep-sleep cadence stub (next step)
        └── mac.c             # prints public BLE address at boot
```

## GATT layout

**One** primary service, custom 128-bit UUID
`6b 63 6c 6b - 00 01 - 00 00 - 00 00 - 00 00 00 00 00 01`
(the first four bytes spell "kclk" in ASCII so the UUID is
recognisable in a hex dump). It carries three characteristics
declared with `BT_GATT_SERVICE_DEFINE`:

| Char | UUID | Type | Encoding | Notes |
| --- | --- | --- | --- | --- |
| Temperature | `0x2A6E` | read-only | int16, **0.01 °C** | Standard SIG ESS Temperature UUID — `nRF Connect` renders it as a temperature in the right scale. |
| Humidity    | `0x2A6F` | read-only | uint16, **0.01 %RH** | Standard SIG ESS Humidity UUID. |
| Battery mV  | Custom 128-bit: `…-0002` | read-only | uint16, **mV** | Custom characteristic under the same service; the Pi-side converts to volts. |

> **Note:** Zephyr 3.7 removed the upstream `bt/services/ess.h` header
> and the `BT_ES_DEFINE` / `bt_es_set_*` macros that 3.x LTS betas
> exposed. We therefore declare the temperature and humidity
> characteristics manually under a single custom service, but keep
> the standard 16-bit ESS characteristic UUIDs so `nRF Connect`
> recognises them and the Pi-side GATT bindings can read by them
> without an ESS-specific Knowledge Base entry.

## Building

**Inside the Docker container** (See `docker/README.md`).

```sh
cd /work/firmware/outdoor-sensor
west update                     # clones Zephyr 3.7 LTS once
west build -b xiao_ble app
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
**Connect**. The custom service `kclock` (UUID starting `6b 63 6c 6b`)
appears under "Unknown Service" or — for the temperature and humidity
characteristics — labelled by `nRF Connect` as **Temperature** and
**Humidity** thanks to their standard 16-bit ESS UUIDs. Reading
each characteristic returns the latest values. Battery-mV returns 0
until the SAADC divider is wired.

## Open follow-ups

- Deep-sleep cadence (`power.c`).
- Real battery-mV reading via SAADC + divider.
- Notification / subscription on characteristics (instead of polled
  read) once the Pi-side GATT client lands.
- Bonding storage on the Pi side per `docs/decisions/0004-ble-pairing.md`.
