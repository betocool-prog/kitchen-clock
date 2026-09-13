#!/usr/bin/env python3
#
# scripts/probe-pygame-video-drivers.py
#
# Probes PyGame's SDL2 video drivers on a target host. We use this on
# the Pi to pick the right SDL_VIDEODRIVER for that machine.
#
# Why system Python? We probe *two* Pythons at different stages:
#
#   /usr/bin/python3            — system's apt python3-pygame
#                                 (Bookworm/Trixie SDL 2.0.x + fbcon).
#   /opt/kitchen-clock-venv/bin/python — venv's piwheels pygame
#                                 (newer SDL with kmsdrm/EGL).
#
# And we run this on the Pi before we rebuild the venv, so the
# printer just sets the driver for the call to `pygame.display.set_mode`.
#
# Exit code: 0 if any real (non-`dummy`) driver initialised
# successfully, else 1.

import os
import sys


CANDIDATES = ["kmsdrm", "fbcon", "directfb", "x11", "dummy"]


def main() -> int:
    print(f"Python: {sys.executable}", file=sys.stderr)
    print(f"Python version: {sys.version.split()[0]}", file=sys.stderr)
    print(f"Drivers probed: {CANDIDATES}", file=sys.stderr)
    print("", file=sys.stderr)

    import pygame
    pygame.init()
    print(f"pygame version: {pygame.version.ver}", file=sys.stderr)
    print(f"SDL version:    {pygame.version.SDL}", file=sys.stderr)
    print("", file=sys.stderr)

    print("Driver probe results:")
    successes_real = 0
    for d in CANDIDATES:
        os.environ["SDL_VIDEODRIVER"] = d
        try:
            pygame.display.quit()
        except Exception:
            pass
        try:
            pygame.display.init()
        except Exception as e:
            msg = str(e).splitlines()[0][:80]
            print(f"  {d:<8}: FAIL on init ({msg})")
            pygame.display.quit()
            continue
        try:
            surf = pygame.display.set_mode((100, 100))
            print(f"  {d:<8}: OK              -> {surf.get_size()}")
            if d != "dummy":
                successes_real += 1
        except Exception as e:
            msg = str(e).splitlines()[0][:80]
            print(f"  {d:<8}: FAIL ({msg})")
        finally:
            pygame.display.quit()

    print("", file=sys.stderr)
    print(f"Working real drivers: {successes_real}/{len(CANDIDATES) - 1}",
          file=sys.stderr)
    return 0 if successes_real >= 1 else 1


if __name__ == "__main__":
    sys.exit(main())
