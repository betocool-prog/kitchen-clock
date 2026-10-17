# Sensor unit — firmware (Zephyr / nRF52)

_Zephyr 3.7 LTS application, board `xiao_ble`. Current release: **v9**
(`dist/klock-sensor-YYYY-MM-DD-v9.uf2`)._

**One binary, two deployments.** The same firmware image ships to
both the indoor and the outdoor sensor node. The firmware does **not**
know or persist which role it is playing; that decision lives on the
Pi in the sensor registry
(`firmware/main-unit/kitchen_clock/config/sensors.py`, ADR 0004)
and is matched against the unit's public BLE address.

## Transport (ADR 0012)

The panel reads the sensors by **passive scanning** — it never opens
a GATT connection. Every 15 s the firmware re-samples the BME280 +
SAADC and refreshes the advertising packet, which carries the values
as **Environmental Sensing service data** (UUID16 `0x181A`):

```
advertising packet:
  flags                          (AD 0x01)
  complete 16-bit service UUIDs  (AD 0x03) — 0x181A; this is the element
                                   BlueZ's SetDiscoveryFilter(UUIDs=…)
                                   matches, so the Pi's server-side
                                   discovery filter keeps neighbour
                                   devices off D-Bus
  complete local name            (AD 0x09) — "kclock-XX" (last address byte)
  ESS service data               (AD 0x16) — 2-byte UUID 0x181A + payload:
        byte  0     flags / firmware-version marker (0xNN = vNN)
        bytes 1-2   temperature, int16 LE centi-°C   (0.01 °C)
        bytes 3-4   humidity,    uint16 LE centi-%RH  (0.01 %RH)
        bytes 5-6   battery,    uint16 LE raw SAADC counts
                     (0 = "no data", same sentinel as the GATT char)
```

The GATT service below is retained, connectable, for interactive
debugging (nRF Connect, `scripts/probe-ble-gatt.py`); on connect the
firmware still self-disconnects after 5 s so a forgotten debug
session cannot wedge BlueZ state.

## Layout

```
firmware/outdoor-sensor/
├── west.yml                  # Zephyr 3.7 LTS manifest
└── app/
    ├── prj.conf              # Kconfig
    ├── CMakeLists.txt        # top-level build script
    ├── boards/
    │   └── xiao_ble.overlay   # I²C + UART0 console + SAADC AIN7
    │                          #   + divider-enable GPIO P0.14
    └── src/
        ├── main.c            # entry; init + 15 s measurement timer
        ├── ble.c / ble.h     # advertising payload (name + ESS service
        │                     #   data + UUID16 list) and the debug GATT
        │                     #   service (0x2A6E T, 0x2A6F H, custom batt)
        ├── sensor.c          # BME280 wrapper + SAADC battery read
        ├── power.c           # deep-sleep cadence stub (next step)
        ├── blinky.c          # 2 Hz heartbeat on P0.26
        └── mac.c             # prints public BLE address at boot
```

## GATT layout (debug path)

**One** primary service, custom 128-bit UUID
`6b 63 6c 6b - 00 01 - 00 00 - 00 00 - 00 00 00 00 00 01`
(the first four bytes spell "kclk" in ASCII so the UUID is
recognisable in a hex dump). It carries three characteristics
declared with `BT_GATT_SERVICE_DEFINE`:

| Char | UUID | Type | Encoding | Notes |
| --- | --- | --- | --- | --- |
| Temperature | `0x2A6E` | read-only | int16, **0.01 °C** | Standard SIG ESS Temperature UUID — `nRF Connect` renders it as a temperature in the right scale. |
| Humidity    | `0x2A6F` | read-only | uint16, **0.01 %RH** | Standard SIG ESS Humidity UUID. |
| Battery raw | Custom 128-bit: `…-0002` | read-only | uint16, **raw 12-bit SAADC counts** | Same values as the broadcast payload's battery field; `0` = "no data". mV calibration is still open (divider + reference scaling). |

> **Note:** Zephyr 3.7 removed the upstream `bt/services/ess.h` header
> and the `BT_ES_DEFINE` / `bt_es_set_*` macros that 3.x LTS betas
> exposed. We therefore declare the temperature and humidity
> characteristics manually under a single custom service, but keep
> the standard 16-bit ESS characteristic UUIDs so `nRF Connect`
> recognises them and host-side GATT probes can read by them.

