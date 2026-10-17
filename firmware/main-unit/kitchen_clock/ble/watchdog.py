"""In-service BLE watchdog — scanner transport (ADR 0012).

When *no* registered sensor has reported for `STALE_THRESHOLD_S`,
the scanner (or bluetoothd) is suspect and the runner restarts
discovery — rate-limited to one attempt per `RECOVERY_COOLDOWN_S`,
and always as a background asyncio task so the render loop never
blocks on D-Bus.

Why a scanner restart, not the old `bluetoothctl` cycling:

  - The 2026-10-17 incident: the connect/poll model wedged D-Bus so
    thoroughly that `bluetoothctl` calls *crashed* (libdbus
    assertion) and even `org.freedesktop.DBus.ListNames` returned
    ENOBUFS. The then-watchdog kept spawning `bluetoothctl` every
    tick for an hour and left discovery permanently on, feeding the
    flood. Rate-limiting and staying inside bleak's own
    scanner-start path (same process, same D-Bus connection) avoids
    both failure modes.
  - `ScannerHub.restart()` is `stop()` + `start()` on *our* scanner
    with *our* UUID filter — it can never leave unfiltered
    discovery running the way `bluetoothctl scan on` did.

If D-Bus is dead the restart raises; that is logged and retried
after the cooldown. A hard-wedged daemon needs the reboot only the
operator can perform — the journal lines make that state explicit
("restart failed" repeating with cooldown spacing).
"""
from __future__ import annotations

import logging
import time

# How long without any sensor report before the scanner is restarted.
# The firmware samples every 15 s and advertises continuously, so
# 90 s means ~6 missed sample rounds — clearly transport trouble,
# not a single lost packet.
STALE_THRESHOLD_S = 90.0

# Minimum spacing between restart attempts. Keeps a dead D-Bus from
# turning the watchdog into a restart storm (the 2026-10-17 failure
# mode of the old tick-count watchdog).
RECOVERY_COOLDOWN_S = 120.0


class ScanWatchdog:
    """Rate-limited staleness watchdog for the scanner transport."""

    def __init__(self,
                 stale_threshold_s: float = STALE_THRESHOLD_S,
                 cooldown_s: float = RECOVERY_COOLDOWN_S):
        self._stale_threshold = stale_threshold_s
        self._cooldown = cooldown_s
        self._last_recovery = float("-inf")

    def should_fire(self, stale_s: float) -> bool:
        """True when a restart is due. Consumes the cooldown slot."""
        if stale_s < self._stale_threshold:
            return False
        now = time.monotonic()
        if now - self._last_recovery < self._cooldown:
            return False
        self._last_recovery = now
        return True

    async def recover(self, hub) -> bool:
        """Restart the hub's scanner. Never raises.

        Returns True when the restart succeeded, False when it
        failed (logged); the next attempt waits out the cooldown.
        """
        logging.warning(
            "BLE watchdog: no sensor reports for %.0f s "
            "→ restarting scanner", hub.min_stale_seconds(),
        )
        try:
            await hub.restart()
            return True
        except Exception as exc:  # noqa: BLE001 — watchdog must not raise
            logging.warning(
                "BLE watchdog: scanner restart failed: %s: %s",
                type(exc).__name__, exc,
            )
            return False
