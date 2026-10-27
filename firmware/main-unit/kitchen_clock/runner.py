"""Renderer-loop helpers shared by PygameRunner and FbdevRunner.

Path A (ADR 0011): this file is shared across host (PyGame) and
Pi runtime (FbdevRunner). It deliberately imports nothing from
pygame so it stays importable from either side without side-effects.

Transport (ADR 0012): in live mode the runner carries a
`ble_hub` (ScannerHub) — a filtered passive scanner that never
opens a GATT connection. `_tick()` therefore never touches the
radio: it drains the hub's cached reports, merges them into the
render cache, and draws. Scanner start/restart run as their own
awaitables (never blocking the render loop), and the watchdog
(`ble/watchdog.py`) restarts the scanner — rate-limited — when no
registered sensor has reported for `STALE_THRESHOLD_S`.

Render-cache semantics (the panel never blanks on BLE trouble):

  `current_readings` — what the transport surfaced this tick
    (fresh, `stale:Ns`, `no-report`, ...). Journal/diag only.

  `last_readings` — last-known-good per tile, merged *per field*:
    a report that carries a fresh temperature but no battery
    value updates only the temperature slot; the other slots keep
    their previous good values. A tile that has never seen data
    stays `None` and renders as `n/a`.
"""

import asyncio
import time as _time
from typing import Callable, List, Optional, Tuple

from .ble.bleak_client import SensorReading
from .ble.watchdog import ScanWatchdog

SensorTuple = Tuple[str, str, str]


def _is_complete(reading) -> bool:
    """True when every GATT char read came back and the connection
    itself was established.

    Kept for callers/tests that want the strict definition; the
    render cache no longer requires it — `merge_reading` promotes
    whichever fields are valid so a partial report still refreshes
    the fields it carries.
    """
    return (
        reading.source in ("live", "mock")
        and not reading.temp_error
        and not reading.hum_error
        and not reading.batt_error
    )


def _any_field_ok(reading) -> bool:
    """True when the reading carries at least one usable field."""
    if reading.source not in ("live", "mock"):
        return False
    return not (reading.temp_error and reading.hum_error
                and reading.batt_error)


def merge_reading(old: Optional[SensorReading],
                  new: SensorReading) -> SensorReading:
    """Per-field promotion: valid fields from `new`, the rest from `old`.

    A field is "valid" when its per-characteristic read succeeded
    (`*_error` empty and raw bytes present). Failed or missing
    fields inherit the previous good value so one flaky
    characteristic (e.g. the battery ADC sentinel) cannot freeze an
    otherwise-fresh tile.
    """

    def pick(new_raw, new_err, old_raw):
        if new_err or not new_raw:
            return old_raw, ""
        return new_raw, ""

    if old is None:
        raw_t, e_t = new.raw_temp, ""
        raw_h, e_h = new.raw_hum, ""
        raw_b, e_b = new.raw_batt, ""
    else:
        raw_t, e_t = pick(new.raw_temp, new.temp_error, old.raw_temp)
        raw_h, e_h = pick(new.raw_hum, new.hum_error, old.raw_hum)
        raw_b, e_b = pick(new.raw_batt, new.batt_error, old.raw_batt)

    return SensorReading(
        mac=new.mac, name=new.name, location=new.location,
        raw_temp=raw_t, raw_hum=raw_h, raw_batt=raw_b,
        temp_error=e_t, hum_error=e_h, batt_error=e_b,
        source=new.source,
    )


async def safe_read(client) -> SensorReading:
    """Run a client's read() coroutine and surface exceptions as a
    SensorReading with source='error:...'. The origin sensor tuple
    is recovered from the client's `.sensor` attribute if present.
    """
    sensor = getattr(client, "sensor", None)
    if sensor is not None:
        mac, name, loc = sensor
    else:
        mac, name, loc = "?", "?", "?"
    try:
        return await client.read()
    except Exception as e:
        return SensorReading(
            mac=mac, name=name, location=loc,
            source=f"error:{type(e).__name__}:{e}",
        )


