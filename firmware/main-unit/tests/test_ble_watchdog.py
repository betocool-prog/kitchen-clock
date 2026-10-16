"""Tests for the in-service BLE watchdog.

We mock `subprocess.run` (and `time.sleep` to keep tests fast)
so we don't actually call out to bluetoothctl during a unit
test. The runner is responsible for invoking
`maybe_reset_ble_locks` with a count; we test the threshold
boundary and the shape of the command lines that would go to
bluetoothctl on the Pi.
"""
import unittest
from unittest.mock import MagicMock, patch

from kitchen_clock.ble.watchdog import (
    FAIL_TICK_THRESHOLD,
    SCAN_OFF_SETTLE_S,
    maybe_reset_ble_locks,
)


class TestThreshold(unittest.TestCase):
    """Below threshold → no shell-out. At/above → one shell-out."""

    def test_below_threshold_is_idempotent(self):
        for n in range(0, FAIL_TICK_THRESHOLD):
            with patch(
                "kitchen_clock.ble.watchdog.subprocess.run",
            ) as mock_run, patch(
                "kitchen_clock.ble.watchdog.time.sleep",
            ):
                self.assertFalse(maybe_reset_ble_locks(n))
                mock_run.assert_not_called()

    def test_at_threshold_invokes_reset(self):
        with patch(
            "kitchen_clock.ble.watchdog.subprocess.run",
        ) as mock_run, patch(
            "kitchen_clock.ble.watchdog.time.sleep",
        ):
            self.assertTrue(
                maybe_reset_ble_locks(FAIL_TICK_THRESHOLD),
            )
            # off + on
            self.assertEqual(mock_run.call_count, 2)

    def test_well_above_threshold_still_invokes(self):
        with patch(
            "kitchen_clock.ble.watchdog.subprocess.run",
        ) as mock_run, patch(
            "kitchen_clock.ble.watchdog.time.sleep",
        ):
            self.assertTrue(
                maybe_reset_ble_locks(FAIL_TICK_THRESHOLD + 50),
            )
            self.assertEqual(mock_run.call_count, 2)


class TestBluetoothctlCommandLine(unittest.TestCase):
    """Argument shape that would actually run on the Pi."""

    def test_off_then_on(self):
        with patch(
            "kitchen_clock.ble.watchdog.subprocess.run",
            return_value=MagicMock(returncode=0),
        ) as mock_run, patch(
            "kitchen_clock.ble.watchdog.time.sleep",
        ):
            maybe_reset_ble_locks(FAIL_TICK_THRESHOLD)
            args = mock_run.call_args_list
            self.assertEqual(args[0][0][0], ["bluetoothctl", "scan", "off"])
            self.assertEqual(args[1][0][0], ["bluetoothctl", "scan", "on"])

    def test_settle_sleep_between_off_and_on(self):
        with patch(
            "kitchen_clock.ble.watchdog.subprocess.run",
        ) as mock_run, patch(
            "kitchen_clock.ble.watchdog.time.sleep",
        ) as mock_sleep:
            self.assertTrue(
                maybe_reset_ble_locks(FAIL_TICK_THRESHOLD),
            )
            # The runner does ONE sleep between off and on.
            self.assertEqual(mock_sleep.call_count, 1)
            self.assertAlmostEqual(
                mock_sleep.call_args.args[0], SCAN_OFF_SETTLE_S,
                places=6,
            )

    def test_settle_constant_is_a_finite_number(self):
        # If we accidentally set SCAN_OFF_SETTLE_S to a runaway
        # value the system would still self-heal but slowly.
        # Pin a sane upper bound.
        self.assertLessEqual(SCAN_OFF_SETTLE_S, 2.5)


class TestResilience(unittest.TestCase):
    """The runner must not crash if bluetoothctl is missing or
    hangs. The watchdog function swallows the relevant errors and
    still returns True so caching resets can fire.
    """

    def test_missing_bluetoothctl_does_not_raise(self):
        with patch(
            "kitchen_clock.ble.watchdog.subprocess.run",
            side_effect=FileNotFoundError("bluetoothctl"),
        ), patch(
            "kitchen_clock.ble.watchdog.time.sleep",
        ):
            # Should still return True (attempted) and not raise.
            self.assertTrue(
                maybe_reset_ble_locks(FAIL_TICK_THRESHOLD),
            )

    def test_bluetoothctl_timeout_does_not_raise(self):
        import subprocess as _sub
        with patch(
            "kitchen_clock.ble.watchdog.subprocess.run",
            side_effect=_sub.TimeoutExpired(cmd=["bluetoothctl"], timeout=5),
        ), patch(
            "kitchen_clock.ble.watchdog.time.sleep",
        ):
            self.assertTrue(
                maybe_reset_ble_locks(FAIL_TICK_THRESHOLD),
            )


class TestThresholdDefault(unittest.TestCase):
    """Pin the threshold default so a regression here is loud."""

    def test_threshold_is_five(self):
        self.assertEqual(FAIL_TICK_THRESHOLD, 5)


if __name__ == "__main__":
    unittest.main()
