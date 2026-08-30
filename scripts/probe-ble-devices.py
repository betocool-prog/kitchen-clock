#!/usr/bin/env python3
#
# scripts/probe-ble-devices.py
#
# Smoke-test BLE discovery from the host. Scans nearby peripherals
# via BlueZ (hci0) under ~/kitchen-clock conda-env using `bleak`,
# and prints them in a small table.
#
# Useful before integrating bleak into the Pi-side app: confirms
# the XIAO nRF52840 sensor unit advertising `kclock-XX` is
# reachable from this machine.
#
# Examples:
#   python scripts/probe-ble-devices.py
#   python scripts/probe-ble-devices.py --filter kclock
#   python scripts/probe-ble-devices.py --timeout 8

import argparse
import asyncio

from bleak import BleakScanner


async def scan(timeout_s: float, name_filter: str | None) -> None:
    devices = await BleakScanner.discover(timeout=timeout_s)
    devices = sorted(devices, key=lambda d: d.address)

    if name_filter:
        devices = [d for d in devices if (d.name or "").startswith(name_filter)]

    if not devices:
        print(f"(no matching devices found within {timeout_s:.1f}s)")
        return

    print(f"{'MAC':<18}  {'RSSI':>5}  {'NAME'}")
    print("-" * 60)
    for d in devices:
        # bleak 3.x deprecated the `rssi` attribute on BLEDevice in
        # favour of `details['rssi']` (and/or a `metadata` object).
        # Read whichever is available without raising.
        rssi = None
        direct = getattr(d, "rssi", None)
        if direct is not None:
            rssi = direct
        else:
            details = getattr(d, "details", None) or {}
            candidate = details.get("rssi")
            rssi = candidate if candidate is not None else None
        rssi_str = str(rssi) if rssi is not None else "-"
        name = d.name or "(unnamed)"
        print(f"{d.address:<18}  {rssi_str:>5}  {name}")


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument(
        "--timeout", type=float, default=4.0,
        help="scan window in seconds (default 4)",
    )
    ap.add_argument(
        "--filter", dest="name_filter", default=None,
        help="only show devices whose advertised name starts with this prefix (e.g. 'kclock')",
    )
    args = ap.parse_args()
    asyncio.run(scan(args.timeout, args.name_filter))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