async def read_all_sensors(
    sensors: List[SensorTuple],
    client_factory: Callable[[SensorTuple], object],
) -> List[SensorReading]:
    """Per-sensor reads, one per sensor, preserving input order.

    With the scanner transport this is a pure state drain (no radio
    work, no concurrency needed). Exceptions in any sensor's
    pipeline are caught per-sensor so a single peripheral going dark
    does not stall the rest of the dashboard. Output list has
    length == len(sensors).
    """
    readings = []
    for s in sensors:
        readings.append(await safe_read(client_factory(s)))
    return readings


class BLEClientCache:
    """Memoize BLE clients per sensor tuple."""

    def __init__(self, factory: Callable[[SensorTuple], object]):
        self._factory = factory
        self._cache: dict = {}

    def client_for(self, sensor: SensorTuple):
        if sensor not in self._cache:
            self._cache[sensor] = self._factory(sensor)
        return self._cache[sensor]

    def reset_backoffs(self) -> None:
        """Force-clear cached clients' connection-failure state.

        Retained for the legacy GATT client (`RealBleakClient`);
        the scanner transport has no connection state to clear.
        """
        for client in self._cache.values():
            reset = getattr(client, "reset_backoff", None)
            if callable(reset):
                reset()

    def __len__(self) -> int:
        return len(self._cache)


