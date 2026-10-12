#!/usr/bin/env python3
"""Record a small piece of RAM frame by frame and show what changed.

The runner answers one debug request per frame, so reading the same range
over and over gives one sample per frame. Each 4-byte word that changed is
printed as runs of values, e.g. "2A5 x2, 2A6 x2, 2A7 x2" for a counter that
steps every other frame.

  py -3.12 tools\\trace.py 0x021FCF00 0x200              record 180 frames
  py -3.12 tools\\trace.py 0x021FCF00 0x200 --press      press A first
  py -3.12 tools\\trace.py 0x021FCF00 0x200 --frames 300
"""

from __future__ import annotations

import argparse
import time

from memscan import Runner


def number(text: str) -> int:
    return int(text, 0)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("addr", type=number)
    parser.add_argument("length", type=number)
    parser.add_argument("--frames", type=int, default=180)
    parser.add_argument("--press", action="store_true", help="press A before recording")
    parser.add_argument("--port", type=int, default=19842)
    args = parser.parse_args()
    if args.length > 0x8000 or args.length % 4:
        raise SystemExit("length must be a multiple of 4, at most 0x8000")

    runner = Runner(args.port)
    if args.press:
        runner.call(cmd="frontend_input", action="key", key="Z", down=True)
        time.sleep(0.1)
        runner.call(cmd="frontend_input", action="key", key="Z", down=False)
    start = time.monotonic()
    samples = [runner.read(args.addr, args.length) for _ in range(args.frames)]
    seconds = time.monotonic() - start
    print(f"{args.frames} samples in {seconds:.2f}s "
          f"(about {args.frames / seconds:.0f} per second; the game runs 60 frames per second)")

    changed = 0
    for off in range(0, args.length, 4):
        values = [int.from_bytes(s[off:off + 4], "little") for s in samples]
        if len(set(values)) == 1:
            continue
        changed += 1
        runs: list[list[int]] = []
        for v in values:
            if runs and runs[-1][0] == v:
                runs[-1][1] += 1
            else:
                runs.append([v, 1])
        text = ", ".join(f"{v:X} x{n}" for v, n in runs[:24])
        if len(runs) > 24:
            text += f", ... ({len(runs) - 24} more changes)"
        print(f"0x{args.addr + off:08X}: {text}")
    print(f"{changed} of {args.length // 4} words changed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
