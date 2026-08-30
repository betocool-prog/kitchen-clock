# Checklist 01 — Pi on the LAN

Pre-flight + post-flash verification for the first boot of the
main Pi Zero W unit. Both SSH and the **direct UART serial
console** are kept alive as paths; use whichever comes up first.
(Ssh-only-first is preferred; UART is the standby when network /
NM fail.)

## Inputs you have

- [ ] SD card (≥ 8 GB) flashed with **Pi OS Lite Bookworm 32-bit**
      (Pi Zero W is ARMv6; the 64-bit Bookworm will not boot).
- [ ] Your plaintext login password. (`openssl passwd -6` once you
      need a new hash.)
- [ ] Your home WiFi SSID and the AP's pre-computed PSK in hex
      (`psk=<64 chars>` form). Verify it by running
      `wpa_passphrase "your-SSID" 'plaintext-passphrase'` from a
      reference machine and comparing.
- [ ] Your SSH public key (`cat ~/.ssh/id_ed25519.pub`).
- [ ] A **3.3 V USB-TTL serial adapter** — FTDI, CP2102 or CH340
      — and three flying leads (TX, RX, GND) ready to solder onto
      the Pi Zero W's GPIO header. The adapter is **not**
      RS232-level.

## On the host

- [ ] `cp secrets.env.example secrets.env`
- [ ] Edit `secrets.env` with all values. Watch out for envsubst
      literal `${...}` after editing — `bash scripts/build-sd-bundle.sh`
      renders them, and a missing value aborts.
- [ ] `bash scripts/build-sd-bundle.sh` — renders into `./build/sd/`.
- [ ] Eyeball `build/sd/userconf.txt`, `build/sd/wpa_supplicant.conf`,
      `build/sd/homewifi.nmconnection`. They should show real
      values, not `${VAR}` strings.

## SD prep

- [ ] Plug the SD card into the host.
- [ ] Confirm the device: `lsblk`. Expect `mmcblk0` (built-in),
      `sdc` (USB card reader), etc.
- [ ] `sudo scripts/prep-sdcard.sh /dev/sdX` — mounts the two
      partitions and copies the bundle. Two of the changes are
      idempotent if you re-run:
      - `enable_uart=1` appended to `config.txt`
      - `console=serial0,115200` prepended to `cmdline.txt`
      - `/etc/systemd/system/getty.target.wants/serial-getty@ttyAMA0.service`
        symlink dropped to `/lib/systemd/system/serial-getty@.service`
- [ ] Re-check the boot layer: `sudo mount /dev/sdX1 /mnt && ls /mnt`
      — `cmdline.txt`, `config.txt`, `locale.txt`, `ssh`,
      `timezone`, `userconf.txt`, `wpa_supplicant.conf`, and
      `<HOSTNAME>` are all present.
- [ ] Verify the UART edits: `grep enable_uart=1 /mnt/config.txt`
      and `grep console=serial0 /mnt/cmdline.txt`.

## First boot — SSH path

- [ ] Insert SD; plug 5.1 V / 2.5 A micro-USB into the **PWR** port.
- [ ] Wait ~60 s.
- [ ] `ping 192.168.0.49` from any LAN machine.
- [ ] `ssh -v betocool@192.168.0.49` — watch the debug log for
      `Authenticated via publickey`, also check that the
      `kitchen-clock main unit` banner appears.

## First boot — direct UART console (do this if SSH fails)

If SSH doesn't come up, **don't pull power**. Solder the
3.3 V USB-TTL adapter to the Pi Zero W's GPIO header:

```
   Pi Zero W GPIO header            USB-TTL dongle
   ─────────────────────────        ──────────────────
    GND       (pin 6 / 9 / ...)     ↔  GND
    GPIO 14   (pin 8)               →  RX (host receives)
    GPIO 15   (pin 10)              ←  TX (host transmits)
```

- [ ] Wire the three leads. **Do not** connect the adapter's 3V3
      output to the Pi — the Pi is independently powered.
- [ ] Plug the USB-TTL dongle into your laptop.
- [ ] `ls /dev/ttyUSB*` — a new device appears. On Windows, a new
      `COM<n>` from the Device Manager.
- [ ] Open the console:
      ```
      tio -b 115200 /dev/ttyUSB0
      ```
      (or `screen /dev/ttyUSB0 115200`, or `minicom -D /dev/ttyUSB0 -b 115200`)
- [ ] Watch boot messages. You should see:
      - `[    0.0] Booting Linux on physical CPU 0x0`
      - `serial8250 ... ttyS0 at I/O 0x...`
      - `Raspbian GNU/Linux 12 kclock login:`
- [ ] Log in as `betocool` with the password from `secrets.env`.

## What to check from the UART shell

Once you're in:

```sh
hostname;                  # → kclock
ip -4 addr show wlan0;     # → 192.168.0.49/24 (if NM came up)
date;                      # → AWST
cat /etc/timezone;         # → Australia/Perth
nmcli -t -f NAME con show; # → homewifi (and maybe preconfigured)
sudo journalctl -u NetworkManager -b 0 | tail -30
sudo nmcli device wifi list
sudo rfkill list
```

If `nmcli con show` doesn't list `homewifi`:

- NM silently rejected the `.nmconnection` because of a key typo.
  Most common: `address1=` is mis-keyed. Our template is now
  correct (singular `address1`); re-run prep against a fresh
  image and re-check.

