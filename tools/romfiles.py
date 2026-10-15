#!/usr/bin/env python3
"""List or pull out files from the game's ROM filesystem.

  py -3.12 tools\\romfiles.py                    -> generated\\romfiles.txt
  py -3.12 tools\\romfiles.py extract PATH ...   -> generated\\rom\\PATH

The list shows each file's id, size and first bytes (its "magic"), which
tell file types apart: RTFN is a Nintendo font, NARC an archive of files,
0x10 at the start usually means LZ77-compressed. Everything pulled out is
Nintendo's data, so it stays in generated\\ and out of git.
"""

from __future__ import annotations

import argparse
from pathlib import Path

try:
    import ndspy.rom
except ImportError as exc:
    raise SystemExit("ndspy 4.2.0 is required: py -3.12 -m pip install ndspy==4.2.0") from exc

ROOT = Path(__file__).resolve().parent.parent


def walk(folder, prefix=""):
    for i, name in enumerate(folder.files):
        yield folder.firstID + i, prefix + name
    for name, sub in folder.folders:
        yield from walk(sub, prefix + name + "/")


def magic(data: bytes) -> str:
    head = data[:4]
    text = "".join(chr(b) if 32 <= b < 127 else "." for b in head)
    return f"{head.hex(' '):11}  {text}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("what", nargs="?", choices=["extract"])
    parser.add_argument("paths", nargs="*")
    parser.add_argument("--rom", type=Path, default=ROOT / "acww.nds")
    args = parser.parse_args()
    rom = ndspy.rom.NintendoDSRom(args.rom.read_bytes())

    if args.what == "extract":
        for path in args.paths:
            file_id = rom.filenames.idOf(path)
            if file_id is None:
                raise SystemExit(f"no file called {path!r} (see generated\\romfiles.txt)")
            out = ROOT / "generated" / "rom" / path
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(rom.files[file_id])
            print(f"saved {out} ({len(rom.files[file_id]):,} bytes)")
        return 0

    lines = [f"{file_id:5}  {len(rom.files[file_id]):9,}  {magic(rom.files[file_id])}  {path}"
             for file_id, path in walk(rom.filenames)]
    out = ROOT / "generated" / "romfiles.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n")
    fonts = [line for line in lines if "RTFN" in line or "font" in line.lower()]
    print(f"{len(lines)} files listed in {out}")
    print("look like fonts:" if fonts else "nothing obviously font-like")
    for line in fonts[:20]:
        print("  " + line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
