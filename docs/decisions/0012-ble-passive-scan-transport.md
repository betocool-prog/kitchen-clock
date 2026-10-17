# 12. BLE transport: passive scan of broadcast payloads

Date: 2026-10-17

## Status

Accepted. Amends the connect/poll halves of
[0004 — BLE pairing](0004-ble-pairing.md); the GATT service itself stays.

## Context

The panel needs current T/H/B from two battery-powered sensor units.
ADR 0004 decided: sensors advertise connectable, the Pi opens a GATT
connection and polls the three characteristics. Two iterations of that
model on the bench Pi (Zero W, BCM43430A1, BlueZ 5.82) both ended in
multi-hour outages:

- **Hold-the-link model** (pre-2026-10): BlueZ cached a phantom
  `Connected: yes` after the peripheral dropped the link; the next
  connect attempt silently died inside bleak's conn-acquire path. This
  produced the `bluetoothctl` scan-cycle watchdog and, later, the
  firmware's 5-second self-disconnect (commit 1d6f2de) to clean the
  daemon's state.
- **Windowed-reconnect model** (v7, 2026-10-17): the runner issued both
  sensors' GATT connects *concurrently* on a single-radio controller,
  each wrapped in a 15-second timeout, and the render loop awaited
  them — so a BLE outage froze the panel clock for 15 s per tick. The
  watchdog fired `bluetoothctl scan off/on` on *every* tick past its
  threshold (its fail counter never reset) and left discovery
  permanently on. After ~1 h of that connect storm the **system D-Bus
  daemon saturated**: `org.freedesktop.DBus.ListNames` returned
  `ENOBUFS`, `bluetoothctl` crashed with a libdbus assertion, and
  nothing in-process could reach BlueZ again. The panel showed `n/a`
  until the operator rebooted.

Meanwhile the sensors themselves were healthy throughout: both were
advertising and serving fresh GATT data (verified independently from
the dev host's own radio).

The common disease is *connection state* on a marginal central stack:
every failure mode lives in ConnectDevice / disconnect cleanup /
discovery-filter churn. The actual data payload is 7 bytes, and the
user-visible requirement is "sensor wakes every 15 s, sends T/H/B, the
panel updates and otherwise keeps the last values".

## Decision

**The sensor embeds T/H/B in its advertising packet; the Pi never opens
a GATT connection.**

Firmware (v8, `firmware/outdoor-sensor/app/src/ble.c`):

- Advertising stays connectable (GATT debugging via nRF Connect still
  works; the 5 s self-disconnect stays as the debug-session tidy-up),
  but now carries an ESS **service-data** element (UUID16 0x181A):
  `flags(u8, fw-version) + temp(i16 centi-°C) + hum(u16 centi-%RH) +
  batt(u16 raw SAADC, 0 = no-data sentinel)` — same encodings as the
  GATT chars, little-endian.
- Measurement cadence 30 s → **15 s**; each sample rewrites the
  service-data payload and refreshes the advertisement
  (stop + start; ~ms gap).
- The GATT service and its three characteristics are unchanged.

Pi app (`kitchen_clock/ble/scanner.py`):

- A single long-lived `BleakScanner` with a **server-side UUID filter**
  (`0000181a-…`) — bluetoothd only forwards reports for devices
  advertising that service data, so neighbour devices (phones, watches,
  TVs) never cross D-Bus. This is what keeps the transport load on the
  same order as the old model *despite* scanning continuously.
- Reports are mapped to registry sensors by MAC (name as fallback),
  decoded into the same `SensorReading` the GATT path produced, and
  cached in the hub. `ScannerClient.read()` drains the cache — the
  render loop never touches the radio.
- Render-cache promotion is **per field** (`merge_reading`): a report
  that carries a fresh temperature but no battery value updates only
  the temperature slot; failed fields keep the last good value. A tile
  that has never seen data stays `n/a`.
- Watchdog (`ble/watchdog.py`): when *no* registered sensor has
  reported for 90 s, restart the hub's scanner — at most once per
  120 s, as a background asyncio task. If D-Bus is dead the restart
  raises, is logged, and is retried after the cooldown; a hard-wedged
  daemon needs the operator's reboot, and the journal says so.

If the UUID filter ever proves not to match service-data-only
advertisements on some BlueZ build (empirically verified on the bench
Pi's 5.82), the fallback is one line: drop `service_uuids` and filter
client-side by `kclock-` name prefix, accepting the extra D-Bus report
traffic.

## Consequences

- **Nothing to wedge.** No connections, no GATT discovery, no
  ConnectDevice timeouts, no disconnect cleanup. A Pi-side BlueZ
  hiccup is at worst a scanner restart; a sensor reboot is just a gap
  in reports while the panel holds its last values.
- The panel clock can no longer freeze on BLE trouble — the render
  loop and the transport are fully decoupled (the 15 s connect-timeout
  freeze was a direct symptom of coupling them).
- Sensor deep-sleep (the `power.c` stub's goal) drops in naturally:
  wake → sample → advertise a burst → sleep 15 s. The passive listener
  does not care whether the advertisement is continuous or bursty.
- Journal volume drops from ~3 lines/s (per-tick state lines) to
  on-change plus a 60 s heartbeat.
- Pairing/bonding (ADR 0004) becomes moot for the data path — the
  panel trusts MAC + name mapping, same threat model ("kitchen
  appliance, not a vault"). The GATT debug path remains unencrypted
  read-only, as before.
- Battery still ships raw ADC counts (divider/VDD calibration is a
  separate, analog-front-end question — unchanged by this ADR).
- Cost: a coordinated upgrade — sensors must run v8 firmware before the
  panel can see values (v7 advertises by name only, the UUID filter
  screens it out; the runner's journal says so via the probe).
