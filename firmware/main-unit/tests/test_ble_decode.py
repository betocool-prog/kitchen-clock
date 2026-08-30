"""Pure-Python tests for the BLE decode pipeline and the runner loop."""
import asyncio
import struct
import unittest
from unittest.mock import MagicMock

from kitchen_clock.ble.bleak_client import (
    decode_temperature,
    decode_humidity,
    decode_battery_mv,
    SensorReading,
    MockBleakClient,
    RealBleakClient,
    make_client,
)
from kitchen_clock.runner import (
    safe_read,
    read_all_sensors,
    BLEClientCache,
)


class TestDecode(unittest.TestCase):
    def test_temperature_22_5(self):
        self.assertAlmostEqual(decode_temperature(struct.pack("<h", 2250)), 22.5)

    def test_temperature_negative(self):
        self.assertAlmostEqual(decode_temperature(struct.pack("<h", -1500)), -15.0)

    def test_temperature_zero(self):
        self.assertAlmostEqual(decode_temperature(struct.pack("<h", 0)), 0.0)

    def test_temperature_short(self):
        self.assertIsNone(decode_temperature(b""))
        self.assertIsNone(decode_temperature(b"\x00"))

    def test_temperature_invalid_min(self):
        # int16 minimum: -32768 → -327.68 °C
        self.assertAlmostEqual(decode_temperature(struct.pack("<h", -32768)), -327.68)

    def test_humidity_50(self):
        self.assertAlmostEqual(decode_humidity(struct.pack("<H", 5000)), 50.0)

    def test_humidity_max(self):
        self.assertAlmostEqual(decode_humidity(struct.pack("<H", 65535)), 655.35)

    def test_humidity_short(self):
        self.assertIsNone(decode_humidity(b""))
        self.assertIsNone(decode_humidity(b"\x00"))

    def test_battery_3700(self):
        self.assertEqual(decode_battery_mv(struct.pack("<H", 3700)), 3700)

    def test_battery_short(self):
        self.assertIsNone(decode_battery_mv(b""))
        self.assertIsNone(decode_battery_mv(b"\x00"))

    def test_sensor_reading_props(self):
        r = SensorReading(
            mac="0", name="kclock-x", location="indoor",
            raw_temp=struct.pack("<h", 2150),
            raw_hum=struct.pack("<H", 5500),
            raw_batt=struct.pack("<H", 3500),
        )
        self.assertAlmostEqual(r.temp_c, 21.5)
        self.assertAlmostEqual(r.hum_percent, 55.0)
        self.assertEqual(r.batt_mV, 3500)

    def test_sensor_reading_no_data(self):
        r = SensorReading(mac="0", name="kclock-x", location="indoor")
        self.assertIsNone(r.temp_c)
        self.assertIsNone(r.hum_percent)
        self.assertIsNone(r.batt_mV)

    def test_sensor_reading_error_path(self):
        r = SensorReading(
            mac="0", name="kclock-x", location="indoor",
            raw_temp=struct.pack("<h", 2250),
            temp_error="BleakError: timeout",
        )
        self.assertIsNone(r.temp_c)
        self.assertIsNone(r.batt_mV)


class TestMockClient(unittest.TestCase):
    def test_mock_returns_reading(self):
        sensor = ("FF:FF:FF:FF:FF:FF", "kclock-mock", "mock")
        c = MockBleakClient(sensor)
        r = asyncio.run(c.read())
        self.assertEqual(r.mac, sensor[0])
        self.assertEqual(r.location, "mock")
        self.assertEqual(r.source, "mock")
        # mock emits ±1.5 °C around 22.0°C and ±5/+8 %RH around 50.0%.
        # We assert against the integer-scaled (centi-) values, not
        # the decoded float, because our decode is exercised in
        # the boundary tests above.
        temp_centi = struct.unpack("<h", r.raw_temp)[0]
        hum_centi = struct.unpack("<H", r.raw_hum)[0]
        self.assertGreater(temp_centi, 2050)   # 20.50..24.00 °C
        self.assertLess(temp_centi, 2400)
        self.assertGreater(hum_centi, 4500)    # 45.00..58.00 %RH
        self.assertLess(hum_centi, 5800)
        self.assertEqual(decode_battery_mv(r.raw_batt), 3700)

    def test_make_client_mock(self):
        c = make_client(("AA:BB:CC:DD:EE:FF", "kclock-z", "indoor"), mode="mock")
        self.assertIs(type(c), MockBleakClient)

    def test_make_client_live(self):
        c = make_client(("AA:BB:CC:DD:EE:FF", "kclock-z", "indoor"), mode="live")
        self.assertIs(type(c), RealBleakClient)

    def test_make_client_unknown(self):
        with self.assertRaises(ValueError):
            make_client(("AA:BB:CC:DD:EE:FF", "kclock-z", "indoor"), mode="bogus")


