#!/usr/bin/env python3
#
# scripts/probe-ble-gatt.py
#
# Smoke-test the XIAO-nRF52840 sensor unit over GATT from the host.
# Connects via bleak, walks services, reads each well-known value,
# prints decoded values. Mirrors the fixtures in firmware/outdoor-sensor.
#
# Usage:
#   python scripts/probe-ble-gatt.py
#   python scripts/probe-ble-gatt.py D0:44:B3:EE:AC:9F
#   python scripts/probe-ble-gatt.py --sensor outdoor --ticks 5 --period 2
#
# Returns 0 on at least one successful characteristic read; non-zero
# only on hard connection failure.

import argparse
import asyncio
import struct
import sys

from bleak import BleakClient, BleakError

# Match the fixture in firmware/outdoor-sensor/app/src/ble.c.
CHAR_TEMP_UUID = "00002a6e-0000-1000-8000-00805f9b34fb"  # 0x2A6E, int16, 0.01 °C
CHAR_HUM_UUID = "00002a6f-0000-1000-8000-00805f9b34fb"   # 0x2A6F, uint16, 0.01 %RH
SVC_KCLOCK_UUID = "6b636c6b-0001-0000-0000-0000-00000001"  # custom 128-bit
CHAR_BATTMV_UUID = "6b636c6b-0001-0000-0000-0000-00000002" # custom 128-bit, uint16 mV

# Match against strings we keep in firmware/main-unit/config/sensors.py.
KNOWN_SENSOR_MACS = (
    ("D0:44:B3:EE:AC:9F", "kclock-d0", "outdoor"),
    ("D3:B3:63:7C:F2:30", "kclock-d3", "indoor"),
)

TEMP_SCALE = 100.0
HUM_SCALE = 100.0


def _to_int(b: bytes, fmt: str):
    return struct.unpack(fmt, b[:struct.calcsize(fmt)])[0]


def decode_temperature(raw: bytes):
    if len(raw) < 2:
        return None
    return _to_int(raw, "<h") / TEMP_SCALE


def decode_humidity(raw: bytes):
    if len(raw) < 2:
        return None
    return _to_int(raw, "<H") / HUM_SCALE


def decode_battery_mv(raw: bytes):
    if len(raw) < 2:
        return None
    return _to_int(raw, "<H")


async def read_all(client: BleakClient):
    """Read temperature, humidity, and battery-mV characteristics.

    Returns a dict mapping each characteristic's UUID to its (decoded,
    raw) tuple.  Missing characteristics are reported as (None, raw).
    """
    out = {}

    reads = (
        (CHAR_TEMP_UUID, "<h", TEMP_SCALE, "°C"),
        (CHAR_HUM_UUID, "<H", HUM_SCALE, "%RH"),
        (CHAR_BATTMV_UUID, "<H", 1, "mV"),
    )

    decoders = {
        CHAR_TEMP_UUID:     decode_temperature,
        CHAR_HUM_UUID:      decode_humidity,
        CHAR_BATTMV_UUID:   decode_battery_mv,
    }

    for char_uuid, _fmt, _scale, _unit in reads:
        try:
            raw = bytes(await client.read_gatt_char(char_uuid))
        except (BleakError, Exception) as e:
            out[char_uuid] = (None, b"", f"{type(e).__name__}: {e}")
            continue
        out[char_uuid] = (None, raw, "decode")  # placeholder
        try:
            out[char_uuid] = (decoders[char_uuid](raw), raw, "ok")
        except Exception as e:
            out[char_uuid] = (None, raw, f"decode-failed: {e}")
    return out


async def probe_once(mac: str, name: str, location: str) -> int:
    print(f"\n=== {name} ({location})  [{mac}] ===")
    client = BleakClient(mac)
    try:
        async with client:    # bleak ≥0.21: connect() runs on entry
            services = client.services  # post-connect property, no await
            print("services:")
            for svc in services:
                if svc.uuid.lower() in (SVC_KCLOCK_UUID, "00001801-0000-1000-8000-00805f9b34fb"):
                    keep = "  ★" if svc.uuid.lower() == SVC_KCLOCK_UUID else ""
                    print(f"  0x{svc.uuid.lower().replace('-', '')[:8]} … {svc.description!r}{keep}")
                chars = []
                for ch in svc.characteristics:
                    name_ = ch.uuid.lower()
                    if name_ in (CHAR_TEMP_UUID, CHAR_HUM_UUID, CHAR_BATTMV_UUID):
                        chars.append(name_.split("-")[0])
                if chars:
                    print(f"    characteristics matching our fixtures: {chars}")

            readings = await read_all(client)
            print()
            print("decoded readings:")
            for char_uuid, (val, _raw, status) in readings.items():
                kind = {
                    CHAR_TEMP_UUID:   "temperature",
                    CHAR_HUM_UUID:    "humidity   ",
                    CHAR_BATTMV_UUID: "battery-mV ",
                }[char_uuid]
                if status == "ok":
                    print(f"  {kind}  {val:>9.2f}")
                elif status == "decode-failed":
                    print(f"  {kind}  ⚠︎ decode error: {val}")
                else:
                    err = (val or "<none>") if val else "no data"
                    print(f"  {kind}  ⚠︎ {err}")
    except (BleakError, Exception) as e:
        print(f"connect failed: {type(e).__name__}: {e}")
        return 1
    return 0


def parse_sensor_arg(arg: str):
    """Return (mac, name, location) for a MAC or sensor-name argument."""
    if arg:
        # explicit MAC
        return (arg.upper(), None, None)
    # default: the wired kclock-d0 in our registry
    for mac, name, loc in KNOWN_SENSOR_MACS:
        return (mac, name, loc)
    raise SystemExit("no sensors configured")


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument(
        "mac",
        nargs="?",
        default=None,
        help="MAC to probe (defaults to the wired kclock-d0 known-good sensor).",
    )
    ap.add_argument(
        "--sensor", choices=("outdoor", "indoor", "all"), default="all",
        help="Pick a sensor-by-role from the registry instead of by MAC.",
    )
    ap.add_argument(
        "--ticks", type=int, default=1,
        help="Number of read cycles (>1 cycles every --period seconds).",
    )
    ap.add_argument(
        "--period", type=float, default=2.0,
        help="Period between repeat reads in seconds (only used when --ticks>1).",
    )
    args = ap.parse_args()

    targets = []
    if args.sensor == "all":
        # If a MAC was provided, only probe that one; otherwise probe
        # all known sensors that we can.
        if args.mac:
            for mac, name, loc in KNOWN_SENSOR_MACS + ((args.mac.upper(), "(cli)", "(cli)"),):
                if mac == args.mac.upper():
                    targets.append((mac, name, loc))
        else:
            targets = list(KNOWN_SENSOR_MACS)
    else:
        for mac, name, loc in KNOWN_SENSOR_MACS:
            if loc == args.sensor:
                targets.append((mac, name, loc))

    if not targets and not args.mac:
        print(f"sensor role {args.sensor!r} not found in registry")
        return 1

    if args.mac and not targets:
        # Allow probing an arbitrary MAC not in the registry (we
        # still get a single-device probe).
        targets = [(args.mac.upper(), "(cli)", "(cli)")]

    rc = 0
    for target in targets:
        for tick in range(args.ticks):
            r = asyncio.run(probe_once(*target))
            rc |= r
            if tick + 1 < args.ticks:
                import time
                time.sleep(args.period)
    return rc


if __name__ == "__main__":
    sys.exit(main())
