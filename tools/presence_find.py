#!/usr/bin/env python3
"""Find what Discord presence needs in the running game's memory.

  py -3.12 tools\\presence_find.py

Start the game first and stand outside in your town. The tool asks for your
name, your town's name and your bells, then walks you through going in and
out of a few buildings, taking a one-frame snapshot of main RAM at each stop.
It keeps the bytes that hold one value whenever you are outside and a
different value in each building: those are the "which room am I in"
candidates. Everything it finds goes to generated\\presence_find.json.
"""

from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path

from memscan import RAM_START, Runner
from textfind import encode_ww

SAVE_START, SAVE_SIZE = 0x021D7350, 0x15FE0   # the save image in RAM (shop.py)
OUT = Path("generated/presence_find.json")


def snap(runner: Runner) -> bytes:
    ram = bytes.fromhex(runner.call(cmd="read_region", region="mainram")["hex"])
    if len(ram) != 0x400000:
        raise SystemExit(f"unexpected main RAM size {len(ram):#x}")
    return ram


def stop(runner: Runner, where: str) -> bytes:
    input(f"\n>> {where}, wait until the screen has settled, then press Enter ")
    ram = snap(runner)
    print("   snapshot taken")
    return ram


def find_all(ram: bytes, needle: bytes) -> list[int]:
    hits, start = [], 0
    while needle:
        i = ram.find(needle, start)
        if i < 0:
            return hits
        hits.append(i)
        start = i + 1
    return hits


def in_save(offset: int) -> bool:
    return SAVE_START <= RAM_START + offset < SAVE_START + SAVE_SIZE


def describe(offsets: list[int]) -> list[str]:
    return [f"0x{RAM_START + o:08X}" + (f" (save +0x{RAM_START + o - SAVE_START:05X})"
                                       if in_save(o) else "") for o in offsets]


def differing(a: bytes, b: bytes) -> list[int]:
    out = []
    for i in range(0, len(a), 256):
        if a[i:i + 256] != b[i:i + 256]:
            out.extend(j for j in range(i, i + 256) if a[j] != b[j])
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=19842)
    args = parser.parse_args()
    runner = Runner(args.port)
    found: dict = {}

    print("Stand outside in your town for this first part.")
    name = input("Your character's name, exactly as the game shows it: ").strip()
    town = input("Your town's name: ").strip()
    bells = int(input("Bells in your pockets right now: ").replace(",", "").strip())
    town1 = snap(runner)

    for label, text in (("player_name", name), ("town_name", town)):
        encoded = encode_ww(text)
        hits = find_all(town1, encoded) if encoded else []
        found[label] = {"text": text, "hits": describe(hits)}
        print(f"{label}: {len(hits)} place(s), {sum(map(in_save, hits))} in the save")

    bell_hits = find_all(town1, struct.pack("<I", bells))
    print(f"bells: {len(bell_hits)} place(s) hold {bells}")

    shop = stop(runner, "Go inside Nook's shop")
    print("\n>> Still in the shop: sell something, or take a bag of bells out of")
    new_bells = int(input("   your wallet, then type your new bells amount: ")
                    .replace(",", "").strip())
    shop_b = snap(runner)
    bell_hits = [o for o in bell_hits
                 if shop_b[o:o + 4] == struct.pack("<I", new_bells)]
    # In case the game keeps bells in 16 bits rather than 32:
    short_hits = [o for o in find_all(town1, struct.pack("<H", bells & 0xFFFF))
                  if shop_b[o:o + 2] == struct.pack("<H", new_bells & 0xFFFF)]
    found["bells"] = {"before": bells, "after": new_bells,
                      "hits": describe(bell_hits),
                      "hits_16bit": describe(short_hits[:50])}
    print(f"bells: {len(bell_hits)} place(s) went from {bells} to {new_bells}")

    town2 = stop(runner, "Go back outside")
    house = stop(runner, "Go inside your house")
    town3 = stop(runner, "Go back outside")
    other_name = input("\nName another building you can go into "
                       "(museum, Able Sisters, town hall...): ").strip()
    other = stop(runner, f"Go inside the {other_name}")
    town4 = stop(runner, "Go back outside")
    shop2 = stop(runner, "Go inside Nook's shop once more")

    rooms = differing(town1, shop)
    rooms = [j for j in rooms if town1[j] == town2[j] == town3[j] == town4[j]]
    rooms = [j for j in rooms if shop[j] == shop_b[j] == shop2[j]]
    rooms = [j for j in rooms if house[j] not in (town1[j], shop[j])]
    rooms = [j for j in rooms if other[j] not in (town1[j], shop[j], house[j])]
    found["room"] = {
        "other_building": other_name,
        "candidates": [
            {"addr": f"0x{RAM_START + j:08X}", "town": town1[j], "shop": shop[j],
             "house": house[j], "other": other[j],
             "word_at": f"0x{RAM_START + (j & ~3):08X}",
             "words": [int.from_bytes(s[j & ~3:(j & ~3) + 4], "little")
                       for s in (town1, shop, house, other)]}
            for j in rooms],
    }
    print(f"\nroom: {len(rooms)} candidate byte(s)")
    for c in found["room"]["candidates"][:30]:
        print(f"  {c['addr']}  town {c['town']:3}  shop {c['shop']:3}  "
              f"house {c['house']:3}  {other_name} {c['other']:3}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(found, indent=1))
    print(f"\nsaved {OUT}: send that file over")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
