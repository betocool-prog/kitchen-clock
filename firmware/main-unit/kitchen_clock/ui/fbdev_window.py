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

Layout (v5, docs/design/layout-v5.png — designed blind via
`scripts/render-layout-mockup.py`, numerically audited):

  - three 5-px white divider lines: x=700 (vertical, full height),
    y=123 across the left box, y=300 across the right box
  - top-left box: the date, "Sun, 18 Oct 2026", width-fitted
  - bottom-left box: the time, "10:32 PM", width-fitted
  - top-right box: the Outside sensor block — 4 lines
    ("Outside" / "Temp: 34.2 °C" / "Rel. Hum.: 23.3%" /
    "Battery: 3.33V"), uniform font sized to the widest worst-case
    line, 1.35-em baseline grid, block centred
  - bottom-right box: the Inside block, same treatment

Font sizes are constants (computed once at init from worst-case
representative strings, since DejaVu digits are not tabular), so
nothing jumps size day to day. Missing values render as red "n/a"
lines; a tile that has never seen data still renders its title and
three n/a lines.

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
from . import textfit


FB_PATH = "/dev/fb0"
SYSFB = "/sys/class/graphics/fb0"

# Per-tick journal chatter (tick started / draw entered / drew in)
# is gated behind this env var; the slow-tick breakdown (>0.5 s)
# always prints — it's a regression signal, not chatter.
DEBUG_DRAW_ENV = "KITCHEN_CLOCK_DEBUG_DRAW"


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
    """Path A's fbdev renderer on the Pi runtime — layout v5."""

    # Worst-case representative fit strings (measured on DejaVu
    # Bold: "Wed"/"May" are the widest name abbreviations, '4'/'0'
    # the widest digits, "Rel. Hum.: 100.0%" the widest sensor
    # line — see textfit.py and the design loop in
    # docs/design/ for how these were derived).
    DATE_FIT_WORST = "Wed, 44 May 2026"
    TIME_FIT_WORST = "44:44 PM"
    SENSOR_FIT_LINES = (
        "Outside",
        "Temp: -12.3 °C",
        "Rel. Hum.: 100.0%",
        "Battery: 4.99V",
    )

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
        self.img = Image.new("RGB", (self.width, self.height),
                             textfit.BG)
        self.draw = ImageDraw.Draw(self.img)
        self.time_formatter = time_formatter

        # Layout v5: plans hold fixed font sizes and positions so
        # the per-frame draw is pure text placement.
        font_path = textfit.resolve_font_path()
        regions = textfit.divided_regions()
        self._date_plan = textfit.fit_single(
            font_path, self.DATE_FIT_WORST, regions["left_top"],
        )
        self._time_plan = textfit.fit_single(
            font_path, self.TIME_FIT_WORST, regions["left_bottom"],
        )
        self._sensor_plans = [
            textfit.fit_block(font_path, self.SENSOR_FIT_LINES,
                              regions["right_top"]),
            textfit.fit_block(font_path, self.SENSOR_FIT_LINES,
                              regions["right_bottom"]),
        ]
        self._ink = textfit.InkCache()
        print(
            f"[FbdevRunner] layout v5: date {self._date_plan['size']} pt, "
            f"time {self._time_plan['size']} pt, "
            f"sensors {self._sensor_plans[0]['size']} pt "
            f"(font {font_path})",
            file=__import__("sys").stderr, flush=True,
        )

    async def run(self):
        import sys
        debug = bool(os.environ.get(DEBUG_DRAW_ENV))
        print("[FbdevRunner] run() entered", file=sys.stderr, flush=True)
        try:
            # Scanner transport (ADR 0012): discovery runs beside the
            # render loop; a failed start is journalled, not fatal.
            await self._start_ble()
            tick_n = 0
            while True:
                t_loops = _monotonic()
                if debug:
                    print(
                        f"[FbdevRunner] tick #{tick_n + 1} starting",
                        file=sys.stderr, flush=True,
                    )
                await self._tick()
                t_ticked = _monotonic()
                tick_n += 1
                if debug:
                    print(
                        f"[FbdevRunner] tick #{tick_n} drew in "
                        f"{t_ticked - t_loops:.3f}s",
                        file=sys.stderr, flush=True,
                    )
                await asyncio.sleep(self.period_s)
        finally:
            try:
                self.mm.close()
            finally:
                os.close(self.fd)

    def _draw(self):
        import sys
        debug = bool(os.environ.get(DEBUG_DRAW_ENV))
        if debug:
            print("[FbdevRunner] _draw entered", file=sys.stderr,
                  flush=True)
        t0 = _monotonic()
        tf = textfit

        self.draw.rectangle(
            (0, 0, self.width, self.height), fill=tf.BG,
        )
        tf.draw_dividers(self.draw)

        # Top-left: date. Bottom-left: time.
        if self.time_formatter is not None:
            tf.draw_fitted(self.draw, self._date_plan,
                           self.time_formatter.date(), self._ink)
            tf.draw_fitted(self.draw, self._time_plan,
                           self.time_formatter.clock(), self._ink)

        # Right column: one sensor block per registered sensor, in
        # registry order (layout v5 has two right boxes).
        for i, sensor in enumerate(self.sensors):
            if i >= len(self._sensor_plans):
                break
            plan = self._sensor_plans[i]
            last_r = (self.last_readings[i]
                      if i < len(self.last_readings) else None)
            tf.draw_fitted_block(
                self.draw, plan,
                self._sensor_block_lines(sensor, last_r),
            )
        t_paint = _monotonic()

        rgb = self.img.tobytes()
        t_tobytes = _monotonic()
        packed = rgb_to_framebuffer(rgb, self.bpp, self.width, self.height)
        t_pack = _monotonic()
        # Single memmove-style write.
        self.mm[: len(packed)] = packed
        t_blit = _monotonic()

        # Always print slow-tick breakdowns — a regression signal.
        if (t_blit - t0) > 0.5 or debug:
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

    def _sensor_block_lines(self, sensor, last_r):
        """The four block lines for one sensor slot (layout v5).

        Title always renders (white); value lines render white with
        the latest known-good value, or red `n/a` when the field has
        never produced data.
        """
        _, _, loc = sensor
        title = (loc or "(unnamed)").capitalize()
        lines = [title]
        if last_r is None:
            lines += [("Temp: n/a", textfit.NA_FG),
                      ("Rel. Hum.: n/a", textfit.NA_FG),
                      ("Battery: n/a", textfit.NA_FG)]
            return lines
        lines.append(f"Temp: {last_r.temp_c:.1f} °C"
                     if last_r.temp_c is not None
                     else ("Temp: n/a", textfit.NA_FG))
        lines.append(f"Rel. Hum.: {last_r.hum_percent:.1f}%"
                     if last_r.hum_percent is not None
                     else ("Rel. Hum.: n/a", textfit.NA_FG))
        if last_r.batt_mv is not None:
            lines.append(f"Battery: {last_r.batt_mv / 1000:.2f}V")
        else:
            lines.append(("Battery: n/a", textfit.NA_FG))
        return lines
