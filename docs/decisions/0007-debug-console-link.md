# 7. Debug console link to the XIAO nRF52840

Date: 2026-08-29

## Status

Accepted.

## Context

During Zephyr bring-up, `printk(...)` output that *doesn't* reach the host
is indistinguishable from silent failure. We hit this concretely on the
first flash: every BLE init code path ran to completion and emitted
nothing, because we wired the Y-split into the
USB-C data lines (we don't — the Pi-side chase is unrelated), and because
the host's CDC-ACM endpoint for the XIAO refused to re-enumerate cleanly
after every `bossac`-triggered reset, swallowing output until we
unplugged and replugged.

The on-board primary debug link is **USB-CDC** (a USB ACM endpoint on the
native USB port of the nRF52840). Board DTS defaults to that endpoint for
`zephyr,console`.

Constraints:

- The same XIAO is meant to live behind an SMA pigtail in a weatherproof
  enclosure. We want a debug link that survives "soft reboot from the
  Pi side" without manual intervention.
- The user has a 3.3 V USB-serial dongle to hand.
- The XIAO nRF52840 board DTS already defines `uart0_default` pinctrl on
  **P1.11 (TX) and P1.12 (RX)** — castellations on the bottom of the
  module. So we don't have to invent a pin map, we just need to enable
  that uart0 and re-target the console.

## Decision

**`printk(...)` goes to UART0 on the XIAO's P1.11 (TX) / P1.12 (RX)
pads, paired with an external 3.3 V USB-serial dongle on the bench.**

- The XIAO's USB-C port stays enabled for an auxiliary CDC ACM endpoint
  used by BLE HCI traces / mcumgr (`zephyr,bt-c2h-uart = &usb_cdc_acm_uart`),
  but no longer carries the printk stream.
- Host-side, we read `/dev/ttyUSB0` (or `/dev/ttyACM0` for the CDC dongle)
  with `tio` at 115 200 baud / 8N1.

## Consequences

- One more solder joint per unit at assembly time: TX on the dongle → a
  flying lead to XIAO P1.11; RX on the dongle → XIAO P1.12;
  GND → XIAO GND. The board's castellations are the right contact
  points, but in the final outdoor enclosure the debug link is not
  broken out — it's only used during bench bring-up and during any
  field-recovery rework.
- We add `CONFIG_UART_CONSOLE=y`, drop `CONFIG_UART_CONSOLE=n`,
  and we set the chosen console in-app overlay rather than letting the
  board default to USB-CDC.
- The on-board `led0` (P0.26, labelled "Red LED" in the board DTS but
  colloquially the "I'm alive" blink in our flow) is reused for the
  250 ms heartbeat — see `app/src/blinky.c`.
- Future production units (i.e. post bring-up) can keep the CDC console
  on if the flea-power tax is acceptable on the production release.
  For now we optimise for reliability of diagnostics over a single shared
  endpoint.
