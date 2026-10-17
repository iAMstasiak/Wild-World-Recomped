#!/usr/bin/env python3
"""Show what a Wild World save file holds.

  py -3.12 tools\\saveinfo.py              acww.sav
  py -3.12 tools\\saveinfo.py some.sav     any other save

The game's save (0x15FE0 bytes, the same layout as the copy in RAM at
0x021D7350) is in the file twice. For each copy this prints its 16-bit sums
(how the game checks a save), the town's name and each player slot's name
and bells, so the launcher's Saves page can tell a Wild World save from
anything else and show what is in it.
"""

from __future__ import annotations

import argparse
import struct
from pathlib import Path

from textfind import decode_ww

COPY = 0x15FE0                      # one copy of the save
TOWN = 0x0004                       # the town's name, 8 characters
PLAYER, PLAYER_SIZE = 0x000C, 0x228C
NAME, BELLS = 0x2282, 0x1B40        # inside a player: name, wallet (u32)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("save", nargs="?", default="acww.sav")
    args = parser.parse_args()

    data = Path(args.save).read_bytes()
    print(f"{args.save}: {len(data):,} bytes")
    for n, base in enumerate((0, COPY), 1):
        block = data[base:base + COPY]
        if len(block) < COPY:
            print(f"copy {n}: not there")
            continue
        words = struct.unpack(f"<{COPY // 2}H", block)
        total = sum(words) & 0xFFFF
        tail = ", ".join(f"0x{base + COPY - 8 + i * 2:05X}={w:04X}"
                         for i, w in enumerate(words[-4:]))
        print(f"copy {n} at 0x{base:05X}: sum of all 16-bit words 0x{total:04X}; "
              f"last words {tail}")
        town = decode_ww(block[TOWN:TOWN + 8].rstrip(b"\0"))
        print(f"  town: {town!r}")
        for p in range(4):
            at = PLAYER + p * PLAYER_SIZE
            name = decode_ww(block[at + NAME:at + NAME + 8].rstrip(b"\0"))
            bells = struct.unpack_from("<I", block, at + BELLS)[0]
            print(f"  player {p + 1}: {name!r}, {bells:,} bells")
    print("copies identical:", data[:COPY] == data[COPY:2 * COPY])
    rest = data[2 * COPY:]
    print(f"after the copies: {len(rest):,} bytes, "
          f"{'all 0xFF' if rest.count(0xFF) == len(rest) else 'not blank'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
