#!/usr/bin/env python3
"""Wild World's changes to recomp-ui: its look, and rebinding that sticks.

recomp-ui (the launcher window, MIT) only has built-in themes, one per
console. This adds launcher_theme_acww() to its launcher_theme.h and lets
launcher_theme_by_name("acww") pick it; launcher/main.cpp asks for it. The
colours: a dark evening-green ground, the leaf's green for Play, warm
bell-gold headings, cream text and sky-blue focus outlines.

It also fixes the Configure page for consoles whose controls the host keeps
(the DS): the page shows Settings.player_key_bind / player_pad_bind, but a
key or controller button pressed to rebind went to recomp-ui's own
keybinds.ini store instead, so the chip never changed. Now it goes into the
settings the page shows, which launcher/main.cpp saves to keybinds.ini.

For a one-player game, the dashboard card and the Configure page drop
their "PLAYER 1" labels. The launcher can bring its own font
(assets/fonts/launcher.ttf, beside the .exe) and its own corner picture
(the file named by the ACWW_LAUNCHER_BRAND environment variable) and its
own subtitle under the title (ACWW_LAUNCHER_SUBTITLE; GameInfo.platform has
to stay "NINTENDO DS", because recomp-ui picks the console profile by it).

Safe to run again: edits already there are skipped. Run it again after
updating recomp-ui (git pull), then rebuild the launcher:
cmake --build launcher\\build
"""

from __future__ import annotations

import argparse
from pathlib import Path

