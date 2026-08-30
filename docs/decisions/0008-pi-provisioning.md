# 8. Pi SD-card provisioning

Date: 2026-08-29 (originally accepted)
Date: 2026-08-30 (revised to reflect bench reality)

## Status

Accepted. Provisioning path working as confirmed on **Raspberry Pi OS Lite (32-bit) Trixie / 2026-05-21 firmware / kernel 6.18.34+rpt-rpi-v6**. Earlier draft assumed Bookworm; the actual bench image is Trixie. The repo has been updated accordingly.

## Context

The main unit needs to appear on the LAN (192.168.0.49/24, static)
with a primary user (`betocool`) ready for SSH login, optionally
without a display or keyboard, on first boot from a freshly
flashed image. The Pi is a single-purpose kitchen appliance —
frequent re-imaging is rare, but credential rotation must be possible.

Constraints:

- The SD card's boot partition is FAT32 and must remain readable
  from a Windows host (the standard Pi compromise).
- WiFi credentials are sensitive. The AP stores a 32-byte pre-hashed
  PSK; using that hex form means the file on the SD card carries
  zero plaintext.
- Login must work both by SSH public key and by password, so that
  we can recover by direct keyboard login if the laptop key is
  rotated.
- The user-supplied login password is a complete SHA-512 crypt
  hash ($6$…). Do not re-hash; do not hash plaintext.

Notes discovered in practice:

- **Trixie's `cmdline.txt` may not include a `root=` token.** If it
  doesn't, the kernel drops to initramfs with a BusyBox shell.
  Our prep detects this and appends `root=PARTUUID=…` derived
  from `p2`'s blkid output.
- **Trixie ignores the Bookworm `/boot/firmware/<hostname>` empty
  marker.** We additionally write `/etc/hostname` directly on the
  rootfs.
- **Trixie uses `console=ttyS0,115200` by default**, not
  `console=serial0`. We do not overwrite the image's own console
  choice — the kernel will route printk to whichever device it
  knows about. On the BCM2835 + 8250-driver framework in 6.18, that
  ends up on GPIO 14/15 (per the bench bring-up in PR-driven
  bring-up). If the user wired GPIO 32/33 and the kernel took
  ttyS0 to GPIO 14/15, they would still see logs there.
- **`enable_uart=1` in `config.txt` is still useful** even when
  console=ttyS0, because it exposes UART0 hardware in device-tree.
- **Trixie keeps wifi soft-blocked until CRDA has a regulatory
- domain.** Without `cfg80211.ieee80211_regdom=<alpha-2>` in
- cmdline the kernel's rfkill keeps wifi blocked at boot. The
- message-of-the-day reads "Wi-Fi is currently blocked by rfkill.
- Use raspi-config to set the country before use." `prep-sdcard.sh`
- addresses this three ways: append `cfg80211.ieee80211_regdom=AU`
- to cmdline; write `0` to every
- `/var/lib/systemd/rfkill/platform-…:wlan` flag file the image
- ships; mirror `raspi-config nonint do_wifi_country AU` by writing
- `/etc/default/crda` (`REGDOMAIN=AU`) and a `country=AU` line in
- `/etc/wpa_supplicant/wpa_supplicant.conf`.
- **Trixie firstboot rolls our prep back.** This is the actual root
- cause of `rfkill list` showing soft-blocked after a clean flash +
- prep. Specifically: Trixie's firstrun.sh writes a `1` to
- `/var/lib/systemd/rfkill/platform-…:wlan` on first boot so the
- radio is held off until the user explicitly sets a country via
- `raspi-config nonint do_wifi_country`. The same firstrun.sh
- writes `WirelessEnabled=false` to
- `/var/lib/NetworkManager/NetworkManager.state` (see
- `pi-gen/stage2/02-net-tweaks/01-run.sh`). Both flips make our
- pre-boot prep overwriteable. We schedule a systemd one-shot
  `kclock-wifi-unblock.service` — installed by `prep-sdcard.sh`
  into `/etc/systemd/system/` and symlinked into
  `/etc/systemd/system/NetworkManager.service.requires/` —
  that runs after `local-fs.target` and before
  `network-pre.target` / NM. Its execs set:
  * `rfkill unblock wifi` (and `bluetooth` for completeness),
  * `sed -i s/WirelessEnabled=…/WirelessEnabled=true/` on the NM
    state file,
  * `iw reg set <alpha-2 from /proc/cmdline>` so the kernel's
    CRDA reads our cmdline hint instead of stale userspace state.
  This is what the RPi forums and `raspi-config`'s own
  `do_wifi_country` do, minus the `raspi-config` interactive shell.
- **The cmdline's regdom alone is not enough on Trixie.** The
  cmdline hint unblocks the kernel handler at very early boot,
  but `systemd-rfkill` then re-reads the persistent state file
  (which Trixie firstboot set to `1`) and re-blocks wifi before
  NM checks. Our one-shot unit is the corrective side-effect:
  unblock wifi once `systemd-rfkill` has finished.

## Why Trixie ships with this behaviour (design rationale)

The Pi Foundation's stance: **wifi transmissions are
legally-restricted per country, and shipping a card with no country
context means the radio can't be sure which channels are legal
to use**. The Trixie default is `WirelessEnabled=false` plus rfkill
soft-blocking the device on first boot. The Pi tooling assumes
that either (a) you've used Raspberry Pi Imager's customisation
page, which records your country and writes a tiny firstrun.sh
that calls `raspi-config do_wifi_country`, or (b) you're a console
operator who'll run `raspi-config` interactively. Both paths
end up calling `do_wifi_country`, which does what we replicate
via four locations: cmdline's `cfg80211.ieee80211_regdom=<XX>`,
`/etc/default/crda`'s `REGDOMAIN=<XX>`,
`/etc/wpa_supplicant/wpa_supplicant.conf`'s `country=<XX>`, and the
runtime `iw reg set <XX>`.

