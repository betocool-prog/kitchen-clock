# Pi image overlay

Customisations applied on top of `pi-gen`'s `lite` Bookworm image:

- Install Python 3.12 + system LVGL dev deps via apt.
- Install our `kitchen_clock` Python package.
- Drop `/etc/kitchen-clock/config.toml` with Perth defaults.
- Drop `wpa_supplicant.conf` template on the FAT32 boot partition.
- Enable our systemd unit `kitchen-clock.service`.

The directory structure here mirrors what pi-gen expects (`stage2/`,
`stage3/`, etc.) so files can be added without config rework once the
overlay is wired up in `docker/Dockerfile`.
