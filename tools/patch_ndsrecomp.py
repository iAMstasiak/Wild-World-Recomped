#!/usr/bin/env python3
"""Apply acwwrecomp's small changes to the pinned ndsrecomp checkout.

  --rtc-offset-days N    start the --rtc-host clock N whole days ahead
  --rtc-offset-hours N   ... and N hours ahead (both add up)

These let day- and time-driven game logic (shop upgrades, opening hours,
events) be tested without changing the Windows clock.

Safe to run again: edits that are already there are skipped. Rebuild the
runner afterwards: cmake --build C:\\acww\\ndsrecomp\\runner\\build-acww
"""

from __future__ import annotations

import argparse
from pathlib import Path

# (file, text to find, replacement, marker that shows the edit is already in)
EDITS = [
    ("runner/src/io.h",
     "extern bool g_nds_rtc_host;\n",
     "extern bool g_nds_rtc_host;\n"
     "// acwwrecomp: whole days added to the host clock (--rtc-offset-days N).\n"
     "extern int g_nds_rtc_offset_days;\n",
     "extern int g_nds_rtc_offset_days;"),
    ("runner/src/io.cpp",
     "bool g_nds_rtc_host = false;\n",
     "bool g_nds_rtc_host = false;\n"
     "int g_nds_rtc_offset_days = 0;   // acwwrecomp\n",
     "int g_nds_rtc_offset_days = 0;"),
    ("runner/src/io.cpp",
     "    const std::time_t now = std::time(nullptr);\n",
     "    const std::time_t now = std::time(nullptr) +\n"
     "        static_cast<std::time_t>(g_nds_rtc_offset_days) * 86400;   // acwwrecomp\n",
     "static_cast<std::time_t>(g_nds_rtc_offset_days) * 86400"),
    ("runner/src/main.cpp",
     "            g_nds_rtc_host = true;\n",
     "            g_nds_rtc_host = true;\n"
     "        } else if (a == \"--rtc-offset-days\" && i + 1 < argc) {\n"
     "            // acwwrecomp: start the --rtc-host clock N whole days ahead.\n"
     "            g_nds_rtc_offset_days = static_cast<int>(std::strtol(argv[++i], nullptr, 10));\n",
     "a == \"--rtc-offset-days\""),
    ("runner/src/main.cpp",
     "\"[--discover-static-misses] [--rtc-host] \"",
     "\"[--discover-static-misses] [--rtc-host] [--rtc-offset-days N] \"",
     "[--rtc-offset-days N]"),
    # --rtc-offset-hours, layered on the edits above
    ("runner/src/io.h",
     "extern int g_nds_rtc_offset_days;\n",
     "extern int g_nds_rtc_offset_days;\n"
     "extern int g_nds_rtc_offset_hours;   // acwwrecomp: --rtc-offset-hours N\n",
     "extern int g_nds_rtc_offset_hours;"),
    ("runner/src/io.cpp",
     "int g_nds_rtc_offset_days = 0;   // acwwrecomp\n",
     "int g_nds_rtc_offset_days = 0;   // acwwrecomp\n"
     "int g_nds_rtc_offset_hours = 0;  // acwwrecomp\n",
     "int g_nds_rtc_offset_hours = 0;"),
    ("runner/src/io.cpp",
     "        static_cast<std::time_t>(g_nds_rtc_offset_days) * 86400;   // acwwrecomp\n",
     "        static_cast<std::time_t>(g_nds_rtc_offset_days) * 86400 +\n"
     "        static_cast<std::time_t>(g_nds_rtc_offset_hours) * 3600;   // acwwrecomp\n",
     "static_cast<std::time_t>(g_nds_rtc_offset_hours) * 3600"),
    ("runner/src/main.cpp",
     "            g_nds_rtc_offset_days = static_cast<int>(std::strtol(argv[++i], nullptr, 10));\n",
     "            g_nds_rtc_offset_days = static_cast<int>(std::strtol(argv[++i], nullptr, 10));\n"
     "        } else if (a == \"--rtc-offset-hours\" && i + 1 < argc) {\n"
     "            // acwwrecomp: ... and N hours ahead.\n"
     "            g_nds_rtc_offset_hours = static_cast<int>(std::strtol(argv[++i], nullptr, 10));\n",
     "a == \"--rtc-offset-hours\""),
    ("runner/src/main.cpp",
     "[--rtc-offset-days N] \"",
     "[--rtc-offset-days N] [--rtc-offset-hours N] \"",
     "[--rtc-offset-hours N]"),
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
            print(f"  already there: {rel}: {marker}")
            continue
        if text.count(old) != 1:
            raise SystemExit(f"{rel}: expected exactly one '{old.strip()}' "
                             f"(found {text.count(old)}); nothing was changed")
        texts[rel] = (text.replace(old, new), crlf)
        changed.add(rel)
        print(f"  patched: {rel}: {marker}")

    for rel in sorted(changed):
        text, crlf = texts[rel]
        out = text.replace("\n", "\r\n") if crlf else text
        (args.root / rel).write_bytes(out.encode("utf-8"))
    print(f"{len(changed)} file(s) changed" + ("; now rebuild the runner" if changed else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
