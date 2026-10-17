#!/usr/bin/env python3
"""Write acww.sav once per in-game save instead of once per page.

Saving sends the cartridge's backup chip a run of page writes (18 for an
ordinary save), and the runner rewrote the whole 256 KB save file after each
of them, waiting for the disk every time. Now a page write only marks the
save as changed (io.cpp), and the frame loop writes the file once the game
has been quiet for 750 ms (frontend.cpp). The runner still writes any unsaved
change when it closes. The timing lives in tools/acww_saves.h, which this
copies into the runner.

Run after the other patch_*.py scripts. Safe to run again: edits that are
already there are skipped, and the header is refreshed. Rebuild the runner
afterwards: cmake --build C:\\acww\\ndsrecomp\\runner\\build-acww
"""

from __future__ import annotations

import argparse
from pathlib import Path

IO = "runner/src/io.cpp"
FRONTEND = "runner/src/frontend.cpp"
HEADER = Path(__file__).with_name("acww_saves.h")

# (file, text to find, replacement, marker that shows the edit is already in)
EDITS = [
    (IO,
     '#include "battery_save.h"\n',
     '#include "battery_save.h"\n'
     '#include "acww_saves.h"   // acwwrecomp: one save-file write per save\n',
     '#include "acww_saves.h"'),
    (IO,
     "    if (last && g_cart_backup.dirty && !g_cart_save_path.empty())\n"
     "        nds_io_flush_cartridge_save();\n",
     "    if (last && g_cart_backup.dirty && !g_cart_save_path.empty())\n"
     "        acww_saves::written();   // acwwrecomp: written once the game stops saving\n",
     "acww_saves::written();"),
    (FRONTEND,
     '#include "acww_game.h"   // acwwrecomp: backups, mods, Discord\n',
     '#include "acww_game.h"   // acwwrecomp: backups, mods, Discord\n'
     '#include "acww_saves.h"   // acwwrecomp: one save-file write per save\n',
     '#include "acww_saves.h"'),
    (FRONTEND,
     "        acww_game::frame();   // acwwrecomp: mods and Discord\n",
     "        acww_game::frame();   // acwwrecomp: mods and Discord\n"
     "        acww_saves::tick();   // acwwrecomp: write acww.sav once the game stops saving\n",
     "acww_saves::tick();"),
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=Path(r"C:\acww\ndsrecomp"))
    args = parser.parse_args()
    if not HEADER.is_file():
        raise SystemExit(f"{HEADER} is missing: paste tools\\acww_saves.h first")

    texts: dict[str, tuple[str, bool]] = {}
    for rel, *_ in EDITS:
        if rel not in texts:
            raw = (args.root / rel).read_bytes().decode("utf-8")
            texts[rel] = (raw.replace("\r\n", "\n"), "\r\n" in raw)

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

    target = args.root / "runner/src/acww_saves.h"
    header = HEADER.read_bytes().replace(b"\r\n", b"\n")
    if not target.is_file() or target.read_bytes().replace(b"\r\n", b"\n") != header:
        target.write_bytes(header)
        changed.add(str(target))
        print("  wrote: runner/src/acww_saves.h")
    else:
        print("  already there: runner/src/acww_saves.h")
    print(f"{len(changed)} file(s) changed" + ("; now rebuild the runner" if changed else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
