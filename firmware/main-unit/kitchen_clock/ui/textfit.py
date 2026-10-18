"""Text fitting for the panel renderers (layout v5).

Port of the design-loop logic in `scripts/render-layout-mockup.py`
(`docs/design/layout-v5.png` is the approved reference). Conventions:

  - origin top-left, landscape, 1024 x 600
  - 5-px white divider lines centred on the division coordinates:
      vertical x=700 (136/199 of the width),
      left-box  y=123 (24/117 of the height),
      right-box y=300 (1/2)
  - text: white on black, DejaVu Sans Bold — the font-loader
    candidate order shared with the Pi runtime
  - font sizes are chosen ONCE from worst-case representative
    strings (digits in DejaVu are NOT tabular), so sizes never jump
    day to day; every element is left-aligned at a 24 px margin and
    vertically centred on its ink
  - "ink" means visible pixels (Image.getbbox on a scratch render),
    not font metrics — descenders count only where glyphs paint

Per-string vertical centring needs one ink measurement per unique
string; `InkCache` memoises those so the render loop only pays the
measurement when a string first appears (once a minute for the
clock, once a day for the date).
"""

import os

from PIL import Image, ImageDraw, ImageFont

# --- panel geometry (layout v5) -------------------------------------------

WIDTH, HEIGHT = 1024, 600
V_SPLIT = 136 / 199         # vertical divider: x ~ 700
LEFT_SPLIT = 24 / 117       # left box split:   y ~ 123
RIGHT_SPLIT = 1 / 2          # right box split:  y = 300
LINE_W = 5

FG = (255, 255, 255)
BG = (0, 0, 0)
NA_FG = (220, 60, 60)        # n/a lines render red

MARGIN = 24                  # left/right text margin in every box
BLOCK_LEADING = 1.35         # sensor-block baseline step, in em


def divided_regions():
    """Interior boxes (excluding the 5-px lines) for layout v5."""
    x_v = round(WIDTH * V_SPLIT)
    y_l = round(HEIGHT * LEFT_SPLIT)
    y_r = round(HEIGHT * RIGHT_SPLIT)
    half = LINE_W // 2
    return {
        "left_top": (0, 0, x_v - half - 1, y_l - half - 1),
        "left_bottom": (0, y_l + half + 1, x_v - half - 1, HEIGHT - 1),
        "right_top": (x_v + half + 1, 0, WIDTH - 1, y_r - half - 1),
        "right_bottom": (x_v + half + 1, y_r + half + 1, WIDTH - 1,
                         HEIGHT - 1),
    }


def draw_dividers(d):
    """The three 5-px white division lines (part of the design)."""
    x_v = round(WIDTH * V_SPLIT)
    y_l = round(HEIGHT * LEFT_SPLIT)
    y_r = round(HEIGHT * RIGHT_SPLIT)
    half = LINE_W // 2
    d.rectangle([x_v - half, 0, x_v + half, HEIGHT - 1], fill=FG)
    d.rectangle([0, y_l - half, x_v + half, y_l + half], fill=FG)
    d.rectangle([x_v - half, y_r - half, WIDTH - 1, y_r + half], fill=FG)


# --- fonts ----------------------------------------------------------------

# Pi font-loader candidate order (fbdev_window): the first existing
# file wins on the Pi, so it must here too.
FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/TTF/DejaVuSans.ttf",
    "/usr/share/fonts/TTF/LiberationSans-Bold.ttf",
)


def resolve_font_path():
    for p in FONT_CANDIDATES:
        if os.path.exists(p):
            return p
    raise SystemExit("no Pi font candidate found on this host")


# --- ink measurement ------------------------------------------------------

def ink_offsets(font, text):
    """Ink bbox of `text` drawn with `font` at origin (0, 0).

    Returns (dx0, dy0, dx1, dy1): the visible-pixel box relative to
    the draw position. `Image.getbbox` measures ink, not metrics, so
    descenders/ascenders count only where glyphs actually paint.
    """
    scratch = Image.new("L", (4000, 600), 0)
    d = ImageDraw.Draw(scratch)
    d.text((100, 100), text, fill=255, font=font)
    box = scratch.getbbox()
    if box is None:
        raise ValueError(f"text paints no ink: {text!r}")
    dx0, dy0, dx1, dy1 = box
    return dx0 - 100, dy0 - 100, dx1 - 100, dy1 - 100