## Building

**Inside the Docker container** (see `docker/README.md`):

```sh
cd /work/firmware            # west workspace root (.west/ lives here)
west update                  # clones Zephyr 3.7 LTS once
west build -b xiao_ble outdoor-sensor/app
cp build/zephyr/zephyr.uf2 /work/dist/outdoor-sensor.uf2
```

`scripts/build-sensor.sh` runs the same steps from the host in one
shot and is the canonical path (it passes the build through the
image's `bash` entrypoint and `cd`s into the workspace for you).

## Flashing (UF2)

1. Plug the XIAO USB-C cable into the host.
2. Double-tap the XIAO's RST button in <0.5 s. The board enumerates
   as a USB mass-storage drive called `XIAO-BOOT` (auto-mounts under
   `/media/$USER/XIAO-BOOT/` on Zorin).
3. `cp dist/outdoor-sensor.uf2 /media/$USER/XIAO-BOOT/`.
4. The board auto-reboots into the new firmware.

Release artefacts are kept as `dist/klock-sensor-YYYY-MM-DD-vN.uf2`
so the bench journal lines (`boot vN`) can be matched to the exact
image that was flashed.

## Verifying

### From the host (no wires)

```sh
python scripts/probe-ble-scan.py --duration 20
```

runs the production `ScannerHub` (same filter and decode as the
panel) and prints the latest decoded T/H/B per registered sensor.

### Console

`printk(...)` is routed to the XIAO nRF52840's external **UART0** pads
(P1.11 = TX, P1.12 = RX). Connect a 3.3 V USB-serial dongle (FTDI,
CP2102 or CH340) to those two castellations plus GND, and read it
from the host:

```sh
tio -b 115200 /dev/ttyUSB0
```

The on-board USB-C port is **not** the printk link — Linux can lose
the CDC-ACM endpoint after a soft reset of the XIAO, swallowing
output. UART is robust against that.

You should see lines like:

```
kitchen-clock sensor firmware: boot v9
MAC: 0 addresses (controller not yet initialised)
BME280 ready
BAT-enable GPIO gpio0.14 -> low
SAADC ready: SAADC channel 7, gain enum=0 (0=ADC_GAIN_1_6, 5=ADC_GAIN_1_2, etc.), reference enum=3 (3=ADC_REF_VDD_1_4)
BLE ready: name=kclock-d0
BLE addr[0] = D0:44:B3:EE:AC:9F
sample: 23.44 C, 58.69 %RH
sample: SAADC raw = 1107 (panel: 'B: 1107 ADC')
blinky: thread running (P0.26, 250 ms period)
kitchen-clock sensor firmware: idle (periodic measurement every 15 s, broadcast payload + auto-disconnect)
sample: 23.39 C, 59.69 %RH
sample: SAADC raw = 1110 (panel: 'B: 1110 ADC')
...
```

(The `MAC:` line is expected to say "0 addresses" — Zephyr 3.7's
`bt_id_get()` only reports identities after `bt_enable()`; the real
address follows in the `BLE addr[0]` line from `ble.c`.)

The LED at **P0.26** also blinks at 2 Hz (250 ms on / 250 ms off) so
you can confirm the firmware is alive even if the host-side serial
is disconnected.

### nRF Connect (debug GATT path)

In **nRF Connect for Mobile** → **Scan** → pick `kclock-XX` →
**Connect**. The custom service `kclock` (UUID starting `6b 63 6c 6b`)
appears under "Unknown Service" or — for the temperature and humidity
characteristics — labelled by `nRF Connect` as **Temperature** and
**Humidity** thanks to their standard 16-bit ESS UUIDs. Reading each
characteristic returns the latest values; battery returns the raw
SAADC count (~1100 on a healthy 26650 through the divider). The link
self-disconnects after 5 s — reconnect to re-read.

## Open follow-ups

- Deep-sleep cadence (`power.c`): sleep → measure → advertise a burst
  → sleep 15 s. The passive-scan panel does not care whether the
  advertisement is continuous or bursty (ADR 0012), so this drops in
  without touching the Pi side.
- Battery **raw → mV** calibration (divider ratio + VDD-vs-internal
  reference question; see `boards/xiao_ble.overlay`).
- GATT notifications are no longer planned — the broadcast payload
  replaced the subscribe/poll idea (ADR 0012).
