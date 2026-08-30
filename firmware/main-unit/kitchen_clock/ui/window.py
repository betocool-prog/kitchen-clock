"""Renderer dispatcher (Path A — see ADR 0011).

PyGame is the only renderer in this project, on host dev and on the
Pi runtime. The `KITCHEN_CLOCK_RENDERER` env var is retained as a
symmetric hook for tests, but values other than `pygame` raise a
clear error pointing at ADR 0011.
"""
import os

from .pygame_window import PygameRunner


def make_renderer(renderer=None):
    if renderer is None:
        renderer = os.environ.get("KITCHEN_CLOCK_RENDERER", "pygame").lower()
    if renderer != "pygame":
        raise ValueError(
            f"unknown renderer: {renderer!r}; Path A only ships "
            f"pygame (see docs/decisions/0011-pygame-on-pi-runtime.md)."
        )
    return PygameRunner