class InkCache:
    """Memoise per-string ink offsets, per font size.

    Entries are tiny and strings repeat heavily (the clock changes
    once a minute, the date once a day); the cache is capped and
    simply clears when full — worst case a few re-measurements.
    """

    def __init__(self, cap=4096):
        self._cap = cap
        self._cache = {}

    def offsets(self, font, text):
        key = (font.path, font.size, text)
        try:
            return self._cache[key]
        except KeyError:
            pass
        offs = ink_offsets(font, text)
        if len(self._cache) >= self._cap:
            self._cache.clear()
        self._cache[key] = offs
        return offs


# --- sizing ---------------------------------------------------------------

def find_size_for_ink_width(font_path, text, target_w):
    """Largest font size whose ink width is <= target (px)."""
    lo, hi = 8, 400
    best = None
    while lo <= hi:
        mid = (lo + hi) // 2
        font = ImageFont.truetype(font_path, mid)
        dx0, dx1 = (lambda o: (o[0], o[2]))(ink_offsets(font, text))
        w = dx1 - dx0
        if w <= target_w:
            best = mid
            lo = mid + 1
        else:
            hi = mid - 1
    if best is None:
        raise ValueError(f"cannot fit ink width {target_w} for {text!r}")
    return best


def fit_single(font_path, fit_text, box):
    """Plan a single-line element: fixed font + draw conventions.

    The font is sized ONCE from `fit_text` (a worst-case
    representative string) so the size never changes; each actual
    string is left-aligned at MARGIN and centred vertically on its
    own ink at draw time (one cached measurement per unique string).
    """
    box_w = box[2] - box[0] + 1
    max_w = box_w - 2 * MARGIN
    size = find_size_for_ink_width(font_path, fit_text, max_w)
    return {
        "font_path": font_path,
        "size": size,
        "font": ImageFont.truetype(font_path, size),
        "box": box,
        "max_w": max_w,
    }


def draw_fitted(d, plan, text, ink_cache, fg=FG):
    """Draw one planned single-line element with `text`."""
    offs = ink_cache.offsets(plan["font"], text)
    box = plan["box"]
    cy = (box[1] + box[3]) / 2
    draw_y = round(cy - (offs[1] + offs[3]) / 2)
    d.text((box[0] + MARGIN, draw_y), text, fill=fg, font=plan["font"])


def fit_block(font_path, fit_lines, box):
    """Plan a multi-line block: uniform font + baseline grid.

    The font is sized ONCE so the WIDEST of `fit_lines` (worst-case
    representative strings) fits the width cap; all lines share that
    size on a BLOCK_LEADING-em baseline grid, and the block is
    centred vertically using the fit strings' ink. Actual strings
    are drawn left-aligned at MARGIN on the same fixed grid.
    """
    box_w = box[2] - box[0] + 1
    max_w = box_w - 2 * MARGIN

    def widest_ink(size):
        font = ImageFont.truetype(font_path, size)
        return max(ink_offsets(font, ln)[2] - ink_offsets(font, ln)[0]
                   for ln in fit_lines)

    lo, hi = 8, 400
    best = None
    while lo <= hi:
        mid = (lo + hi) // 2
        if widest_ink(mid) <= max_w:
            best = mid
            lo = mid + 1
        else:
            hi = mid - 1
    if best is None:
        raise ValueError(f"cannot fit ink width {max_w} for {fit_lines!r}")
    size = best

    font = ImageFont.truetype(font_path, size)
    step = round(size * BLOCK_LEADING)
    offs = [ink_offsets(font, ln) for ln in fit_lines]
    tops = [i * step + o[1] for i, o in enumerate(offs)]
    bottoms = [i * step + o[3] for i, o in enumerate(offs)]
    block_top, block_bottom = min(tops), max(bottoms)
    cy = (box[1] + box[3]) / 2
    base = round(cy - (block_top + block_bottom) / 2)
    return {
        "font_path": font_path,
        "size": size,
        "font": font,
        "step": step,
        "base": base,                # absolute draw y for line 0
        "box": box,
        "max_w": max_w,
        "n_lines": len(fit_lines),
    }


def draw_fitted_block(d, plan, lines, fg=FG):
    """Draw a planned block's actual lines on the fixed grid.

    `lines` may mix colours: pass a list of (text, colour) pairs or
    plain strings (default white then applies; n/a lines pass the
    red NA_FG explicitly).
    """
    box = plan["box"]
    for i, item in enumerate(lines):
        text, colour = (item, fg) if isinstance(item, str) else item
        d.text((box[0] + MARGIN, plan["base"] + i * plan["step"]), text,
               fill=colour, font=plan["font"])
