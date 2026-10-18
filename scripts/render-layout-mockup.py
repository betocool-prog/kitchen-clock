#!/usr/bin/env python3
#
# scripts/render-layout-mockup.py
#
# Layout-scaffold generator for the 1024x600 panel (ADR 0001 /
# display design loop). Renders the division skeleton plus the
# agreed elements so far to a PNG, host-side, before any fbdev /
# panel work.
#
# Conventions (agreed 2026-10-18):
#   - origin top-left, landscape, 1024 x 600
#   - fractions are rounded to whole pixels; 5-px lines are centred
#     on the division coordinate
#   - horizontals extend into the vertical divider (clean T-junctions)
#   - text: white on black, DejaVu Sans Bold — the Pi font loader's
#     first candidate (firmware/main-unit/kitchen_clock/ui/
#     fbdev_window.py), so host mockups render with the exact font
#     file the panel will use
#   - "occupy X% of the height" = the rendered INK height of the
#     string (visible pixels), not the em size; sizes are found by
#     search, then the ink is centred vertically in its box
#
# Usage:
#   python scripts/render-layout-mockup.py                 # docs/design/layout-v5.png
#   python scripts/render-layout-mockup.py -o /tmp/v2.png
#
# The printed region/ink table is the "blind" audit: the geometry is
# read numerically, not visually.

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 1024, 600
LINE_W = 5
FG = (255, 255, 255)
BG = (0, 0, 0)

# Division fractions (v1):
V_SPLIT = 136 / 199        # vertical: x = WIDTH * V_SPLIT (~700)
LEFT_SPLIT = 24 / 117      # left box:  y = HEIGHT * LEFT_SPLIT (~123)
RIGHT_SPLIT = 1 / 2         # right box: y = HEIGHT * RIGHT_SPLIT (300)

# Date element (v2 → v3) — top-left box, left-aligned, white on black.
# v2 tried 90 % ink height and overran the box width; option A (agreed
# 2026-10-18): the size is driven by the width fit — ink capped at
# box width minus balanced margins — and the resulting height is
# whatever the typeface gives.
DATE_TEXT = "Sun, 18 Oct 2026"
DATE_LEFT_MARGIN = 24
DATE_RIGHT_MARGIN = 24

# Time element (v4) — left-bottom box, same conventions as the date:
# width-driven fit, left-aligned at the same margin, vertically
# centred on ink.
TIME_TEXT = "10:32 PM"
TIME_LEFT_MARGIN = 24
TIME_RIGHT_MARGIN = 24

# Sensor blocks (v5) — right-column boxes. Four lines each
# ("\\n" boundaries per the agreed spec), left-aligned; the degree
# symbol stands in for the user's "deg". Uniform type size: the
# font is sized so the WIDEST line fits the width cap, then all
# lines share that size on a leading grid; the whole block is
# vertically centred in its box.
SENSOR_LINES_OUTSIDE = (
    "Outside",
    "Temp: 34.2 °C",
    "Rel. Hum.: 23.3%",
    "Battery: 3.33V",
)
SENSOR_LINES_INSIDE = (
    "Inside",
    "Temp: 34.2 °C",
    "Rel. Hum.: 23.3%",
    "Battery: 3.33V",
)
SENSOR_LEFT_MARGIN = 24
SENSOR_RIGHT_MARGIN = 24
BLOCK_LEADING = 1.35   # baseline step, in em

# Pi font-loader candidate order (fbdev_window.load_fonts): the
# first existing file wins on the Pi, so it must here too.
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
        if Path(p).exists():
            return p
    raise SystemExit("no Pi font candidate found on this host")


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
        raise SystemExit(f"text paints no ink: {text!r}")
    dx0, dy0, dx1, dy1 = box
    return dx0 - 100, dy0 - 100, dx1 - 100, dy1 - 100


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
            best = (mid, w)
            lo = mid + 1
        else:
            hi = mid - 1
    if best is None:
        raise SystemExit(f"cannot fit ink width {target_w}")
    return best


