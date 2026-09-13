"""Renderer-loop helpers shared by PygameRunner and LvglRunner.

The two backends differ only on the `_draw()` side; the
"gather → draw → sleep → repeat" loop is identical, as is the
per-sensor exception fence.

Path A (ADR 0011): this file is shared across host (PyGame) and
Pi runtime (FbdevRunner). It deliberately imports nothing from
pygame so it stays importable from either side without side-effects.
"""
import asyncio
import time as _time
from typing import Callable, List, Tuple

from .ble.bleak_client import SensorReading

SensorTuple = Tuple[str, str, str]


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
    """Concurrent GATT reads, one per sensor. Preserves input order.

    Exceptions in any sensor's pipeline are caught per-sensor so a
    single peripheral going dark does not stall the rest of the
    dashboard. Output list has length == len(sensors).
    """
    clients = [(s, client_factory(s)) for s in sensors]
    tasks = [safe_read(c) for _, c in clients]
    return list(await asyncio.gather(*tasks))


class BLEClientCache:
    """Memoize BLE clients per sensor tuple so we don't churn GATT
    connections every tick.
    """

    def __init__(self, factory: Callable[[SensorTuple], object]):
        self._factory = factory
        self._cache: dict = {}

    def client_for(self, sensor: SensorTuple):
        if sensor not in self._cache:
            self._cache[sensor] = self._factory(sensor)
        return self._cache[sensor]

    def __len__(self) -> int:
        return len(self._cache)


class BaseRunner:
    """Common "gather → draw → sleep → repeat" loop.

    Concrete subclasses implement:
      - `run()`     (event-loop glue: pygame event pump, lvgl tick, etc.)
      - `_draw()`   (surface rendering)

    Both subclasses share:
      - per-tick concurrent GATT reads via `read_all_sensors`
      - per-sensor exception fence via `safe_read`
      - BLE-client caching via `BLEClientCache`
    """

    def __init__(self, *, make_client, sensors, period_s: float = 2.0):
        self.cache = BLEClientCache(make_client)
        self.sensors = list(sensors)
        self.period_s = period_s
        self.last_readings: list = [None] * len(self.sensors)

    async def _tick(self) -> None:
        import sys
        t0_read = _time.monotonic()
        self.last_readings = await read_all_sensors(
            self.sensors, self.cache.client_for,
        )
        t1_read = _time.monotonic()
        # Compact one-line BLE state summary — gives journalctl a
        # way to see whether each tile is producing live readings or
        # sitting on connect-fail / per-character errors. Don't roof
        # the journal: a tick is ~0.3 s, so 3 lines/s is fine.
        try:
            tick_n = getattr(self, "_ble_tick_counter", 0) + 1
            self._ble_tick_counter = tick_n
            states = " ".join(
                f"{r.location}={r.source.split(':', 1)[0]}"
                f":T={r.temp_c if isinstance(r.temp_c, (int, float)) else '-'}"
                f":H={r.hum_percent if isinstance(r.hum_percent, (int, float)) else '-'}"
                f":B={r.batt_mV if isinstance(r.batt_mV, int) else '-'}"
                for r in self.last_readings
            )
            print(
                f"[BaseRunner] tick #{tick_n} state: {states}",
                file=sys.stderr, flush=True,
            )
        except Exception:
            pass
        # Highlight non-live / non-mock states with the raw source
        # string sojourners can grep for the full exception at the
        # next layer down (e.g. "ModulationError: ...").
        for r in self.last_readings:
            if r.source not in ("live", "mock"):
                print(
                    f"[BaseRunner] BLE diag[{r.location}]: "
                    f"mac={r.mac} source={r.source}",
                    file=sys.stderr, flush=True,
                )
        # Render to the surface.
        t0_draw = _time.monotonic()
        self._draw()
        t1_draw = _time.monotonic()
        # Slow-tick diagnostic: bump the threshold once per tick to
        # see breakdown when something regresses.
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