Our instance adopts neither path — we're a console-less operator
who's copy-pasting files — so we have to *replicate what Imager
would have written*. The bundle we ship encodes country = `AU`
derived from `secrets.env` and stamps it into all four places,
plus the systemd-revert guard for the rfkill flag and the NM state
file. The "intuitive default" of "wifi just works" is what
Imager+Bookworm gave; the "safer default" of "blocked until a
country is explicitly set" is what Trixie + RPi's regulatory
defaults give once Imager is bypassed.

**In short:** the gating isn't a Trixie bug; it's a regulatory
default with the assumption you'll set the country before
putting the device on the air. We just don't have a console in
this deployment, so we set the country in the SD-card files
instead.

## Decision

`scripts/prep-sdcard.sh` mounts both partitions and drops files
in-place. `scripts/build-sd-bundle.sh` renders the templates from
`secrets.env` into `build/sd/`. `scripts/fix-cmdline.sh` is an
out-of-band recovery helper when `cmdline.txt` is empty or missing
the root= token at the bench.

```
boot partition (FAT32):
  userconf.txt                              username:crypt-hash
  ssh                                       (empty; enables sshd)
  <HOSTNAME>                                (empty; Bookworm marker — Trixie ignores)
  locale.txt                                LANG/LC_ALL/LANGUAGE
  timezone                                  Australia/Perth
  wpa_supplicant.conf                       (NM ignores on Trixie; defensive)
  config.txt + 'enable_uart=1'              exposes UART0
  cmdline.txt + 'root=PARTUUID=…'           only appended when missing

rootfs (ext4):
  /etc/NetworkManager/system-connections/homewifi.nmconnection
                                           static IPv4 (PSK)
  /etc/NetworkManager/conf.d/10-kclock-wifi-managed.conf
                                           unmanaged → managed
  /etc/ssh/sshd_config.d/02-kclock-sshd.conf
                                           keys + password, no root
  /etc/ssh/sshd_config.d/99-kclock-banner-ssh.conf
                                           Banner /etc/issue.net
  /etc/issue.net                           "kitchen-clock main unit" copy
  /etc/systemd/system/getty.target.wants/serial-getty@ttyAMA0.service
                                           symlink → /lib/systemd/system/serial-getty@.service
  /etc/hostname                            (Trixie won't read the bootfs marker)
  /etc/hosts                               (add a 127.0.0.1 alias for the hostname)
  /home/betocool/.ssh/authorized_keys      user's public key
```

The bootstrap flow:

```
secrets.env.example       → cp secrets.env.example secrets.env
                                  ↓ (user fills in values)
secrets.env               ← gitignored, contains real values
                                  ↓ scripts/build-sd-bundle.sh
build/sd/                 ← rendered, on the build machine only
                                  ↓ sudo scripts/prep-sdcard.sh /dev/sdX
SD card FAT32 + ext4      ← installed in-place
                                  ↓ power on, ~60 s
Pi on LAN at 192.168.0.49 ← accepts SSH (key + password)
```

## Code-side safety

The bootfs is FAT32, which a) does not support POSIX rename-after-create
on every msdos/vfat combo, and b) zeroed single-line files under some
`sed -i` patterns. As of this revision:

- `prep-sdcard.sh` does **not** call `sed -i` against FAT32 paths.
  Instead: read content into a shell variable, branch on what's there,
  write back via `printf '…' > "${file}""`. `cmdline.txt` content is
  preserved; if there's no `root=`, we append `root=PARTUUID=…`
  derived from `blkid -s PARTUUID` of the EXT4 root partition.
- The previous edition of `cmdline.txt` on the SD is backed up to
  `${MNT_BOOT}/cmdline.txt.bak-prep` (one-time). If something else
  gets wedged, restore via `cp cmdline.txt.bak-prep cmdline.txt `.
- `config.txt` is handled similarly with `enable_uart=1` appended
  via shell variable + `printf` rather than `sed -i`.

## Consequences

- No monitor required at any point on the bench.
- Re-imaging remains the only fine-grained credential-rotation
  path. Acceptable for a kitchen appliance.
- The PSK on the SD card is the AP-side hashed form; no plaintext
  ever appears. The login-password hash (`$6$…`) is non-reversible
  without `john`; an attacker with the SD card does **not** recover
  the plaintext.
- sshd accepts both keys and passwords (current default).
- The /boot/firmware partition is **not** LUKS-encrypted. Visible
  from a Windows host. Acceptable threat-model compromise.
- The hostname is set on both the bootfs (`<HOSTNAME>` empty file)
  *and* the rootfs (`/etc/hostname`). Trixie only honours the
  rootfs side; older Bookworm honours both.
- `cmdline.txt` is appended-to, not overwritten. We never splice
  the kernel's own `console=` choice. If a future image has its
  own `root=` token, it's preserved.

## Out of scope right now

Once we move to a pi-gen-produced image (phase 2), all of this
moves into `docker/pi-overlay/`. Until then, host-side prep +
recovery script is the working path.

## Followups

- Once the Pi-side app exists, fold `kitchen-clock.service` into
  the SD-prep bundle.
- Drop a `kclock`/`success` log so /var/lib/systemd/rfkill/ doesn't
  keep flipping back to "blocked" between boots after firstboot
  touches it. (Use `echo 0 > /var/lib/systemd/rfkill/<idx>:wlan`
  the first time we run a service-tier prep.)
- Validate checksum of `secrets.env` at every `build-sd-bundle.sh`
  so a corrupt local secrets file leads to a build-time error
  rather than a runtime-mismatch.
