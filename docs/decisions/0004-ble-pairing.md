# 4. BLE pairing

Date: 2026-08-22

## Status

Accepted.

## Context

The indoor Pi needs current readings from two battery-powered MCUs reporting
temperature, humidity, and battery voltage. Both sensor units run identical
firmware; their role ("indoor" / "outdoor" / any custom name) is decided by
deployment location, not by firmware. Constraints:

- Sensor units must run for months on 2× AA.
- Pi has no input device to enter a PIN or pair interactively.
- The nRF52840 has a robust BLE peripheral stack; the Pi Zero 2 W has a
  usable BLE host via BlueZ.

Options considered:

- Just-works / no pairing, accepting any advertiser — fast but trivially
  spoofable.
- LE Legacy Pairing with a fixed PIN — adds friction.
- Out-of-band exchange via NFC or QR — extra hardware.
- Manual one-time pairing via `bluetoothctl`, save the bond key on the Pi.
- Hard-coding role in the local-name suffix — couples role to firmware;
  swapping roles requires re-flashing.

## Decision

**Pi scans; sensor units advertise; pair once per MAC; trust the bonded
peer; role is decided on the Pi side.**

- Each sensor unit exposes a custom GATT service with three characteristics:
  temperature (centi-°C, int16), humidity (centi-%, uint16), battery
  voltage (mV, uint16).
- Local-name pattern: `kclock-XXXX` where `XXXX` is the **last two bytes**
  of the public device address, in upper-case hex. The role is **not** in
  the name. The pattern supports a flat list of paired peers without a
  shared schema.
- Advertising is connectable, 2–5 s interval. Each wake-up: read sensor,
  update char values, sleep.
- On the Pi: `bluetoothctl` lists nearby advertisers with the `kclock-`
  prefix. On first sight of an unknown MAC, initiate a Just-Works pairing;
  the bond key is stored in `/var/lib/bluetooth/<bdaddr>/info` (BlueZ
  default).
- After bonding, the Pi rejects peers with the same `XXXX` suffix but a
  different MAC.
- Re-pairing only happens if the bonded sensor is missing for >5 min, or
  if the user runs `scripts/repair.sh` over SSH.

**Role mapping (on the Pi):** `/etc/kitchen-clock/config.toml` carries a
list of bonded peers:

```toml
[[sensors]]
mac = "AA:BB:CC:DD:EE:01"
role = "indoor"   # free-form, shown in the UI

[[sensors]]
mac = "AA:BB:CC:DD:EE:02"
role = "outdoor"
```

The Pi scans for both bonded MACs, reads the role from the config and
shows each sensor's data labelled accordingly. Swapping a unit indoors ↔
outdoors is a config edit, not a firmware change. New sensors added later
just need a new `[[sensors]]` block; the firmware stays the same.

## Consequences

- No PIN entry UI needed.
- Bond keys live on the Pi filesystem; another SD-card clone on the same
  Pi (with the same MACs) rejoins without re-pairing.
- 2–5 s advertising cadence + BLE 1M PHY chosen for low average current
  (~30 µA average on each sensor at a 4 s interval).
- The Pi's BLE and Wi-Fi share an antenna; scan windows are short to keep
  dropouts rare. Captured in the BLE scanner code on the Pi side, not on
  the sensor side.
- Threat model is "kitchen appliance, not a vault": a duplicate `kclock-`
  name in the wild is treated as peer failure, not security.
- Role flexibility: redeploy between indoor and outdoor by editing the
  config; no firmware touch.
- Adding a third, fourth, fifth sensor later requires only a new MAC +
  config entry.
