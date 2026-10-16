#!/usr/bin/env python3
"""Move save backups, mods and Discord presence into the runner.

What play.ps1, tools/mods.py and tools/presence.py did from outside the
game, so players don't need Python: the runner backs up the save before it
loads it, writes the mods chosen in settings.toml into the game once their
code is in memory, and shows what you're doing on your Discord profile. The
code lives in tools/acww_game.h, which this copies into the runner.

Run after the other patch_*.py scripts (patch_settings.py included). Safe
to run again: edits that are already there are skipped, and the header is
refreshed. Rebuild the runner afterwards:
cmake --build C:\\acww\\ndsrecomp\\runner\\build-acww
"""

from __future__ import annotations

import argparse
from pathlib import Path

MAIN = "runner/src/main.cpp"
FRONTEND = "runner/src/frontend.cpp"
HEADER = Path(__file__).with_name("acww_game.h")

# (file, text to find, replacement, marker that shows the edit is already in)
EDITS = [
    (MAIN,
     '#include "acww_settings.h"   // acwwrecomp: settings.toml\n',
     '#include "acww_settings.h"   // acwwrecomp: settings.toml\n'
     '#include "acww_game.h"   // acwwrecomp: backups, mods, Discord\n',
     '#include "acww_game.h"'),
    (MAIN,
     "    nds_io_set_cartridge_save_path(save_path.c_str());\n",
     "    // acwwrecomp: back up the save, load the mods and start Discord.\n"
     "    acww_game::start(config_path, save_path);\n"
     "    nds_io_set_cartridge_save_path(save_path.c_str());\n",
     "acww_game::start(config_path, save_path);"),
    (FRONTEND,
     '#include "acww_hdtext.h"   // acwwrecomp: HD letters\n',
     '#include "acww_hdtext.h"   // acwwrecomp: HD letters\n'
     '#include "acww_game.h"   // acwwrecomp: backups, mods, Discord\n',
     '#include "acww_game.h"'),
    (FRONTEND,
     "        debug_pump();\n",
     "        debug_pump();\n"
     "        acww_game::frame();   // acwwrecomp: mods and Discord\n",
     "acww_game::frame();"),
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=Path(r"C:\acww\ndsrecomp"))
    args = parser.parse_args()
    if not HEADER.is_file():
        raise SystemExit(f"{HEADER} is missing: paste tools\\acww_game.h first")

    texts: dict[str, tuple[str, bool]] = {}
    for rel, *_ in EDITS:
        if rel not in texts:
            raw = (args.root / rel).read_bytes().decode("utf-8")
            texts[rel] = (raw.replace("\r\n", "\n"), "\r\n" in raw)
    if "acww_settings.h" not in texts[MAIN][0]:
        raise SystemExit("run patch_settings.py first; nothing was changed")

    changed = set()
    for rel, old, new, marker in EDITS:
        text, crlf = texts[rel]
        if marker in text:
            print(f"  already there: {rel}: {marker.strip()[:60]}")
            continue
        if text.count(old) != 1:
            raise SystemExit(f"{rel}: expected exactly one '{old.strip()[:60]}' "
                             f"(found {text.count(old)}); nothing was changed")
        texts[rel] = (text.replace(old, new), crlf)
        changed.add(rel)
        print(f"  patched: {rel}: {marker.strip()[:60]}")

    for rel in sorted(changed):
        text, crlf = texts[rel]
        out = text.replace("\n", "\r\n") if crlf else text
        (args.root / rel).write_bytes(out.encode("utf-8"))

    target = args.root / "runner/src/acww_game.h"
    header = HEADER.read_bytes().replace(b"\r\n", b"\n")
    if not target.is_file() or target.read_bytes().replace(b"\r\n", b"\n") != header:
        target.write_bytes(header)
        changed.add(str(target))
        print("  wrote: runner/src/acww_game.h")
    else:
        print("  already there: runner/src/acww_game.h")
    print(f"{len(changed)} file(s) changed" + ("; now rebuild the runner" if changed else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
