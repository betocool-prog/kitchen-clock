"""Tests for the scanner-transport watchdog (ADR 0012).

The watchdog is a rate-limited `ScannerHub.restart()` driver: it
must fire only past `STALE_THRESHOLD_S`, at most once per
`RECOVERY_COOLDOWN_S`, never raise on a failed restart, and never
touch subprocesses (the old bluetoothctl cycling fed the
2026-10-17 D-Bus wedge).
"""
import asyncio
import time
import unittest
from unittest.mock import AsyncMock

from kitchen_clock.ble.watchdog import (
    RECOVERY_COOLDOWN_S,
    STALE_THRESHOLD_S,
    ScanWatchdog,
)


class FakeHub:
    """Minimal hub stand-in: restart() is an AsyncMock."""

    def __init__(self, restart_exc=None):
        self.restart = AsyncMock(side_effect=restart_exc)
        self.min_stale_seconds = lambda: STALE_THRESHOLD_S


class TestShouldFire(unittest.TestCase):
    def test_below_threshold_never_fires(self):
        wd = ScanWatchdog()
        for _ in range(10):
            self.assertFalse(wd.should_fire(STALE_THRESHOLD_S - 0.1))

    def test_at_threshold_fires_once_then_cooldown(self):
        wd = ScanWatchdog()
        self.assertTrue(wd.should_fire(STALE_THRESHOLD_S))
        # Immediately after: suppressed by the cooldown.
        self.assertFalse(wd.should_fire(STALE_THRESHOLD_S * 10))

    def test_fires_again_after_cooldown_elapses(self):
        wd = ScanWatchdog()
        self.assertTrue(wd.should_fire(STALE_THRESHOLD_S))
        # Simulate the cooldown having elapsed.
        wd._last_recovery = time.monotonic() - RECOVERY_COOLDOWN_S - 1
        self.assertTrue(wd.should_fire(STALE_THRESHOLD_S))

    def test_threshold_edge_is_inclusive(self):
        wd = ScanWatchdog()
        self.assertTrue(wd.should_fire(STALE_THRESHOLD_S + 0.001))


class TestRecover(unittest.TestCase):
    def test_restart_called_once_and_returns_true(self):
        wd = ScanWatchdog()
        hub = FakeHub()
        self.assertTrue(asyncio.run(wd.recover(hub)))
        hub.restart.assert_awaited_once_with()

    def test_restart_failure_does_not_raise(self):
        wd = ScanWatchdog()
        hub = FakeHub(
            restart_exc=RuntimeError("No buffer space available"),
        )
        self.assertFalse(asyncio.run(wd.recover(hub)))

    def test_recover_consumes_no_extra_cooldown(self):
        # recover() itself must not bump _last_recovery — only
        # should_fire() grants cooldown slots.
        wd = ScanWatchdog()
        before = wd._last_recovery
        asyncio.run(wd.recover(FakeHub()))
        self.assertEqual(wd._last_recovery, before)


class TestConstants(unittest.TestCase):
    """Pin the tuning so a regression here is loud."""

    def test_threshold_at_least_a_few_sample_rounds(self):
        # Firmware samples every 15 s; the threshold must tolerate
        # several missed rounds without flapping.
        self.assertGreaterEqual(STALE_THRESHOLD_S, 45.0)

    def test_cooldown_longer_than_threshold(self):
        # A restart storm is the failure mode this guards against.
        self.assertGreaterEqual(RECOVERY_COOLDOWN_S, 60.0)


if __name__ == "__main__":
    unittest.main()
