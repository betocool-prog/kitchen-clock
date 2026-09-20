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
        self.fmt_at(self.tf, 2026, 9, 20, 10, 42, 13)

    def fmt_at(self, tf, y, mo, d, h, mi, s):
        self.fake = datetime(y, mo, d, h, mi, s, tzinfo=AWST)

    def assert_clock(self, expected):
        self.assertEqual(self.tf.clock(self.fake), expected)

    def test_am_no_leading_zero(self):
        # 9 AM should NOT be padded to "09" because leading AM/PM
        # makes "AM 09:..." look weird.
        self.fmt_at(self.tf, 2026, 9, 20, 9, 0, 0)
        self.assert_clock("AM 9:00:00")

    def test_am_noon_keeps_12(self):
        # Affirm 12:00:00 reads as "AM 12:00:00" (not "AM 0:00:00").
        self.fmt_at(self.tf, 2026, 9, 20, 0, 0, 0)
        self.assert_clock("AM 12:00:00")

    def test_pm_noon_no_ampm_continuity(self):
        # 12:00:00 PM is "PM 12:00:00", not "PM 0:00:00".
        self.fmt_at(self.tf, 2026, 9, 20, 12, 0, 0)
        self.assert_clock("PM 12:00:00")

    def test_pm_late(self):
        self.fmt_at(self.tf, 2026, 9, 20, 22, 5, 9)
        self.assert_clock("PM 10:05:09")

    def test_pm_one_digit_hour_trimmed(self):
        # %I returns "01"-"12"; we trim a leading zero so the
        # rect of digits doesn't carry a ghost space.
        self.fmt_at(self.tf, 2026, 9, 20, 13, 30, 0)
        self.assert_clock("PM 1:30:00")


class TestClock24h(unittest.TestCase):
    def setUp(self):
        self.tf = TimeFormatter(tz_name="Australia/Perth",
                                time_format="24h")

    def test_no_ampm_in_24h(self):
        fake = datetime(2026, 9, 20, 13, 25, 48, tzinfo=AWST)
        self.assertEqual(self.tf.clock(fake), "13:25:48")

    def test_midnight_pads_zero(self):
        fake = datetime(2026, 9, 20, 0, 1, 2, tzinfo=AWST)
        self.assertEqual(self.tf.clock(fake), "00:01:02")


class TestDateString(unittest.TestCase):
    def setUp(self):
        self.tf = TimeFormatter(tz_name="Australia/Perth")

    def test_compact_date(self):
        # Sep 20, 2026 was a Sunday.
        fake = datetime(2026, 9, 20, 14, 0, 0, tzinfo=AWST)
        self.assertEqual(self.tf.date(fake), "Sun 20 Sep")

    def test_first_of_month(self):
        fake = datetime(2026, 1, 1, 0, 0, 0, tzinfo=AWST)
        # 1 Jan 2026 is a Thursday.
        self.assertEqual(self.tf.date(fake), "Thu 01 Jan")

    def test_zero_padded_day(self):
        # 7 March 2026 (Saturday) — %d pads single-digit day to "07".
        fake = datetime(2026, 3, 7, 12, 0, 0, tzinfo=AWST)
        self.assertEqual(self.tf.date(fake), "Sat 07 Mar")


class TestTimezone(unittest.TestCase):
    def test_utc_works(self):
        tf = TimeFormatter(tz_name="UTC")
        fake = datetime(2026, 9, 20, 14, 30, 0, tzinfo=ZoneInfo("UTC"))
        self.assertEqual(tf.clock(fake), "PM 2:30:00")
        self.assertEqual(tf.date(fake), "Sun 20 Sep")

    def test_wrong_zoneinfo_key_raises_at_construction(self):
        with self.assertRaises(Exception):
            TimeFormatter(tz_name="Not/A/RealZone")


if __name__ == "__main__":
    unittest.main()
