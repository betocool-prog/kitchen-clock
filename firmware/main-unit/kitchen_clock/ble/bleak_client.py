"""BLE GATT service definitions, decode pipeline, and clients.

The GATT characteristic layout mirrors firmware/outdoor-sensor/app/src/ble.c.
Tests at firmware/main-unit/tests/test_ble_decode.py exercise the decode
pipeline without any bluetooth hardware.

Characteristic shape (matches ble.c):
  temperature : int16 little-endian, 0.01 °C (uint16 used to be; stay int16
                for negative rooms).
  humidity    : uint16 little-endian, 0.01 %RH.
  battery-mV  : uint16 little-endian, mV. Allowed to be empty when the firmware
                still hasn't a battery rail connected.
"""

import random
import struct
from dataclasses import dataclass
from typing import Optional

CHAR_TEMP_UUID = "00002a6e-0000-1000-8000-00805f9b34fb"
CHAR_HUM_UUID = "00002a6f-0000-1000-8000-00805f9b34fb"
SVC_KCLOCK_UUID = "6b636c6b-0001-0000-0000-0000-00000001"
CHAR_BATTMV_UUID = "6b636c6b-0001-0000-0000-0000-00000002"

TEMP_SCALE_C = 100.0   # int16 LE × 0.01 → °C
HUM_SCALE_RH = 100.0   # uint16 LE × 0.01 → %RH


def _read_int(raw, fmt):
    """Decode an integer of `fmt` from `raw`. Returns None on short reads."""
    size = struct.calcsize(fmt)
    if raw is None or len(raw) < size:
        return None
    return struct.unpack(fmt, raw[:size])[0]


def decode_temperature(raw):
    """int16 little-endian, 0.01 °C → °C. Returns None on short reads."""
    v = _read_int(raw, "<h")
    return None if v is None else v / TEMP_SCALE_C


def decode_humidity(raw):
    """uint16 little-endian, 0.01 %RH → %RH. Returns None on short reads."""
    v = _read_int(raw, "<H")
    return None if v is None else v / HUM_SCALE_RH


def decode_battery_mv(raw):
    """uint16 little-endian mV → mV. Returns None on short reads or absence."""
    return _read_int(raw, "<H")


@dataclass
class SensorReading:
    """A single decoded read-through of a bonded sensor unit."""
    mac: str
    name: str
    location: str
    raw_temp: bytes = b""
    raw_hum: bytes = b""
    raw_batt: bytes = b""
    temp_error: str = ""
    hum_error: str = ""
    batt_error: str = ""
    source: str = ""   # 'live', 'mock', 'connect-fail', ...

    @property
    def temp_c(self) -> Optional[float]:
        if self.temp_error:
            return None
        v = decode_temperature(self.raw_temp)
        return None if v is None else v

    @property
    def hum_percent(self) -> Optional[float]:
        if self.hum_error:
            return None
        v = decode_humidity(self.raw_hum)
        return None if v is None else v

    @property
    def batt_mV(self) -> Optional[int]:
        if self.batt_error:
            return None
        v = decode_battery_mv(self.raw_batt)
        return None if v is None else v


class RealBleakClient:
    """Concrete bleak-based client. Used when KITCHEN_CLOCK_BLE='live'."""

    def __init__(self, sensor):
        # sensor: a (mac, name, location) tuple
        self.sensor = sensor
        self._client = None

    async def _ensure_connected(self):
        if self._client is None:
            from bleak import BleakClient as _B
            self._client = _B(self.sensor[0])
            await self._client.__aenter__()
        return self._client

    async def read(self) -> SensorReading:
        mac, name, loc = self.sensor
        try:
            client = await self._ensure_connected()
        except Exception as e:
            return SensorReading(
                mac=mac, name=name, location=loc,
                source=f"connect-fail:{type(e).__name__}",
            )

        async def _safe_read(char_uuid):
            try:
                return bytes(await client.read_gatt_char(char_uuid)), ""
            except Exception as e:
                return b"", f"{type(e).__name__}: {e}"

        t_raw, t_err = await _safe_read(CHAR_TEMP_UUID)
        h_raw, h_err = await _safe_read(CHAR_HUM_UUID)
        b_raw, b_err = await _safe_read(CHAR_BATTMV_UUID)

        return SensorReading(
            mac=mac, name=name, location=loc,
            raw_temp=t_raw, raw_hum=h_raw, raw_batt=b_raw,
            temp_error=t_err, hum_error=h_err, batt_error=b_err,
            source="live",
        )


class MockBleakClient:
    """Synthetic reader for offline dev iteration. Emits the same byte
    format as the firmware so decode-pipeline tests stay honest."""

    def __init__(self, sensor):
        self.sensor = sensor

    async def read(self) -> SensorReading:
        mac, name, loc = self.sensor
        temp_centi = int((22 + random.uniform(-1.5, 2.0)) * TEMP_SCALE_C)
        hum_centi = int((50 + random.uniform(-5.0, 8.0)) * HUM_SCALE_RH)
        return SensorReading(
            mac=mac, name=name, location=loc,
            raw_temp=struct.pack("<h", temp_centi),
            raw_hum=struct.pack("<H", hum_centi),
            raw_batt=struct.pack("<H", 3700),
            source="mock",
        )


def make_client(sensor, mode="mock"):
    """Factory: which BLE client backs a sensor read."""
    if mode == "mock":
        return MockBleakClient(sensor)
    if mode == "live":
        return RealBleakClient(sensor)
    raise ValueError(f"unknown ble mode: {mode!r}")
