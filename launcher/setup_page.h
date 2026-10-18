// The launcher's first-run setup (launcher): until the game is built, this
// page is drawn in place of the dashboard and Play is off (recomp-ui, as
// patched by tools/patch_recompui.py). Set Up downloads the compiler pack and
// builds the game from the player's ROM with WildWorldBuild (build_job.h);
// the dashboard comes back when it's done.
#pragma once

#include <cfloat>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <string>
#include <system_error>
#include <vector>

#include <SDL3/SDL_misc.h>

#include "build_job.h"
#include "imgui.h"
#include "launcher_files.h"
#include "layout.h"
#include "rom_art.h"

// From recomp-ui, as patched by tools/patch_recompui.py.
extern bool (*acww_setup_needed)();
extern void (*acww_setup_page)();
bool acww_ui_begin_card(const char* id, float width, bool fill);
void acww_ui_end_card();
void acww_ui_heading(const char* text);
ImVec4 acww_ui_color(int which);   // 0 text, 1 muted, 2 good, 3 warning, 4 heading
const char* acww_ui_rom();
bool acww_ui_rom_ok();
void acww_ui_set_rom(const char* path);
void acww_ui_set_boxart(const char* path);

namespace acww {
namespace setup {

namespace fs = std::filesystem;

struct Page {
    Layout layout;
    std::string version;   // the launcher's; a game built by another version is built again
    bool built = false;
    std::string rom_problem;
    BuildJob job;
};

inline Page& page() {
    static Page p;
    return p;
}

// game\built.txt names the version that built the game there.
inline bool is_built(const Layout& l, const std::string& version) {
    std::error_code ec;
    if (!fs::exists(l.runner, ec)) return false;
    std::ifstream file(l.game / "built.txt");
    std::string line;
    std::getline(file, line);
    return line == version;
}

inline bool needed() {
    const Page& p = page();
    return p.layout.setup && !p.built;
}

inline void init(const Layout& l, const std::string& version) {
    Page& p = page();
    p.layout = l;
    p.version = version;
    p.built = !l.setup || is_built(l, version);
}

inline void muted(const char* text) {
    ImGui::PushStyleColor(ImGuiCol_Text, acww_ui_color(1));
    ImGui::TextWrapped("%s", text);
    ImGui::PopStyleColor();
}

// A filled dot for a step that's done, a ring for one still to do.
inline void dot(bool done) {
    const float r = ImGui::GetTextLineHeight() * 0.3f;
    const ImVec2 at = ImGui::GetCursorScreenPos();
    const ImVec2 c(at.x + r + 2.0f, at.y + ImGui::GetTextLineHeight() * 0.5f + 3.0f);
    ImDrawList* dl = ImGui::GetWindowDrawList();
    const ImU32 colour = ImGui::GetColorU32(acww_ui_color(done ? 2 : 1));
    if (done) dl->AddCircleFilled(c, r, colour);
    else dl->AddCircle(c, r, colour, 0, 1.5f);
    ImGui::Dummy(ImVec2(r * 2.0f + 4.0f, ImGui::GetTextLineHeight()));
}

inline std::string minutes_text(double seconds) {
    const int s = static_cast<int>(seconds);
    char text[32];
    std::snprintf(text, sizeof(text), "%d:%02d", s / 60, s % 60);
    return text;
}

inline void choose_rom() {
    Page& p = page();
    static const char* const kPatterns[] = {"*.nds"};
    char path[1024] = {};
    if (launcher_try_pick_file("Choose your Animal Crossing: Wild World ROM", kPatterns, 1, "DS ROMs", path,
                               sizeof(path)) != 1)
        return;
    acww_ui_set_rom(path);
    p.rom_problem = acww_ui_rom_ok() ? "" : "That isn't Animal Crossing: Wild World (USA, revision 1), the "
                                            "version this is made for.";
}

// The ROM's box art, name and publisher, which the launcher reads when it
// opens: setup may have been given a ROM the launcher hadn't seen then.
inline void show_rom_art(const std::string& rom) {
    const std::string box_art = make_box_art(rom);
    if (!box_art.empty()) {
        _putenv(("ACWW_LAUNCHER_BRAND=" + box_art).c_str());
        acww_ui_set_boxart(box_art.c_str());
    }
    const RomTitle title = read_banner_title(rom);
    if (!title.name.empty()) {
        _putenv(("ACWW_LAUNCHER_GAME_TITLE=" + title.name).c_str());
        const std::string detail = title.publisher.empty() ? "USA" : title.publisher + "  \u00B7  USA";
        _putenv(("ACWW_LAUNCHER_GAME_DETAIL=" + detail).c_str());
    }
}

inline void open_folder(const fs::path& folder) {
    std::error_code ec;
    const std::string path = fs::absolute(folder, ec).u8string();
    SDL_OpenURL(path.c_str());   // SDL itself: ImGui's hook reads SDL3's answer back to front
}

// The three things setup needs, each with a dot.
inline void draw_steps(bool rom_ok, bool pack_ok, bool built) {
    Page& p = page();
    if (!ImGui::BeginTable("acww_setup_steps", 3, ImGuiTableFlags_SizingStretchProp)) return;
    ImGui::TableSetupColumn("dot", ImGuiTableColumnFlags_WidthFixed, 24.0f);
    ImGui::TableSetupColumn("what", ImGuiTableColumnFlags_WidthFixed, 150.0f);
    ImGui::TableSetupColumn("detail", ImGuiTableColumnFlags_WidthStretch);

    ImGui::TableNextRow();
    ImGui::TableNextColumn();
    dot(rom_ok);
    ImGui::TableNextColumn();
    ImGui::TextUnformatted("Your ROM");
    ImGui::TableNextColumn();
    if (rom_ok) {
        ImGui::TextUnformatted(fs::u8path(acww_ui_rom()).filename().u8string().c_str());
        ImGui::SameLine();
        ImGui::BeginDisabled(p.job.running());
        if (ImGui::SmallButton("Change...")) choose_rom();
        ImGui::EndDisabled();
    } else {
        muted("Animal Crossing: Wild World (USA, revision 1), dumped from your own cartridge.");
        if (ImGui::Button("Choose Your ROM...")) choose_rom();
        if (!p.rom_problem.empty()) {
            ImGui::PushStyleColor(ImGuiCol_Text, acww_ui_color(3));
            ImGui::TextWrapped("%s", p.rom_problem.c_str());
            ImGui::PopStyleColor();
        }
    }

    ImGui::TableNextRow();
    ImGui::TableNextColumn();
    dot(pack_ok);
    ImGui::TableNextColumn();
    ImGui::TextUnformatted("The compiler");
    ImGui::TableNextColumn();
    if (pack_ok) ImGui::TextUnformatted("Ready");
    else muted("Downloaded from w64devkit and SDL when you start (70 MB).");

    ImGui::TableNextRow();
    ImGui::TableNextColumn();
    dot(built);
    ImGui::TableNextColumn();
    ImGui::TextUnformatted("The game");
    ImGui::TableNextColumn();
    if (built) ImGui::TextUnformatted("Built");
    else muted("Built from your ROM on this PC: about 15 minutes on a recent one.");
    ImGui::EndTable();
}

inline void draw_running(const BuildStatus& s) {
    Page& p = page();
    ImGui::TextUnformatted(s.phase.c_str());
    char overlay[16];
    std::snprintf(overlay, sizeof(overlay), "%d%%", static_cast<int>(std::floor(s.fraction * 100.0f)));
    ImGui::ProgressBar(s.fraction, ImVec2(-FLT_MIN, 0.0f), overlay);
    std::string line = minutes_text(s.elapsed);
    if (s.left >= 0.0) {
        const int minutes = static_cast<int>(std::ceil(s.left / 60.0));
        line += minutes <= 1 ? "  -  about a minute left"
                             : "  -  about " + std::to_string(minutes) + " minutes left";
    }
    if (!s.detail.empty()) line += "  -  " + s.detail;
    muted(line.c_str());
    ImGui::Dummy(ImVec2(0, 8.0f));
    if (ImGui::Button("Cancel", ImVec2(140.0f, 34.0f))) p.job.cancel();
    ImGui::SameLine();
    muted("Leave the launcher open while it builds. You can carry on using your PC.");
}

inline void draw_failed(const BuildStatus& s) {
    ImGui::PushStyleColor(ImGuiCol_Text, acww_ui_color(3));
    ImGui::TextWrapped("Setup stopped: %s.", s.error.c_str());
    ImGui::PopStyleColor();
    if (!s.log.empty()) {
        ImGui::Dummy(ImVec2(0, 4.0f));
        if (ImGui::BeginChild("acww_setup_log", ImVec2(-FLT_MIN, 140.0f), ImGuiChildFlags_Borders,
                              ImGuiWindowFlags_HorizontalScrollbar)) {
            for (const std::string& l : s.log) ImGui::TextColored(acww_ui_color(1), "%s", l.c_str());
        }
        ImGui::EndChild();
    }
    ImGui::Dummy(ImVec2(0, 8.0f));
}

inline void draw() {
    Page& p = page();
    const BuildStatus s = p.job.status();
    if (s.state == BuildStatus::kDone && !p.built) {
        std::ofstream file(p.layout.game / "built.txt", std::ios::trunc);
        file << p.version << "\n";
        p.built = true;   // the dashboard comes back next frame
        show_rom_art(acww_ui_rom());
    }
    const bool rom_ok = acww_ui_rom_ok();
    std::error_code ec;
    const bool pack_ok = fs::exists(p.layout.pack / "pack.txt", ec);

    if (acww_ui_begin_card("acww_setup", 0.0f, true)) {
        acww_ui_heading("SET UP THE GAME");
        muted("Wild World Recomped builds the game on your PC from your own copy of Animal Crossing: "
              "Wild World. It only does this once. Nothing from Nintendo is downloaded.");
        ImGui::Dummy(ImVec2(0, 10.0f));
        draw_steps(rom_ok, pack_ok, p.built);
        ImGui::Dummy(ImVec2(0, 14.0f));
        if (s.state == BuildStatus::kRunning) {
            draw_running(s);
        } else {
            if (s.state == BuildStatus::kFailed) draw_failed(s);
            if (!s.note.empty()) muted(s.note.c_str());
            ImGui::BeginDisabled(!rom_ok);
            if (ImGui::Button(s.state == BuildStatus::kFailed ? "Try Again" : "Set Up", ImVec2(180.0f, 38.0f)))
                p.job.start(p.layout, acww_ui_rom());
            ImGui::EndDisabled();
            if (!rom_ok && ImGui::IsItemHovered(ImGuiHoveredFlags_AllowWhenDisabled))
                ImGui::SetTooltip("Choose your ROM first");
            if (s.state == BuildStatus::kFailed) {
                ImGui::SameLine();
                if (ImGui::Button("Open the Logs", ImVec2(180.0f, 38.0f))) open_folder(p.layout.work / "logs");
            }
        }
    }
    acww_ui_end_card();
}

}  // namespace setup
}  // namespace acww
