"""Tests for the in-service BLE watchdog.

We mock `subprocess.run` so we don't actually call out to
dbus-send during a unit test. The runner is responsible for
invoking `maybe_restart_bluetooth` with a count; we test the
threshold boundary and the shape of the command line that
would actually run on the Pi.
"""
import unittest
from unittest.mock import MagicMock, patch

from kitchen_clock.ble.watchdog import (
    FAIL_TICK_THRESHOLD,
    maybe_restart_bluetooth,
)


class TestThreshold(unittest.TestCase):
    """Below threshold → no call. At/above → single call."""

    def test_below_threshold_is_idempotent(self):
        for n in range(0, FAIL_TICK_THRESHOLD):
            with patch(
                "kitchen_clock.ble.watchdog.subprocess.run",
            ) as mock_run:
                self.assertFalse(maybe_restart_bluetooth(n))
                mock_run.assert_not_called()

    def test_at_threshold_invokes(self):
        with patch(
            "kitchen_clock.ble.watchdog.subprocess.run",
        ) as mock_run:
            self.assertTrue(
                maybe_restart_bluetooth(FAIL_TICK_THRESHOLD),
            )
            mock_run.assert_called_once()

    def test_well_above_threshold_still_invokes(self):
        with patch(
            "kitchen_clock.ble.watchdog.subprocess.run",
        ) as mock_run:
            self.assertTrue(maybe_restart_bluetooth(FAIL_TICK_THRESHOLD + 50))
            mock_run.assert_called_once()


class TestDbusCommandLine(unittest.TestCase):
    """Argument shape that would be sent to dbus-send on the Pi."""

    def test_args_match_dbus_spec(self):
        with patch(
            "kitchen_clock.ble.watchdog.subprocess.run",
        ) as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            maybe_restart_bluetooth(FAIL_TICK_THRESHOLD)
            args = mock_run.call_args[0][0]
            # Order of arguments is what systemctl equivalent
            # would be — easy to correlate in journalctl if the
            # call produces no result.
            self.assertEqual(args[0], "dbus-send")
            self.assertIn("--system", args[1:])
            self.assertIn("--print-reply", args)
            self.assertIn("--dest=org.freedesktop.systemd1", args)
            self.assertIn("/org/freedesktop/systemd1", args)
            self.assertIn(
                "org.freedesktop.systemd1.Manager.RestartUnit", args,
            )
            # The pair of trailing string args:
            self.assertEqual(
                args[-2:],
                ["string:bluetooth.service", "string:fail"],
            )

    def test_call_does_not_raise_on_subprocess_failure(self):
        """subprocess.run with check=False would normally still
        raise in the worst cases (BrokenPipeError, FileNotFoundError)
        when dbus-send is missing. We must not crash the runner."""
        with patch(
            "kitchen_clock.ble.watchdog.subprocess.run",
            side_effect=FileNotFoundError("dbus-send"),
        ):
            # Should still return True (attempted) and not raise.
            self.assertTrue(
                maybe_restart_bluetooth(FAIL_TICK_THRESHOLD),
            )


class TestThresholdDefault(unittest.TestCase):
    """Pin the threshold default so a regression here is loud."""

    def test_threshold_is_five(self):
        # Decided as ~1.25 s of "every tile connect-failing"
        # at the default period of 0.25 s. Anything lower would
        # false-positive during the perennial BLE re-advertise
        # cycle of peripheral firmware.
        self.assertEqual(FAIL_TICK_THRESHOLD, 5)


if __name__ == "__main__":
    unittest.main()
