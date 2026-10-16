"""Pure-Python tests for the BLE decode pipeline and the runner loop."""
import asyncio
import struct
import time
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
    CHAR_TEMP_UUID,
    CHAR_HUM_UUID,
    SVC_KCLOCK_UUID,
    CHAR_BATTMV_UUID,
)
from kitchen_clock.runner import (
    safe_read,
    read_all_sensors,
    BLEClientCache,
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

    def test_battery_zero_is_sentinel(self):
        # Firmware currently reports 0 mV when the ADC divider
        # isn't wired. The SensorReading property surfaces that
        # as `None` (i.e. "we don't have a value yet") rather
        # than a misleading-precise 0 mV.
        r = SensorReading(
            mac="0", name="kclock-x", location="indoor",
            raw_temp=struct.pack("<h", 2150),
            raw_hum=struct.pack("<H", 5500),
            raw_batt=struct.pack("<H", 0),
        )
        self.assertIsNone(r.batt_mV)
        # The decoder itself still returns 0 so the underlying
        # value is recoverable if we ever want to branch on it.
        self.assertEqual(decode_battery_mv(r.raw_batt), 0)


class TestUuidCanonicalisation(unittest.TestCase):
    """Pin the UUID text we hand to bleak against lead-by-error
    regressions. The 4 UUIDs were verified on the Pi's actual
    GATT DB with `bleak`'s `get_services()` -- the canonical
    textual forms printed here are what bluez stores, not what
    the firmware bytes look like in C source.

      firmware byte text     bleak canonical
      ─────────────────────────────────────────
      6b636c6b-0001-…-0001   01000000-…-01006b6c636b
      6b636c6b-0001-…-0002   02000000-…-01006b6c636b
    """

    def test_service_uuid_is_canonical(self):
        self.assertEqual(
            SVC_KCLOCK_UUID,
            "01000000-0000-0000-0000-01006b6c636b",
        )

    def test_battery_uuid_is_canonical(self):
        self.assertEqual(
            CHAR_BATTMV_UUID,
            "02000000-0000-0000-0000-01006b6c636b",
        )

    def test_ess_uuids_are_standard(self):
        # The 16-bit ESS chars are identical in both forms because
        # the meaningful value lands at byte 2 not 12-15, so the
        # text is plain.
        self.assertEqual(CHAR_TEMP_UUID, "00002a6e-0000-1000-8000-00805f9b34fb")
        self.assertEqual(CHAR_HUM_UUID,  "00002a6f-0000-1000-8000-00805f9b34fb")

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


class TestRealBleakClientReconnect(unittest.TestCase):
    """RealBleakClient must clear stale state on connect/read failure
    and apply exponential backoff so the loop recovers when a
    peripheral comes back into range."""

    SENSOR = ("D0:44:B3:EE:AC:9F", "kclock-d0", "outdoor")
    CHAR_UUIDS = (CHAR_TEMP_UUID, CHAR_HUM_UUID, CHAR_BATTMV_UUID)

    def setUp(self):
        import kitchen_clock.ble.bleak_client as mod

        self._mod = mod
        self._orig_B = mod._B

    def tearDown(self):
        self._mod._B = self._orig_B

    def _stub_factory(self, aenter_raises=False, read_raises=False):
        """Build a factory that returns a stub bleak.BleakClient stub.

        The factory is installed as `mod._B`, which is what the
        production code uses to construct peripherals.
        """
        stubs = []   # captured for assertion
        outer = self

        class _Stub:
            def __init__(self, mac, **kwargs):
                self.mac = mac
                self.aenter_calls = 0
                self._aenter_raises = aenter_raises
                self._read_raises = read_raises
                self.init_kwargs = kwargs
                stubs.append(self)

            async def __aenter__(self):
                self.aenter_calls += 1
                if self._aenter_raises:
                    raise ConnectionError("stub-connection-failed")
                if not self._read_raises:
                    self.read_data = (
                        struct.pack("<h", 2150),
                        struct.pack("<H", 5500),
                        struct.pack("<H", 3700),
                    )
                return self

            async def __aexit__(self, *_):
                return None

            async def read_gatt_char(self, char_uuid):
                if self._read_raises:
                    raise ConnectionError("not connected")
                idx = outer.CHAR_UUIDS.index(char_uuid) if char_uuid in outer.CHAR_UUIDS else 0
                return self.read_data[idx]

        return _Stub, stubs

    def _new_client(self):
        return RealBleakClient(self.SENSOR)

    def test_aenter_failure_drops_client_and_starts_backoff(self):
        StubCls, stubs = self._stub_factory(aenter_raises=True)
        self._mod._B = StubCls
        rc = self._new_client()
        before = time.monotonic()
        with self.assertRaises(ConnectionError) as cm:
            asyncio.run(rc._ensure_connected())
        self.assertIn("stub-connection-failed", str(cm.exception))
        self.assertIsNone(rc._client,
                          "broken client should be dropped on connect fail")
        self.assertEqual(rc._fail_count, 1)
        # Backoff after 1 fail is 2**1 = 2 s.
        self.assertGreaterEqual(rc._next_attempt_at, before + 2.0 - 0.05)
        self.assertLessEqual(rc._next_attempt_at, before + 2.0 + 0.05)
        self.assertEqual(stubs[0].aenter_calls, 1)

    def test_cooldown_blocks_repeats_and_eventually_releases(self):
        StubCls, _stubs = self._stub_factory(aenter_raises=True)
        self._mod._B = StubCls
        rc = self._new_client()
        # Force a cooldown into the future.
        rc._fail_count = 1
        rc._next_attempt_at = time.monotonic() + 600
        rc._client = None
        with self.assertRaises(ConnectionError) as cm:
            asyncio.run(rc._ensure_connected())
        self.assertIn("in reconnect cooldown", str(cm.exception))

    def test_successful_connect_after_failures_resets_count(self):
        StubCls, stubs = self._stub_factory(aenter_raises=False)
        self._mod._B = StubCls
        rc = self._new_client()
        rc._fail_count = 5
        rc._next_attempt_at = 0.0  # allow connect
        asyncio.run(rc._ensure_connected())
        self.assertEqual(rc._fail_count, 0,
                         "successful connect should reset the fail counter")
        self.assertIsNotNone(rc._client)
        # The freshly-built stub has been used.
        self.assertEqual(stubs[-1].aenter_calls, 1)

    def test_read_failure_clears_client_and_rebuilds_on_next_tick(self):
        StubCls, stubs = self._stub_factory(aenter_raises=False,
                                            read_raises=True)
        self._mod._B = StubCls
        rc = self._new_client()
        # First read fails.
        r = asyncio.run(rc.read())
        self.assertTrue(r.temp_error.startswith("ConnectionError"))
        self.assertIsNone(rc._client,
                          "stale bleak client should not be reused after "
                          "a failed read")
        # We deliberately don't bump _fail_count on read failures —
        # the connect path is the one that triggers backoff. A flaky
        # read shouldn't put the loop into cooldown; a repeated
        # connection failure will, and that's where backoff is
        # appropriate.
        self.assertEqual(rc._fail_count, 0)
        self.assertEqual(rc._next_attempt_at, 0.0)

    def test_read_passes_through_when_connected(self):
        StubCls, _ = self._stub_factory(aenter_raises=False,
                                         read_raises=False)
        self._mod._B = StubCls
        rc = self._new_client()
        r = asyncio.run(rc.read())
        self.assertAlmostEqual(r.temp_c, 21.5)
        self.assertAlmostEqual(r.hum_percent, 55.0)
        self.assertEqual(r.batt_mV, 3700)

    def test_connect_timeout_replaces_aenter_hang(self):
        """A peripheral that swallows the connect attempt (no reply) should
        be moved on within CONNECT_TIMEOUT_S, not the bluez default 30 s."""

        class _HangingAenter:
            def __init__(self, mac, **kwargs):
                self.mac = mac

            async def __aenter__(self):
                # Sleep well past the connect timeout; the runner's
                # wait_for must catch this and surface a
                # ConnectionError instead of letting the test hang
                # on the daemon.
                await asyncio.sleep(RealBleakClient.CONNECT_TIMEOUT_S + 5)
                return self

            async def __aexit__(self, *_):
                return None

            async def read_gatt_char(self, _):
                return b""

        self._mod._B = _HangingAenter
        rc = self._new_client()
        t0 = time.monotonic()
        # Force instant first-attempt (don't bump _fail_count yet).
        rc._next_attempt_at = 0.0
        with self.assertRaises(ConnectionError) as cm:
            asyncio.run(rc._ensure_connected())
        elapsed = time.monotonic() - t0
        self.assertIn("connect >", str(cm.exception))
        self.assertLess(
            elapsed,
            RealBleakClient.CONNECT_TIMEOUT_S + 1.0,
            f"aenter hang should be capped at ~{RealBleakClient.CONNECT_TIMEOUT_S}s, "
            f"but waited {elapsed:.2f}s",
        )
        self.assertIsNone(rc._client, "broken client dropped on timeout")
        self.assertEqual(rc._fail_count, 1, "timeout increments fail_count")
        self.assertGreater(
            rc._next_attempt_at, t0,
            "backoff schedule applied after timeout",
        )

    def test_read_timeout_replaces_char_hang(self):
        """A peripheral that drops mid-GATT should not block the tick."""

        class _HungOnce:
            def __init__(self, mac, **kwargs):
                self.mac = mac

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_):
                return None

            async def read_gatt_char(self, _):
                # First temperature read hangs forever, exercise the
                # wait_for catching it.
                await asyncio.sleep(RealBleakClient.READ_TIMEOUT_S + 5)
                return b""

        self._mod._B = _HungOnce
        rc = self._new_client()
        rc._next_attempt_at = 0.0
        t0 = time.monotonic()
        r = asyncio.run(rc.read())
        elapsed = time.monotonic() - t0
        self.assertTrue(
            r.temp_error.startswith("TimeoutError"),
            f"hung read should produce TimeoutError, got: {r.temp_error!r}",
        )
        # The read() runs three char reads in series, each gated by
        # READ_TIMEOUT_S, so worst-case is 3 × timeout.
        budget = 3 * RealBleakClient.READ_TIMEOUT_S + 0.5
        self.assertLess(
            elapsed,
            budget,
            f"read hang should be capped at ~{budget:.1f}s (3 chars × "
            f"{RealBleakClient.READ_TIMEOUT_S:.1f}s), but waited "
            f"{elapsed:.2f}s",
        )
        self.assertIsNone(rc._client, "broken client dropped on read timeout")


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
    """Path A: dispatcher returns PygameRunner or FbdevRunner by env."""

    def test_default_is_fbdev(self):
        # Default (env var unset) → fbdev because the canonical
        # command path is the Pi service unit. Override → pygame
        # for host dev.
        from kitchen_clock.ui.window import make_renderer
        from kitchen_clock.ui.fbdev_window import FbdevRunner
        from kitchen_clock.ui.pygame_window import PygameRunner
        self.assertIs(make_renderer(), FbdevRunner)
        self.assertIs(make_renderer("fbdev"), FbdevRunner)
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

    def test_fbdev_window_is_importable(self):
        # Even with no PIL installed and no /dev/fb0 present, the
        # module must import. PIL is loaded lazily at __init__.
        import importlib
        mod = importlib.import_module("kitchen_clock.ui.fbdev_window")
        self.assertTrue(hasattr(mod, "FbdevRunner"))
        self.assertTrue(hasattr(mod, "discover_fb0"))
        self.assertTrue(hasattr(mod, "rgb_to_framebuffer"))

    def test_rgb_to_framebuffer_32bpp(self):
        from kitchen_clock.ui.fbdev_window import rgb_to_framebuffer
        # 1 pixel: red (255, 0, 0).
        rgb = bytes([255, 0, 0])
        out = rgb_to_framebuffer(rgb, bpp=32, width=1, height=1)
        # BGRX X-mask little-endian (Linux KMS default): B byte 0,
        # G byte 1, R byte 2, X byte 3.
        self.assertEqual(out, bytes([0x00, 0x00, 0xFF, 0x00]))

    def test_rgb_to_framebuffer_32bpp_rgbx_override(self):
        import os
        from kitchen_clock.ui.fbdev_window import rgb_to_framebuffer
        old = os.environ.get("KITCHEN_CLOCK_FB_BYTE_ORDER")
        os.environ["KITCHEN_CLOCK_FB_BYTE_ORDER"] = "RGBX"
        try:
            rgb = bytes([255, 0, 0])
            out = rgb_to_framebuffer(rgb, bpp=32, width=1, height=1)
            # RGBX: R byte 0, G byte 1, B byte 2, X byte 3.
            self.assertEqual(out, bytes([0xFF, 0x00, 0x00, 0x00]))
        finally:
            if old is None:
                os.environ.pop("KITCHEN_CLOCK_FB_BYTE_ORDER", None)
            else:
                os.environ["KITCHEN_CLOCK_FB_BYTE_ORDER"] = old

    def test_rgb_to_framebuffer_16bpp(self):
        from kitchen_clock.ui.fbdev_window import rgb_to_framebuffer
        rgb = bytes([255, 0, 0])
        out = rgb_to_framebuffer(rgb, bpp=16, width=1, height=1)
        # RGB565 with r=255 (max), g=0, b=0:
        #   v = ((255 & 0xF8) << 8) | ((0 & 0xFC) << 3) | (0 >> 3)
        #     = 0xF800
        self.assertEqual(out, bytes([0x00, 0xF8]))


