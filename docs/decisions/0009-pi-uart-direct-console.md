# 9. Pi Zero direct UART serial console

Date: 2026-08-30 (replaces the OTG-plan document that was already
numbered 0009 — see "Switched from" below).

## Status

Accepted.

## Context

Provisioned Pi Zero W boards are operated headless: the SD card
arrives in our bench, the Pi is plugged into power + LAN, and we
must SSH in to verify. During the first boot — when the Wi-Fi link
is still being brought up by NetworkManager, or the keys have
been mistyped, or NM silently dropped the connection profile
because of a keyfile syntax error — we are stuck: no SSH login
means no way to read NM state, no way to see where boot stopped,
and no way to verify `userconf.txt` was consumed at all.

We need a **standby debug path** that does not depend on the
Wi-Fi link being healthy.

Options considered:

1. **USB OTG serial console** via `g_serial` on the Pi's second
   micro-B port. Originally selected in the previous version of
   this ADR. Removed in this iteration after a bench attempt showed
   the OTG gadget did not enumerate reliably on the user's host
   (likely a USB-stack / cable issue, but the OTG setup is a soft
   intellectual dependency on host enumeration that we don't want
   to fight against during a bring-up).
2. **USB Ethernet over OTG** (`g_ether`) — heavier, would add a
   second NIC on the laptop side.
3. **GPIO 14 (TX) and GPIO 15 (RX) wired directly to a 3.3 V
   USB-TTL dongle** on the bench. Most reliable path: kernel-level
   UART drive, no enumeration dance, no drivers beyond the FTDI /
   CP2102 / CH340 that the host already has.

## Decision

We **enable the Pi Zero W's UART0 (`ttyAMA0 = serial0`) as a serial
console** and bring up a `serial-getty` on it so the bench can plug
in a 3.3 V USB-TTL converter directly onto the GPIO header. The
modifications are added to the SD card as part of the existing
provisioning bundle:

1. Append `enable_uart=1` to `/boot/firmware/config.txt`, with a
   comment header tag. This enables UART0 at 3.3 V CMOS levels,
   115 200 baud 8N1.
2. Prepend `console=serial0,115200 ` (note the trailing space) to
   the single line in `/boot/firmware/cmdline.txt`, so the kernel
   prints all boot messages to `serial0` for the first-Pi coupling
   to the USB-TTL adapter.
3. Drop a symlink on the rootfs:
   ```
   /etc/systemd/system/getty.target.wants/serial-getty@ttyAMA0.service
   → /lib/systemd/system/serial-getty@.service
   ```
   so systemd runs a login getty on `/dev/ttyAMA0` once the system
   has come up. Resolution prefers `/lib/...` and falls back to
   `/usr/lib/...` for classic Bookworm.

The user's bench adapter — a 3.3 V FTDI / CP2102 / CH340
USB-TTL dongle — is wired as:

```
  Pi Zero W GPIO header            USB-TTL dongle
  ─────────────────────────        ──────────────────
   GND        (pin 6 / 9 / ...)     ↔  GND
   GPIO 14 TX (pin 8)               →  RX (host receives)
   GPIO 15 RX (pin 10)              ←  TX (host transmits)
```

The adapter's 3.3 V output **must not** be tied to the Pi's 3V3
rail (no current share on the adapter's supply); the Pi is
separately powered via its PWR micro-B.

The host opens the console as:

```
  tio -b 115200 /dev/ttyUSB0
```

(Linux: FTDI/CP210x/CH340 enumerate as `ttyUSB0`. Windows: a new
COM port under Device Manager.)

## Switched from

The previous version of this ADR (`docs/decisions/0009` —
later renamed and rewritten) proposed  the USB-OTG `g_serial`
gadget approach. After a bench attempt, the OTG CDC-ACM device
did not enumerate on the host; rather than continue down a path
with brittle host-side enumeration, we accept the soldering step
on the bench and switch to the GPIO UART. The OTG approach
remains recorded here for completeness.

## Consequences

- A console is available **before** NetworkManager has come up.
  Boot messages can be observed end to end on first boot.
- One-time bench soldering cost: a USB-TTL dongle, three flying
  leads (TX, RX, GND) from the Pi's GPIO 14/15/GND to the
  dongle's TX/RX/GND. These are 3.3 V CMOS levels; **do not**
  use RS232-level adapters (would damage the BCM2835 pads).
- The console survives unit-to-unit network changes (no Wi-Fi
  dependency), reboots, and OTA firmware pushes. It is the
  deepest "always on" path.
- If the user later moves to a fully pi-gen image, the
  `enable_uart=1` line and the `console=serial0,115200` cmd
  token should be ported into the `docker/pi-overlay/` rather
  than running host-side after each flash.
- We use 115 200 baud 8N1. No flow control (no RTS/CTS lines
  are broken out); for short, infrequent debug logs, this is
  good enough. If we ever need flow control, GPIO 16 / 17 are
  the next pad.

## When the console helps vs. doesn't

The direct UART console helps whenever the **boot-level** state
is misbehaving:

- `userconf.txt` rejected (bad hash, wrong username) — visible
  immediately on the console as "no user is being created".
- NetworkManager rejecting `homewifi.nmconnection` due to a key
  typo or missing uuid — visible as `device (wlan0):
  Activation: failed`.
- `cmdline.txt` corrupted by hand — visible in the mmcblk
  device tree.

The UART console does **not** help if:

- The Pi is fine but our bundling shipped a wrong PSK hex.
  Console shows a successful association attempt; the bad
  material is on the *host* side. We re-confirm with
  `wpa_passphrase` from any reference machine.

## Followups

- A new entry in `docs/checklists/01-pi-on-lan.md` covering
  the UART-direct console workflow next to the SSH workflow.
- Once we learn a working PSK schema from a reference
  Telstra modem, capture it in `0002-weather-source.md` or a
  new ADR.