class BaseRunner:
    """Common "gather → draw → sleep → repeat" loop.

    Concrete subclasses implement:
      - `run()`     (event-loop glue: pygame event pump, fbdev blit)
      - `_draw()`   (surface rendering)

    Both subclasses share:
      - per-tick transport drain via `read_all_sensors`
      - per-field render-cache promotion via `merge_reading`
      - BLE-client caching via `BLEClientCache`
      - scanner-mode watchdog: when *no* registered sensor has
        reported for `STALE_THRESHOLD_S`, restart the hub's
        scanner — at most once per `RECOVERY_COOLDOWN_S`, as a
        background task so the render loop never blocks.

    Set `runner.ble_hub = ScannerHub(...)` before `run()` for the
    live scanner transport (ADR 0012); without it the runner is in
    mock/synthetic mode and the watchdog is inert.
    """

    # Journal cadence: per-tick state lines only fire on change or
    # every HEARTBEAT_TICKS (~60 s at the 0.25 s period) so a healthy
    # panel no longer writes 3+ lines/s to the journal.
    HEARTBEAT_TICKS = 240

    def __init__(self, *, make_client, sensors, period_s: float = 2.0):
        self.cache = BLEClientCache(make_client)
        self.sensors = list(sensors)
        self.period_s = period_s
        self.last_readings: list = [None] * len(self.sensors)
        self.current_readings: list = [None] * len(self.sensors)
        self.ble_hub = None                    # ScannerHub in live mode
        self.history = None                    # HistoryStore in live mode
        self._scan_watchdog = ScanWatchdog()
        self._recovery_in_flight = False
        self._ble_tick_counter = 0
        self._last_state_line = ""
        self._last_diag_sources: dict = {}
        self._legacy_hint_count = 0

    async def _start_ble(self) -> None:
        """Start the scanner transport, if attached.

        Never raises: a failed start (e.g. bluetoothd not up yet) is
        journalled and retried by the watchdog's restart path.
        """
        import sys
        hub = self.ble_hub
        if hub is None:
            return
        try:
            await hub.start()
        except Exception as exc:
            print(
                f"[BaseRunner] BLE scanner start failed: "
                f"{type(exc).__name__}: {exc} "
                f"(watchdog will retry)",
                file=sys.stderr, flush=True,
            )

    async def _recover_scanner(self, hub) -> None:
        """Watchdog recovery body — runs as a background task."""
        import sys
        try:
            ok = await self._scan_watchdog.recover(hub)
            print(
                f"[BaseRunner] BLE watchdog: scanner restart "
                f"{'succeeded' if ok else 'failed — will retry after cooldown'}",
                file=sys.stderr, flush=True,
            )
        finally:
            self._recovery_in_flight = False

    async def _tick(self) -> None:
        import sys
        t0_read = _time.monotonic()
        self.current_readings = await read_all_sensors(
            self.sensors, self.cache.client_for,
        )
        t1_read = _time.monotonic()

        # Promote per-field: every valid field refreshes the tile's
        # cached value; failed fields keep the previous good one.
        # Partial reports are also surfaced in the journal state so
        # the user can see them.
        any_complete = False
        for i, r in enumerate(self.current_readings):
            if r is None:
                continue
            if _any_field_ok(r):
                self.last_readings[i] = merge_reading(
                    self.last_readings[i], r,
                )
                any_complete = True

        # Scanner-mode watchdog: when *no* sensor reported recently,
        # restart the scanner — rate-limited, never on the render
        # loop's own coroutine.
        hub = self.ble_hub
        if hub is not None and not any_complete:
            stale_s = hub.min_stale_seconds()
            if (self._scan_watchdog.should_fire(stale_s)
                    and not self._recovery_in_flight):
                self._recovery_in_flight = True
                task = asyncio.create_task(self._recover_scanner(hub))
                task.add_done_callback(lambda _t: None)

        # Compact one-line BLE state summary for the journal — on
        # change or heartbeat only (see HEARTBEAT_TICKS).
        try:
            self._ble_tick_counter += 1
            tick_n = self._ble_tick_counter
            states = " ".join(
                f"{r.location}={r.source.split(':', 1)[0]}"
                f":T={r.temp_c if isinstance(r.temp_c, (int, float)) else '-'}"
                f":H={r.hum_percent if isinstance(r.hum_percent, (int, float)) else '-'}"
                f":B={r.batt_mv if isinstance(r.batt_mv, int) else '-'}"
                for r in self.current_readings if r is not None
            )
            if states != self._last_state_line or tick_n % self.HEARTBEAT_TICKS == 0:
                print(
                    f"[BaseRunner] tick #{tick_n} state: {states}",
                    file=sys.stderr, flush=True,
                )
                self._last_state_line = states
        except Exception:
            pass

        # Non-live/non-mock sources get a diag line when the source
        # *changes* (not every tick — a stale sensor would otherwise
        # spam one line per tick as its age grows).
        for r in self.current_readings:
            if r is None:
                continue
            if r.source in ("live", "mock"):
                continue
            last = self._last_diag_sources.get(r.location)
            if last == r.source:
                continue
            self._last_diag_sources[r.location] = r.source
            print(
                f"[BaseRunner] BLE diag[{r.location}]: "
                f"mac={r.mac} source={r.source}",
                file=sys.stderr, flush=True,
            )

        # One-time hint when our sensors advertise without service
        # data — v7-era firmware needs flashing before the scanner
        # transport can see any values.
        if hub is not None and hub.legacy_reports > self._legacy_hint_count:
            self._legacy_hint_count = hub.legacy_reports
            print(
                f"[BaseRunner] BLE hint: {hub.legacy_reports} report(s) "
                f"from registered sensors without service data — "
                f"old firmware? flash dist/klock-sensor-*-v8.uf2",
                file=sys.stderr, flush=True,
            )

        # Render to the surface.
        t0_draw = _time.monotonic()
        self._draw()
        t1_draw = _time.monotonic()
        if (t1_draw - t0_read) > 0.5:
            print(
                f"[BaseRunner] tick breakdown: "
                f"read={(t1_read - t0_read):.2f}s "
                f"draw={(t1_draw - t0_draw):.2f}s "
                f"total={(t1_draw - t0_read):.2f}s",
                file=sys.stderr, flush=True,
            )

    async def run(self) -> None:
        raise NotImplementedError("subclass")

    def _draw(self) -> None:
        raise NotImplementedError("subclass")
