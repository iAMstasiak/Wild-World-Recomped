#!/usr/bin/env python3
"""Save the game's DS menu icon as a big PNG, e.g. for Discord's art assets.

  py -3.12 tools\\icon_png.py            -> generated\\icon-1024.png
  py -3.12 tools\\icon_png.py --size 512

The icon is read from your ROM and scaled up with hard pixel edges. It is
Nintendo's art, so the file goes in generated\\ and stays out of git.
"""

from __future__ import annotations

import argparse
import struct
import zlib
from pathlib import Path

from shortcut import ROOT, read_banner_icon


def write_png_rgba(path: Path, size: int, argb: list[int]) -> None:
    rows = bytearray()
    for y in range(size):
        rows.append(0)
        for x in range(size):
            p = argb[(y * 32 // size) * 32 + x * 32 // size]
            rows += bytes(((p >> 16) & 255, (p >> 8) & 255, p & 255, p >> 24))

    def chunk(tag: bytes, data: bytes) -> bytes:
        body = tag + data
        return (struct.pack(">I", len(data)) + body +
                struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF))

    header = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) +
                     chunk(b"IDAT", zlib.compress(bytes(rows), 9)) +
                     chunk(b"IEND", b""))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--rom", type=Path, default=ROOT / "acww.nds")
    parser.add_argument("--size", type=int, default=1024)
    args = parser.parse_args()
    out = ROOT / "generated" / f"icon-{args.size}.png"
    write_png_rgba(out, args.size, read_banner_icon(args.rom))
    print(f"saved {out} ({args.size}x{args.size})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
