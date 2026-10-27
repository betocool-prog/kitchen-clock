"""Entry point: `python -m kitchen_clock`.

Env vars:
  KITCHEN_CLOCK_RENDERER    — 'pygame' (default). Other values raise;
                              see ADR 0011 (PyGame on host and Pi).
  KITCHEN_CLOCK_BLE         — 'mock' (default) or 'live' (scanner
                              transport, ADR 0012: the panel passively
                              scans ESS service-data advertisements
                              and never opens a GATT connection).
  KITCHEN_CLOCK_TIMEZONE    — IANA tz database key, default
                              'Australia/Perth' (AWST).
  KITCHEN_CLOCK_TIME_FORMAT — '24h' (default) or '12h'.

CLI flags:
  --mock                    — equivalent: KITCHEN_CLOCK_BLE=mock.
  --sensor <outdoor|indoor|all>
  --period <seconds>
  --timezone <IANA tz name>
  --time-format <12h|24h>
"""
import argparse
import asyncio
import os
import sys

from .config import sensors as sensors_mod
from .history import HistoryStore
from .ble.bleak_client import make_client
from .ble.scanner import ScannerClient, ScannerHub
from .time import TimeFormatter, DEFAULT_TIMEZONE, DEFAULT_TIME_FORMAT
from .ui.window import make_renderer


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="kitchen-clock",
        description="Kitchen-clock main unit dev runner.",
    )
    ap.add_argument("--mock", action="store_true",
                    help="Bypass BLE; read synthetic readings.")
    ap.add_argument("--sensor", default="all",
                    choices=("outside", "inside", "all"),
                    help="Filter which bonded sensors to read.")
    ap.add_argument("--period", default=0.25, type=float,
                    help="Period between read cycles in seconds (default: 0.25 = 4 fps).")
    ap.add_argument("--timezone", default=None,
                    help="IANA tz database key for the wall-clock "
                         f"(default: {DEFAULT_TIMEZONE}; respected only "
                         "if --render-time is not suppressed).")
    ap.add_argument("--time-format", default=None,
                    choices=("12h", "24h"),
                    help="'24h' (default) or '12h' with trailing AM/PM.")
    args = ap.parse_args()

    ble_mode = "mock" if args.mock \
        else os.environ.get("KITCHEN_CLOCK_BLE", "mock").lower()

    if ble_mode not in ("mock", "live"):
        sys.stderr.write(
            f"unknown BLE mode {ble_mode!r} "
            "(KITCHEN_CLOCK_BLE: 'mock' or 'live')\n",
        )
        return 1

    if args.sensor == "all":
        sensor_list = list(sensors_mod.KCLOCK_SENSORS)
    else:
        s = sensors_mod.by_location(args.sensor)
        sensor_list = [s] if s else []

    if not sensor_list:
        sys.stderr.write(f"sensor role {args.sensor!r} not in registry\n")
        return 1

    tz_name = args.timezone or os.environ.get(
        "KITCHEN_CLOCK_TIMEZONE", DEFAULT_TIMEZONE,
    )
    tf_format = args.time_format or os.environ.get(
        "KITCHEN_CLOCK_TIME_FORMAT", DEFAULT_TIME_FORMAT,
    )
    time_formatter = TimeFormatter(tz_name=tz_name,
                                  time_format=tf_format)

    renderer_cls = make_renderer()
    hub = None
    history = None
    if ble_mode == "live":
        # Scanner transport (ADR 0012): the hub runs a filtered
        # passive scan; clients drain its cached reports. No GATT
        # connections are ever opened. Fresh reports feed the
        # 24 h min/max history (layout v6); the sink is guarded so
        # history can never take the scanner down.
        import time as _time

        hub = ScannerHub(sensor_list)
        history = HistoryStore()

        def _on_sample(sensor, decoded):
            mac, name, loc = sensor
            history.record(name, _time.time(),
                           decoded["temp_c"], decoded["hum_percent"])

        hub.on_sample = _on_sample
        client_factory = lambda s: ScannerClient(s, hub)  # noqa: E731
    else:
        client_factory = lambda s: make_client(s, mode="mock")  # noqa: E731

    runner = renderer_cls(
        make_client=client_factory,
        sensors=sensor_list,
        period_s=args.period,
        time_formatter=time_formatter,
    )
    if hub is not None:
        runner.ble_hub = hub
        runner.history = history

    asyncio.run(runner.run())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
