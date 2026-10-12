#!/usr/bin/env python3
"""Show (or set) Tom Nook's shop progress in the running game.

  py -3.12 tools\\shop.py                  stage, Bells spent, visitor flag
  py -3.12 tools\\shop.py --spent 240000   set the Bells-spent counter

Addresses (ADME rev 1; the save image sits at 0x021D7350 in RAM):
  0x021ED104  Bells spent at the shop, all stages combined (u32)
  0x021ED15A  renovation booking: day, month, year - 2000, booked (4 bytes)
  0x021ED15E  bits 9-10: shop stage 0..3 (u16; low 5 bits: other shop state)
  0x021ED328  bit 7: a player from another town has shopped (u32 flags)
"""

from __future__ import annotations

import argparse

from memscan import Runner

SPENT, BOOKING, STAGE_WORD, FLAGS = 0x021ED104, 0x021ED15A, 0x021ED15E, 0x021ED328
STAGES = ["Nook's Cranny", "Nook 'n' Go", "Nookway", "Nookington's"]
NEXT_AT = [25_000, 90_000, 240_000]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=19842)
    parser.add_argument("--spent", type=int, help="set the Bells-spent counter")
    args = parser.parse_args()

    runner = Runner(args.port)
    if args.spent is not None:
        runner.call(cmd="write_mem", cpu=9, addr=SPENT,
                    hex=(args.spent & 0xFFFFFFFF).to_bytes(4, "little").hex())
        print(f"Bells spent set to {args.spent:,}")

    spent = int.from_bytes(runner.read(SPENT, 4), "little")
    word = int.from_bytes(runner.read(STAGE_WORD, 2), "little")
    visitor = bool(int.from_bytes(runner.read(FLAGS, 4), "little") >> 7 & 1)
    stage = (word >> 9) & 3
    print(f"shop:          {STAGES[stage]} (stage {stage}, raw 0x{word:04X})")
    print(f"Bells spent:   {spent:,}")
    if stage < 3:
        print(f"next stage at: {NEXT_AT[stage]:,}"
              + ("  (also needs a visitor, unless the mod is on)" if stage == 2 else ""))
    print(f"visitor flag:  {'yes' if visitor else 'no'}")
    day, month, year, booked = runner.read(BOOKING, 4)
    print("renovation:    " + (f"booked for {day:02}/{month:02}/{2000 + year}"
                               if booked else "not booked"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
