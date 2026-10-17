"""Direct-framebuffer renderer for the Pi runtime.

The Pi Zero W on Trixie runs SDL 2.32 (the piwheels cp313 wheel)
without any working video driver:

  * `kmsdrm` ships but Pi Zero W has no GPU; GLES can't initialise.
  * `fbcon` is NOT compiled into SDL 2.32 for armv6 multi-arch builds.
  * `x11`/`directfb` need an X server or DirectFB respectively —
    not realistic for a kiosk clock.

This module renders directly to `/dev/fb0` via mmap and `PIL`,
bypassing SDL entirely. The framebuffer is what the HDMI panel
displays verbatim — exactly the same surface the kernel boot
splash uses.

API mirrors `PygameRunner` so `BaseRunner` keeps a single code
path. The two runners are interchangeable at the call site.
"""
import asyncio
import mmap
import os
import time as _time
from pathlib import Path

try:
    import numpy as np
    _NUMPY_AVAILABLE = True
except ImportError:                          # noqa: F401
    np = None                                # type: ignore
    _NUMPY_AVAILABLE = False


def _monotonic() -> float:
    return _time.monotonic()

# PIL is only required at instantiation time, not at module import,
# so the module itself stays importable on hosts without Pillow.
try:
    from PIL import Image, ImageDraw, ImageFont  # type: ignore
except ImportError:                              # noqa: F401
    Image = ImageDraw = ImageFont = None

from ..runner import BaseRunner
from ..ble.bleak_client import SensorReading


FB_PATH = "/dev/fb0"
SYSFB = "/sys/class/graphics/fb0"


def _read_sysfs(name):
    with open(f"{SYSFB}/{name}") as f:
        return f.read().strip()


def discover_fb0():
    """Return (width, height, bpp, pitch) for the first framebuffer."""
    parts = _read_sysfs("virtual_size").split(",")
    x = int(parts[0])
    y = int(parts[1])
    bpp = int(_read_sysfs("bits_per_pixel"))
    try:
        pitch = int(_read_sysfs("stride"))
    except FileNotFoundError:
        pitch = x * (bpp // 8)
    return x, y, bpp, pitch


def load_fonts():
    """Return (font_big, font_small) — both PIL ImageFont instances.

    Sizes have been tuned to fit the EastRising 9" panel (1024x600)
    with two vertically-stacked sensor tiles. See the layout in
    `_draw` for the relationship between font sizes and row offsets.
    """
    candidates = (
        # Debian pack names (DejaVu/Liberation standard Trixie paths)
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        # Fedora-ish paths and Pi-camera-stack fallbacks
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
        "/usr/share/fonts/TTF/LiberationSans-Bold.ttf",
    )
    for path in candidates:
        if not Path(path).exists():
            continue
        try:
            return (
                ImageFont.truetype(path, 48),
                ImageFont.truetype(path, 28),
            )
        except Exception:
            continue
    fallback = ImageFont.load_default()
    print(
        "[FbdevRunner] WARNING: no TrueType fonts found; falling back "
        "to PIL default. apt-get install fonts-dejavu-core for "
        "readable text.",
        file=__import__("sys").stderr,
    )
    return fallback, fallback


def load_clock_font(size: int = 96):
    """Sized for the wall-clock face (HH:MM:SS).

    Bigger than `font_big` so the seconds-changed-in-real-time
    is readable from across the kitchen. We re-resolve the path
    instead of caching because PIL's `truetype` doesn't expose
    a cheap sizing API in the version bundled on Trixie.
    """
    candidates = (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/TTF/LiberationSans-Bold.ttf",
    )
    for path in candidates:
        if not Path(path).exists():
            continue
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def rgb_to_framebuffer(rgb_bytes: bytes, bpp: int,
                       width: int, height: int) -> bytes:
    """Pack Python RGB bytes into the framebuffer's pixel format.

    Supports:

      * 32 bpp (BGRX X-mask little-endian) — Pi Trixie KMS default.
      * 16 bpp RGB 565                     — older Pi config.

    Anything else is best-effort binary copy.

    Performance notes: the per-frame wall-time on a Pi Zero W is
    dominated by the per-pixel Python loop in the 16-bit path
    (~14 s on a 1024×600 panel). When numpy is available we
    vectorise: bit-shift the RGB trio into a `uint16` array and
    repack as little-endian bytes. That step runs at C speed —
    ~50 ms on the same panel.

    Byte order on the wire: the kernel fb writes B at byte 0, G at
    byte 1, R at byte 2, X (alpha/ignored) at byte 3 on little-endian.
    Override by exporting `KITCHEN_CLOCK_FB_BYTE_ORDER=RGBX` if a
    future driver rearranges this.
    """
    if _NUMPY_AVAILABLE and bpp in (16, 32):
        return _rgb_to_framebuffer_numpy(rgb_bytes, bpp, width, height)
    return _rgb_to_framebuffer_pure(rgb_bytes, bpp, width, height)


def _rgb_to_framebuffer_numpy(rgb_bytes: bytes, bpp: int,
                             width: int, height: int) -> bytes:
    """Vectorised RGB→framebuffer packing via numpy."""
    rgb = np.frombuffer(rgb_bytes, dtype=np.uint8).reshape(height, width, 3)
    if bpp == 16:
        # Promote channels to uint16 for roomy bit shifts.
        r = rgb[:, :, 0].astype(np.uint16)
        g = rgb[:, :, 1].astype(np.uint16)
        b = rgb[:, :, 2].astype(np.uint16)
        # RGB565: bits 15..11 = R, 10..5 = G, 4..0 = B, all little-endian.
        packed = ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)
        # `<u2` enforces little-endian regardless of host endianness.
        return packed.astype("<u2").tobytes()
    # 32-bit path.
    order = os.environ.get("KITCHEN_CLOCK_FB_BYTE_ORDER", "BGRX").upper()
    out = np.empty((height, width, 4), dtype=np.uint8)
    if order == "RGBX":
        out[:, :, :3] = rgb
    else:                       # BGRX (default)
        out[:, :, 0] = rgb[:, :, 2]
        out[:, :, 1] = rgb[:, :, 1]
        out[:, :, 2] = rgb[:, :, 0]
    out[:, :, 3] = 0           # X (alpha/ignored)
    return out.tobytes()


