# Docker — dev environment

A single Debian Bookworm image (created in step 3) provides:

- Zephyr 3.7 LTS SDK at `/opt/zephyr-sdk`.
- Zephyr Python tooling (`west`, `pyelftools`) in `/opt/zephyr-venv`.
- `pi-gen` to assemble the Raspberry Pi OS SD-card image.
- `qemu-user-static` + binfmt for ARM binary smoke tests.

Once the Dockerfile is in place:

```sh
docker build -t kitchen-clock-build:latest -f docker/Dockerfile .
```

Entry points are the thin shell wrappers under `scripts/`:

- `scripts/build-sensor.sh` — Zephyr firmware → UF2.
- `scripts/build-image.sh` — Raspberry Pi OS image → `.img`.
