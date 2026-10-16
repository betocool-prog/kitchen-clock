#!/usr/bin/env python3
"""Manual BLE poller — debug aid for the kclock GATT path.

A standalone replacement for `kitchen-clock.service` while we
diagnose reconnection reliability on the Pi. Stops one contender
on the hci0 bus (so we have the radio to ourselves), prints the
full connect/read stack for each iteration, and accepts:

  --mac X               filter to a single sensor
  --interval-s 5.0      wall-clock seconds between full cycles
  --keep-open           don't disconnect between iterations
  --connect-timeout 15  matches what the service uses; raise for slow
                        startups
  --char-timeout 2      per-characteristic read timeout

Pairs with `kitchen_clock.ble.bleak_client` import for canonical
UUID + decode math — we want to see the same bytes the production
runner sees, on the same parsing, so pass/fail is honest.

Exit with Ctrl-C. The Pi's systemd unit is unaffected — touching
the service is *your* responsibility:

  sudo systemctl stop kitchen-clock.service   ← do this first
  /opt/kitchen-clock-venv/bin/python ble-poll-debug.py
"""
import argparse
import asyncio
import sys
import time

CHAR_TEMP_UUID = "00002a6e-0000-1000-8000-00805f9b34fb"
CHAR_HUM_UUID = "00002a6f-0000-1000-8000-00805f9b34fb"
CHAR_BATTMV_UUID = "6b636c6b-0001-0000-0000-0000-00000002"


SENSORS = (
    ("D3:B3:63:7C:F2:30", "kclock-d3", "indoor"),
    ("D0:44:B3:EE:AC:9F", "kclock-d0", "outdoor"),
)


def write(line: str) -> None:
    """Write a single line to stderr, flushed for tailing in tests."""
    sys.stderr.write(line + "\n")
    sys.stderr.flush()


async def poll_one(sensor, *, connect_timeout, char_timeout,
                   keep_open) -> None:
    from bleak import BleakClient
    from kitchen_clock.ble.bleak_client import (
        decode_temperature, decode_humidity, decode_battery_raw,
    )
    mac, name, location = sensor
    t0 = time.monotonic()
    try:
        client = BleakClient(mac, timeout=connect_timeout)
        await asyncio.wait_for(
            client.__aenter__(), timeout=connect_timeout,
        )
    except Exception as exc:
        elapsed = time.monotonic() - t0
        write(
            f"[{name}] connect-fail: {type(exc).__name__}: "
            f"{exc} ({elapsed:.2f}s)"
        )
        return
    elapsed = time.monotonic() - t0
    write(f"[{name}] connected ({elapsed:.2f}s, hci=0)")

    for label, char_uuid in (
        ("T", CHAR_TEMP_UUID),
        ("H", CHAR_HUM_UUID),
        ("B", CHAR_BATTMV_UUID),
    ):
        try:
            raw = await asyncio.wait_for(
                client.read_gatt_char(char_uuid), timeout=char_timeout,
            )
            raw = bytes(raw)
        except asyncio.TimeoutError:
            write(
                f"[{name}] {label} read TimeoutError "
                f"> {char_timeout:.0f}s"
            )
            client._ = None
            break
        except Exception as exc:
            write(
                f"[{name}] {label} read-fail: "
                f"{type(exc).__name__}: {exc}"
            )
            client._ = None
            break
        # Decode alongside the raw hex so we can spot a firmware
        # regression vs. a decode regression.
        decoded = "<?>"
        if label == "T":
            v = decode_temperature(raw)
            decoded = f"{v:.2f} C" if v is not None else "<short>"
        elif label == "H":
            v = decode_humidity(raw)
            decoded = f"{v:.2f} %RH" if v is not None else "<short>"
        elif label == "B":
            v = decode_battery_raw(raw)
            decoded = f"{v} ADC" if v is not None else "<short>"
        write(f"[{name}] {label}={raw.hex()} ({decoded})")

    if not keep_open:
        try:
            await asyncio.wait_for(
                client.__aexit__(None, None, None), timeout=2,
            )
            write(f"[{name}] disconnected")
        except Exception as exc:
            write(
                f"[{name}] disconnect-fail: {type(exc).__name__}: {exc}"
            )


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mac", default=None,
                    help="Filter to a single MAC; default = both.")
    ap.add_argument("--interval-s", type=float, default=5.0,
                    help="Seconds between full cycles.")
    ap.add_argument("--keep-open", action="store_true",
                    help="Don't disconnect between iterations.")
    ap.add_argument("--connect-timeout", type=float, default=15.0,
                    help="Bleak connect timeout (also scanner budget).")
    ap.add_argument("--char-timeout", type=float, default=2.0,
                    help="Per-characteristic read timeout.")
    args = ap.parse_args()
    targets = [s for s in SENSORS
               if args.mac is None or args.mac == s[0]]
    if not targets:
        write(f"no sensor matches --mac {args.mac}")
        return 2
    write(
        f"polling {len(targets)} sensor(s) every "
        f"{args.interval_s}s; Ctrl-C to stop"
    )
    while True:
        t_loop = time.monotonic()
        for sensor in targets:
            await poll_one(
                sensor,
                connect_timeout=args.connect_timeout,
                char_timeout=args.char_timeout,
                keep_open=args.keep_open,
            )
        write("---")
        elapsed = time.monotonic() - t_loop
        sleep_for = max(0.0, args.interval_s - elapsed)
        if sleep_for:
            await asyncio.sleep(sleep_for)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        write("bye")