def fit_text(d, font_path, text, box, *, left_margin, right_margin):
    """Draw `text` width-fitted inside `box`; return an audit dict.

    Conventions shared with the date element: the font size is the
    largest whose ink width fits (box width − margins), the text is
    left-aligned at `left_margin`, and the ink is centred vertically
    in the box.
    """
    box_w = box[2] - box[0] + 1
    box_h = box[3] - box[1] + 1
    max_w = box_w - left_margin - right_margin
    size, ink_w = find_size_for_ink_width(font_path, text, max_w)
    font = ImageFont.truetype(font_path, size)
    dx0, dy0, dx1, dy1 = ink_offsets(font, text)
    ink_h = dy1 - dy0
    cy = (box[1] + box[3]) / 2
    draw_y = round(cy - (dy0 + dy1) / 2)
    d.text((box[0] + left_margin, draw_y), text, fill=FG, font=font)
    x0 = box[0] + left_margin + dx0
    return {
        "font": font_path,
        "size_pt": size,
        "ink": (x0, draw_y + dy0, x0 + ink_w, draw_y + dy1),
        "ink_w": ink_w, "ink_h": ink_h,
        "box_w": box_w, "box_h": box_h,
        "max_w": max_w,
        "overflow_right_px": max(0, x0 + ink_w - 1 - box[2]),
        "left_margin": left_margin,
        "right_margin": right_margin,
    }


def fit_text_block(d, font_path, lines, box, *,
                   left_margin, right_margin, leading=BLOCK_LEADING):
    """Draw a left-aligned, width-fitted block of lines in `box`.

    The font size is the largest whose WIDEST line fits the width
    cap; every line shares that size, stacked on a `leading`-em
    baseline grid. The whole block's ink is centred vertically.
    Returns an audit dict with per-line ink widths.
    """
    box_w = box[2] - box[0] + 1
    box_h = box[3] - box[1] + 1
    max_w = box_w - left_margin - right_margin

    def widest_ink(size):
        font = ImageFont.truetype(font_path, size)
        return max(ink_offsets(font, ln)[2] - ink_offsets(font, ln)[0]
                   for ln in lines)

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
        raise SystemExit(f"cannot fit ink width {max_w} for {lines!r}")
    size = best

    font = ImageFont.truetype(font_path, size)
    step = round(size * leading)
    offs = [ink_offsets(font, ln) for ln in lines]
    widths = [o[2] - o[0] for o in offs]
    # Baseline grid: draw origins spaced by `step`; first line's
    # origin at 0. Simulate to find the block's ink extents.
    tops = [i * step + o[1] for i, o in enumerate(offs)]
    bottoms = [i * step + o[3] for i, o in enumerate(offs)]
    block_top, block_bottom = min(tops), max(bottoms)
    cy = (box[1] + box[3]) / 2
    base = round(cy - (block_top + block_bottom) / 2)
    for i, ln in enumerate(lines):
        d.text((box[0] + left_margin, base + i * step), ln,
               fill=FG, font=font)
    x0 = box[0] + left_margin
    return {
        "font": font_path,
        "size_pt": size,
        "step": step,
        "lines": list(lines),
        "line_ink_w": widths,
        "ink": (x0, base + block_top,
                x0 + max(widths), base + block_bottom),
        "ink_h": block_bottom - block_top,
        "box_w": box_w, "box_h": box_h,
        "max_w": max_w,
        "overflow_right_px": max(
            0, box[0] + left_margin + max(widths) - 1 - box[2]),
        "left_margin": left_margin,
        "right_margin": right_margin,
    }


