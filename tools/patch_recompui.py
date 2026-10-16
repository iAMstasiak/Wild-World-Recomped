#!/usr/bin/env python3
"""Give recomp-ui a "Wild World" colour theme for the launcher.

recomp-ui (the launcher window, MIT) only has built-in themes, one per
console. This adds launcher_theme_acww() to its launcher_theme.h and lets
launcher_theme_by_name("acww") pick it; launcher/main.cpp asks for it. The
colours: a dark evening-green ground, the leaf's green for Play, warm
bell-gold headings, cream text and sky-blue focus outlines.

Safe to run again: edits already there are skipped. Run it again after
updating recomp-ui (git pull), then rebuild the launcher:
cmake --build launcher\\build
"""

from __future__ import annotations

import argparse
from pathlib import Path

THEME = "src/common/launcher_theme.h"

# (file, text to find, replacement, marker that shows the edit is already in)
EDITS = [
    (THEME,
     "// Pick a built-in theme by name",
     "// acwwrecomp: \"Wild World\" theme for Wild World Recomped. A dark\n"
     "// evening-green ground, the leaf's green for brand + Play, warm bell-gold\n"
     "// headings and cream text like the game's signs, sky-blue focus. Flat,\n"
     "// no scanlines.\n"
     "static inline LauncherTheme launcher_theme_acww(void) {\n"
     "    LauncherTheme t = launcher_theme_default();\n"
     "    t.background      = lng_rgba(0.047f, 0.063f, 0.043f, 1.0f); // #0C100B\n"
     "    t.background2     = lng_rgba(0.071f, 0.094f, 0.063f, 1.0f); // #121810\n"
     "    t.panel           = lng_rgba(0.078f, 0.102f, 0.071f, 1.0f); // #141A12\n"
     "    t.panel_hovered   = lng_rgba(0.118f, 0.153f, 0.106f, 1.0f); // #1E271B\n"
     "    t.control         = lng_rgba(0.098f, 0.129f, 0.086f, 1.0f); // #192116\n"
     "    t.control_hovered = lng_rgba(0.137f, 0.180f, 0.122f, 1.0f); // #232E1F\n"
     "    t.border          = lng_rgba(0.184f, 0.231f, 0.165f, 1.0f); // #2F3B2A\n"
     "    t.accent          = lng_rgba(0.361f, 0.776f, 0.294f, 1.0f); // #5CC64B leaf green\n"
     "    t.accent_dim      = lng_rgba(0.235f, 0.604f, 0.200f, 1.0f); // #3C9A33\n"
     "    t.accent_text     = lng_rgba(0.043f, 0.078f, 0.039f, 1.0f); // #0B140A\n"
     "    t.accent2         = lng_rgba(0.886f, 0.725f, 0.353f, 1.0f); // #E2B95A bell gold\n"
     "    t.text            = lng_rgba(0.941f, 0.929f, 0.886f, 1.0f); // #F0EDE2 cream\n"
     "    t.text_muted      = lng_rgba(0.612f, 0.620f, 0.557f, 1.0f); // #9C9E8E\n"
     "    t.good            = lng_rgba(0.482f, 0.827f, 0.420f, 1.0f); // #7BD36B\n"
     "    t.focus_ring      = lng_rgba(0.431f, 0.765f, 0.941f, 1.0f); // #6EC3F0 sky\n"
     "    t.scanlines       = 0;\n"
     "    return t;\n"
     "}\n"
     "\n"
     "// Pick a built-in theme by name",
     "launcher_theme_acww(void)"),
    (THEME,
     "static inline LauncherTheme launcher_theme_by_name(const char* name) {\n",
     "static inline LauncherTheme launcher_theme_by_name(const char* name) {\n"
     "    if (name && (name[0] == 'a' || name[0] == 'A') &&\n"
     "        (name[1] == 'c' || name[1] == 'C') &&\n"
     "        (name[2] == 'w' || name[2] == 'W') &&\n"
     "        (name[3] == 'w' || name[3] == 'W'))\n"
     "        return launcher_theme_acww();   // acwwrecomp\n",
     "return launcher_theme_acww();"),
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=Path(r"C:\acww\recomp-ui"))
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
    print(f"{len(changed)} file(s) changed" + ("; now rebuild the launcher" if changed else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
