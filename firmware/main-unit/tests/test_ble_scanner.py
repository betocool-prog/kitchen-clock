"""Tests for the passive-scan transport (ADR 0012).

Covers the pure pieces — ESS service-data decode, render-cache
merge, hub mapping/staleness, and the hub-backed client — without
any bluetooth hardware. The bleak types are duck-typed with
SimpleNamespace so the suite runs wherever the package is
importable.
"""
import struct
import time
import unittest
from types import SimpleNamespace

from kitchen_clock.ble.scanner import (
    ESS_SERVICE_DATA_UUID,
    FRESH_WINDOW_S,
    ScannerClient,
    ScannerHub,
    decode_service_data,
)
from kitchen_clock.runner import _any_field_ok, merge_reading


def make_payload(flags=0x08, temp_centi=2258, hum_centi=6009,
                 batt_mv=1109):
    return struct.pack("<BhhH", flags, temp_centi, hum_centi, batt_mv)


class TestDecodeServiceData(unittest.TestCase):
    def test_valid_payload_decodes_all_fields(self):
        d = decode_service_data(make_payload())
        self.assertEqual(d["flags"], 0x08)
        self.assertAlmostEqual(d["temp_c"], 22.58)
        self.assertAlmostEqual(d["hum_percent"], 60.09)
        self.assertEqual(d["batt_mv"], 1109)

    def test_negative_temperature(self):
        d = decode_service_data(make_payload(temp_centi=-550))
        self.assertAlmostEqual(d["temp_c"], -5.5)

    def test_battery_sentinel_zero_maps_to_none(self):
        d = decode_service_data(make_payload(batt_mv=0))
        self.assertIsNone(d["batt_mv"])
        self.assertAlmostEqual(d["temp_c"], 22.58)

    def test_short_payload_is_none(self):
        self.assertIsNone(decode_service_data(make_payload()[:6]))

    def test_none_is_none(self):
        self.assertIsNone(decode_service_data(None))


def fake_device(address):
    return SimpleNamespace(address=address)


def fake_advert(name, sd_payload=None):
    sd = {} if sd_payload is None else {ESS_SERVICE_DATA_UUID: sd_payload}
    return SimpleNamespace(local_name=name, service_data=sd)


SENSORS = (
    ("D0:44:B3:EE:AC:9F", "kclock-d0", "outdoor"),
    ("D3:B3:63:7C:F2:30", "kclock-d3", "indoor"),
)


class TestScannerHub(unittest.TestCase):
    def test_report_lands_via_mac(self):
        hub = ScannerHub(SENSORS)
        hub._on_detection(
            fake_device("D0:44:B3:EE:AC:9F"),
            fake_advert("kclock-d0", make_payload()),
        )
        r, age = hub.report_for(SENSORS[0])
        self.assertIsNotNone(r)
        self.assertEqual(r.source, "live")
        self.assertIsNotNone(age)
        self.assertAlmostEqual(r.temp_c, 22.58, places=2)
        self.assertAlmostEqual(r.hum_percent, 60.09, places=2)
        self.assertEqual(r.batt_mv, 1109)
        self.assertEqual(hub.report_count, 1)

    def test_report_lands_via_name_when_mac_unknown(self):
        hub = ScannerHub(SENSORS)
        hub._on_detection(
            fake_device("AA:BB:CC:DD:EE:FF"),
            fake_advert("kclock-d3", make_payload()),
        )
        r, _ = hub.report_for(SENSORS[1])
        self.assertIsNotNone(r)
        self.assertAlmostEqual(r.temp_c, 22.58, places=2)

    def test_unregistered_device_ignored(self):
        hub = ScannerHub(SENSORS)
        hub._on_detection(
            fake_device("AA:BB:CC:DD:EE:FF"),
            fake_advert("some-phone", make_payload()),
        )
        self.assertEqual(hub.report_count, 0)
        self.assertEqual(hub.latest, {})

    def test_legacy_firmware_counts_and_does_not_promote(self):
        hub = ScannerHub(SENSORS)
        hub._on_detection(
            fake_device("D0:44:B3:EE:AC:9F"),
            fake_advert("kclock-d0", sd_payload=None),
        )
        self.assertEqual(hub.legacy_reports, 1)
        self.assertEqual(hub.report_count, 0)
        r, _ = hub.report_for(SENSORS[0])
        self.assertIsNone(r)

    def test_staleness_clocks(self):
        hub = ScannerHub(SENSORS)
        now = time.monotonic()
        hub._started_at = now - 100.0
        # Nothing seen: both metrics count from start.
        self.assertAlmostEqual(hub.min_stale_seconds(), 100.0, delta=1.0)
        self.assertAlmostEqual(hub.stale_seconds(), 100.0, delta=1.0)
        # One sensor fresh: min (freshest) collapses, max stays.
        hub.last_seen["kclock-d0"] = now - 1.0
        self.assertLess(hub.min_stale_seconds(), 2.0)
        self.assertGreater(hub.stale_seconds(), 90.0)


