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
And a background pattern drawn faintly behind everything
(ACWW_LAUNCHER_BACKGROUND, ACWW_LAUNCHER_BACKGROUND_MODE = cover or tile).
The game card can show the game's own name and a detail line in place of its
Region/File rows (ACWW_LAUNCHER_GAME_TITLE, ACWW_LAUNCHER_GAME_DETAIL), and a
card of its own under the controller card (ACWW_LAUNCHER_TOWN for its
heading, ACWW_LAUNCHER_TOWN_1, _2, ... for "Label<tab>Value" rows or lines).

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
    (IMGUI,
     "void draw_crt_background(ImVec2 origin, ImVec2 size) {\n",
     "// acwwrecomp: the game's background pattern (ACWW_LAUNCHER_BACKGROUND, a\n"
     "// picture with see-through paper), faint over the ground colour: scaled to\n"
     "// cover the window (ACWW_LAUNCHER_BACKGROUND_MODE=cover) or tiled.\n"
     "static void acww_draw_pattern(ImDrawList* dl, ImVec2 origin, ImVec2 size) {\n"
     "    static LauncherTexture tex = {0, 0, 0};\n"
     "    static bool tried = false;\n"
     "    if (!tried) {\n"
     "        tried = true;\n"
     "        const char* path = std::getenv(\"ACWW_LAUNCHER_BACKGROUND\");\n"
     "        if (path && path[0]) tex = launcher_texture_load(path);\n"
     "    }\n"
     "    if (!tex.id || tex.w <= 0 || tex.h <= 0) return;\n"
     "    const ImU32 tint = IM_COL32(255, 255, 255, 84);   // about a third\n"
     "    const char* mode = std::getenv(\"ACWW_LAUNCHER_BACKGROUND_MODE\");\n"
     "    if (mode && std::strcmp(mode, \"cover\") == 0) {\n"
     "        const float s = std::max(size.x / tex.w, size.y / tex.h);\n"
     "        const ImVec2 at(origin.x + (size.x - tex.w * s) * 0.5f,\n"
     "                        origin.y + (size.y - tex.h * s) * 0.5f);\n"
     "        dl->AddImage(tid(tex), at, ImVec2(at.x + tex.w * s, at.y + tex.h * s),\n"
     "                     ImVec2(0, 0), ImVec2(1, 1), tint);\n"
     "        return;\n"
     "    }\n"
     "    const float tw = px((float)tex.w), th = px((float)tex.h);\n"
     "    if (tw < 8.0f || th < 8.0f) return;\n"
     "    for (float y = origin.y; y < origin.y + size.y; y += th)\n"
     "        for (float x = origin.x; x < origin.x + size.x; x += tw)\n"
     "            dl->AddImage(tid(tex), ImVec2(x, y), ImVec2(x + tw, y + th),\n"
     "                         ImVec2(0, 0), ImVec2(1, 1), tint);\n"
     "}\n"
     "\n"
     "void draw_crt_background(ImVec2 origin, ImVec2 size) {\n",
     "static void acww_draw_pattern("),
    (IMGUI,
     "                                imcol(th.accent, 0.0f),  imcol(th.accent, 0.0f));\n",
     "                                imcol(th.accent, 0.0f),  imcol(th.accent, 0.0f));\n"
     "    acww_draw_pattern(bg, origin, size);   // acwwrecomp\n",
     "acww_draw_pattern(bg, origin, size);   // acwwrecomp"),
    (IMGUI,
     "    return ImGui::BeginChild(id, ImVec2(px(logical_w), 0.0f), flags, wflags);\n"
     "}\n"
     "void end_panel() { ImGui::EndChild(); }\n",
     "    // acwwrecomp: solid cards, so the background pattern stays behind them.\n"
     "    ImGui::PushStyleColor(ImGuiCol_ChildBg, col(g_th->panel));\n"
     "    const bool open = ImGui::BeginChild(id, ImVec2(px(logical_w), 0.0f), flags, wflags);\n"
     "    ImGui::PopStyleColor();\n"
     "    return open;\n"
     "}\n"
     "void end_panel() { ImGui::EndChild(); }\n",
     "acwwrecomp: solid cards"),
    (IMGUI,
     "    if (ImGui::BeginTable(\"meta\", 2, ImGuiTableFlags_SizingStretchProp)) {\n",
     "    // acwwrecomp: the game's own name, centred, in place of Region/File.\n"
     "    const char* acww_title = std::getenv(\"ACWW_LAUNCHER_GAME_TITLE\");\n"
     "    const char* acww_detail = std::getenv(\"ACWW_LAUNCHER_GAME_DETAIL\");\n"
     "    if (acww_title && acww_title[0]) {\n"
     "        const float tw = ImGui::CalcTextSize(acww_title).x;\n"
     "        ImGui::SetCursorPosX(ImGui::GetCursorPosX() + (availw > tw ? (availw - tw) * 0.5f : 0.0f));\n"
     "        ImGui::TextUnformatted(acww_title);\n"
     "        if (acww_detail && acww_detail[0]) {\n"
     "            const float dw = ImGui::CalcTextSize(acww_detail).x;\n"
     "            ImGui::SetCursorPosX(ImGui::GetCursorPosX() + (availw > dw ? (availw - dw) * 0.5f : 0.0f));\n"
     "            ImGui::TextColored(col(th.text_muted), \"%s\", acww_detail);\n"
     "        }\n"
     "    } else if (ImGui::BeginTable(\"meta\", 2, ImGuiTableFlags_SizingStretchProp)) {\n",
     "std::getenv(\"ACWW_LAUNCHER_GAME_TITLE\")"),
    (IMGUI,
     "void panel_controller_draw(LauncherModel* m, const LauncherTheme* th) {\n"
     "    draw_controllers_row(m, *th);\n",
     "// acwwrecomp: a card under the controller card, from ACWW_LAUNCHER_TOWN (its\n"
     "// heading) and ACWW_LAUNCHER_TOWN_1, _2, ... (\"Label<tab>Value\", or a line).\n"
     "static void acww_town_card(const LauncherTheme& th) {\n"
     "    const char* heading = std::getenv(\"ACWW_LAUNCHER_TOWN\");\n"
     "    if (!heading || !heading[0]) return;\n"
     "    ImGui::Dummy(ImVec2(0, px(th.spacing_md)));\n"
     "    if (begin_panel(\"acww_town\")) {\n"
     "        eyebrow(heading);\n"
     "        bool in_table = false;\n"
     "        for (int i = 1; i <= 8; ++i) {\n"
     "            char name[32];\n"
     "            std::snprintf(name, sizeof(name), \"ACWW_LAUNCHER_TOWN_%d\", i);\n"
     "            const char* row = std::getenv(name);\n"
     "            if (!row || !row[0]) break;\n"
     "            const char* tab = std::strchr(row, '\\t');\n"
     "            if (tab && !in_table &&\n"
     "                ImGui::BeginTable(\"acww_town_rows\", 2, ImGuiTableFlags_SizingStretchProp)) {\n"
     "                in_table = true;\n"
     "                ImGui::TableSetupColumn(\"k\", ImGuiTableColumnFlags_WidthFixed, px(96));\n"
     "                ImGui::TableSetupColumn(\"v\", ImGuiTableColumnFlags_WidthStretch);\n"
     "            }\n"
     "            if (tab && in_table) {\n"
     "                const std::string label(row, tab);\n"
     "                ImGui::TableNextRow();\n"
     "                ImGui::TableNextColumn();\n"
     "                ImGui::TextColored(col(th.text_muted), \"%s\", label.c_str());\n"
     "                ImGui::TableNextColumn();\n"
     "                ImGui::TextUnformatted(tab + 1);\n"
     "            } else if (!tab) {\n"
     "                if (in_table) { ImGui::EndTable(); in_table = false; }\n"
     "                ImGui::PushStyleColor(ImGuiCol_Text, col(th.text_muted));\n"
     "                ImGui::TextWrapped(\"%s\", row);\n"
     "                ImGui::PopStyleColor();\n"
     "            }\n"
     "        }\n"
     "        if (in_table) ImGui::EndTable();\n"
     "    }\n"
     "    end_panel();\n"
     "}\n"
     "\n"
     "void panel_controller_draw(LauncherModel* m, const LauncherTheme* th) {\n"
     "    draw_controllers_row(m, *th);\n"
     "    acww_town_card(*th);\n",
     "acww_town_card(*th);"),
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
