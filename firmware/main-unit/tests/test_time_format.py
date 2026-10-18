"""Tests for the AWST clock + date formatter.

We don't mock datetime.now() — we pass a fixed tz-aware datetime
into the `clock(fake_value=)` / `date(fake_value=)` knobs so the
tests stay deterministic regardless of when they're run. The tests
also pin the en_US locale behaviour: %p returns AM/PM, %a returns
`Sun` for a Sunday in en_US. If the kitchen ever installs under a
different locale we'd want a locale fixture in here.
"""
import unittest
from datetime import datetime

try:
    from zoneinfo import ZoneInfo
except ImportError:                                    # pragma: no cover
    from backports.zoneinfo import ZoneInfo            # type: ignore

from kitchen_clock.time import (
    TimeFormatter,
    DEFAULT_TIMEZONE,
    DEFAULT_TIME_FORMAT,
)


AWST = ZoneInfo("Australia/Perth")


class TestDefaults(unittest.TestCase):
    def test_defaults_are_AWST_12h(self):
        tf = TimeFormatter()
        self.assertEqual(tf.tz, AWST)
        self.assertEqual(tf.time_format, "12h")
        # constants exposed match the constructor defaults.
        self.assertEqual(DEFAULT_TIMEZONE, "Australia/Perth")
        self.assertEqual(DEFAULT_TIME_FORMAT, "12h")

    def test_unknown_format_raises(self):
        with self.assertRaises(ValueError):
            TimeFormatter(time_format="binary")


class TestClockString(unittest.TestCase):
    def setUp(self):
        self.tf = TimeFormatter(tz_name="Australia/Perth",
                                time_format="12h")
        self.fmt_at(self.tf, 2026, 9, 20, 10, 42, 0)

    def fmt_at(self, tf, y, mo, d, h, mi, s):
        self.fake = datetime(y, mo, d, h, mi, s, tzinfo=AWST)

    def assert_clock(self, expected):
        self.assertEqual(self.tf.clock(self.fake), expected)

    def test_no_seconds_in_format(self):
        # The clock intentionally drops seconds so the panel paints
        # at full cadence; we keep this assertion long so the
        # format regaining seconds trips any regression.
        self.assert_clock("10:42 AM")

    def test_seconds_in_input_ignored(self):
        # Seconds in the *input* datetime don't change the
        # output — we don't render them.
        self.fmt_at(self.tf, 2026, 9, 20, 10, 42, 59)
        self.assert_clock("10:42 AM")

    def test_am_no_leading_zero(self):
        self.fmt_at(self.tf, 2026, 9, 20, 9, 0, 0)
        self.assert_clock("9:00 AM")

    def test_am_noon_keeps_12(self):
        self.fmt_at(self.tf, 2026, 9, 20, 0, 0, 0)
        self.assert_clock("12:00 AM")

    def test_pm_noon_no_ampm_continuity(self):
        self.fmt_at(self.tf, 2026, 9, 20, 12, 0, 0)
        self.assert_clock("12:00 PM")

    def test_pm_late(self):
        self.fmt_at(self.tf, 2026, 9, 20, 22, 5, 0)
        self.assert_clock("10:05 PM")

    def test_pm_one_digit_hour_trimmed(self):
        self.fmt_at(self.tf, 2026, 9, 20, 13, 30, 0)
        self.assert_clock("1:30 PM")


class TestClock24h(unittest.TestCase):
    def setUp(self):
        self.tf = TimeFormatter(tz_name="Australia/Perth",
                                time_format="24h")

    def test_no_ampm_in_24h(self):
        fake = datetime(2026, 9, 20, 13, 25, 48, tzinfo=AWST)
        self.assertEqual(self.tf.clock(fake), "13:25")

    def test_midnight_pads_zero(self):
        fake = datetime(2026, 9, 20, 0, 1, 2, tzinfo=AWST)
        self.assertEqual(self.tf.clock(fake), "00:01")


class TestDateString(unittest.TestCase):
    def setUp(self):
        self.tf = TimeFormatter(tz_name="Australia/Perth")

    def test_compact_date(self):
        # Sep 20, 2026 was a Sunday.
        fake = datetime(2026, 9, 20, 14, 0, 0, tzinfo=AWST)
        self.assertEqual(self.tf.date(fake), "Sun, 20 Sep 2026")

    def test_first_of_month(self):
        fake = datetime(2026, 1, 1, 0, 0, 0, tzinfo=AWST)
        # 1 Jan 2026 is a Thursday.
        self.assertEqual(self.tf.date(fake), "Thu, 01 Jan 2026")

    def test_zero_padded_day(self):
        # 7 March 2026 (Saturday) — %d pads single-digit day to "07".
        fake = datetime(2026, 3, 7, 12, 0, 0, tzinfo=AWST)
        self.assertEqual(self.tf.date(fake), "Sat, 07 Mar 2026")


class TestTimezone(unittest.TestCase):
    def test_utc_works(self):
        tf = TimeFormatter(tz_name="UTC")
        fake = datetime(2026, 9, 20, 14, 30, 0, tzinfo=ZoneInfo("UTC"))
        self.assertEqual(tf.clock(fake), "2:30 PM")
        self.assertEqual(tf.date(fake), "Sun, 20 Sep 2026")

    def test_wrong_zoneinfo_key_raises_at_construction(self):
        with self.assertRaises(Exception):
            TimeFormatter(tz_name="Not/A/RealZone")


if __name__ == "__main__":
    unittest.main()
