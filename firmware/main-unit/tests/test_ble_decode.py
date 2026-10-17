"""Pure-Python tests for the BLE decode pipeline and the runner loop."""
import asyncio
import struct
import time
import unittest
from unittest.mock import MagicMock, patch

from kitchen_clock.ble.bleak_client import (
    decode_temperature,
    decode_humidity,
    decode_battery_raw,
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
        self.assertEqual(decode_battery_raw(struct.pack("<H", 3700)), 3700)

    def test_battery_short(self):
        self.assertIsNone(decode_battery_raw(b""))
        self.assertIsNone(decode_battery_raw(b"\x00"))

    def test_battery_zero_is_sentinel(self):
        # Firmware currently reports 0 ADC counts when the
        # divider / ADC pin hasn't reported a meaningful
        # voltage yet. The SensorReading property surfaces
        # that as `None` (i.e. "we don't have a value yet")
        # rather than a misleading-precise 0 ADC.
        r = SensorReading(
            mac="0", name="kclock-x", location="indoor",
            raw_temp=struct.pack("<h", 2150),
            raw_hum=struct.pack("<H", 5500),
            raw_batt=struct.pack("<H", 0),
        )
        self.assertIsNone(r.batt_raw)
        # Decoder itself still returns 0 so a future firmware
        # change that supplies a real reading propagates cleanly.
        self.assertEqual(decode_battery_raw(r.raw_batt), 0)


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
        self.assertEqual(r.batt_raw, 3500)

    def test_sensor_reading_no_data(self):
        r = SensorReading(mac="0", name="kclock-x", location="indoor")
        self.assertIsNone(r.temp_c)
        self.assertIsNone(r.hum_percent)
        self.assertIsNone(r.batt_raw)

    def test_sensor_reading_error_path(self):
        r = SensorReading(
            mac="0", name="kclock-x", location="indoor",
            raw_temp=struct.pack("<h", 2250),
            temp_error="BleakError: timeout",
        )
        self.assertIsNone(r.temp_c)
        self.assertIsNone(r.batt_raw)


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
        self.assertEqual(decode_battery_raw(r.raw_batt), 3700)

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

    def test_reset_backoff_clears_fail_count_and_client(self):
        """`reset_backoff()` (called after a bluetooth.service
        watchdog cycle) must force-clear cached state so the next
        `read()` goes live at once, instead of honouring the
        exponential backoff schedule.
        """
        rc = self._new_client()
        # Plant a worst-case backoff: 5 fails in a row would
        # have set cooldown near the 60 s ceiling.
        rc._fail_count = 6
        rc._next_attempt_at = time.monotonic() + 60.0
        rc._client = object()   # sentinel for "any cached client"

        rc.reset_backoff()

        self.assertEqual(rc._fail_count, 0)
        self.assertEqual(rc._next_attempt_at, 0.0)
        self.assertIsNone(
            rc._client,
            "calling reset_backoff must drop the cached _client so "
            "the next read() builds a fresh BleakClient instance",
        )

    def test_reset_backoff_actually_unblocks_next_read(self):
        """After reset_backoff the next read attempt goes live
        immediately instead of waiting out `_next_attempt_at`.
        """
        StubCls, _ = self._stub_factory(aenter_raises=False)
        self._mod._B = StubCls
        rc = self._new_client()
        # Plant backoff far in the future.
        rc._fail_count = 6
        rc._next_attempt_at = time.monotonic() + 600.0
        rc.reset_backoff()
        # Without reset_backoff this would raise ConnectionError.
        r = asyncio.run(rc.read())
        self.assertIn(r.source, ("live",),
            "post-reset read should connect, not stay in backoff")

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
        self.assertEqual(r.batt_raw, 3700)

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
    BLE tick doesn't blank a tile's last live value. Also exercises
    the BLE watchdog bookkeeping: a sequence of all-failing ticks
    triggers `maybe_restart_bluetooth` at the threshold.
    """

    class _NullRunner:
        from kitchen_clock.runner import BaseRunner as _Base

        def __init__(self, sensors):
            self.sensors = list(sensors)
            self.period_s = 0.1
            self.last_readings = [None] * len(sensors)
            self.current_readings = [None] * len(sensors)
            self._ble_tick_counter = 0
            self._no_live_ticks = 0

        # Reuse BaseRunner._tick, but stub the renderer so the
        # test doesn't import pygame or open /dev/fb0.
        async def _tick(self):
            from kitchen_clock.runner import BaseRunner
            return await BaseRunner._tick(self)

        def _draw(self):
            pass

    def _reading(self, location, source, T=None, H=None, B=None,
                T_err=None, H_err=None, B_err=None):
        """Build a SensorReading with per-characteristic values or
        error strings. Pass `T=22.5` for a successful T read;
        pass `T_err="TimeoutError: > 2.0s"` for a timed-out T.
        Same for H and B.
        """
        r = SensorReading(
            mac="00:00:00:00:00:00", name="k-" + location, location=location,
            source=source,
        )
        if T_err is not None:
            r.temp_error = T_err
            r.raw_temp  = b""
        elif T is not None:
            r.raw_temp = struct.pack("<h", int(T * 100))
        if H_err is not None:
            r.hum_error = H_err
            r.raw_hum   = b""
        elif H is not None:
            r.raw_hum = struct.pack("<H", int(H * 100))
        if B_err is not None:
            r.batt_error = B_err
            r.raw_batt   = b""
        elif B is not None:
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


class TestRunnerWatchdog(unittest.TestCase):
    """`BaseRunner` triggers the BLE watchdog after
    `FAIL_TICK_THRESHOLD` consecutive ticks where no fresh live
    reading landed. We mock the watchdog itself so a unit-test
    run doesn't spawn a dbus subprocess.
    """

    def _NullRunner(self, sensors):
        from kitchen_clock.runner import BaseRunner
        from kitchen_clock.ble.bleak_client import SensorReading

        outer = self

        class _Run(BaseRunner):
            async def _tick(self):
                return await BaseRunner._tick(self)
            def _draw(self):
                pass

        r = _Run(
            make_client=lambda s: _StubClient_with_self(s, self),
            sensors=sensors, period_s=0.0,
        )
        r.queue = lambda: outer.queue
        return r

    def setUp(self):
        self.queue = []
        # Patch the watchdog module function the runner imports.
        # The runner imports `maybe_reset_ble_locks` and the
        # threshold constant from `kitchen_clock.ble.watchdog`.
        self.patcher = patch("kitchen_clock.runner.maybe_reset_ble_locks")
        self.mock_watch = self.patcher.start()

    def tearDown(self):
        self.patcher.stop()

    def _reading(self, location, source, T=None, H=None, B=None,
                T_err=None, H_err=None, B_err=None):
        """Mirror of `TestRunnerRenderCache._reading`. Build a
    SensorReading with optional per-characteristic value or
    error string."""
        r = SensorReading(
            mac="00", name="k-" + location, location=location,
            source=source,
        )
        if T_err is not None:
            r.temp_error = T_err
            r.raw_temp  = b""
        elif T is not None:
            r.raw_temp = struct.pack("<h", int(T * 100))
        if H_err is not None:
            r.hum_error = H_err
            r.raw_hum   = b""
        elif H is not None:
            r.raw_hum = struct.pack("<H", int(H * 100))
        if B_err is not None:
            r.batt_error = B_err
            r.raw_batt   = b""
        elif B is not None:
            r.raw_batt = struct.pack("<H", int(B))
        return r

    def test_no_live_ticks_counter_accumulates(self):
        sensors = [("11", "k-x", "outdoor")]
        runner = self._NullRunner(sensors)
        fail = [self._reading("outdoor", "connect-fail:ConnectionError")]
        runner.cache = BLEClientCache(lambda s: _StubClient(fail))
        for _ in range(3):
            asyncio.run(runner._tick())
        self.assertEqual(runner._no_live_ticks, 3)
        self.assertEqual(self.mock_watch.call_count, 0,
            "below threshold no watchdog")

    def test_watchdog_resets_cached_client_backoffs(self):
        """After the watchdog fires, every cached ble client must
        have its `_fail_count`, `_next_attempt_at` and cached
        `_client` cleared — the runner calls
        `cache.reset_backoffs()` in that path.  We check that
        the call fans out across all cached clients and that
        post-reset the next read goes live at once.
        """
        import time as _t
        sensors = [("11", "k-x", "outdoor")]
        runner = self._NullRunner(sensors)
        # Build a cache with two real RealBleakClient entries and
        # plant a worst-case cooldown on each.
        from kitchen_clock.ble.bleak_client import RealBleakClient

        clients = [
            RealBleakClient(("11", "k-x", "outdoor")),
            RealBleakClient(("12", "k-y", "indoor")),
        ]
        runner.cache._cache = {
            sensors[0]: clients[0],
            ("12", "k-y", "indoor"): clients[1],
        }
        # Plant dangerous state.
        now = _t.monotonic()
        for c in clients:
            c._fail_count = 6
            c._next_attempt_at = now + 600.0
            c._client = object()

        # Simulate the runner's post-watchdog housekeeping:
        # testing the cache method directly is enough because the
        # runner just forwards to it.
        runner.cache.reset_backoffs()

        for c in clients:
            self.assertEqual(c._fail_count, 0)
            self.assertEqual(c._next_attempt_at, 0.0)
            self.assertIsNone(c._client)

    def test_reset_backoffs_only_calls_attr_getable_clients(self):
        """Slots in the cache may belong to a `MockBleakClient`
        (from `make_client(mode="mock")`) which doesn't expose
        `reset_backoff`. The walker should tolerate that — we
        don't want to crash the runner when somebody passes a
        custom client impl.
        """
        sensors = [("11", "k-x", "outdoor")]
        runner = self._NullRunner(sensors)
        class _OtherClient:
            def __init__(self):
                self.sensor = sensors[0]
            async def read(self):
                from kitchen_clock.ble.bleak_client import SensorReading
                return SensorReading(mac="11", name="k-x",
                                     location="outdoor", source="mock")

        other = _OtherClient()
        runner.cache._cache = {sensors[0]: other}
        # Just calling reset_backoffs without errors is the contract.
        runner.cache.reset_backoffs()

    def test_threshold_invokes_watchdog(self):
        from kitchen_clock.ble.watchdog import FAIL_TICK_THRESHOLD
        sensors = [("11", "k-x", "outdoor")]
        runner = self._NullRunner(sensors)
        fail = [self._reading("outdoor", "connect-fail:ConnectionError")]
        runner.cache = BLEClientCache(lambda s: _StubClient(fail))
        for _ in range(FAIL_TICK_THRESHOLD):
            asyncio.run(runner._tick())
        # One invocation right at the threshold crossing.
        self.assertEqual(self.mock_watch.call_count, 1)
        self.assertEqual(runner._no_live_ticks, FAIL_TICK_THRESHOLD)

    def test_threshold_invokes_each_tick_above(self):
        from kitchen_clock.ble.watchdog import FAIL_TICK_THRESHOLD
        sensors = [("11", "k-x", "outdoor")]
        runner = self._NullRunner(sensors)
        fail = [self._reading("outdoor", "connect-fail:ConnectionError")]
        runner.cache = BLEClientCache(lambda s: _StubClient(fail))
        for _ in range(FAIL_TICK_THRESHOLD + 2):
            asyncio.run(runner._tick())
        # The watchdog fires every tick at or above the threshold
        # so a sustained outage keeps the python alarm pumping
        # rather than latching once.
        self.assertEqual(
            self.mock_watch.call_count, 3,
            "3 calls at tick counts 5/6/7 (i.e. threshold + 2 extras)",
        )

    def test_live_tick_resets_counter(self):
        from kitchen_clock.ble.watchdog import FAIL_TICK_THRESHOLD
        sensors = [("11", "k-x", "outdoor")]
        runner = self._NullRunner(sensors)
        # run 2 failed ticks first
        fail_readings = [self._reading("outdoor", "connect-fail:ConnectionError")] * 2
        runner.cache = BLEClientCache(lambda s: _StubClient(fail_readings))
        for _ in range(2):
            asyncio.run(runner._tick())
        old_calls = self.mock_watch.call_count
        # A live tick resets the counter and panel rendering captures
        # the live value.
        live = self._reading("outdoor", "live", T=21.0, H=50.0)
        runner.cache = BLEClientCache(lambda s: _StubClient([live]))
        asyncio.run(runner._tick())
        self.assertEqual(runner._no_live_ticks, 0)
        self.assertEqual(self.mock_watch.call_count, old_calls,
            "live tick did not invoke watchdog beyond what failed ticks already did")


class _StubClient_with_self:
    """Helper for TestRunnerWatchdog that reads from a queue
    shared with the test method. Mirrors _StubClient's signature.
    """
    def __init__(self, sensor, test_self):
        self._remaining = list(test_self.queue)
        self.sensor = sensor
    async def read(self):
        if not self._remaining:
            from kitchen_clock.ble.bleak_client import SensorReading
            return SensorReading(
                mac="00", name="x", location="x",
                source="connect-fail:ConnectionError",
            )
        return self._remaining.pop(0)


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


class TestRunnerPartialPromotion(unittest.TestCase):
    """Partial live readings must not overwrite `last_readings`.

    With the v7 windowed BLE firmware the central can connect
    inter-window — ble_noise gives the central a 5-second window
    during which the peripheral might still be in the middle of
    its own measurement and the GATT chars aren't populated yet.
    We treat that as a "partial live" tick and surface it in the
    journal state line, but the *render cache* continues to carry
    the last fully-good reading, so the panel doesn't flash a
    half-set.
    """

    class _NullRunner:
        from kitchen_clock.runner import BaseRunner as _Base

        def __init__(self, sensors):
            self.sensors = list(sensors)
            self.period_s = 0.1
            self.last_readings = [None] * len(sensors)
            self.current_readings = [None] * len(sensors)
            self._ble_tick_counter = 0
            self._no_live_ticks = 0

        async def _tick(self):
            from kitchen_clock.runner import BaseRunner
            return await BaseRunner._tick(self)

        def _draw(self):
            pass

    def _reading(self, location, source, T=None, H=None, B=None,
                T_err=None, H_err=None, B_err=None):
        r = SensorReading(
            mac="00", name="k-" + location, location=location,
            source=source,
        )
        if T_err is not None:
            r.temp_error = T_err
        elif T is not None:
            r.raw_temp = struct.pack("<h", int(T * 100))
        if H_err is not None:
            r.hum_error = H_err
        elif H is not None:
            r.raw_hum = struct.pack("<H", int(H * 100))
        if B_err is not None:
            r.batt_error = B_err
        elif B is not None:
            r.raw_batt = struct.pack("<H", int(B))
        return r

    def test_partial_live_does_not_overwrite_last_good(self):
        sensors = [("11", "k1", "outdoor")]
        runner = self._NullRunner(sensors)

        full = self._reading("outdoor", "live", T=21.5, H=40.0, B=3500)
        runner.cache = BLEClientCache(lambda s: _StubClient([full]))
        asyncio.run(runner._tick())
        self.assertEqual(runner.last_readings[0].temp_c, 21.5)
        self.assertEqual(runner.last_readings[0].hum_percent, 40.0)
        self.assertEqual(runner.last_readings[0].batt_raw, 3500)

        # Tick 2: T succeeded, H and B timed out.
        partial = self._reading(
            "outdoor", "live", T=22.5,
            H_err="TimeoutError: > 2.0s",
            B_err="TimeoutError: > 2.0s",
        )
        runner.cache = BLEClientCache(lambda s: _StubClient([partial]))
        asyncio.run(runner._tick())

        # Render cache is unchanged.
        self.assertEqual(runner.last_readings[0].temp_c, 21.5)
        self.assertEqual(runner.last_readings[0].hum_percent, 40.0)
        self.assertEqual(runner.last_readings[0].batt_raw, 3500)

        # But the journal state is the partial one — user can see it.
        self.assertEqual(runner.current_readings[0].temp_c, 22.5)
        self.assertIsNone(runner.current_readings[0].hum_percent)
        self.assertIsNone(runner.current_readings[0].batt_raw)

    def test_partial_live_then_full_live_promotes_latest_full(self):
        sensors = [("11", "k1", "outdoor")]
        runner = self._NullRunner(sensors)

        full1 = self._reading("outdoor", "live", T=21.5, H=40.0, B=3500)
        runner.cache = BLEClientCache(lambda s: _StubClient([full1]))
        asyncio.run(runner._tick())

        partial = self._reading(
            "outdoor", "live", T=22.5,
            H_err="TimeoutError: > 2.0s",
            B_err="TimeoutError: > 2.0s",
        )
        runner.cache = BLEClientCache(lambda s: _StubClient([partial]))
        asyncio.run(runner._tick())

        # The full tick after the partial promotes the new full values.
        full2 = self._reading("outdoor", "live", T=24.0, H=50.0, B=3700)
        runner.cache = BLEClientCache(lambda s: _StubClient([full2]))
        asyncio.run(runner._tick())

        self.assertEqual(runner.last_readings[0].temp_c, 24.0)
        self.assertEqual(runner.last_readings[0].hum_percent, 50.0)
        self.assertEqual(runner.last_readings[0].batt_raw, 3700)

    def test_is_complete_helper(self):
        """`_is_complete()` gates whether a reading is renderable."""
        from kitchen_clock.runner import _is_complete as is_complete
        full = self._reading("outdoor", "live", T=21.5, H=40.0, B=3500)
        self.assertTrue(is_complete(full))

        no_temp = self._reading(
            "outdoor", "live",
            T_err="TimeoutError: > 2.0s",
            H=40.0, B=3500,
        )
        self.assertFalse(is_complete(no_temp))

        no_hum = self._reading(
            "outdoor", "live", T=21.5,
            H_err="TimeoutError: > 2.0s",
            B=3500,
        )
        self.assertFalse(is_complete(no_hum))

        no_batt = self._reading(
            "outdoor", "live", T=21.5, H=40.0,
            B_err="TimeoutError: > 2.0s",
        )
        self.assertFalse(is_complete(no_batt))

        # A connect-fail: source != "live"/"mock", so reading is
        # not promoted even before _is_complete's error check.
        failed = self._reading("outdoor", "connect-fail:ConnectionError")
        self.assertFalse(is_complete(failed))


if __name__ == "__main__":    unittest.main()
