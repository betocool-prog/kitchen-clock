"""Unit tests for the layout v6 sensor-block lines (FbdevRunner).

The runner is built with `object.__new__` so no /dev/fb0 is needed;
only the attributes `_sensor_block_lines` reads are set.
"""

import struct
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

try:
    from kitchen_clock.ui import fbdev_window, textfit
except ImportError:                  # Pillow missing on this host
    fbdev_window = None

from kitchen_clock.ble.bleak_client import SensorReading
from kitchen_clock.history import HistoryStore
from kitchen_clock.time import TimeFormatter

AWST = ZoneInfo("Australia/Perth")
SENSOR = ("D0:44:B3:EE:AC:9F", "kclock-d0", "outside")


def reading(temp=2258, hum=5540, batt_mv=3990):
    return SensorReading(
        mac=SENSOR[0], name=SENSOR[1], location=SENSOR[2],
        raw_temp=struct.pack("<h", temp), raw_hum=struct.pack("<H", hum),
        raw_batt=struct.pack("<H", batt_mv), source="live",
    )


class FakeHub:
    def __init__(self, age):
        self.age = age

    def report_for(self, sensor):
        return None, self.age


@unittest.skipIf(fbdev_window is None, "Pillow not installed")
class TestSensorBlockLines(unittest.TestCase):
    def setUp(self):
        r = object.__new__(fbdev_window.FbdevRunner)
        r.time_formatter = TimeFormatter()
        r.history = HistoryStore()
        r.ble_hub = FakeHub(age=5.0)
        self.r = r

    def lines(self, last_r):
        return self.r._sensor_block_lines(SENSOR, last_r)

    def test_fresh_block_with_hi_lo(self):
        t_lo = datetime(2026, 10, 27, 5, 40, tzinfo=AWST).timestamp()
        t_hi = datetime(2026, 10, 27, 13, 5, tzinfo=AWST).timestamp()
        self.r.history.record("kclock-d0", t_lo, 15.2, 60.0)
        self.r.history.record("kclock-d0", t_hi, 24.1, 40.0)
        white = textfit.FG
        self.assertEqual(self.lines(reading()), [
            ("Outside", white),
            ("Temp: 22.6 °C", white),
            ("Rel. Hum.: 55.4%", white),
            "",
            ("Hi: 24.1 °C 13:05", white),
            ("Lo: 15.2 °C 05:40", white),
            ("Battery: 3.99V", white),
        ])

    def test_empty_history_is_red_na(self):
        lines = self.lines(reading())
        self.assertEqual(lines[4], ("Hi: n/a", textfit.NA_FG))
        self.assertEqual(lines[5], ("Lo: n/a", textfit.NA_FG))

    def test_stale_greys_block_but_keeps_red(self):
        self.r.ble_hub = FakeHub(age=fbdev_window.STALE_AFTER_S)
        lines = self.lines(reading())
        self.assertEqual(lines[0], ("Outside (stale)", textfit.STALE_FG))
        self.assertEqual(lines[1], ("Temp: 22.6 °C", textfit.STALE_FG))
        self.assertEqual(lines[4][1], textfit.NA_FG)    # Hi n/a stays red

    def test_just_under_threshold_is_fresh(self):
        self.r.ble_hub = FakeHub(age=fbdev_window.STALE_AFTER_S - 1)
        self.assertEqual(self.lines(reading())[0], ("Outside", textfit.FG))

    def test_never_seen_is_not_stale(self):
        self.r.ble_hub = FakeHub(age=None)
        lines = self.lines(None)
        self.assertEqual(lines[0], ("Outside", textfit.FG))
        self.assertEqual(len(lines), 7)
        self.assertEqual(lines[3], "")
        self.assertTrue(all(c == textfit.NA_FG
                            for _, c in lines[1:3] + lines[4:]))

    def test_low_battery_flag(self):
        lines = self.lines(reading(batt_mv=fbdev_window.LOW_BATT_MV))
        self.assertEqual(lines[6], ("Battery: 3.20V (!)", textfit.NA_FG))


if __name__ == "__main__":
    unittest.main()
