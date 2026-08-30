"""Renderer-loop helpers shared by PygameRunner and LvglRunner.

The two backends differ only on the `_draw()` side; the
"gather → draw → sleep → repeat" loop is identical, as is the
per-sensor exception fence.

Path C (ADR 0005): this file is shared across host (PyGame) and
Pi runtime (LVGL). It deliberately imports nothing from pygame or
lvgl so it stays importable from either side without side-effects.
"""
import asyncio
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
        self.last_readings = await read_all_sensors(
            self.sensors, self.cache.client_for,
        )
        self._draw()

    async def run(self) -> None:
        raise NotImplementedError("subclass")

    def _draw(self) -> None:
        raise NotImplementedError("subclass")
