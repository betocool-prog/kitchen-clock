# 4. BLE pairing

Date: 2026-08-22

## Status

Accepted.

## Context

The indoor Pi needs current outdoor temperature and humidity from a
battery-powered MCU. Constraints:

- Outdoor sensor must run for months on 2× AA.
- Pi has no input device to enter a PIN or pair interactively.
- The nRF52840 has a robust BLE peripheral stack; the Pi Zero 2 W has a
  usable BLE host via BlueZ.

Options considered:

- Just-works / no pairing, accepting any advertiser — fast but trivially
  spoofable.
- LE Legacy Pairing with a fixed PIN — adds friction.
- Out-of-band exchange via NFC or QR — extra hardware.
- Manual one-time pairing via `bluetoothctl`, save the bond key on the Pi.

## Decision

**Pi scans; sensor advertises; pair once; trust the bonded peer.**

- Outdoor sensor exposes a custom GATT service with three characteristics:
  temperature (centi-°C, int16), humidity (centi-%, uint16), battery
  voltage (mV, uint16).
- Local-name pattern: `kclock-outdoor-XX` where `XX` is the last two bytes
  of the MAC, expressed in hex. This supports multiple outdoor sensors
  added later.
- Advertising is connectable, 2–5 s interval. Each wake-up: read sensor,
  update char values, sleep.
- On the Pi: `bluetoothctl` lists nearby advertisers filtering on the
  `kclock-outdoor-` prefix. On first sight of a known MAC, initiate a
  Just-Works pairing; the bond key is stored in
  `/var/lib/bluetooth/<bdaddr>/info` (BlueZ default).
- After bonding, the Pi rejects peers with the same name suffix but a
  different MAC.
- Re-pairing only happens if the bonded sensor is missing for >5 min, or
  if the user runs `scripts/repair.sh` over SSH.

## Consequences

- No PIN entry UI needed.
- Bond key on the Pi filesystem; another SD-card clone on the same Pi can
  rejoin without re-pairing (assuming the same MAC).
- 2–5 s advertising cadence + BLE 1M PHY chosen for low average current
  (~30 µA average on the outdoor side at a 4 s interval).
- The Pi's BLE and Wi-Fi share an antenna; scan windows are short to limit
  dropouts. Captured in the BLE scanner code on the Pi side, not on the
  sensor side.
- Threat model is "kitchen appliance, not a vault": a duplicate outdoor
  name in the wild is treated as peer failure, not security.