class TestScannerClient(unittest.TestCase):
    def test_no_report_yet(self):
        hub = ScannerHub(SENSORS)
        client = ScannerClient(SENSORS[0], hub)
        r = asyncio_run(client.read())
        self.assertEqual(r.source, "no-report")
        self.assertFalse(_any_field_ok(r))

    def test_fresh_report_is_live(self):
        hub = ScannerHub(SENSORS)
        hub._on_detection(
            fake_device("D0:44:B3:EE:AC:9F"),
            fake_advert("kclock-d0", make_payload()),
        )
        client = ScannerClient(SENSORS[0], hub)
        r = asyncio_run(client.read())
        self.assertEqual(r.source, "live")
        self.assertAlmostEqual(r.temp_c, 22.58, places=2)

    def test_stale_report_keeps_data_but_marks_source(self):
        hub = ScannerHub(SENSORS)
        hub._on_detection(
            fake_device("D0:44:B3:EE:AC:9F"),
            fake_advert("kclock-d0", make_payload()),
        )
        # Age the report past the fresh window.
        hub.last_seen["kclock-d0"] = (
            time.monotonic() - (FRESH_WINDOW_S + 15.0)
        )
        client = ScannerClient(SENSORS[0], hub)
        r = asyncio_run(client.read())
        self.assertTrue(r.source.startswith("stale:"))
        self.assertAlmostEqual(r.temp_c, 22.58, places=2)


class TestMergeReading(unittest.TestCase):
    def test_first_reading_passes_through(self):
        new = ScannerHub(SENSORS).latest.get("x")  # None → exercise None-old
        reading = _mk_reading(temp=2258, hum=6009, batt=1109)
        merged = merge_reading(new, reading)
        self.assertEqual(merged.raw_temp, struct.pack("<h", 2258))
        self.assertEqual(merged.batt_mv, 1109)

    def test_failed_field_keeps_previous_value(self):
        old = _mk_reading(temp=2258, hum=6009, batt=1109)
        # New report: fresh temp, battery read failed (empty raw).
        new = _mk_reading(temp=2350, hum=6100, batt=None,
                           batt_mv=b"", batt_error="TimeoutError")
        merged = merge_reading(old, new)
        self.assertEqual(merged.temp_c, 23.5)
        self.assertEqual(merged.hum_percent, 61.0)
        # Battery keeps the old good raw bytes.
        self.assertEqual(merged.batt_mv, 1109)
        self.assertEqual(merged.batt_error, "")

    def test_battery_sentinel_refreshes_to_n_a(self):
        # A fresh report with the 0 sentinel updates the battery
        # slot to "no data" rather than freezing the old value —
        # honest about the ADC's current state.
        old = _mk_reading(temp=2258, hum=6009, batt=1109)
        new = _mk_reading(temp=2350, hum=6100, batt=0)
        merged = merge_reading(old, new)
        self.assertEqual(merged.temp_c, 23.5)
        self.assertIsNone(merged.batt_mv)


def _mk_reading(temp=None, hum=None, batt=None,
                batt_mv=None, batt_error=""):
    from kitchen_clock.ble.bleak_client import SensorReading
    raw_t = b"" if temp is None else struct.pack("<h", temp)
    raw_h = b"" if hum is None else struct.pack("<H", hum)
    if batt_mv is None:
        raw_b = b"" if batt is None else struct.pack("<H", batt)
    else:
        raw_b = batt_mv
    return SensorReading(
        mac="D0:44:B3:EE:AC:9F", name="kclock-d0", location="outdoor",
        raw_temp=raw_t, raw_hum=raw_h, raw_batt=raw_b,
        batt_error=batt_error, source="live",
    )


def asyncio_run(coro):
    import asyncio
    return asyncio.run(coro)


if __name__ == "__main__":
    unittest.main()
