#!/usr/bin/env python3
"""Choose how hard the compiler works on the game's generated code.

The recompiled game is about 1 GB of C, compiled at -O2. That is most of a
full rebuild, and it is what a player's PC will have to build too. This
adds a CMake setting, NDS_TITLE_BANK_OPT (default -O2, as before), so the
generated title banks can be compiled at -O1 instead: about three times
faster to compile, possibly a little slower to run.

  cmake -S C:\\acww\\ndsrecomp\\runner -B C:\\acww\\ndsrecomp\\runner\\build-acww -DNDS_TITLE_BANK_OPT=-O1
  cmake -S C:\\acww\\ndsrecomp\\runner -B C:\\acww\\ndsrecomp\\runner\\build-acww -DNDS_TITLE_BANK_OPT=-O2

Run after the other patch_*.py scripts. Safe to run again: edits that are
already there are skipped. Rebuild the runner afterwards:
cmake --build C:\\acww\\ndsrecomp\\runner\\build-acww
"""

from __future__ import annotations

import argparse
from pathlib import Path

CMAKE = "runner/CMakeLists.txt"

# (file, text to find, replacement, marker that shows the edit is already in)
EDITS = [
    (CMAKE,
     "if(TITLE_BANK_SOURCES AND NOT MSVC)\n"
     "    set_source_files_properties(${TITLE_BANK_SOURCES}\n"
     "        PROPERTIES COMPILE_OPTIONS \"-w;-O2;-g0\")\n"
     "endif()\n",
     "# acwwrecomp: how hard the compiler works on the generated title banks\n"
     "# (tools/patch_build.py). -O1 compiles them about three times faster.\n"
     "set(NDS_TITLE_BANK_OPT \"-O2\" CACHE STRING\n"
     "    \"Optimisation level for the generated title banks (-O1 or -O2)\")\n"
     "if(TITLE_BANK_SOURCES AND NOT MSVC)\n"
     "    set_source_files_properties(${TITLE_BANK_SOURCES}\n"
     "        PROPERTIES COMPILE_OPTIONS \"-w;${NDS_TITLE_BANK_OPT};-g0\")\n"
     "endif()\n",
     "NDS_TITLE_BANK_OPT"),
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=Path(r"C:\acww\ndsrecomp"))
    args = parser.parse_args()

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
    print(f"{len(changed)} file(s) changed" + ("; now reconfigure and rebuild the runner"
                                                if changed else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
