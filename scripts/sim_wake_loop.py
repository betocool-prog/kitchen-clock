#!/usr/bin/env python3
"""Phase-0 timing sim for the wake-mod-30s plan.

Mirrors the *control-cycle* invariants the eventual Pi-side service
will need once the klock firmware changes shape:

  wake -> measure -> sleep (30 s)

without any BLE / draw / sensor dependencies. Runs forever in the
background and prints a single line per cycle so we can tail it
from a terminal.

CLI knobs:

  --cycle-s 30.0           seconds between simulated wakes
  --measure-ms 50.0        simulated measurement latency
  --max-ticks 0            0 = run forever
  --seed                   deterministic random for CI sanity

This is what we use to *think* about the plan, not what we run on
the Pi. Letting it run on the laptop for ~3 cycles with
`--cycle-s 5` confirms the loop is sane before we go to BLE.
"""
import argparse
import asyncio
import random
import sys
import time


def log(line: str) -> None:
    sys.stdout.write(line + "\n")
    sys.stdout.flush()


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cycle-s", type=float, default=30.0,
                    help="Seconds between simulated wakes.")
    ap.add_argument("--measure-ms", type=float, default=50.0,
                    help="Simulated measurement latency.")
    ap.add_argument("--max-ticks", type=int, default=0,
                    help="Stop after this many ticks (0 = forever).")
    ap.add_argument("--seed", type=int, default=None)
    args = ap.parse_args()

    if args.seed is not None:
        random.seed(args.seed)

    log(
        f"[sim] cycle_s={args.cycle_s} measure_ms={args.measure_ms} "
        f"max_ticks={args.max_ticks or '∞'}"
    )

    t_origin = time.monotonic()
    tick_n = 0
    while True:
        # Wake time is anchored to t_origin, not to the previous
        # wake. So a 30-s cycle with 50ms measurement drift stays
        # close to "every 30 s", not "every 30.05 s of slow drift".
        target_wall_s = tick_n * args.cycle_s
        now = time.monotonic() - t_origin
        if target_wall_s > now:
            await asyncio.sleep(target_wall_s - now)
        t_wake = time.monotonic()
        # Simulated measurement.
        await asyncio.sleep(args.measure_ms / 1000.0)
        t_measure_done = time.monotonic()
        # Simulated T / H / B with realistic ranges; we don't
        # actually compute anything BLE-side, so random is fine.
        T_c = 20.0 + random.uniform(-2.0, 5.0)
        H_pct = 40.0 + random.uniform(-5.0, 25.0)
        V_mv = 3650 + random.randint(-200, 0)
        log(
            f"[tick #{tick_n:03d}] wall+={target_wall_s:.2f}s "
            f"wake_to_measured={(t_measure_done - t_wake) * 1000:.0f}ms "
            f"T={T_c:.2f}°C H={H_pct:.2f}%RH V={V_mv} mV"
        )
        tick_n += 1
        if args.max_ticks and tick_n >= args.max_ticks:
            log("[sim] done")
            return 0


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log("[sim] bye")
        sys.exit(0)