class TestSafeRead(unittest.TestCase):
    def test_passes_through_success(self):
        c = MockBleakClient(("11:22", "klock-A", "indoor"))
        r = asyncio.run(safe_read(c))
        self.assertEqual(r.mac, "11:22")
        self.assertEqual(r.source, "mock")

    def test_captures_runtime_error(self):
        class Boom:
            sensor = ("ff:ff", "kclk-b", "outdoor")
            async def read(self):
                raise RuntimeError("kaboom")
        r = asyncio.run(safe_read(Boom()))
        self.assertEqual(r.mac, "ff:ff")
        self.assertEqual(r.location, "outdoor")
        self.assertIn("kaboom", r.source)


class TestConcurrentReads(unittest.TestCase):
    def test_preserves_input_order(self):
        sensors = [
            ("aa:bb", "kclock-A", "indoor"),
            ("cc:dd", "kclock-B", "outdoor"),
            ("ee:ff", "kclock-C", "indoor"),
        ]
        factory = lambda s: MockBleakClient(s)
        out = asyncio.run(read_all_sensors(sensors, factory))
        self.assertEqual([r.mac for r in out], ["aa:bb", "cc:dd", "ee:ff"])
        for r in out:
            self.assertEqual(r.source, "mock")

    def test_one_exception_does_not_stop_others(self):
        good_sensor = ("11:22:33:44:55:66", "kclock-good", "indoor")
        bad_sensor = ("aa:bb:cc:dd:ee:ff", "kclock-bad", "outdoor")

        class Explody:
            sensor = bad_sensor
            async def read(self):
                raise RuntimeError("BLE down")

        def factory(s):
            return Explody() if s == bad_sensor else MockBleakClient(good_sensor)

        out = asyncio.run(read_all_sensors([good_sensor, bad_sensor], factory))
        self.assertEqual(len(out), 2)
        # outdoor (bad) is at index 1 in the sensors list
        self.assertEqual(out[0].source, "mock")
        self.assertEqual(out[0].location, "indoor")
        self.assertIn("BLE down", out[1].source)
        self.assertEqual(out[1].location, "outdoor")

    def test_empty_sensor_list(self):
        out = asyncio.run(read_all_sensors([], lambda s: MockBleakClient(s)))
        self.assertEqual(out, [])

    def test_repeated_runs_use_factory_each_tick(self):
        # unlike the BLEClientCache, this helper does *not* memoize;
        # the renderer layer is expected to provide a memoized
        # factory wrapper if it wants persistent GATT connections.
        # Here we just confirm the factory is called twice for two
        # ticks.
        ticks = []
        sensors = [("aa:bb", "kclock-A", "indoor")]

        def factory(s):
            ticks.append(s)
            return MockBleakClient(s)

        asyncio.run(read_all_sensors(sensors, factory))
        asyncio.run(read_all_sensors(sensors, factory))
        self.assertEqual(len(ticks), 2)


class TestBLEClientCache(unittest.TestCase):
    def test_caches_per_sensor(self):
        sensor = ("11:22", "k-A", "indoor")
        factory = MagicMock(return_value=object())
        cache = BLEClientCache(factory)
        c1 = cache.client_for(sensor)
        c2 = cache.client_for(sensor)
        factory.assert_called_once_with(sensor)
        self.assertIs(c1, c2)

    def test_distinct_sensors_get_distinct_clients(self):
        s1 = ("11:22", "k-A", "indoor")
        s2 = ("33:44", "k-B", "outdoor")
        factory = MagicMock(side_effect=lambda s: object())
        cache = BLEClientCache(factory)
        self.assertIsNot(cache.client_for(s1), cache.client_for(s2))

    def test_len(self):
        factory = MagicMock(side_effect=lambda s: object())
        cache = BLEClientCache(factory)
        cache.client_for(("11:22", "k-A", "indoor"))
        cache.client_for(("33:44", "k-B", "outdoor"))
        self.assertEqual(len(cache), 2)


class TestRendererDispatch(unittest.TestCase):
    """Path A: dispatcher returns PygameRunner unconditionally."""

    def test_default_is_pygame(self):
        from kitchen_clock.ui.window import make_renderer
        from kitchen_clock.ui.pygame_window import PygameRunner
        self.assertIs(make_renderer(), PygameRunner)
        self.assertIs(make_renderer("pygame"), PygameRunner)

    def test_unknown_renderer_raises(self):
        from kitchen_clock.ui.window import make_renderer
        with self.assertRaises(ValueError):
            make_renderer("lvgl")
        with self.assertRaises(ValueError):
            make_renderer("bogus")

    def test_lvgl_window_module_is_gone(self):
        # Path A removes the lvgl module outright; a stray import
        # path should fail with ImportError, not be a soft deprecation.
        import importlib
        with self.assertRaises(ImportError):
            importlib.import_module("kitchen_clock.ui.lvgl_window")


if __name__ == "__main__":
    unittest.main()
