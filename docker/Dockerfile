# Dockerfile for the kitchen-clock build environment.
# Mirrors `docs/decisions/0005-dev-environment.md`. Sets up
# west + Zephyr SDK 0.17.x + pi-gen. You run the builds.
#
# Build:
#   docker build -t kitchen-clock-build:latest -f docker/Dockerfile .
#
# Use (interactive shell — recommended for first time):
#   docker run -it --rm -v "$PWD":/work kitchen-clock-build:latest
#   # inside the container:
#   source /opt/zephyr-venv/bin/activate
#   cd /work/firmware/outdoor-sensor   # (after west init)
#   west build -b xiao_nrf52840 app
#   cp build/zephyr/zephyr.uf2 /work/dist/outdoor-sensor.uf2
#
# Use (one-shot):
#   docker run --rm -v "$PWD":/work kitchen-clock-build:latest \
#       bash -c 'source /opt/zephyr-venv/bin/activate && \
#                west build -b xiao_nrf52840 /work/firmware/outdoor-sensor/app && \
#                cp build/zephyr/zephyr.uf2 /work/dist/outdoor-sensor.uf2'
#
# Either way, the produced UF2 lands in `dist/outdoor-sensor.uf2` on the
# host, ready to drag-and-drop into `XIAO-BOOT` after the XIAO is
# double-tapped into the bootloader.
FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive

# Build dependencies for Zephyr (cmake/ninja/python/bison/flex/dtc) +
# pi-gen (kpartx/dosfstools/cpio/mtools) + helpful host tools.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        cmake \
        ninja-build \
        ccache \
        git \
        wget \
        curl \
        ca-certificates \
        xz-utils \
        python3 \
        python3-pip \
        python3-venv \
        python3-dev \
        bison \
        flex \
        device-tree-compiler \
        qemu-user-static \
        binfmt-support \
        cpio \
        file \
        unzip \
        dosfstools \
        mtools \
        kpartx \
        rsync \
        openssh-client \
        pkg-config \
    && rm -rf /var/lib/apt/lists/*

# Python tooling used by west / Zephyr build (kept in a venv at
# /opt/zephyr-venv per ADR 0005).
RUN python3 -m venv /opt/zephyr-venv \
    && /opt/zephyr-venv/bin/pip install --upgrade pip \
    && /opt/zephyr-venv/bin/pip install \
        west \
        pyelftools \
        pyserial \
        intelhex \
        pyyaml \
        anytree \
        cbor2

# Zephyr SDK 0.17.2. SHA verified against the upstream `sha256.sum.txt`
# that ships at the same release tag — no hard-coded hash here so the
# Dockerfile stays inspectable. If upstream ever rotates, this layer
# busts cleanly.
ARG ZEPHYR_SDK_VERSION=0.17.2
RUN cd /tmp \
    && wget -q "https://github.com/zephyrproject-rtos/sdk-ng/releases/download/v${ZEPHYR_SDK_VERSION}/sha256.sum.txt" \
    && wget -q "https://github.com/zephyrproject-rtos/sdk-ng/releases/download/v${ZEPHYR_SDK_VERSION}/zephyr-sdk-${ZEPHYR_SDK_VERSION}_linux-x86_64_gnu.tar.xz" \
    && sha256sum -c sha256.sum.txt --ignore-missing \
    && mkdir -p /opt/zephyr-sdk \
    && tar -xJf "zephyr-sdk-${ZEPHYR_SDK_VERSION}_linux-x86_64_gnu.tar.xz" \
        -C /opt/zephyr-sdk --strip-components=1 \
    && rm "zephyr-sdk-${ZEPHYR_SDK_VERSION}_linux-x86_64_gnu.tar.xz" sha256.sum.txt

# Install the toolchains. `yes` accepts all bundle prompts; `-c` confirms
# the host tools re-detection step. arm-zephyr-eabi is what
# `xiao_nrf52840` actually uses; the rest of the bundles are harmless
# bloat on disk but keep the image reproducible across boards later.
RUN yes | /opt/zephyr-sdk/setup.sh -c

ENV ZEPHYR_TOOLCHAIN_PATH=/opt/zephyr-sdk
# Zephyr pulls in `arm-zephyr-eabi` from the SDK; override GCC's
# search path so the cross-compiler in `$ZEPHYR_TOOLCHAIN_PATH`
# comes first on PATH inside the container.
ENV PATH="/opt/zephyr-sdk/arm-zephyr-eabi/bin:/opt/zephyr-sdk/x86_64-pokysdk-linux/usr/bin:/opt/pi-gen:${PATH}"

# pi-gen (Pi OS image assembler, used for `scripts/build-image.sh`).
# Cloned at this depth so we get the README, default config, and
# stage hooks — we layer our overlay under docker/pi-overlay/ at run
# time.
RUN git clone --depth 1 https://github.com/RPi-Distro/pi-gen.git /opt/pi-gen

WORKDIR /work

# Default to bash for interactive use; you source the venv and call
# west by hand. This is intentional — the build is your command.
ENTRYPOINT ["/bin/bash"]
CMD ["-l"]
