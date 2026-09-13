#!/usr/bin/env python3
#
# scripts/capture-fb0-screenshot.py
#
# Capture the Pi's `/dev/fb0` framebuffer to a PNG. Run on the Pi
# after a few tiles have been drawn by `kitchen-clock` (or stopped
# in foreground), so the screenshot shows what is on the panel.
#
# The Pi's framebuffer layout changes per panel + KMS config. We
# read geometry from sysfs, decode the raw framebuffer bytes to
# RGB888 in this script, and write a PNG via Pillow.
#
# Usage (on the Pi):
#   /opt/kitchen-clock-venv/bin/python scripts/capture-fb0-screenshot.py \
#     /tmp/panel.png
#   scp /tmp/panel.png user@host:path/to/dest/
#
# Requires Python with Pillow visible (we use the venv's
# /opt/kitchen-clock-venv/bin/python because the venv has been
# built with `--system-site-packages` so apt's python3-pil is
# visible).
#
# Tested with /dev/fb0 1024x600, 16bpp RGB565 (EastRising 9" panel).

import argparse
import os
import struct
import sys


SYSFB = "/sys/class/graphics/fb0"


def _read_sysfs(name: str) -> str:
    with open(f"{SYSFB}/{name}") as f:
        return f.read().strip()


def discover_fb0():
    """Return (width, height, bpp, stride) for the first framebuffer."""
    parts = _read_sysfs("virtual_size").split(",")
    width = int(parts[0])
    height = int(parts[1])
    bpp = int(_read_sysfs("bits_per_pixel"))
    try:
        stride = int(_read_sysfs("stride"))
    except FileNotFoundError:
        stride = width * (bpp // 8)
    return width, height, bpp, stride


def rgb565_to_rgb888(raw: bytes, width: int, height: int) -> bytes:
    n = width * height
    out = bytearray(n * 3)
    for i in range(n):
        v = struct.unpack("<H", raw[i * 2 : i * 2 + 2])[0]
        r = ((v >> 11) & 0x1F) * 255 // 31
        g = ((v >> 5) & 0x3F) * 255 // 63
        b = (v & 0x1F) * 255 // 31
        out[i * 3 + 0] = r
        out[i * 3 + 1] = g
        out[i * 3 + 2] = b
    return bytes(out)


def xrgb8888_to_rgb888(raw: bytes, width: int, height: int,
                       byte_order: str = "BGRX") -> bytes:
    n = width * height
    out = bytearray(n * 3)
    for i in range(n):
        src = i * 4
        bx = raw[src + 0]
        gx = raw[src + 1]
        rx = raw[src + 2]
        if byte_order.upper() == "RGBX":
            r, g, b = rx, gx, bx
        else:
            r, g, b = rx, gx, bx  # BGRX default
            r, g, b = b, g, r
        out[i * 3 + 0] = r
        out[i * 3 + 1] = g
        out[i * 3 + 2] = b
    return bytes(out)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Snapshot /dev/fb0 to a PNG.")
    ap.add_argument("output", nargs="?", default="/tmp/panel.png",
                    help="Output PNG path (default: /tmp/panel.png)")
    args = ap.parse_args()

    out_dir = os.path.dirname(os.path.abspath(args.output)) or "."
    os.makedirs(out_dir, exist_ok=True)

    width, height, bpp, stride = discover_fb0()
    nbytes = stride * height

    fb = os.open("/dev/fb0", os.O_RDONLY)
    try:
        raw = os.read(fb, nbytes)
    finally:
        os.close(fb)

    if len(raw) < nbytes:
        print(
            f"WARN: short read {len(raw)} < {nbytes} bytes; "
            f"PNG will still encode whatever was captured.",
            file=sys.stderr,
        )

    if bpp == 16:
        rgb = rgb565_to_rgb888(raw[: nbytes], width, height)
    elif bpp == 32:
        rgb = xrgb8888_to_rgb888(raw[: nbytes], width, height)
    else:
        print(
            f"ERROR: bits_per_pixel={bpp} is not in the supported "
            f"set {{16, 32}}; cannot decode.",
            file=sys.stderr,
        )
        return 2

    from PIL import Image
    img = Image.frombytes("RGB", (width, height), bytes(rgb))
    img.save(args.output, "PNG")
    print(
        f"Captured {width}x{height}@{bpp}bpp → {args.output} "
        f"({os.path.getsize(args.output)} bytes)",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
