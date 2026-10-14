#!/usr/bin/env python3
"""Give the runner's window the project's name and the game's DS icon.

  Title bar   "Wild World Recomped" instead of "ndsrecomp firmware preview".
              The FPS and governor step are added after the name only when
              ACWW_SHOW_FPS=1 is set (play.ps1 -Fps does this).
  Icon        the window and taskbar icon is the game's own DS menu icon,
              read from the banner of the ROM given with --rom when the game
              starts, so none of Nintendo's art ships with the project.

Run after tools/patch_ndsrecomp.py, tools/patch_hd.py and
tools/patch_smooth2d.py. Safe to run again: edits that are already there are
skipped. Rebuild the runner afterwards:
cmake --build C:\\acww\\ndsrecomp\\runner\\build-acww
"""

from __future__ import annotations

import argparse
from pathlib import Path

FRONTEND = "runner/src/frontend.cpp"

# (file, text to find, replacement, marker that shows the edit is already in)
EDITS = [
    # --- the --rom path, handed from main.cpp to the frontend -------------
    ("runner/src/frontend.h",
     "#include \"perf_governor.h\"\n",
     "#include \"perf_governor.h\"\n"
     "\n"
     "// acwwrecomp: the --rom path, for the window icon (set in main.cpp).\n"
     "extern const char* g_acww_rom_path;\n",
     "extern const char* g_acww_rom_path;"),
    ("runner/src/main.cpp",
     "            rom_path = argv[++i];\n",
     "            rom_path = argv[++i];\n"
     "            g_acww_rom_path = argv[i];   // acwwrecomp: window icon\n",
     "g_acww_rom_path = argv[i];"),
    (FRONTEND,
     "#if defined(NDS_HAVE_COMPUTE_RENDERER)\n"
     "#include \"melonds_compute/ComputeHost.h\"\n"
     "#endif\n",
     "#if defined(NDS_HAVE_COMPUTE_RENDERER)\n"
     "#include \"melonds_compute/ComputeHost.h\"\n"
     "#endif\n"
     "\n"
     "// acwwrecomp: the project's name for the title bar, and the --rom path.\n"
     "const char* g_acww_rom_path = nullptr;\n"
     "static const char* const kAcwwTitle = \"Wild World Recomped\";\n",
     "const char* g_acww_rom_path = nullptr;"),

    # --- the icon: read the DS banner, hand it to the window --------------
    (FRONTEND,
     "bool set_window_fullscreen(SDL_Window* window, NdsFullscreenMode mode) {\n",
     r'''// acwwrecomp: the window and taskbar icon is the game's own DS menu icon,
// read from the banner of the player's ROM: 32x32 pixels in 8x8 tiles, 4 bits
// per pixel, 16 colours, colour 0 see-through. Nothing of it ships with the
// project. It is drawn at 2x with hard pixel edges so Windows shrinks it
// cleanly to the title bar and taskbar sizes.
bool acww_read_banner_icon(std::vector<uint32_t>& out) {
    if (!g_acww_rom_path || !*g_acww_rom_path) return false;
    std::ifstream rom(g_acww_rom_path, std::ios::binary);
    if (!rom) return false;
    uint8_t header[0x6C] = {};
    if (!rom.read(reinterpret_cast<char*>(header), sizeof(header)))
        return false;
    const uint32_t banner = static_cast<uint32_t>(header[0x68]) |
                            static_cast<uint32_t>(header[0x69]) << 8 |
                            static_cast<uint32_t>(header[0x6A]) << 16 |
                            static_cast<uint32_t>(header[0x6B]) << 24;
    if (banner == 0) return false;
    // Banner bytes 0x20-0x21F are the tiles, 0x220-0x23F the palette.
    uint8_t icon[0x220] = {};
    rom.seekg(static_cast<std::streamoff>(banner) + 0x20);
    if (!rom.read(reinterpret_cast<char*>(icon), sizeof(icon))) return false;
    uint32_t palette[16];
    for (int i = 0; i < 16; ++i) {
        const uint32_t c = static_cast<uint32_t>(icon[0x200 + i * 2]) |
                           static_cast<uint32_t>(icon[0x201 + i * 2]) << 8;
        auto expand = [](uint32_t v) { return (v << 3) | (v >> 2); };
        palette[i] = 0xFF000000u | expand(c & 31u) << 16 |
                     expand((c >> 5) & 31u) << 8 | expand((c >> 10) & 31u);
    }
    palette[0] = 0;
    out.assign(32 * 32, 0);
    for (int y = 0; y < 32; ++y) {
        for (int x = 0; x < 32; ++x) {
            const int tile = (y / 8) * 4 + x / 8;
            const uint8_t pair = icon[tile * 32 + (y % 8) * 4 + (x % 8) / 2];
            out[y * 32 + x] = palette[(x & 1) ? (pair >> 4) : (pair & 15)];
        }
    }
    return true;
}

void acww_set_window_icon(SDL_Window* window) {
#if defined(NDS_HAVE_SDL3)
    static std::vector<uint32_t> icon;
    static bool tried = false;
    if (!tried) {
        tried = true;
        if (acww_read_banner_icon(icon)) {
            std::fprintf(stderr,
                         "[acwwrecomp] window icon: the DS menu icon from %s\n",
                         g_acww_rom_path);
        } else {
            icon.clear();
            std::fprintf(stderr,
                         "[acwwrecomp] window icon: could not read the ROM's "
                         "banner, keeping the default icon\n");
        }
    }
    if (!window || icon.empty()) return;
    constexpr int kScale = 2;
    SDL_Surface* surface = SDL_CreateSurface(32 * kScale, 32 * kScale,
                                             SDL_PIXELFORMAT_ARGB8888);
    if (!surface) return;
    for (int y = 0; y < 32 * kScale; ++y) {
        uint32_t* row = reinterpret_cast<uint32_t*>(
            static_cast<uint8_t*>(surface->pixels) + y * surface->pitch);
        for (int x = 0; x < 32 * kScale; ++x)
            row[x] = icon[(y / kScale) * 32 + x / kScale];
    }
    SDL_SetWindowIcon(window, surface);
    SDL_DestroySurface(surface);
#else
    (void)window;
#endif
}

bool set_window_fullscreen(SDL_Window* window, NdsFullscreenMode mode) {
''',
     "void acww_set_window_icon(SDL_Window* window) {"),
    (FRONTEND,
     "        std::fprintf(stderr, \"[sdl] window failed: %s\\n\", SDL_GetError());\n"
     "        return false;\n"
     "    }\n",
     "        std::fprintf(stderr, \"[sdl] window failed: %s\\n\", SDL_GetError());\n"
     "        return false;\n"
     "    }\n"
     "    acww_set_window_icon(presentation.windows[0]);   // acwwrecomp\n",
     "acww_set_window_icon(presentation.windows[0]);"),
    (FRONTEND,
     "            std::fprintf(stderr, \"[sdl] bottom window failed: %s\\n\",\n"
     "                         SDL_GetError());\n"
     "            destroy_presentation(presentation);\n"
     "            return false;\n"
     "        }\n",
     "            std::fprintf(stderr, \"[sdl] bottom window failed: %s\\n\",\n"
     "                         SDL_GetError());\n"
     "            destroy_presentation(presentation);\n"
     "            return false;\n"
     "        }\n"
     "        acww_set_window_icon(presentation.windows[1]);   // acwwrecomp\n",
     "acww_set_window_icon(presentation.windows[1]);"),

    # --- the name in the title bar -----------------------------------------
    (FRONTEND,
     "        presentation.separate ? \"ndsrecomp - Top Screen\"\n"
     "                               : \"ndsrecomp firmware preview\",\n",
     "        presentation.separate ? \"Wild World Recomped - Top Screen\"\n"
     "                               : kAcwwTitle,   // acwwrecomp\n",
     ": kAcwwTitle,   // acwwrecomp"),
    (FRONTEND,
     "            \"ndsrecomp - Bottom Screen\",\n",
     "            \"Wild World Recomped - Bottom Screen\",\n",
     "\"Wild World Recomped - Bottom Screen\","),
    (FRONTEND,
     r'''            const std::string top_title = !savestate_notice.empty()
                ? "ndsrecomp - " + savestate_notice
                : presentation.separate
                ? "ndsrecomp - Top Screen - " + fps_text + governor_text
                : "ndsrecomp firmware preview - " + fps_text +
                      governor_text;
            SDL_SetWindowTitle(presentation.windows[0],
                               top_title.c_str());
            if (presentation.separate) {
                const std::string bottom_title =
                    "ndsrecomp - Bottom Screen - " + fps_text +
                    governor_text;
''',
     r'''            // acwwrecomp: the project's name; FPS only with ACWW_SHOW_FPS=1.
            static const bool show_fps = [] {
                const char* value = std::getenv("ACWW_SHOW_FPS");
                return value && *value && std::strcmp(value, "0") != 0;
            }();
            const std::string name = kAcwwTitle;
            const std::string stats =
                show_fps ? " - " + fps_text + governor_text : "";
            const std::string top_title = !savestate_notice.empty()
                ? name + " - " + savestate_notice
                : presentation.separate
                ? name + " - Top Screen" + stats
                : name + stats;
            SDL_SetWindowTitle(presentation.windows[0],
                               top_title.c_str());
            if (presentation.separate) {
                const std::string bottom_title =
                    name + " - Bottom Screen" + stats;
''',
     "// acwwrecomp: the project's name; FPS only with ACWW_SHOW_FPS=1."),
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
    print(f"{len(changed)} file(s) changed" + ("; now rebuild the runner" if changed else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
