"""Renderer dispatcher (Path A — see ADR 0011).

Two backends, picked by env var `KITCHEN_CLOCK_RENDERER` (defaults
to `fbdev`, the Pi-renderer, because the default command path is the
Pi service unit):

  * `pygame` — host dev backend; opens an SDL2 window on the laptop.
  * `fbdev`  — direct `/dev/fb0` blit via Pillow, the Pi runtime,
               bypassing SDL (Pi Zero W Trixie's SDL 2.32 has no
               working video driver).

Any other value raises a clear error.
"""
import os


def make_renderer(renderer=None):
    if renderer is None:
        if os.environ.get("KITCHEN_CLOCK_RENDERER") == "":
            raise ValueError(
                "KITCHEN_CLOCK_RENDERER set to empty; choose "
                "'pygame' or 'fbdev'"
            )
        renderer = os.environ.get("KITCHEN_CLOCK_RENDERER", "fbdev").lower()
    if renderer == "pygame":
        from .pygame_window import PygameRunner
        return PygameRunner
    if renderer == "fbdev":
        from .fbdev_window import FbdevRunner
        return FbdevRunner
    raise ValueError(
        f"unknown renderer: {renderer!r}; supported: 'pygame', 'fbdev'. "
        f"See docs/decisions/0011-pygame-on-pi-runtime.md."
    )