def _rgb_to_framebuffer_pure(rgb_bytes: bytes, bpp: int,
                            width: int, height: int) -> bytes:
    """Pure-Python RGB→framebuffer packing (slow on Pi Zero W)."""
    order = os.environ.get("KITCHEN_CLOCK_FB_BYTE_ORDER", "BGRX").upper()
    n = width * height
    rgb_view = memoryview(rgb_bytes)
    if bpp == 32:
        out = bytearray(n * 4)
        out_view = memoryview(out)
        is_rgbx = order == "RGBX"
        for i in range(n):
            src = i * 3
            dst = i * 4
            r = rgb_view[src + 0]
            g = rgb_view[src + 1]
            b = rgb_view[src + 2]
            if is_rgbx:
                out_view[dst + 0] = r
                out_view[dst + 1] = g
                out_view[dst + 2] = b
            else:
                out_view[dst + 0] = b
                out_view[dst + 1] = g
                out_view[dst + 2] = r
            out_view[dst + 3] = 0
        return bytes(out)
    if bpp == 16:
        out = bytearray(n * 2)
        out_view = memoryview(out)
        for i in range(n):
            r = rgb_view[3 * i]
            g = rgb_view[3 * i + 1]
            b = rgb_view[3 * i + 2]
            v = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
            out_view[2 * i] = v & 0xFF
            out_view[2 * i + 1] = (v >> 8) & 0xFF
        return bytes(out)
    return rgb_bytes[: n * (bpp // 8)]


class FbdevRunner(BaseRunner):
    """Path A's fbdev renderer on the Pi runtime."""

    def __init__(self, *, make_client, sensors, period_s: float = 2.0,
                 time_formatter=None):
        if Image is None:
            raise RuntimeError(
                "Pillow (python3-pil) is required for FbdevRunner; "
                "install with: sudo apt-get install python3-pil"
            )
        super().__init__(
            make_client=make_client, sensors=sensors, period_s=period_s
        )

        self.width, self.height, self.bpp, self.pitch = discover_fb0()
        print(
            f"[FbdevRunner] fb0: {self.width}x{self.height} "
            f"@ {self.bpp}bpp, stride={self.pitch}",
            file=__import__("sys").stderr,
        )
        self.fd = os.open(FB_PATH, os.O_RDWR)
        size = self.pitch * self.height
        self.mm = mmap.mmap(
            self.fd, size, mmap.MAP_SHARED,
            mmap.PROT_WRITE | mmap.PROT_READ,
        )
        self.img = Image.new("RGB", (self.width, self.height), (0, 0, 0))
        self.draw = ImageDraw.Draw(self.img)
        self.font_big, self.font_small = load_fonts()
        self.time_formatter = time_formatter
        # Clock face uses larger digits than the body font. Sized so
        # 'HH:MM:SS' fits the 1024 px panel with margin; must coexist
        # with the date row directly below.
        self.font_clock = self._load_clock_font()

    async def run(self):
        import sys
        # flush=True on every runtime print: when this runner runs in
        # the background of an SSH session (`&`), the parent shell
        # may exit before the runner's stdio is flushed and we'd lose
        # the timing trace we need for first-tick diagnostics.
        print("[FbdevRunner] run() entered", file=sys.stderr, flush=True)
        try:
            # Scanner transport (ADR 0012): discovery runs beside the
            # render loop; a failed start is journalled, not fatal.
            await self._start_ble()
            tick_n = 0
            while True:
                t_loops = _monotonic()
                print(
                    f"[FbdevRunner] tick #{tick_n + 1} starting",
                    file=sys.stderr, flush=True,
                )
                await self._tick()
                t_ticked = _monotonic()
                tick_n += 1
                print(
                    f"[FbdevRunner] tick #{tick_n} drew in "
                    f"{t_ticked - t_loops:.3f}s",
                    file=sys.stderr,
                    flush=True,
                )
                await asyncio.sleep(self.period_s)
        finally:
            try:
                self.mm.close()
            finally:
                os.close(self.fd)

    def _load_clock_font(self):
        return load_clock_font(96)

    def _draw(self):
        import sys
        print("[FbdevRunner] _draw entered", file=sys.stderr, flush=True)
        t0 = _monotonic()
        self.draw.rectangle(
            (0, 0, self.width, self.height), fill=(0, 0, 0),
        )
        # Top: BIG AWST clock + date row.
        # Bottom: vertically stacked sensor tiles.
        #
        # Layout maths (EastRising 9" panel, 1024x600):
        #   font_big bbox ~74 px  (size 48 + ascent + descent + leading)
        #   font_small bbox ~52 px (size 28 + ascent + descent + leading)
        #   font_clock at size 96 has bbox ~150 px.
        #   clock+date strip = 8 (top margin) + ~150 (clock) + ~6 (gap)
        #     + ~52 (date) + 8 (gap) = 224 px.
        #   remaining 600-224 = 376 px for two tiles + a small gap.
        clock_top_y = 8
        date_y = 162                    # immediately below the clock
        clock_face_x = self.width // 2  # we'll right-justify by bbox
        if self.time_formatter is not None:
            self._draw_clock(clock_top_y, clock_face_x)
        else:
            # Static placeholder when the time formatter isn't
            # wired up — preserves the project's "kitchen-clock —
            # library" tagline from before the AWST work.
            self.draw.text(
                (20, 8), "kitchen-clock — library",
                fill=(255, 255, 255), font=self.font_big,
            )
        tiles_y = 224
        tile_h = 180                    # 224 + 180 + 8 + 180 = 592, leaves 8 bottom margin
        # Render a tile per registered sensor, even when no live
        # reading has landed yet. Without this the panel shows
        # only the clock on a cold start and any BLE outage.
        for i, sensor in enumerate(self.sensors):
            last_r = self.last_readings[i] if i < len(self.last_readings) else None
            cur_r = self.current_readings[i] if i < len(self.current_readings) else None
            self._draw_tile(
                sensor, i, last_r, cur_r, base_y=tiles_y + i * tile_h,
            )
        t_paint = _monotonic()

        rgb = self.img.tobytes()
        t_tobytes = _monotonic()
        packed = rgb_to_framebuffer(rgb, self.bpp, self.width, self.height)
        t_pack = _monotonic()
        # Single memmove-style write.
        self.mm[: len(packed)] = packed
        t_blit = _monotonic()

        print(
            f"[FbdevRunner] _draw breakdown tick: "
            f"paint={(t_paint - t0):.3f}s "
            f"tobytes={(t_tobytes - t_paint):.3f}s "
            f"packRGB565={(t_pack - t_tobytes):.3f}s "
            f"blit={(t_blit - t_pack):.3f}s "
            f"total={(t_blit - t0):.3f}s",
            file=sys.stderr,
            flush=True,
        )

    def _draw_one(self, r: SensorReading, idx: int,
                  *, base_y: int = 0) -> None:
        raise NotImplementedError(
            "_draw_one is now folded into _draw_tile; the panel"
        )

    def _draw_tile(self, sensor, idx, last_r, cur_r, *, base_y=0) -> None:
        """One tile per sensor slot. Always renders, even on cold start.

        \`last_r\` is the last-known-good reading (cached). When it
        is None we still paint the tile using \`cur_r\`'s source
        string so the failure is visible on-screen — a black tile
        in the BLE-down case is harder to triage than one with the
        connect-fail line.
        """
        mac, name, loc = sensor
        x = 20
        src = "live" if last_r is not None else (
            cur_r.source if cur_r is not None else "no-data"
        )
        head = f"{loc or '(unnamed)'} \u2014 {name or mac}  [{src}]"
        self.draw.text(
            (x, base_y), head,
            fill=(255, 255, 255), font=self.font_big,
        )
        if last_r is None:
            # No live ever. Show three n/a rows in the failure
            # colour so the tile reads "the data is not flowing".
            self._draw_line("T", None, "\u00b0C",   x, base_y + 70)
            self._draw_line("H", None, "%RH", x, base_y + 96)
            self._draw_line("B", None, "ADC", x, base_y + 122)
            return
        self._draw_line("T", last_r.temp_c, "\u00b0C",   x, base_y + 70)
        self._draw_line("H", last_r.hum_percent, "%RH", x, base_y + 96)
        self._draw_line("B", last_r.batt_raw, "ADC", x, base_y + 122)

    def _draw_clock(self, top_y: int, center_x: int) -> None:
        """Render the wall-clock face and date row.

        Centred horizontally so the seconds change always visible
        in the kitchen doesn't compete with the tiles for the
        left edge.
        """
        clock_text = self.time_formatter.clock()
        date_text = self.time_formatter.date()
        # PIL's `textbbox` lets us measure the glyph extents so we
        # can right-justify around `center_x` without estimating
        # Arial-vs-DejaVuSans widths.
        cx_t, cy_t, cw_t, ch_t = self.draw.textbbox(
            (0, 0), clock_text, font=self.font_clock,
        )
        self.draw.text(
            (center_x - cw_t // 2, top_y),
            clock_text,
            fill=(255, 255, 255),
            font=self.font_clock,
        )
        # Date row directly below the clock, centred to the same
        # horizontal axis.
        cx_d, cy_d, cw_d, ch_d = self.draw.textbbox(
            (0, 0), date_text, font=self.font_big,
        )
        # We are already past the clock bbox — `cy_d` is the
        # ascender; align with our planned date_y rather than
        # letting the bbox play it loose.
        self.draw.text(
            (center_x - cw_d // 2, top_y + 154),
            date_text,
            fill=(180, 180, 180),
            font=self.font_big,
        )

    def _draw_line(self, label, value, unit, x, y):
        if value is None:
            text, color = f"{label}: n/a", (220, 60, 60)
        elif isinstance(value, float):
            text, color = f"{label}: {value:.1f} {unit}", (255, 255, 255)
        else:
            text, color = f"{label}: {value} {unit}", (255, 255, 255)
        self.draw.text((x, y), text, fill=color, font=self.font_small)
