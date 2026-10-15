#!/usr/bin/env python3
"""Save the DS's whole 2D picture state while the game runs, for study.

  py -3.12 tools\\vramdump.py talk       -> generated\\vram\\talk.zip

One zip holds every VRAM bank, both palettes, the sprite table (OAM), the
2D display registers of both screens and both finished screen images, so
the pieces that make up a scene (which layer carries the text, where its
letters live, how the box is built) can be taken apart away from the game.
"""

from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path

from grab import write_png
from memscan import Runner

BANKS = [f"vram{c}" for c in "ABCDEFGHI"]
# 2D registers per engine: (name, offset, width in bits). Engine B adds 0x1000.
ENGINE_REGS = [
    ("DISPCNT", 0x00, 32), ("BG0CNT", 0x08, 16), ("BG1CNT", 0x0A, 16),
    ("BG2CNT", 0x0C, 16), ("BG3CNT", 0x0E, 16),
    ("BG0HOFS", 0x10, 16), ("BG0VOFS", 0x12, 16), ("BG1HOFS", 0x14, 16),
    ("BG1VOFS", 0x16, 16), ("BG2HOFS", 0x18, 16), ("BG2VOFS", 0x1A, 16),
    ("BG3HOFS", 0x1C, 16), ("BG3VOFS", 0x1E, 16),
    ("WIN0H", 0x40, 16), ("WIN1H", 0x42, 16), ("WIN0V", 0x44, 16),
    ("WIN1V", 0x46, 16), ("WININ", 0x48, 16), ("WINOUT", 0x4A, 16),
    ("MOSAIC", 0x4C, 16), ("BLDCNT", 0x50, 16), ("BLDALPHA", 0x52, 16),
    ("BLDY", 0x54, 16), ("MASTER_BRIGHT", 0x6C, 16),
]
GLOBAL_REGS = [("POWCNT1", 0x04000304, 16)] + [
    (f"VRAMCNT_{c}", 0x04000240 + i + (1 if i >= 7 else 0), 8)
    for i, c in enumerate("ABCDEFGHI")]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("name", help="a label for this scene, e.g. talk")
    parser.add_argument("--port", type=int, default=19842)
    args = parser.parse_args()
    runner = Runner(args.port)

    regs: dict[str, int] = {}
    for engine, base in (("A", 0x04000000), ("B", 0x04001000)):
        for name, offset, width in ENGINE_REGS:
            reply = runner.call(cmd="read_io", cpu=9, addr=base + offset, width=width)
            regs[f"{engine}.{name}"] = int(reply["value"])
    for name, addr, width in GLOBAL_REGS:
        regs[name] = int(runner.call(cmd="read_io", cpu=9, addr=addr, width=width)["value"])

    out = Path("generated/vram") / f"{args.name}.zip"
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for region in BANKS + ["palA", "palB", "oam"]:
            reply = runner.call(cmd="read_region", region=region)
            z.writestr(f"{region}.bin", bytes.fromhex(reply["hex"]))
        for engine, label in (("A", "top"), ("B", "bottom")):
            reply = runner.call(cmd="framebuffer", engine=engine)
            png = out.parent / f"{args.name}-{label}.png"
            write_png(png, int(reply["w"]), int(reply["h"]), bytes.fromhex(reply["rgb"]))
            z.write(png, png.name)
            png.unlink()
        z.writestr("regs.json", json.dumps(regs, indent=1))
    print(f"saved {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
