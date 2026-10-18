"""Tests for the layout-v5 text-fitting module.

The geometry is pinned to the approved design (docs/design/
layout-v5.png); the draw tests catch regressions like the
default-colour bug where every sensor-block line rendered in the
red n/a colour.
"""
import unittest

from PIL import Image, ImageDraw

from kitchen_clock.ui import textfit


class TestGeometry(unittest.TestCase):
    def test_regions_match_layout_v5(self):
        regions = textfit.divided_regions()
        self.assertEqual(
            regions,
            {
                "left_top": (0, 0, 697, 120),
                "left_bottom": (0, 126, 697, 599),
                "right_top": (703, 0, 1023, 297),
                "right_bottom": (703, 303, 1023, 599),
            },
        )

    def test_dividers_draw_at_the_pinned_coordinates(self):
        img = Image.new("RGB", (1024, 600), textfit.BG)
        textfit.draw_dividers(ImageDraw.Draw(img))
        px = img.convert("L").point(lambda p: 255 if p > 128 else 0)
        import numpy as np
        a = np.array(px) > 0
        self.assertEqual(
            [x for x in range(1024) if a[:, x].all()],
            [698, 699, 700, 701, 702],
        )
        self.assertEqual(
            [y for y in range(121, 126) if a[y, :698].all()],
            [121, 122, 123, 124, 125],
        )
        self.assertEqual(
            [y for y in range(298, 303) if a[y, 703:].all()],
            [298, 299, 300, 301, 302],
        )


class TestBlockDrawing(unittest.TestCase):
    def _plan(self):
        font_path = textfit.resolve_font_path()
        return textfit.fit_block(
            font_path,
            ("Outside", "Temp: -12.3 °C",
             "Rel. Hum.: 100.0%", "Battery: 4.99V"),
            textfit.divided_regions()["right_top"],
        )

    def test_plain_lines_render_white_not_red(self):
        """Regression: the block default colour must be white —
        a default of NA_FG rendered every sensor line near-invisible
        dark red on black."""
        import numpy as np
        img = Image.new("RGB", (1024, 600), textfit.BG)
        textfit.draw_fitted_block(
            ImageDraw.Draw(img), self._plan(),
            ["Outside", "Temp: 34.2 °C",
             "Rel. Hum.: 23.3%", "Battery: 3.33V"],
        )
        crop = np.array(img.crop((703, 0, 1023, 297)))
        ink = crop.max(axis=2) > 100
        self.assertGreater(ink.sum(), 500, "block renders ink")
        title = crop[83:113, :, :]   # first line's rows
        title_ink = title.max(axis=2) > 100
        red_pixels = ((title[:, :, 0] > 150)
                      & (title[:, :, 1] < 100)).sum()
        self.assertGreater(title_ink.sum(), 100)
        self.assertEqual(red_pixels, 0, "title must not be red")

    def test_na_line_renders_red(self):
        import numpy as np
        img = Image.new("RGB", (1024, 600), textfit.BG)
        plan = self._plan()
        textfit.draw_fitted_block(
            ImageDraw.Draw(img), plan,
            ["Outside", "Temp: 34.2 °C",
             "Rel. Hum.: 23.3%",
             ("Battery: n/a", textfit.NA_FG)],
        )
        crop = np.array(img.crop((703, 0, 1023, 297)))
        red = (crop[:, :, 0] > 150) & (crop[:, :, 1] < 100)
        self.assertGreater(red.sum(), 50, "n/a line renders red")
        ys, _ = np.where(red)
        self.assertLess(ys.max(), 298, "stays inside the box")


if __name__ == "__main__":
    unittest.main()
