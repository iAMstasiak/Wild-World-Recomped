#!/usr/bin/env python3
"""Let the game use the controls set in the launcher (keybinds.ini).

The launcher's Configure page saves the keyboard and controller controls to
keybinds.ini. The runner had its own fixed ones (Z/X for A/B and so on); now
key_bit() and controller_bit() in frontend.cpp look them up in keybinds.ini
first, the frame's stick poll adds triggers and sticks bound there, and the
fixed controls stay only when there is no keybinds.ini. The reading lives in
tools/acww_keys.h, which this copies into the runner.

Run after the other patch_*.py scripts. Safe to run again: edits that are
already there are skipped, and the header is refreshed. Rebuild the runner
afterwards: cmake --build C:\\acww\\ndsrecomp\\runner\\build-acww
"""

from __future__ import annotations

import argparse
from pathlib import Path

FRONTEND = "runner/src/frontend.cpp"
HEADER = Path(__file__).with_name("acww_keys.h")

# (file, text to find, replacement, marker that shows the edit is already in)
EDITS = [
    (FRONTEND,
     '#include "recomp_runtime_ui.h"\n',
     '#include "recomp_runtime_ui.h"\n'
     '#include "acww_keys.h"   // acwwrecomp: keybinds.ini\n',
     '#include "acww_keys.h"'),
    (FRONTEND,
     "uint16_t key_bit(SDL_Scancode key) {\n",
     "uint16_t key_bit(SDL_Scancode key) {\n"
     "    // acwwrecomp: the keys set in the launcher, when keybinds.ini is there.\n"
     "    if (acww_keys::current().loaded) return acww_keys::current()(key);\n",
     "if (acww_keys::current().loaded)"),
    (FRONTEND,
     "uint16_t controller_bit(SDL_GameControllerButton button) {\n",
     "uint16_t controller_bit(SDL_GameControllerButton button) {\n"
     "    // acwwrecomp: the controller buttons set in the launcher.\n"
     "    if (acww_keys::current().pad_loaded)\n"
     "        return acww_keys::current().button(static_cast<int>(button));\n",
     "if (acww_keys::current().pad_loaded)"),
    (FRONTEND,
     "                stick_dir(ly, 1u << 7, true);    // Down\n",
     "                stick_dir(ly, 1u << 7, true);    // Down\n"
     "                // acwwrecomp: triggers and sticks set in the launcher.\n"
     "                acww_keys::poll_axes(\n"
     "                    [&](int axis) {\n"
     "                        return SDL_GameControllerGetAxis(\n"
     "                                   controller,\n"
     "                                   static_cast<decltype(SDL_CONTROLLER_AXIS_LEFTX)>(axis)) /\n"
     "                               32767.0f;\n"
     "                    },\n"
     "                    stick_dir);\n",
     "acww_keys::poll_axes("),
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=Path(r"C:\acww\ndsrecomp"))
    args = parser.parse_args()
    if not HEADER.is_file():
        raise SystemExit(f"{HEADER} is missing: paste tools\\acww_keys.h first")

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

    target = args.root / "runner/src/acww_keys.h"
    header = HEADER.read_bytes().replace(b"\r\n", b"\n")
    if not target.is_file() or target.read_bytes().replace(b"\r\n", b"\n") != header:
        target.write_bytes(header)
        changed.add(str(target))
        print("  wrote: runner/src/acww_keys.h")
    else:
        print("  already there: runner/src/acww_keys.h")
    print(f"{len(changed)} file(s) changed" + ("; now rebuild the runner" if changed else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
