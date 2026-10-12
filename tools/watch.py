#!/usr/bin/env python3
"""Find the code that writes to an address: which instructions, how often.

Launch with the range to watch, e.g.  .\\play.ps1 -Watch 0x021FCFA8-0x021FCFAC
(needs the NDS_WATCH runner patch from tools/patch_ndsrecomp.py). Then:

  py -3.12 tools\\watch.py              record for 2 seconds
  py -3.12 tools\\watch.py --press      press A first (e.g. to advance text)

While recording, the game runs in the interpreter with deep tracing on, so
every write goes through the slow bus path with the exact instruction
address. Expect a short stutter; both are switched off again afterwards.
"""

from __future__ import annotations

import argparse
import time
from collections import defaultdict

from memscan import Runner


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seconds", type=float, default=2.0)
    parser.add_argument("--press", action="store_true", help="press A before recording")
    parser.add_argument("--port", type=int, default=19842)
    args = parser.parse_args()

    runner = Runner(args.port)
    before = runner.call(cmd="watch", max=512)["events"]
    last_seq = max((e["seq"] for e in before), default=-1)
    runner.call(cmd="force_tier3", on=1)
    runner.call(cmd="deep_trace", on=1)
    try:
        if args.press:
            runner.call(cmd="frontend_input", action="key", key="Z", down=True)
            time.sleep(0.1)
            runner.call(cmd="frontend_input", action="key", key="Z", down=False)
        time.sleep(args.seconds)
        events = runner.call(cmd="watch", max=512)["events"]
    finally:
        runner.call(cmd="deep_trace", on=0)
        runner.call(cmd="force_tier3", on=0)

    events = [e for e in events if e["seq"] > last_seq and e["write"]]
    if not events:
        print("no writes recorded: was the game launched with -Watch, and did the value change?")
        return 0
    if len(events) >= 512:
        print("(the ring filled up, so the oldest writes were dropped; try --seconds 0.5)")

    by_pc: dict[tuple[int, int], list[dict]] = defaultdict(list)
    for e in events:
        by_pc[(e["cpu"], e["pc"])].append(e)
    print(f"{len(events)} write(s) from {len(by_pc)} instruction(s):")
    for (cpu, pc), hits in sorted(by_pc.items(), key=lambda kv: -len(kv[1])):
        values = ", ".join(f"{h['value']:X}" for h in hits[:8])
        more = f", ... ({len(hits) - 8} more)" if len(hits) > 8 else ""
        addrs = sorted({h["addr"] for h in hits})
        where = ", ".join(f"0x{a:08X}" for a in addrs[:4])
        print(f"  ARM{9 if cpu == 0 else 7} pc 0x{pc:08X}: {len(hits)} write(s) of "
              f"{hits[0]['width']} byte(s) to {where}  values {values}{more}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
