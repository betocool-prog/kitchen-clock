# Decisions

This directory contains Architecture Decision Records (ADRs) for the
kitchen-clock project. ADRs are short, dated markdown files that capture
significant decisions, the options considered, and the consequences.

## Index

- [0001 — Architecture](0001-architecture.md) — main + sensor units, role
  model, power topology.
- [0002 — Weather source](0002-weather-source.md) — Open-Meteo HTTPS API.
- [0003 — Wi-Fi provisioning](0003-wifi-provisioning.md) — SD-card
  `wpa_supplicant.conf` drop.
- [0004 — BLE pairing](0004-ble-pairing.md) — Pi scans, sensors advertise,
  config-driven role labelling.
- [0005 — Dev environment](0005-dev-environment.md) — Docker as build
  farm; conda on host for the visible work.
- [0006 — CAD tooling and enclosure workflow](0006-cad-tooling.md) —
  Onshape for mechanical CAD; no KiCad PCBs.
- [0007 — Debug console link](0007-debug-console-link.md) —
  external UART0 on XIAO P1.11/P1.12 paired with a 3.3 V USB-serial
  dongle, instead of the on-board USB-CDC ACM endpoint.
- [0008 — Pi SD-card provisioning](0008-pi-provisioning.md) —
  eleven files dropped onto a freshly flashed Pi OS Lite Bookworm
  64-bit card by `scripts/build-sd-bundle.sh` and
  `scripts/prep-sdcard.sh`. Static IPv4 on `wlan0`, hashed PSK,
  keys + password allowed.
- [0009 — Pi Zero direct UART console](0009-pi-uart-direct-console.md) —
  3.3 V USB-TTL dongle wired onto GPIO 14/15 + `enable_uart=1` +
  `console=serial0,115200` + `serial-getty@ttyAMA0.service` getty
  symlink. Standby debug path that doesn't depend on Wi-Fi.
  (Previously proposed USB-OTG `g_serial`; renamed because the
  OTG alternative didn't enumerate reliably.)

## Considered and declined (not in this repo)

- **nRF Connect SDK (NCS)** as the firmware base instead of upstream
  Zephyr. Considered in 2026-08; declined. We use upstream Zephyr 3.7
  LTS for long-term API stability and independence from Nordic's
  release cadence. NCS in a container remains an interesting side
  experiment; it just isn't this project.
