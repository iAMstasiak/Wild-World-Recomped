#!/usr/bin/env python3
"""Let the runner read settings.toml, the player's own choices.

settings.toml sits beside game.toml. The runner now reads its [graphics]
and [display] sections when it starts: resolution, texture smoothing, 2D
smoothing, HD letters, the frame rate in the title bar, screen layout and
fullscreen. play.ps1's -HD switches are no longer needed. The reading lives
in tools/acww_settings.h, which this copies into the runner.

Run after the other patch_*.py scripts. Safe to run again: edits that are
already there are skipped, and the header is refreshed. Rebuild the runner
afterwards: cmake --build C:\\acww\\ndsrecomp\\runner\\build-acww
"""

from __future__ import annotations

import argparse
from pathlib import Path

MAIN = "runner/src/main.cpp"
HEADER = Path(__file__).with_name("acww_settings.h")

# (file, text to find, replacement, marker that shows the edit is already in)
EDITS = [
    (MAIN,
     '#include "frontend.h"\n',
     '#include "frontend.h"\n'
     '#include "acww_settings.h"   // acwwrecomp: settings.toml\n',
     '#include "acww_settings.h"'),
    (MAIN,
     "            std::fprintf(stderr, \"invalid frontend config %s: %s\\n\",\n"
     "                         config_path.c_str(), config_error.c_str());\n"
     "            return 2;\n"
     "        }\n"
     "    }\n",
     "            std::fprintf(stderr, \"invalid frontend config %s: %s\\n\",\n"
     "                         config_path.c_str(), config_error.c_str());\n"
     "            return 2;\n"
     "        }\n"
     "    }\n"
     "    // acwwrecomp: the player's choices, from settings.toml beside game.toml.\n"
     "    acww_settings::load(config_path, &frontend_options);\n",
     "acww_settings::load(config_path, &frontend_options);"),
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=Path(r"C:\acww\ndsrecomp"))
    args = parser.parse_args()
    if not HEADER.is_file():
        raise SystemExit(f"{HEADER} is missing: paste tools\\acww_settings.h first")

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

    target = args.root / "runner/src/acww_settings.h"
    header = HEADER.read_bytes().replace(b"\r\n", b"\n")
    if not target.is_file() or target.read_bytes().replace(b"\r\n", b"\n") != header:
        target.write_bytes(header)
        changed.add(str(target))
        print("  wrote: runner/src/acww_settings.h")
    else:
        print("  already there: runner/src/acww_settings.h")
    print(f"{len(changed)} file(s) changed" + ("; now rebuild the runner" if changed else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