THEME = "src/common/launcher_theme.h"
IMGUI = "src/common/backends/imgui/launcher_imgui.cpp"

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
    (IMGUI,
     "bool try_capture(LauncherModel* m, const SDL_Event& ev) {\n",
     "// acwwrecomp: on a console whose controls the host keeps (the Controller\n"
     "// page shows Settings.player_key_bind / player_pad_bind), a captured player\n"
     "// key or controller input belongs there too, not in keybinds.ini.\n"
     "static bool acww_settings_player_binds(const LauncherModel* m) {\n"
     "    const SystemProfile* prof = (const SystemProfile*)m->profile;\n"
     "    return m->settings_bindings && !m->capture_assist &&\n"
     "           !(prof && prof->id && !strcmp(prof->id, \"psx\"));\n"
     "}\n"
     "\n"
     "bool try_capture(LauncherModel* m, const SDL_Event& ev) {\n",
     "static bool acww_settings_player_binds("),
    (IMGUI,
     "        if (m->capturing && m->capture_pad) {\n"
     "            if (m->capture_assist)\n"
     "                launcher_model_set_captured_pad(m, 0);\n",
     "        if (m->capturing && m->capture_pad) {\n"
     "            if (m->capture_assist || acww_settings_player_binds(m))   // acwwrecomp\n"
     "                launcher_model_set_captured_pad(m, 0);\n",
     "if (m->capture_assist || acww_settings_player_binds(m))   // acwwrecomp\n"
     "                launcher_model_set_captured_pad(m, 0);"),
    (IMGUI,
     "            const SystemProfile* prof = (const SystemProfile*)m->profile;\n"
     "            if (m->capture_assist)\n"
     "                launcher_model_set_captured_key(m, 0);\n",
     "            const SystemProfile* prof = (const SystemProfile*)m->profile;\n"
     "            if (m->capture_assist || acww_settings_player_binds(m))   // acwwrecomp\n"
     "                launcher_model_set_captured_key(m, 0);\n",
     "if (m->capture_assist || acww_settings_player_binds(m))   // acwwrecomp\n"
     "                launcher_model_set_captured_key(m, 0);"),
    (IMGUI,
     "    if (m->capturing && m->capture_pad) {\n"
     "        if (m->settings_bindings && m->capture_assist) {\n",
     "    if (m->capturing && m->capture_pad) {\n"
     "        if (acww_settings_player_binds(m)) {   // acwwrecomp: a player's pad chip\n"
     "            int value = 0;\n"
     "            if (ev.type == SDL_EVENT_GAMEPAD_BUTTON_DOWN) {\n"
     "                value = RECOMP_LAUNCHER_PAD_BUTTON((int)LNG_EVGBTN(ev));\n"
     "            } else if (ev.type == SDL_EVENT_GAMEPAD_AXIS_MOTION) {\n"
     "                const int val = (int)LNG_EVGAXISVAL(ev);\n"
     "                if (val >= 20000 || val <= -20000)\n"
     "                    value = RECOMP_LAUNCHER_PAD_AXIS((int)LNG_EVGAXIS(ev), val > 0);\n"
     "            }\n"
     "            if (value) {\n"
     "                launcher_model_set_captured_pad(m, value);\n"
     "                if (m->map_all_active) launcher_model_map_all_advance(m);\n"
     "                else                   launcher_model_cancel_capture(m);\n"
     "            }\n"
     "            return true;\n"
     "        }\n"
     "        if (m->settings_bindings && m->capture_assist) {\n",
     "acwwrecomp: a player's pad chip"),
    (IMGUI,
     "        if (m->settings_bindings && m->capture_assist)\n"
     "            launcher_model_set_captured_key(m, (int)LNG_EVSCAN(ev));\n",
     "        if (m->settings_bindings && m->capture_assist)\n"
     "            launcher_model_set_captured_key(m, (int)LNG_EVSCAN(ev));\n"
     "        else if (acww_settings_player_binds(m))   // acwwrecomp\n"
     "            launcher_model_set_captured_key(m, (int)LNG_EVSCAN(ev));\n",
     "else if (acww_settings_player_binds(m))   // acwwrecomp"),
    # One player: no "PLAYER 1" on the dashboard card or the Configure page.
    (IMGUI,
     "    ImGui::PushID(p);\n"
     "    eyebrow(eb);\n",
     "    ImGui::PushID(p);\n"
     "    if (m->player_count > 1 || m->netplay_supported)   // acwwrecomp: one player\n"
     "        eyebrow(eb);\n",
     "if (m->player_count > 1 || m->netplay_supported)   // acwwrecomp: one player"),
    (IMGUI,
     "        ImGui::Text(\"%s %d\", ui_text(\"CONTROLLER - PLAYER\"), p + 1); "
     "ImGui::PopStyleColor(); ImGui::Spacing();\n",
     "        if (m->player_count > 1)\n"
     "            ImGui::Text(\"%s %d\", ui_text(\"CONTROLLER - PLAYER\"), p + 1);\n"
     "        else\n"
     "            ImGui::TextUnformatted(ui_text(\"CONTROLLER\"));   // acwwrecomp: one player\n"
     "        ImGui::PopStyleColor(); ImGui::Spacing();\n",
     "ImGui::TextUnformatted(ui_text(\"CONTROLLER\"));   // acwwrecomp: one player"),
    (IMGUI,
     "        if (has_pad) ImGui::Text(\"INPUT BINDINGS - PLAYER %d\", p + 1);\n",
     "        if (m->player_count <= 1)   // acwwrecomp: one player\n"
     "            ImGui::TextUnformatted(has_pad ? \"INPUT BINDINGS\" : \"KEYBOARD BINDINGS\");\n"
     "        else if (has_pad) ImGui::Text(\"INPUT BINDINGS - PLAYER %d\", p + 1);\n",
     "has_pad ? \"INPUT BINDINGS\" : \"KEYBOARD BINDINGS\""),
    # The game's own font and corner picture, when it brings them.
    (IMGUI,
     "    std::string font_path = asset(\"assets/fonts/LatoLatin-Regular.ttf\");\n",
     "    // acwwrecomp: the game's own font, when it ships one.\n"
     "    std::string font_path = asset(\"assets/fonts/launcher.ttf\");\n"
     "    if (FILE* game_font = std::fopen(font_path.c_str(), \"rb\")) std::fclose(game_font);\n"
     "    else font_path = asset(\"assets/fonts/LatoLatin-Regular.ttf\");\n",
     "acwwrecomp: the game's own font"),
    (IMGUI,
     "        if (brand_file && brand_file[0])\n"
     "            g_brand = launcher_texture_load(\n",
     "        // acwwrecomp: the game's own corner picture, when the host names one.\n"
     "        const char* acww_brand = std::getenv(\"ACWW_LAUNCHER_BRAND\");\n"
     "        if (acww_brand && acww_brand[0])\n"
     "            g_brand = launcher_texture_load(acww_brand);\n"
     "        else if (brand_file && brand_file[0])\n"
     "            g_brand = launcher_texture_load(\n",
     "std::getenv(\"ACWW_LAUNCHER_BRAND\")"),
    (IMGUI,
     "            ImGui::PushStyleColor(ImGuiCol_Text, col(th.text_muted));\n"
     "            ImGui::TextUnformatted(m->platform);\n",
     "            ImGui::PushStyleColor(ImGuiCol_Text, col(th.text_muted));\n"
     "            // acwwrecomp: the game's own subtitle, when the host names one.\n"
     "            const char* acww_subtitle = std::getenv(\"ACWW_LAUNCHER_SUBTITLE\");\n"
     "            ImGui::TextUnformatted(acww_subtitle && acww_subtitle[0] ? acww_subtitle\n"
     "                                                                     : m->platform);\n",
     "std::getenv(\"ACWW_LAUNCHER_SUBTITLE\")"),
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
