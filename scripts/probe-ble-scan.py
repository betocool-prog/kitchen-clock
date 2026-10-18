#!/usr/bin/env python3
#
# scripts/probe-ble-scan.py
#
# Smoke-test the passive-scan transport (ADR 0012) from the host:
# runs the *production* ScannerHub (same filter, same decode, same
# SensorReading path as the panel app) for a few seconds and
# prints what it saw per registered sensor.
#
# Usage:
#   python scripts/probe-ble-scan.py                 # 20 s sweep, all sensors
#   python scripts/probe-ble-scan.py --duration 60
#   python scripts/probe-ble-scan.py --sensor outdoor
#
# Exit 0 when at least one registered sensor produced a decoded
# report; non-zero otherwise (also when bluetoothd is unreachable).
#
# Expected output against firmware v8:
#   kclock-d0 (outdoor) reports=37 latest: T=23.25°C H=59.28%B B=1109ADC age=0.3s
#
# Against v7-era firmware the line shows `no service data yet
# (v7 firmware?)` — flash dist/klock-sensor-*-v8.uf2.

import argparse
import asyncio
import os
import sys

sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "..",
                   "firmware", "main-unit"),
)

from kitchen_clock.ble.scanner import (  # noqa: E402
    FRESH_WINDOW_S,
    ScannerClient,
    ScannerHub,
)
from kitchen_clock.config import sensors as sensors_mod  # noqa: E402


async def sweep(sensors, duration_s):
    hub = ScannerHub(sensors)
    await hub.start()
    print(f"scanning for {duration_s:.0f} s ...", file=sys.stderr)
    await asyncio.sleep(duration_s)
    clients = [(s, ScannerClient(s, hub)) for s in sensors]
    readings = await asyncio.gather(*(c.read() for _, c in clients))
    return hub, readings


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--sensor", choices=("outside", "inside", "all"),
                    default="all",
                    help="Restrict to one role from the registry.")
    ap.add_argument("--duration", type=float, default=20.0,
                    help="Seconds to listen before reporting.")
    args = ap.parse_args()

    if args.sensor == "all":
        sensors = list(sensors_mod.KCLOCK_SENSORS)
    else:
        entry = sensors_mod.by_location(args.sensor)
        sensors = [entry] if entry else []

    if not sensors:
        print(f"sensor role {args.sensor!r} not in registry", file=sys.stderr)
        return 1

    try:
        hub, readings = asyncio.run(sweep(sensors, args.duration))
    except Exception as e:
        print(f"scanner failed: {type(e).__name__}: {e}", file=sys.stderr)
        return 1

    rc = 0
    for sensor, r in zip(sensors, readings):
        mac, name, loc = sensor
        if r.source == "no-report":
            print(f"{name} ({loc}) no report "
                  f"(powered? in range? v8 firmware?)")
            rc = 1
            continue
        if r.source.startswith("stale"):
            age = r.source.split(":", 1)[1]
            print(f"{name} ({loc}) stale report (age {age}): "
                  f"T={r.temp_c}°C H={r.hum_percent}%B B={r.batt_raw}ADC")
            rc = 1
            continue
        print(f"{name} ({loc}) live: "
              f"T={r.temp_c:.2f}°C H={r.hum_percent:.2f}%B "
              f"B={r.batt_raw}ADC source={r.source}")
    print(f"hub: report_count={hub.report_count} "
          f"legacy(v7?)={hub.legacy_reports} "
          f"fresh_window={FRESH_WINDOW_S:.0f}s", file=sys.stderr)
    return rc


if __name__ == "__main__":
    sys.exit(main())