def build(v_split=V_SPLIT, left_split=LEFT_SPLIT, right_split=RIGHT_SPLIT):
    """Return (image, regions, audit) for the scaffold + date."""
    img = Image.new("RGB", (WIDTH, HEIGHT), BG)
    d = ImageDraw.Draw(img)

    x_v = round(WIDTH * v_split)        # ~700
    y_left = round(HEIGHT * left_split)  # ~123
    y_right = round(HEIGHT * right_split)  # 300
    half = LINE_W // 2

    def vline(x):
        d.rectangle([x - half, 0, x + half, HEIGHT - 1], fill=FG)

    def hline(y, x0, x1):
        d.rectangle([x0, y - half, x1, y + half], fill=FG)

    vline(x_v)
    hline(y_left, 0, x_v + half)
    hline(y_right, x_v - half, WIDTH - 1)

    regions = {
        "left_top": (0, 0, x_v - half - 1, y_left - half - 1),
        "left_bottom": (0, y_left + half + 1, x_v - half - 1, HEIGHT - 1),
        "right_top": (x_v + half + 1, 0, WIDTH - 1, y_right - half - 1),
        "right_bottom": (x_v + half + 1, y_right + half + 1, WIDTH - 1,
                         HEIGHT - 1),
    }

    audit = {}
    font_path = resolve_font_path()
    audit["date"] = fit_text(
        d, font_path, DATE_TEXT, regions["left_top"],
        left_margin=DATE_LEFT_MARGIN, right_margin=DATE_RIGHT_MARGIN,
    )
    audit["date"]["box_name"] = "left_top"
    audit["time"] = fit_text(
        d, font_path, TIME_TEXT, regions["left_bottom"],
        left_margin=TIME_LEFT_MARGIN, right_margin=TIME_RIGHT_MARGIN,
    )
    audit["time"]["box_name"] = "left_bottom"
    audit["outside"] = fit_text_block(
        d, font_path, SENSOR_LINES_OUTSIDE, regions["right_top"],
        left_margin=SENSOR_LEFT_MARGIN, right_margin=SENSOR_RIGHT_MARGIN,
    )
    audit["outside"]["box_name"] = "right_top"
    audit["inside"] = fit_text_block(
        d, font_path, SENSOR_LINES_INSIDE, regions["right_bottom"],
        left_margin=SENSOR_LEFT_MARGIN, right_margin=SENSOR_RIGHT_MARGIN,
    )
    audit["inside"]["box_name"] = "right_bottom"
    return img, regions, audit


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("-o", "--out", default=None,
                    help="output PNG path (default docs/design/layout-v5.png)")
    args = ap.parse_args()

    img, regions, audit = build()
    out = Path(args.out) if args.out else (
        Path(__file__).resolve().parent.parent / "docs" / "design"
        / "layout-v5.png"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)

    print(f"wrote {out} ({WIDTH}x{HEIGHT})")
    print(f"vertical divider:   x={round(WIDTH * V_SPLIT)} "
          f"({V_SPLIT:.4f} of {WIDTH} = {WIDTH * V_SPLIT:.2f})")
    print(f"left-box split:     y={round(HEIGHT * LEFT_SPLIT)} "
          f"({LEFT_SPLIT:.4f} of {HEIGHT} = {HEIGHT * LEFT_SPLIT:.2f})")
    print(f"right-box split:    y={round(HEIGHT * RIGHT_SPLIT)}")
    for name, (x0, y0, x1, y1) in regions.items():
        print(f"  {name:13s} box=({x0:4d},{y0:3d})-({x1:4d},{y1:3d}) "
              f"size={x1 - x0 + 1}x{y1 - y0 + 1}")
    elements = (
        ("date", DATE_TEXT),
        ("time", TIME_TEXT),
        ("outside", None),
        ("inside", None),
    )
    for key, label in elements:
        a = audit[key]
        x0, y0, x1, y1 = a["ink"]
        print(f"{key}: text={label if label else a.get('lines')}")
        print(f"{key}: font={a['font']} @ {a['size_pt']} pt"
              + (f", leading step {a['step']} px" if "step" in a else ""))
        print(f"{key}: ink=({x0},{y0})-({x1},{y1}) "
              f"size={x1 - x0}x{a['ink_h']} "
              f"(width cap {a['max_w']} = box {a['box_w']} − "
              f"{a['left_margin']} − {a['right_margin']})")
        if "line_ink_w" in a:
            print(f"{key}: line ink widths={a['line_ink_w']}")
        print(f"{key}: ink height = {a['ink_h'] / a['box_h']:.0%} of "
              f"{a['box_name']} box height ({a['box_h']} px)")
        rb = regions[a["box_name"]]
        print(f"{key}: left margin={x0 - rb[0]} top margin={y0 - rb[1]} "
              f"bottom margin={rb[3] - y1} right margin="
              f"{rb[2] - x1}")
        if a["overflow_right_px"]:
            print(f"{key}: WARNING ink overflows right box edge by "
                  f"{a['overflow_right_px']} px (box interior width "
                  f"{a['box_w']})")


if __name__ == "__main__":
    main()
