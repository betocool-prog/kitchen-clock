"""Rolling 24-hour temperature history per sensor (layout v6).

The panel shows, per sensor block, the minimum and maximum
temperature over the last 24 hours with the wall-clock time each
extreme occurred (24h "at 10:00" style — no AM/PM, per the agreed
format). This module is the data side: a per-sensor, RAM-only
window of fresh samples with two guards, fed by the scanner hub's
fresh-report callback (each *decoded advertisement report*, which
the firmware refreshes every 15 s).

Guards (both cheap and both born on the bench):

  - **Junk samples**: the sensor firmware pushes exactly 0.00 °C
    *and* 0.00 %RH when the BME280 read fails (see
    firmware/outdoor-sensor/app/src/sensor.c). A single such
    failure would pin "Min: 0.0 °C" for 24 h, so samples with both
    values exactly zero are ignored (either value alone is a
    legitimate reading; both together are the failure sentinel).
  - **Implausible clock**: the Pi has no RTC — before NTP sync the
    wall clock reads 1970. Samples recorded with pre-2020
    timestamps are ignored, otherwise the "at" times would be
    garbage and the window would never expire.

**Dedupe**: advertisement reports arrive several times per second
(the firmware advertises continuously) but carry a *new* payload
only every 15 s. Recording every report would balloon the window
(~260 k samples/day); recording only on a temperature *change*
gives exactly the measurement cadence, and a flat temperature
contributes nothing to min/max anyway — the first occurrence of a
value carries its timestamp, which is the display semantics.

RAM-only by agreement (2026-10-18): after a reboot the extremes
render red `n/a` and converge over the following day. Persistence
is a deliberate later option, not an oversight.
"""

import time as _time
from collections import deque
from typing import Optional, Tuple

# Anything before 2020-01-01 UTC is a pre-NTP-sync clock, not a
# plausible sample time (also rejects the 1970 epoch nonsense).
MIN_PLAUSIBLE_T = 1_578_000_000

# Rolling window length, seconds.
WINDOW_S = 24 * 3600

Minmax = Optional[Tuple[Tuple[float, float], Tuple[float, float]]]


class SensorHistory:
    """One sensor's rolling temperature window."""

    def __init__(self, window_s: float = WINDOW_S):
        self._window_s = window_s
        self._samples = deque()          # (t_wall, temp_c)
        self._last_temp = None           # dedupe on temperature change

    def record(self, t: float, temp_c: float, hum: float) -> bool:
        """Record a fresh sample; True when actually appended.

        `t` is a wall-clock epoch (explicit so tests inject
        timestamps); `hum` is only consulted for the junk guard.
        """
        if t < MIN_PLAUSIBLE_T:
            return False
        if temp_c == 0.0 and hum == 0.0:
            return False
        if temp_c == self._last_temp:
            return False
        self._last_temp = temp_c
        self._samples.append((t, temp_c))
        self._prune(t)
        return True

    def _prune(self, now: float) -> None:
        horizon = now - self._window_s
        while self._samples and self._samples[0][0] < horizon:
            self._samples.popleft()

    def minmax(self, now: Optional[float] = None) -> Minmax:
        """((t_min, min_c), (t_max, max_c)) or None when empty.

        Ties keep the FIRST occurrence's timestamp. `now` is
        injectable for tests; expiry is re-checked on read so a
        long-idle window still returns current data.
        """
        if now is None:
            now = _time.time()
        self._prune(now)
        if not self._samples:
            return None
        min_t, min_v = self._samples[0]
        max_t, max_v = self._samples[0]
        for t, v in self._samples:
            if v < min_v:
                min_t, min_v = t, v
            if v > max_v:
                max_t, max_v = t, v
        return (min_t, min_v), (max_t, max_v)

    def __len__(self) -> int:
        return len(self._samples)


class HistoryStore:
    """Per-sensor history registry, keyed by sensor name."""

    def __init__(self, window_s: float = WINDOW_S):
        self._window_s = window_s
        self._by_name: dict = {}

    def record(self, sensor_name: str, t: float,
               temp_c: float, hum: float) -> bool:
        h = self._by_name.get(sensor_name)
        if h is None:
            h = self._by_name[sensor_name] = SensorHistory(self._window_s)
        return h.record(t, temp_c, hum)

    def minmax(self, sensor_name: str,
               now: Optional[float] = None) -> Minmax:
        h = self._by_name.get(sensor_name)
        if h is None:
            return None
        return h.minmax(now)
