"""Entry point: `python -m kitchen_clock`.

Env vars:
  KITCHEN_CLOCK_RENDERER    — 'pygame' (default). Other values raise;
                              see ADR 0011 (PyGame on host and Pi).
  KITCHEN_CLOCK_BLE         — 'mock' (default) or 'live'.

CLI flags:
  --mock                    — equivalent: KITCHEN_CLOCK_BLE=mock.
  --sensor <outdoor|indoor|all>
  --period <seconds>
"""
import argparse
import asyncio
import os
import sys

from .config import sensors as sensors_mod
from .ble.bleak_client import make_client
from .ui.window import make_renderer


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="kitchen-clock",
        description="Kitchen-clock main unit dev runner.",
    )
    ap.add_argument("--mock", action="store_true",
                    help="Bypass BLE; read synthetic readings.")
    ap.add_argument("--sensor", default="all",
                    choices=("outdoor", "indoor", "all"),
                    help="Filter which bonded sensors to read.")
    ap.add_argument("--period", default=0.25, type=float,
                    help="Period between read cycles in seconds (default: 0.25 = 4 fps).")
    args = ap.parse_args()

    ble_mode = "mock" if args.mock \
        else os.environ.get("KITCHEN_CLOCK_BLE", "mock").lower()

    if args.sensor == "all":
        sensor_list = list(sensors_mod.KCLOCK_SENSORS)
    else:
        s = sensors_mod.by_location(args.sensor)
        sensor_list = [s] if s else []

    if not sensor_list:
        sys.stderr.write(f"sensor role {args.sensor!r} not in registry\n")
        return 1

    renderer_cls = make_renderer()
    runner = renderer_cls(
        make_client=lambda s: make_client(s, mode=ble_mode),
        sensors=sensor_list,
        period_s=args.period,
    )

    asyncio.run(runner.run())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