If `nmcli con show` lists `homewifi` but it's not the active
connection:

- `nmcli con up homewifi` and watch for "Activation: failed".
  Common reasons:
  - "secrets were not provided" — wrong PSK hex.
  - "no carrier" — radio failure, rfkill still set.
  - "no compatible network found" — reg domain / SSID mismatch.
  - "no secrets available" — the `homewifi.nmconnection` was
    ignored (file permissions, wrong path, typo).

If `rfkill list` shows wifi blocked:

- `sudo rfkill unblock wifi` and re-try.

If SSH finally works, do not desolder the UART leads. They are
the standby path for future revisions.

## Recovery if a prior setup locked us out

- [ ] `bash scripts/build-sd-bundle.sh` (re-render the bundle).
- [ ] Edit `secrets.env` if anything has changed.
- [ ] `sudo scripts/prep-sdcard.sh /dev/sdX` (re-applies the
      bundle; idempotent). The script now backs up
      `config.txt` and `cmdline.txt` to `.bak-prep` before any
      edit, so re-runs are safe.
- [ ] If the SD card is in an unknown state, re-flash Pi OS Lite
      Bookworm 32-bit and re-run prep.

## Recovery if `cmdline.txt` is empty / missing `root=`

(Pi OS Trixie images occasionally ship a cmdline.txt without a
`root=PARTUUID=…` token. After our prep script no longer splices
cmdline.txt, recovery is manual.)

- [ ] Pull SD card; on the host, run
      ```
      sudo scripts/fix-cmdline.sh /dev/sdX
      ```
      The script will auto-detect the EXT4 rootfs PARTUUID, back
      the old `cmdline.txt` to `cmdline.txt.bak-cli`, and write a
      complete kernel command line that includes
      `root=PARTUUID=…`. With our Pi Zero W / Trixie kernel the
      line uses `console=ttyS0,115200` (the BCM2835 PL011 on GPIO
      14/15, exposed via the 8250 driver on 6.18).
- [ ] Plug SD back into the Pi, power on.

If you want to do it by hand instead of using the helper, the
same recipe is:

```sh
sudo mount /dev/sdX1 /mnt
sudo cp /mnt/cmdline.txt /mnt/cmdline.txt.bak-cli
PID=$(lsblk -n -o PARTUUID /dev/sdX2)
sudo tee /mnt/cmdline.txt >/dev/null <<EOF
console=ttyS0,115200 console=tty1 root=PARTUUID=${PID} rootfstype=ext4 fsck.repair=yes rootwait cfg80211.ieee80211_regdom=AU
EOF
sudo umount /mnt
```

## What comes after this

Bench-bench bring-up proven: from a 32-bit (Trixie) Pi OS image,
`scripts/prep-sdcard.sh` + baked-in `homewifi.nmconnection` yields
NM `homewifi` **activated with `192.168.0.49/24` manual IPv4**,
default route via `192.168.0.1`, DNS `192.168.0.1 1.1.1.1`, sshd up.
Survives reboot — `kclock-wifi-unblock.service` reasserts
`rfkill unblock wifi` and `WirelessEnabled=true` on every
boot, undoing Trixie firstboot's two-step revert. (See ADR `0008`.)

So the next steps:

- [x] Pi reachable on the LAN at `192.168.0.49/24`.
- [x] `nmcli con show homewifi` returns `STATE: activated`, IPv4 manual.
- [x] `ping 8.8.8.8` from UART shell yields sub-100ms RTT.
- [x] Survives `sudo reboot` / power-cycle (re-runs `prep-sdcard.sh`
      is unnecessary; cards boot presentable straight from cold).
- [ ] Migrate the SD-prep workflow into a pi-gen overlay so a
      `dist/kitchen-clock.img` is produced. See ADR `0008`.
- [ ] Drop `firmware/main-unit/` (Python LVGL app, BLE GATT
      client) and `sudo systemctl enable --now kitchen-clock.service`.
- [ ] Move to read-only root filesystem + overlayfs.
- [ ] Final unit goes into the EastRising panel assembly; see
      `hardware/main-unit/README.md` and ADR `0001-architecture.md`.

## "Why does Trixie block wifi by default?" — quick answer

It's a regulatory default, not a bug. Without a country code,
the kernel's CRDA regulatory database restricts wifi to the
"world-safe" channel set (essentially empty for 2.4GHz out of the
box, empty for 5GHz). Pi OS RPi tooling assumes you used Imager
(whose `raspi-config do_wifi_country` runs at first boot, lifts
the rfkill block, and sets the NetworkManager state) — or that
you'll run `raspi-config do_wifi_country` from a console. Neither
fits headless provisioning, so our prep explicitly:
1. Adds `cfg80211.ieee80211_regdom=AU` to the cmdline.
2. Mirrors what `raspi-config do_wifi_country AU` does via
   `/etc/default/crda`'s `REGDOMAIN=AU` and a `country=AU` in
   `/etc/wpa_supplicant/wpa_supplicant.conf`.
3. Bootstraps a systemd `kclock-wifi-unblock.service` to undo
   the state that firstboot sets *back to "blocked"* on every
   reboot — unconditionally best-effort, marked `RequiredBy=
   NetworkManager.service` so NM can't start until the
   unblock has run.

The whole detail in ADR `0008-pi-provisioning.md`.
