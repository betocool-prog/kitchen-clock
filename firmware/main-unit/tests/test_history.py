"""Unit tests for kitchen_clock.history — the 24 h Hi/Lo window."""

import unittest

from kitchen_clock.history import (
    HistoryStore, SensorHistory, MIN_PLAUSIBLE_T, WINDOW_S,
)

T0 = 1_793_000_000          # 2026-10-26-ish, comfortably plausible


class TestSensorHistory(unittest.TestCase):
    def test_empty_is_none(self):
        self.assertIsNone(SensorHistory().minmax(now=T0))

    def test_minmax_with_times(self):
        h = SensorHistory()
        h.record(T0, 20.0, 50.0)
        h.record(T0 + 15, 25.5, 50.0)
        h.record(T0 + 30, 18.2, 50.0)
        self.assertEqual(h.minmax(now=T0 + 30),
                         ((T0 + 30, 18.2), (T0 + 15, 25.5)))

    def test_ties_keep_first_occurrence(self):
        h = SensorHistory()
        h.record(T0, 20.0, 50.0)
        h.record(T0 + 15, 21.0, 50.0)
        h.record(T0 + 30, 20.0, 50.0)
        (t_lo, _), _ = h.minmax(now=T0 + 30)
        self.assertEqual(t_lo, T0)

    def test_dedupes_unchanged_temperature(self):
        h = SensorHistory()
        self.assertTrue(h.record(T0, 20.0, 50.0))
        self.assertFalse(h.record(T0 + 1, 20.0, 51.0))
        self.assertEqual(len(h), 1)

    def test_rejects_failure_sentinel(self):
        h = SensorHistory()
        self.assertFalse(h.record(T0, 0.0, 0.0))
        # either value alone is a legitimate reading
        self.assertTrue(h.record(T0, 0.0, 40.0))
        self.assertTrue(h.record(T0 + 15, 5.0, 0.0))

    def test_rejects_pre_ntp_clock(self):
        h = SensorHistory()
        self.assertFalse(h.record(MIN_PLAUSIBLE_T - 1, 20.0, 50.0))
        self.assertEqual(len(h), 0)

    def test_window_expires_on_read(self):
        h = SensorHistory()
        h.record(T0, 30.0, 50.0)
        h.record(T0 + 3600, 20.0, 50.0)
        _, (t_hi, hi) = h.minmax(now=T0 + WINDOW_S + 1)
        self.assertEqual((t_hi, hi), (T0 + 3600, 20.0))
        self.assertIsNone(h.minmax(now=T0 + 3600 + WINDOW_S + 1))


class TestHistoryStore(unittest.TestCase):
    def test_per_sensor_isolation(self):
        s = HistoryStore()
        s.record("kclock-a", T0, 10.0, 50.0)
        s.record("kclock-b", T0, 30.0, 50.0)
        self.assertEqual(s.minmax("kclock-a", now=T0)[1][1], 10.0)
        self.assertEqual(s.minmax("kclock-b", now=T0)[0][1], 30.0)
        self.assertIsNone(s.minmax("kclock-c", now=T0))


if __name__ == "__main__":
    unittest.main()
