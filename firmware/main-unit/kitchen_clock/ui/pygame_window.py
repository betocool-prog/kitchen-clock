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
                 surface_size=(WIDTH, HEIGHT), time_formatter=None):
        super().__init__(
            make_client=make_client, sensors=sensors, period_s=period_s,
        )
        self.surface_size = surface_size
        self.time_formatter = time_formatter
        pygame.init()
        self.screen = pygame.display.set_mode(surface_size)
        pygame.display.set_caption("kitchen-clock dev (pygame)")
        self.font_big = pygame.font.SysFont(None, 36)
        self.font_small = pygame.font.SysFont(None, 22)
        self.font_clock = pygame.font.SysFont(None, 64)

    async def run(self):
        try:
            # Scanner transport (ADR 0012): discovery runs beside
            # the render loop even in host dev.
            await self._start_ble()
            while True:
                for evt in pygame.event.get(pygame.QUIT):
                    return
                await self._tick()
                await asyncio.sleep(self.period_s)
        finally:
            pygame.quit()

    def _draw(self):
        self.screen.fill(BLACK)
        if self.time_formatter is not None:
            clock = self.font_clock.render(
                self.time_formatter.clock(), True, WHITE,
            )
            self.screen.blit(
                clock,
                ((self.surface_size[0] - clock.get_width()) // 2, 8),
            )
            date = self.font_big.render(
                self.time_formatter.date(), True, GREY,
            )
            self.screen.blit(
                date,
                ((self.surface_size[0] - date.get_width()) // 2, 80),
            )
            tiles_y = 130
            tile_h = 100
        else:
            title = self.font_big.render(
                "kitchen-clock — library", True, WHITE,
            )
            self.screen.blit(title, (20, 10))
            tiles_y = 60
            tile_h = 110
        for i, sensor in enumerate(self.sensors):
            last_r = self.last_readings[i] if i < len(self.last_readings) else None
            cur_r = self.current_readings[i] if i < len(self.current_readings) else None
            self._draw_tile(
                sensor, i, last_r, cur_r, base_y=tiles_y + i * tile_h,
            )
        pygame.display.flip()

    def _draw_one(self, r, idx, *, base_y=60):
        raise NotImplementedError(
            "_draw_one is now folded into _draw_tile; the panel"
        )

    def _draw_tile(self, sensor, idx, last_r, cur_r, *, base_y=60):
        mac, name, loc = sensor
        x = 20
        src = "live" if last_r is not None else (
            cur_r.source if cur_r is not None else "no-data"
        )
        head = f"{loc or '(unnamed)'} \u2014 {name or mac}  [{src}]"
        self.screen.blit(self.font_big.render(head, True, WHITE), (x, base_y))
        if last_r is None:
            self._draw_line("T", None, "\u00b0C", x, base_y + 45)
            self._draw_line("H", None, "%RH", x, base_y + 70)
            self._draw_line("B", None, "ADC", x, base_y + 95)
            return
        self._draw_line("T", last_r.temp_c, "\u00b0C", x, base_y + 45)
        self._draw_line("H", last_r.hum_percent, "%RH", x, base_y + 70)
        self._draw_line("B", (None if last_r.batt_mv is None else round(last_r.batt_mv / 1000, 2)), "V", x, base_y + 95)

    def _draw_line(self, label, value, unit, x, y):
        if value is None:
            text, color = f"{label}: n/a", RED
        elif isinstance(value, float):
            text, color = f"{label}: {value:.1f} {unit}", WHITE
        else:
            text, color = f"{label}: {value} {unit}", WHITE
        self.screen.blit(self.font_small.render(text, True, color), (x, y))