class TestRunnerRenderCache(unittest.TestCase):
    """`BaseRunner` keeps a stable `last_readings` so a single failed
    BLE tick doesn't blank a tile's last live value.
    """

    class _NullRunner:
        from kitchen_clock.runner import BaseRunner as _Base

        def __init__(self, sensors):
            self.sensors = list(sensors)
            self.period_s = 0.1
            self.last_readings = [None] * len(sensors)
            self.current_readings = [None] * len(sensors)
            self._ble_tick_counter = 0

        # Reuse BaseRunner._tick, but stub the renderer so the
        # test doesn't import pygame or open /dev/fb0.
        async def _tick(self):
            from kitchen_clock.runner import BaseRunner
            return await BaseRunner._tick(self)

        def _draw(self):
            pass

    def _reading(self, location, source, T=None, H=None, B=None):
        r = SensorReading(
            mac="00:00:00:00:00:00", name="k-" + location, location=location,
            source=source,
        )
        if T is not None:
            r.raw_temp = struct.pack("<h", int(T * 100))
        if H is not None:
            r.raw_hum = struct.pack("<H", int(H * 100))
        if B is not None:
            r.raw_batt = struct.pack("<H", int(B))
        return r

    def test_live_promoted_to_render_cache(self):
        sensors = [("11", "k1", "outdoor"), ("22", "k2", "indoor")]
        runner = self._NullRunner(sensors)
        live_outdoor = self._reading("outdoor", "live", T=21.5, H=40.)
        live_indoor = self._reading("indoor", "live", T=22.5, H=60.)
        queued_by_location = {
            "outdoor": [live_outdoor],
            "indoor": [live_indoor],
        }
        runner.cache = BLEClientCache(
            lambda s: _StubClient(queued_by_location[s[2]]),
        )

        asyncio.run(runner._tick())
        self.assertEqual(runner.current_readings[0].source, "live")
        self.assertEqual(runner.current_readings[1].source, "live")
        self.assertAlmostEqual(runner.last_readings[0].temp_c, 21.5)
        self.assertAlmostEqual(runner.last_readings[1].hum_percent, 60.0)

    def test_failing_tick_keeps_live_cache(self):
        sensors = [("11", "k1", "outdoor"), ("22", "k2", "indoor")]
        runner = self._NullRunner(sensors)
        live_outdoor_v1 = self._reading("outdoor", "live", T=21.5, H=40.)
        live_indoor_v1 = self._reading("indoor", "live", T=22.5, H=60.)
        queued = {
            "outdoor": [live_outdoor_v1],
            "indoor": [live_indoor_v1],
        }
        runner.cache = BLEClientCache(lambda s: _StubClient(queued[s[2]]))

        # First tick: both tiles succeed; cache populated.
        asyncio.run(runner._tick())
        self.assertEqual(runner.last_readings[0].temp_c, 21.5)
        self.assertEqual(runner.last_readings[1].temp_c, 22.5)
        # Second tick: outdoor fails; indoor succeeds with new values.
        fail_outdoor = self._reading(
            "outdoor", "connect-fail:ConnectionError",
        )
        new_indoor = self._reading("indoor", "live", T=23.0, H=58.)
        queued = {
            "outdoor": [fail_outdoor],
            "indoor": [new_indoor],
        }
        runner.cache = BLEClientCache(lambda s: _StubClient(queued[s[2]]))

        asyncio.run(runner._tick())
        # current reflects the attempt:
        self.assertEqual(
            runner.current_readings[0].source,
            "connect-fail:ConnectionError",
        )
        self.assertEqual(runner.current_readings[1].source, "live")
        # last_readings is unchanged for the failing sensor:
        self.assertEqual(
            runner.last_readings[0].temp_c, 21.5,
            "outdoor cache should be retained across failure",
        )
        # and is updated for the new indoor reading:
        self.assertEqual(runner.last_readings[1].temp_c, 23.0)

    def test_initial_state_renders_placeholder(self):
        sensors = [("11", "k1", "outdoor")]
        runner = self._NullRunner(sensors)
        fail = self._reading("outdoor", "connect-fail:ConnectionError")
        runner.cache = BLEClientCache(lambda s: _StubClient([fail]))

        asyncio.run(runner._tick())
        self.assertIsNone(
            runner.last_readings[0],
            "no live reading ever means last_readings[0] stays None",
        )


class _StubClient:
    """Helper: returns the queued readings, one per read() call."""

    def __init__(self, queue):
        self._q = list(queue)
        # Sensor tuple shape: (mac, name, location). Pick the
        # location off of the first reading so the runner pairing
        # works without re-keying.
        first = self._q[0]
        self.sensor = (first.mac, first.name, first.location)

    async def read(self):
        return self._q.pop(0)


if __name__ == "__main__":    unittest.main()
