"""Host-side dev runner: opens a PyGame window and pumps BLE reads.

This is **not** the final look — it's the dev cycle for layout, font
choice, and re-read perf. The Pi runtime uses LVGL via the dispatcher
in ui/window.py (Path C, ADR 0005).
"""
import asyncio

import pygame

from ..runner import BaseRunner


WIDTH, HEIGHT = 800, 480
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
GREY = (120, 120, 120)
RED = (220, 60, 60)


class PygameRunner(BaseRunner):
    def __init__(self, *, make_client, sensors, period_s: float = 2.0,
                 surface_size=(WIDTH, HEIGHT)):
        super().__init__(
            make_client=make_client, sensors=sensors, period_s=period_s,
        )
        self.surface_size = surface_size
        pygame.init()
        self.screen = pygame.display.set_mode(surface_size)
        pygame.display.set_caption("kitchen-clock dev (pygame)")
        self.font_big = pygame.font.SysFont(None, 36)
        self.font_small = pygame.font.SysFont(None, 22)

    async def run(self):
        try:
            while True:
                for evt in pygame.event.get(pygame.QUIT):
                    return
                await self._tick()
                await asyncio.sleep(self.period_s)
        finally:
            pygame.quit()

    def _draw(self):
        self.screen.fill(BLACK)
        title = self.font_big.render(
            "kitchen-clock — library", True, WHITE,
        )
        self.screen.blit(title, (20, 10))
        for i, r in enumerate(self.last_readings):
            if r is None:
                continue
            self._draw_one(r, i)
        pygame.display.flip()

    def _draw_one(self, r, idx):
        x = 20
        y = 60 + idx * 110
        head = f"{r.location or '(unnamed)'} — {r.name or r.mac}  [{r.source}]"
        self.screen.blit(self.font_big.render(head, True, WHITE), (x, y))
        self._draw_line("T", r.temp_c, "°C", x, y + 45)
        self._draw_line("H", r.hum_percent, "%RH", x, y + 70)
        self._draw_line("B", r.batt_mV, "mV", x, y + 95)

    def _draw_line(self, label, value, unit, x, y):
        if value is None:
            text, color = f"{label}: n/a", RED
        elif isinstance(value, float):
            text, color = f"{label}: {value:.1f} {unit}", WHITE
        else:
            text, color = f"{label}: {value} {unit}", WHITE
        self.screen.blit(self.font_small.render(text, True, color), (x, y))
