#!/usr/bin/env python3
"""Investigate the GATT surface of a klock-d sensor.

Connects to a single peripheral, walks all services and
characteristics, and stops. Useful when confirming whether a
characteristic UUID (e.g. battery mV) is actually exposed by the
firmware before we refer to it from the runner.
"""
import argparse
import asyncio

from bleak import BleakClient


async def walk(mac: str) -> int:
    print(f"=== {mac} ===")
    try:
        c = BleakClient(mac, timeout=15)
        await asyncio.wait_for(c.connect(), timeout=15)
    except Exception as exc:
        print(f"connect-fail: {type(exc).__name__}: {exc}")
        return 1
    try:
        # bleak 3.x exposes services as a property; older used
        # get_services(). Both are wrong now, so try both.
        services = await asyncio.wait_for(
            c.get_services() if hasattr(c, "get_services")
            else _services_via_property(c),
            timeout=5,
        )
    except Exception as exc:
        print(f"get_services-fail: {type(exc).__name__}: {exc}")
        await c.disconnect()
        return 1
    for s in services:
        desc = s.description or "unknown"
        print(f"  service {s.uuid}  ({desc})")
        for ch in s.characteristics:
            print(f"    char   {ch.uuid}")
            print(f"      props={ch.properties}")
            print(f"      handle={ch.handle}")
    try:
        await c.disconnect()
    except Exception:
        pass
    return 0


async def _services_via_property(c):
    return c.services


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mac", action="append",
                    help="Peripheral MAC; pass twice for both sensors.")
    args = ap.parse_args()
    macs = args.mac or (
        "D3:B3:63:7C:F2:30",
        "D0:44:B3:EE:AC:9F",
    )
    for mac in macs:
        await walk(mac)
    return 0


if __name__ == "__main__":
    asyncio.run(main())
