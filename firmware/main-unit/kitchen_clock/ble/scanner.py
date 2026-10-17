"""Passive-scan BLE transport (ADR 0012).

The panel never opens a GATT connection. Each sensor unit embeds
its current T/H/B in the advertising packet as Environmental
Sensing service data (UUID16 0x181A), refreshed at each 15 s
sample (see firmware/outdoor-sensor/app/src/ble.c). The hub below
runs a *filtered* BleakScanner — bluetoothd only forwards reports
for the ESS service UUID, so neighbour devices never cross D-Bus —
and every matching report is decoded into the same `SensorReading`
the GATT path produced.

Why this exists: the connect/poll model wedged BlueZ twice on the
Pi Zero W bench — first as the stale `Connected: yes` lockout
(ADR 0004 era), then as a full D-Bus saturation after hours of
15 s-timeout connect attempts plus the watchdog's `bluetoothctl`
cycling (2026-10-17 incident). Passive scanning has no connection
state to wedge: reports arrive, tiles update, and a dead radio is
just staleness the watchdog can recover by restarting the scanner.

Service-data payload (matches ble.c):
    byte  0     flags / firmware-version marker (0xNN = vNN)
    bytes 1-2   temperature, int16 LE centi-°C  (0.01 °C)
    bytes 3-4   humidity,    uint16 LE centi-%RH (0.01 %RH)
    bytes 5-6   battery,    uint16 LE raw SAADC counts
                (0 = "no data", same sentinel as the GATT char)

Decode functions are pure and unit-tested (tests/test_ble_scanner.py)
without any bluetooth hardware; the hub itself is exercised on the
bench via scripts/probe-ble-scan.py.
"""

import logging
import time
from typing import Optional, Tuple

from .bleak_client import (
    SensorReading,
    decode_battery_raw,
    decode_humidity,
    decode_temperature,
)

# 0x181A (Environmental Sensing Service) in bleak/bluez canonical
# 128-bit form — the key under which AdvertisementData.service_data
# carries our payload.
ESS_SERVICE_DATA_UUID = "0000181a-0000-1000-8000-00805f9b34fb"

# Advertisement local names are "kclock-XX"; registry names match.
NAME_PREFIX = "kclock-"

# A report older than this is surfaced as 'stale:Ns' (data still
# returned so the panel keeps the last values) and feeds the
# watchdog's staleness clock. The firmware samples every 15 s and
# advertises continuously while awake, so 30 s tolerates one
# missed sample round-trip without flapping.
FRESH_WINDOW_S = 30.0

try:
    from bleak import BleakScanner  # noqa: N813
    BLEAK_AVAILABLE = True
except ImportError:                       # noqa: F401
    BleakScanner = None                   # type: ignore
    BLEAK_AVAILABLE = False


def decode_service_data(sd):
    """Decode a 7-byte ESS service-data payload.

    Returns a dict {"flags", "temp_c", "hum_percent", "batt_raw"}
    or None when the payload is short/garbage. A battery value of
    0 keeps the GATT sentinel semantics and maps to None ("no data")
    so the runner's merge keeps the previous battery reading.
    """
    if sd is None or len(sd) < 7:
        return None
    payload = bytes(sd)
    temp_c = decode_temperature(payload[1:3])
    hum = decode_humidity(payload[3:5])
    batt = decode_battery_raw(payload[5:7])
    if temp_c is None or hum is None or batt is None:
        return None
    return {
        "flags": payload[0],
        "temp_c": temp_c,
        "hum_percent": hum,
        # 0 = firmware "no data" sentinel, same as the GATT char.
        "batt_raw": None if batt == 0 else batt,
    }


