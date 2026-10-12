#!/usr/bin/env python3
"""Find the memory that changes only while dialogue text is typing out.

Stand facing a villager without talking, then run this. It presses A
itself to start the chat and each next line, snapshots main RAM twice
while a line types and twice after it finishes, and keeps the words that
change only while typing. Each line narrows the list; --keep narrows the
previous list further with another conversation. Snapshots use
read_region, so each one is a single frame.

  py -3.12 tools\\textscan.py              2 lines
  py -3.12 tools\\textscan.py --keep       narrow the last list further
"""

from __future__ import annotations

import argparse
import time
from array import array
from pathlib import Path

from memscan import RAM_START, Runner

CANDIDATES = Path("generated/mem/candidates.txt")


def snap(runner: Runner) -> array:
    words = array("I", bytes.fromhex(runner.call(cmd="read_region", region="mainram")["hex"]))
    if len(words) * 4 != 0x400000:
        raise SystemExit(f"unexpected main RAM size {len(words) * 4:#x}")
    return words


def press_a(runner: Runner) -> None:
    for down in (True, False):
        reply = runner.call(cmd="frontend_input", action="key", key="Z", down=down)
        if not reply.get("ok"):
            raise SystemExit("the runner refused the A press; is the game window open?")
        time.sleep(0.1)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=19842)
    parser.add_argument("--lines", type=int, default=2)
    parser.add_argument("--keep", action="store_true",
                        help="start from the previous candidate list")
    parser.add_argument("--settle", type=float, default=4.0,
                        help="seconds to wait for a line to finish typing")
    args = parser.parse_args()

    runner = Runner(args.port)
    keep: set[int] | None = None
    if args.keep:
        if not CANDIDATES.is_file():
            raise SystemExit("--keep needs an earlier run")
        keep = {(int(l.split()[0], 16) - RAM_START) // 4
                for l in CANDIDATES.read_text().splitlines() if l.strip()}
        print(f"starting from {len(keep):,} earlier candidate(s)")
    for line in range(1, args.lines + 1):
        press_a(runner)
        time.sleep(0.15)
        t1 = snap(runner)
        time.sleep(0.25)
        t2 = snap(runner)
        time.sleep(args.settle)
        i1 = snap(runner)
        time.sleep(0.3)
        i2 = snap(runner)
        here = {i for i, (a, b, c, d) in enumerate(zip(t1, t2, i1, i2))
                if a != b and b != c and c == d}
        keep = here if keep is None else keep & here
        print(f"line {line}: {len(here):,} typing-only words, {len(keep):,} on every line so far")

    rows = sorted(keep or ())
    CANDIDATES.parent.mkdir(parents=True, exist_ok=True)
    CANDIDATES.write_text("".join(f"0x{RAM_START + 4 * i:08X} {i2[i]}\n" for i in rows))
    print(f"\n{len(rows):,} candidate(s), saved to {CANDIDATES}")
    print("  address      typing, typing -> finished")
    for i in rows[:60]:
        print(f"  0x{RAM_START + 4 * i:08X}  {t1[i]:08X} {t2[i]:08X} -> {i1[i]:08X}")
    if len(rows) > 60:
        print(f"  ... {len(rows) - 60:,} more")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
