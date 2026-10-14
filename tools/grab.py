#!/usr/bin/env python3
"""Save both screens of the running game as PNG files at DS resolution.

  py -3.12 tools\\grab.py town      -> grabs\\town-top.png, grabs\\town-bottom.png

The pictures are the game's own 256x192 frames (no HD), which is what any
2D smoothing filter starts from, so they are used to compare filters.
"""

from __future__ import annotations

import argparse
import struct
import zlib
from pathlib import Path

from memscan import Runner


def write_png(path: Path, width: int, height: int, rgb: bytes) -> None:
    rows = b"".join(b"\x00" + rgb[y * width * 3:(y + 1) * width * 3]
                    for y in range(height))

    def chunk(tag: bytes, data: bytes) -> bytes:
        body = tag + data
        return (struct.pack(">I", len(data)) + body +
                struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF))

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) +
                     chunk(b"IDAT", zlib.compress(rows, 9)) + chunk(b"IEND", b""))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("name", help="a label for this scene, e.g. town or dialogue")
    parser.add_argument("--port", type=int, default=19842)
    args = parser.parse_args()

    runner = Runner(args.port)
    out = Path("grabs")
    out.mkdir(exist_ok=True)
    # The debug port calls the screens "A" (top) and "B" (bottom).
    for which, label in (("A", "top"), ("B", "bottom")):
        reply = runner.call(cmd="framebuffer", engine=which)
        width, height = int(reply["w"]), int(reply["h"])
        path = out / f"{args.name}-{label}.png"
        write_png(path, width, height, bytes.fromhex(reply["rgb"]))
        print(f"saved {path} ({width}x{height})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
