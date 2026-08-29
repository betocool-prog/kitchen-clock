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

## Considered and declined (not in this repo)

- **nRF Connect SDK (NCS)** as the firmware base instead of upstream
  Zephyr. Considered in 2026-08; declined. We use upstream Zephyr 3.7
  LTS for long-term API stability and independence from Nordic's
  release cadence. NCS in a container remains an interesting side
  experiment; it just isn't this project.
