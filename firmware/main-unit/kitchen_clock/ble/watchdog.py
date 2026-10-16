"""In-service BLE watchdog.

When every tile on the panel fails for `FAIL_TICK_THRESHOLD`
consecutive ticks, the runner arms a recovery cycle. This file
holds the actual recovery routine.

Why a scan off/on cycle, not a system-level restart:

  - Running as `betocool` inside `kitchen-clock.service`, we
    *cannot* `systemctl restart bluetooth.service` — polkit only
    authorises the active session's admin user, and `[Service]
    User=betocool` doesn't carry the magic. The earlier
    `dbus-send RestartUnit(bluetooth.service)` call returned with
    a MethodReturn but the service did not actually restart; the
    journal showed continued `connect-fail: ConnectionError`
    even after the watchdog fired.
  - `bluetoothctl scan off; scan on` is a session-DBus call against
    `org.bluez.Adapter1`. The session DBus ACL permits any user
    with a graphical session bus to flip the discovery filter.
    The HCI controller is reset by `StopDiscovery -> StartDiscovery`
    and any "still-connected" cached entry on the BlueZ adapter
    state is dropped on the next inquiry.
  - This is the exact pattern you ran by hand whenever the lockout
    re-asserted itself. Automating it inside the runner eliminates
    the catch-and-restart loop the user has been doing all week.

Side note: the runner also calls `cache.reset_backoffs()` on the
same tick so the next attempt goes live at once instead of
honouring the exponential-backoff counter we accumulated during
the outage.
"""
from __future__ import annotations

import logging
import subprocess
import time

# How many consecutive ticks with zero live tiles before we
# trigger the watchdog. Tuned empirically: with `--period 0.25`
# the runner does 4 ticks/s, so 5 ticks is ~1.25 s of total
# staleness before we attempt a reset. Lower would false-positive
# during the perennial BLE re-advert cycle of peripheral firmware.
FAIL_TICK_THRESHOLD = 5

# Time to leave the discovery-filter off before re-arming; lets the
# HCI controller process the StopDiscovery confirm and drop any
# "stale Connected" cached entry on the BlueZ adapter state.
SCAN_OFF_SETTLE_S = 0.5

# Hard timeout per `bluetoothctl` subprocess run. `bluetoothctl`
# occasionally takes a few seconds to talk to the session DBus
# daemon; we don't want the runner to spin forever on that call.
BLUETOOTHCTL_TIMEOUT_S = 5.0


def maybe_reset_ble_locks(consecutive_fail_ticks: int) -> bool:
    """Toggle BlueZ scanning to break the stale-Connected lockout.

    Returns True once the recovery cycle has been attempted. The
    runner resets the cached ble client's backoffs so the very
    next `_tick()` reads on a fresh HCI state.
    """
    if consecutive_fail_ticks < FAIL_TICK_THRESHOLD:
        return False

    logging.warning(
        "BLE watchdog: %d consecutive failed ticks → "
        "bluetoothctl scan off/on cycle",
        consecutive_fail_ticks,
    )

    # Try the off/on pair; be tolerant of either failing — we
    # can still have a single-sided reset with the same effect.
    _bluetoothctl_scan_off()
    time.sleep(SCAN_OFF_SETTLE_S)
    _bluetoothctl_scan_on()
    return True


def _bluetoothctl_scan_off() -> None:
    try:
        subprocess.run(
            ["bluetoothctl", "scan", "off"],
            check=False,
            capture_output=True,
            timeout=BLUETOOTHCTL_TIMEOUT_S,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        logging.warning("BLE watchdog: bluetoothctl scan off failed: %s", exc)


def _bluetoothctl_scan_on() -> None:
    try:
        subprocess.run(
            ["bluetoothctl", "scan", "on"],
            check=False,
            capture_output=True,
            timeout=BLUETOOTHCTL_TIMEOUT_S,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        logging.warning("BLE watchdog: bluetoothctl scan on failed: %s", exc)