class ScannerHub:
    """Continuously-running filtered BleakScanner.

    Owns the mapping advertisement → registry sensor and the
    latest report per sensor. `start()`/`restart()` are the only
    radio-touching entry points; both are awaitables so the render
    loop is never blocked. `report_for()` and `stale_seconds()` are
    pure state reads the runner calls at render cadence.
    """

    def __init__(self, sensors):
        # sensors: iterable of (mac, name, location) tuples.
        self._sensors = list(sensors)
        self._by_mac = {
            mac.upper(): (mac, name, loc) for mac, name, loc in self._sensors
        }
        self._by_name = {
            name.lower(): (mac, name, loc) for mac, name, loc in self._sensors
        }
        # name → latest decoded reading
        self.latest: dict = {}
        # name → monotonic timestamp of last report
        self.last_seen: dict = {}
        # Adverts from our MACs/names without decodable service data —
        # old firmware on the unit. Surfaced so the journal can say
        # "flash v8" instead of just showing n/a tiles.
        self.legacy_reports: int = 0
        self.report_count: int = 0
        self._started_at: Optional[float] = None
        self._scanner = None

    async def start(self) -> None:
        """Start discovery with a server-side UUID filter.

        The filter is what keeps neighbour traffic off D-Bus:
        bluetoothd only emits reports for devices advertising the
        ESS service data. The callback re-checks name/MAC anyway so
        a spoofing phone can't feed the panel.
        """
        if BleakScanner is None:
            raise ConnectionError(
                "bleak not importable — cannot run the scanner transport",
            )
        self._scanner = BleakScanner(
            detection_callback=self._on_detection,
            service_uuids=[ESS_SERVICE_DATA_UUID],
        )
        await self._scanner.start()
        self._started_at = time.monotonic()
        logging.info(
            "ScannerHub: discovery started (filter %s)", ESS_SERVICE_DATA_UUID,
        )

    async def restart(self) -> None:
        """Stop + start the scanner — the watchdog recovery path."""
        if self._scanner is None:
            await self.start()
            return
        try:
            await self._scanner.stop()
        except Exception as exc:  # noqa: BLE001 — best effort stop
            logging.warning(
                "ScannerHub: stop before restart failed "
                "(continuing): %s: %s", type(exc).__name__, exc,
            )
        await self._scanner.start()
        logging.info("ScannerHub: discovery restarted")

    def _on_detection(self, device, advertisement_data) -> None:
        """Bleak detection callback (runs on the hub's event loop)."""
        mac = (getattr(device, "address", "") or "").upper()
        name = (getattr(advertisement_data, "local_name", None) or "").strip()
        sensor = self._by_mac.get(mac)
        if sensor is None and name:
            sensor = self._by_name.get(name.lower())
        if sensor is None:
            return

        mac_s, name_s, loc_s = sensor
        service_data = getattr(advertisement_data, "service_data", None) or {}
        sd = service_data.get(ESS_SERVICE_DATA_UUID)
        decoded = decode_service_data(sd)
        if decoded is None:
            # One of ours advertising without/short service data —
            # v7-era firmware. Count once per report; the runner
            # journals the hint.
            self.legacy_reports += 1
            return

        self.latest[name_s] = SensorReading(
            mac=mac_s, name=name_s, location=loc_s,
            raw_temp=bytes(sd)[1:3], raw_hum=bytes(sd)[3:5],
            raw_batt=bytes(sd)[5:7],
            temp_error="", hum_error="", batt_error="",
            source="live",
        )
        self.last_seen[name_s] = time.monotonic()
        self.report_count += 1

    def report_for(self, sensor) -> Tuple[Optional[SensorReading],
                                          Optional[float]]:
        """Latest reading + its age in seconds (None when never seen)."""
        _, name, _ = sensor
        reading = self.latest.get(name)
        if reading is None:
            return None, None
        seen = self.last_seen.get(name)
        age = None if seen is None else time.monotonic() - seen
        return reading, age

    def stale_seconds(self) -> float:
        """How long since ANY registered sensor last reported.

        Sensors that have never reported count from hub start, so
        a cold panel with dead radios still arms the watchdog.
        """
        now = time.monotonic()
        reference = self._started_at if self._started_at is not None else now
        worst = 0.0
        for _, name, _ in self._sensors:
            seen = self.last_seen.get(name)
            if seen is None:
                age = now - reference
            else:
                age = now - seen
            worst = max(worst, age)
        return worst

    def min_stale_seconds(self) -> float:
        """Age of the *freshest* registered sensor's last report.

        This is the watchdog's trigger: when even the best sensor
        hasn't reported for `STALE_THRESHOLD_S`, the transport itself
        (scanner / bluetoothd) is suspect — a single dead sensor unit
        does not fire it.
        """
        now = time.monotonic()
        reference = self._started_at if self._started_at is not None else now
        best = None
        for _, name, _ in self._sensors:
            seen = self.last_seen.get(name)
            age = now - (seen if seen is not None else reference)
            best = age if best is None else min(best, age)
        return 0.0 if best is None else best


class ScannerClient:
    """Drop-in `read()` client backed by the hub — no radio work.

    Returns the latest scanned report as a live reading while
    fresh; an ageing one carries source='stale:Ns' so the runner
    keeps the tile's cached values and the journal shows why.
    """

    def __init__(self, sensor, hub: ScannerHub):
        self.sensor = sensor
        self._hub = hub

    async def read(self) -> SensorReading:
        mac, name, loc = self.sensor
        reading, age = self._hub.report_for(self.sensor)
        if reading is None:
            return SensorReading(
                mac=mac, name=name, location=loc, source="no-report",
            )
        if age is not None and age > FRESH_WINDOW_S:
            return SensorReading(
                mac=reading.mac, name=reading.name, location=reading.location,
                raw_temp=reading.raw_temp, raw_hum=reading.raw_hum,
                raw_batt=reading.raw_batt,
                temp_error="", hum_error="", batt_error="",
                source=f"stale:{age:.0f}s",
            )
        return reading
