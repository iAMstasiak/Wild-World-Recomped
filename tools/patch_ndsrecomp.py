#!/usr/bin/env python3
"""Apply acwwrecomp's small changes to the pinned ndsrecomp checkout.

  --rtc-offset-days N    start the --rtc-host clock N whole days ahead
  --rtc-offset-hours N   ... and N hours ahead (both add up)
  NDS_WATCH=lo-hi        record guest writes to one address range in the
                         debug port's `watch` ring (see tools/watch.py)
  HD at native width     --internal-resolution also works without the
                         runner's widescreen mode (needs --screen-layout
                         separate for now)

The clock offsets let day- and time-driven game logic (shop upgrades,
opening hours, events) be tested without changing the Windows clock.

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
    # NDS_WATCH: a user-chosen watch range (writes only) for finding code
    ("runner/src/bus.cpp",
     "bool watch_addr(uint32_t addr, uint32_t width) {\n",
     "// acwwrecomp: NDS_WATCH=lo-hi (e.g. 0x021FCFA8-0x021FCFAC) replaces the\n"
     "// built-in watch ranges with one range; only writes are recorded.\n"
     "struct UserWatch {\n"
     "    uint32_t lo = 0, hi = 0;\n"
     "    UserWatch() {\n"
     "        if (const char* s = std::getenv(\"NDS_WATCH\")) {\n"
     "            char* end = nullptr;\n"
     "            lo = static_cast<uint32_t>(std::strtoul(s, &end, 0));\n"
     "            if (end && *end == '-')\n"
     "                hi = static_cast<uint32_t>(std::strtoul(end + 1, nullptr, 0));\n"
     "        }\n"
     "    }\n"
     "};\n"
     "const UserWatch g_user_watch;\n"
     "\n"
     "bool watch_addr(uint32_t addr, uint32_t width) {\n"
     "    if (g_user_watch.hi > g_user_watch.lo)\n"
     "        return watch_range(addr, width, g_user_watch.lo, g_user_watch.hi);\n",
     "const UserWatch g_user_watch;"),
    ("runner/src/bus.cpp",
     "    if (!watch_addr(addr, width)) return;\n",
     "    if (!watch_addr(addr, width)) return;\n"
     "    if (g_user_watch.hi > g_user_watch.lo && !write) return;   // acwwrecomp\n",
     "g_user_watch.hi > g_user_watch.lo && !write"),
    # HD at the native width: the runner only built the HD surfaces in its
    # widescreen mode, so --internal-resolution showed nothing extra at 256.
    ("runner/src/frontend.cpp",
     "        if ((options.adaptive_screens & NDS_ADAPTIVE_TOP) &&\n"
     "            !nds_gpu2d_direct_present_frame_active())\n",
     "        if (((options.adaptive_screens & NDS_ADAPTIVE_TOP) ||\n"
     "             (options.internal_resolution > 1 && presentation.gl_top)) &&   // acwwrecomp: HD\n"
     "            !nds_gpu2d_direct_present_frame_active())\n",
     "(options.internal_resolution > 1 && presentation.gl_top)) &&   // acwwrecomp: HD"),
    ("runner/src/gpu2d.cpp",
     "    if (output_width <= 256) {\n",
     "    // acwwrecomp: at the native width the HD presenter still needs this\n"
     "    // compositor's surfaces, so only skip it when HD is off.\n"
     "    if (output_width < 256 || (output_width == 256 && !g_hd_emit_enabled)) {\n",
     "(output_width == 256 && !g_hd_emit_enabled)"),
    ("runner/src/gpu2d.cpp",
     "            if (wide_width > 256u &&\n",
     "            if ((wide_width > 256u ||\n"
     "                 (wide_width == 256u && g_hd_emit_enabled)) &&   // acwwrecomp: HD\n",
     "(wide_width == 256u && g_hd_emit_enabled)) &&   // acwwrecomp: HD"),
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
