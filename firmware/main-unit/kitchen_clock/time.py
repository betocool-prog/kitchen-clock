"""Wall-clock formatting for the AWST (Australia/Perth) clock + date.

The Pi Zero W has no hardware RTC, so the system time derives from
NTP via systemd-timesyncd at boot. While Wi-Fi and a remote server
are reachable, we'd expect the wall clock to keep near-perfect time.
On cold boot before NTP has grabbed, the system clock reads as
January 1 1970; we display that honestly rather than inventing a
fake time. Once NTP lands, the system's monotonic clock keeps
ticking even if Wi-Fi drops — we just resync when Wi-Fi comes
back.

The format chosen by the user: 12-hour with a *leading* AM/PM
marker, and a compact date line ("Mon 20 Sep"). A `--time-format
24h` override exists for kiosk installs in 24-hour regions.

locale: we use `%p` (AM/PM) and `%a %b` (Mon, Sep) — these are
en_US by default in CPython. If the Pi was deployed with a non-en
locale we'd want a different module-level locale switch, but for
the kitchen-clock project we are en-only.
"""
from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo


# tz database key for "Australia/Perth" — the only tz the kitchen
# is built for.
DEFAULT_TIMEZONE = "Australia/Perth"
DEFAULT_TIME_FORMAT = "12h"     # '12h' or '24h'


class TimeFormatter:
    """Build clock and date strings from a tz-aware `datetime`.

    `now(tz=None)` accepts an override at construction so unit tests
    don't have to monkey-patch `datetime.now` to drive deterministic
    strings — pass a fixed datetime in.
    """

    def __init__(self, tz_name: str = DEFAULT_TIMEZONE,
                 time_format: str = DEFAULT_TIME_FORMAT):
        self.tz = ZoneInfo(tz_name)
        if time_format not in ("12h", "24h"):
            raise ValueError(f"unknown time_format: {time_format!r}")
        self.time_format = time_format

    def now(self, fake_value: Optional[datetime] = None) -> datetime:
        """Return the wall clock for the running tz, or a fake datetime."""
        return fake_value or datetime.now(self.tz)

    def clock(self, fake_value: Optional[datetime] = None) -> str:
        """HH:MM:SS, optionally prefixed with AM/PM.

        12h: "AM 10:42:13" or "PM 03:25:48" — leading AM/PM was the
        user's choice. The "%I" formatter returns 1-12 with a leading
        space on values 1-9; we strip that so "AM  9:00:00" never
        shows a stray space.
        24h: "13:25:48"
        """
        t = self.now(fake_value)
        if self.time_format == "24h":
            return t.strftime("%H:%M:%S")
        # 12-hour. %I gives "01"-"12"; trim a leading zero so the
        # leading-space output reads cleanly.
        hour = t.strftime("%I").lstrip("0") or "12"
        return f"{t.strftime('%p')} {hour}:{t.strftime('%M:%S')}"

    def date(self, fake_value: Optional[datetime] = None) -> str:
        """Compact, locale-flavoured date row: 'Mon 20 Sep'."""
        return self.now(fake_value).strftime("%a %d %b")
