# 3. Wi-Fi provisioning

Date: 2026-08-22

## Status

Accepted.

## Context

The main unit must obtain NTP and Open-Meteo data over Wi-Fi, but the Pi
has no screen input. Options considered:

- AP-mode captive portal on first boot.
- BLE configuration from a phone.
- Static / boot-time credential file on the SD card.
- mDNS zero-configuration networking.

## Decision

**Boot-time credential file** strategy, with SSH for aftercare:

1. The Raspberry Pi OS Lite image is built with a pre-populated
   `wpa_supplicant.conf` on the FAT32 boot partition, containing the home
   SSID + PSK + `country=AU`.
2. First boot: NetworkManager (or `systemd-networkd`) reads the file,
   joins the network, brings up `wlan0`, and continues boot.
3. After first boot, the same file is consumed. Re-provisioning the Wi-Fi
   only requires re-imaging the SD card or editing the file on the FAT32
   partition from any computer.
4. SSH is enabled by an empty `ssh` flag file on the boot partition (Pi
   convention). Key-based auth on the running device.

A host-side helper, `scripts/prep-sdcard.sh`, copies the credential
template onto a freshly imaged SD card without a full re-flash.

## Consequences

- No captive-portal UI code to write and maintain.
- No phone-app dependency at provisioning time.
- Changing Wi-Fi credentials = re-mount / re-image the SD card. Acceptable
  for a kitchen appliance that rarely moves.
- The PSK ends up in plaintext on the boot partition of the SD card. This
  is the standard Pi practice and acceptable for this project's threat
  model (kitchen appliance, not a credential vault).
- Image backups / clones therefore contain the PSK. Documented in the
  Wi-Fi ADR's contrast section above.
