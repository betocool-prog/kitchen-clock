"""In-service BLE watchdog.

When every tile on the panel is failing for several ticks in a
row, the most likely cause is one of:

  - bluez stuck with a stale connection cache (advertising has
    become disabled because the peripheral firmware thinks the
    link is still alive)
  - bluez daemon wedged, scanner queue empty
  - the user sat down with the Pi in a poor BLE range

In every case, simply cycling `bluetooth.service` re-reads state
from the controller and re-arms the HCI scan — the user no longer
needs to `sudo systemctl restart bluetooth.service` by hand.

Implementation notes:

  - We shell out to the `dbus-send` CLI rather than using a Python
    DBus binding because:
    * the kitchen-clock.service runs as `User=betocool` and we
      want to avoid tying this dependency to dbus-python;
    * the verb `RestartUnit` is a single method call; pulling in a
      library is overkill;
    * dbus-send is part of base dbus-core and always present on
      Trixie.
  - The verb is `org.freedesktop.systemd1.Manager.RestartUnit`
    with args (string) unit, (string) mode. We pass mode="fail"
    to honour the per-service failure semantics but this is
    essentially a substitute for a manual `systemctl restart`.
  - We never restart bluetooth.service *from inside* the BLE
    wiring: the call is fire-and-forget, the runner sleeps a
    beat, and the next `_tick` observes whether reads return.

`maybe_restart_bluetooth()` is exposed as a single function so
tests can assert the call site without bringing up a dbus loop.
"""
from __future__ import annotations

import logging
import subprocess

# How many consecutive ticks with zero live tiles before we
# trigger the watchdog. Tuned empirically: with `--period 0.25`
# the runner does 4 ticks/s, so 5 ticks is ~1.25 s of total
# staleness before we attempt a reset. Anything lower would
# false-positive during the perennial BLE re-advert cycle of
# peripheral firmware.
FAIL_TICK_THRESHOLD = 5


def maybe_restart_bluetooth(consecutive_fail_ticks: int) -> bool:
    """Invoke `org.freedesktop.systemd1.Manager.RestartUnit` on
    bluetooth.service when the threshold is met.

    Returns True if the systemd call was attempted. The watch
    function is intentionally idempotent at the threshold — the
    runner resets its fail-count after every live tick, so even
    a hot-loop of repeated threshold-crossings can't spam-strobe
    the service.
    """
    if consecutive_fail_ticks < FAIL_TICK_THRESHOLD:
        return False

    logging.warning(
        "BLE watchdog: %d consecutive failed ticks → "
        "RestartUnit('bluetooth.service')",
        consecutive_fail_ticks,
    )
    # OSError covers the case where `dbus-send` isn't on PATH
    # (PathA dev containers, klock firmware with minimal libc,
    # etc.). We don't want to crash the runner just because the
    # dbus helper is missing — the BLE path is what protects the
    # clock's display, not the watchdog itself.
    try:
        subprocess.run(
            [
                "dbus-send",
                "--system",
                "--print-reply",
                "--dest=org.freedesktop.systemd1",
                "/org/freedesktop/systemd1",
                "org.freedesktop.systemd1.Manager.RestartUnit",
                "string:bluetooth.service",
                "string:fail",
            ],
            check=False,
            capture_output=True,
        )
    except OSError as exc:
        logging.warning(
            "BLE watchdog: dbus-send invocation failed: %s", exc,
        )
    return True
