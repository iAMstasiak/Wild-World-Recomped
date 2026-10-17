// The launcher's Saves page (launcher): your save, its backups, and taking a
// save in or out. recomp-ui draws the header, the footer and a Saves button
// that opens this page (tools/patch_recompui.py); the page itself is drawn
// here with Dear ImGui and the card helpers recomp-ui shares (acww_ui_*).
// Restoring or importing always copies the current save into backups\ first.
#pragma once

#include <algorithm>
#include <cfloat>
#include <ctime>
#include <filesystem>
#include <fstream>
#include <string>
#include <system_error>
#include <vector>

#include <SDL3/SDL_misc.h>

#include "imgui.h"
#include "launcher_files.h"
#include "save_file.h"
#include "town.h"

// From recomp-ui, as patched by tools/patch_recompui.py.
extern void (*acww_saves_page)();
bool acww_ui_begin_card(const char* id, float width, bool fill);
void acww_ui_end_card();
void acww_ui_heading(const char* text);
ImVec4 acww_ui_color(int which);   // 0 text, 1 muted, 2 good, 3 warning, 4 heading

namespace acww {
namespace saves {

namespace fs = std::filesystem;

constexpr const char* kSave = "acww.sav";      // the game's save, beside settings.toml
constexpr const char* kBackups = "backups";    // where the game backs it up
constexpr const char* kConfirm = "Replace your save?";

struct Backup {
    fs::path path;
    SaveSummary save;
    bool same = false;   // the same as the current save
};

struct Page {
    int last_frame = -10;
    SaveSummary current;
    std::vector<Backup> backups;
    std::string status;           // what the last action did
    bool status_ok = true;
    // A save waiting for the player to say yes.
    bool ask = false;
    std::string question;
    std::vector<uint8_t> incoming;
    fs::path incoming_from;
    std::string done_text;
};

inline Page& page() {
    static Page p;
    return p;
}

// "Today 13:56", "Yesterday 18:02", "13 Oct 14:27", "2 Feb 2025 09:10".
inline std::string list_time(long long t) {
    if (t <= 0) return "?";
    const std::time_t tt = static_cast<std::time_t>(t);
    const std::tm when = *std::localtime(&tt);
    const std::time_t now_t = std::time(nullptr);
    const std::tm now = *std::localtime(&now_t);
    char clock[8];
    std::strftime(clock, sizeof(clock), "%H:%M", &when);
    const long days = days_ago(tt);
    if (days <= 0) return std::string("Today ") + clock;
    if (days == 1) return std::string("Yesterday ") + clock;
    return date_text(when, when.tm_year != now.tm_year) + " " + clock;
}

inline std::string who(const SaveSummary& s) {
    return s.player + " of " + s.town + ", " + with_commas(s.bells) + " bells";
}

// Reads the save and every backup again.
inline void refresh() {
    Page& p = page();
    p.current = read_save(kSave);
    const std::vector<uint8_t> current = read_save_bytes(kSave);
    p.backups.clear();
    std::error_code ec;
    for (const auto& entry : fs::directory_iterator(kBackups, ec)) {
        if (entry.path().extension() != ".sav") continue;
        const std::vector<uint8_t> bytes = read_save_bytes(entry.path());
        Backup b{entry.path(), summarize_save(bytes), !bytes.empty() && bytes == current};
        if (b.save.valid) b.save.saved = file_unix_time(entry.path());
        p.backups.push_back(b);
    }
    std::sort(p.backups.begin(), p.backups.end(), [](const Backup& a, const Backup& b) {
        if (a.save.saved != b.save.saved) return a.save.saved > b.save.saved;   // newest first
        return a.path.filename().string() > b.path.filename().string();
    });
    set_town_card(kSave);   // the Play page's Save Info card
}

// Copies acww.sav into backups\, named the way the game names its backups.
inline bool backup_current(std::string* error) {
    std::error_code ec;
    if (!fs::exists(kSave, ec)) return true;   // nothing to keep yet
    fs::create_directories(kBackups, ec);
    const std::time_t now = std::time(nullptr);
    char stamp[32];
    std::strftime(stamp, sizeof(stamp), "%Y%m%d-%H%M%S", std::localtime(&now));
    fs::path to = fs::path(kBackups) / ("acww-" + std::string(stamp) + ".sav");
    for (int n = 2; fs::exists(to, ec); ++n)
        to = fs::path(kBackups) / ("acww-" + std::string(stamp) + "-" + std::to_string(n) + ".sav");
    if (!fs::copy_file(kSave, to, ec) || ec) {
        *error = "Couldn't copy your save into the backups folder (" + ec.message() + ")";
        return false;
    }
    const auto saved = fs::last_write_time(kSave, ec);
    if (!ec) fs::last_write_time(to, saved, ec);   // keep when it was saved
    return true;
}

// Backs up acww.sav, then writes `data` over it with the time of `time_from`.
inline bool replace_save(const std::vector<uint8_t>& data, const fs::path& time_from,
                         std::string* error) {
    if (!backup_current(error)) {
        *error += ", so nothing was changed.";
        return false;
    }
    {
        std::ofstream out(kSave, std::ios::binary | std::ios::trunc);
        out.write(reinterpret_cast<const char*>(data.data()), static_cast<std::streamsize>(data.size()));
        if (!out) {
            *error = "Couldn't write acww.sav. Your previous save is in the backups folder.";
            return false;
        }
    }
    std::error_code ec;
    const auto saved = fs::last_write_time(time_from, ec);
    if (!ec) fs::last_write_time(kSave, saved, ec);
    return true;
}

inline void set_status(bool ok, const std::string& text) {
    page().status_ok = ok;
    page().status = text;
}

inline void ask_replace(const fs::path& from, const std::string& question, const std::string& done) {
    Page& p = page();
    p.incoming = read_save_bytes(from);
    p.incoming_from = from;
    p.question = question;
    p.done_text = done;
    p.ask = !p.incoming.empty();
}

inline void import_save() {
    static const char* const kPatterns[] = {"*.sav", "*.dsv", "*.bin"};
    char path[1024] = {};
    if (launcher_try_pick_file("Import a Wild World save", kPatterns, 3, "DS save files",
                               path, sizeof(path)) != 1)
        return;
    const fs::path from = fs::u8path(path);   // the picker hands back UTF-8
    const SaveSummary s = summarize_save(read_save_bytes(from));
    if (!s.valid) {
        set_status(false, "That file isn't a Wild World save the game can load, so nothing "
                          "was changed.");
        return;
    }
    const std::string name = from.filename().u8string();
    ask_replace(from,
                "Replace your save with " + name + " (" + who(s) + ")?\n\nYour current save "
                "is copied into the backups folder first.",
                "Imported " + name + ". Your previous save is in the backups folder.");
}

inline void export_save() {
    static const char* const kPatterns[] = {"*.sav"};
    char path[1024] = {};
    if (launcher_try_pick_save_file("Export your Wild World save", kPatterns, 1, "DS save files",
                                    path, sizeof(path)) != 1)
        return;
    fs::path to = fs::u8path(path);   // the picker hands back UTF-8
    if (!to.has_extension()) to += ".sav";
    std::error_code ec;
    fs::copy_file(kSave, to, fs::copy_options::overwrite_existing, ec);
    if (ec)
        set_status(false, "Couldn't export the save: " + ec.message() + ".");
    else
        set_status(true, "Exported your save to " + to.u8string() + ".");
}

inline void open_backups() {
    std::error_code ec;
    fs::create_directories(kBackups, ec);
    const std::string folder = fs::absolute(kBackups, ec).u8string();
    // SDL itself: ImGui's open-in-shell hook reads SDL3's answer back to front.
    if (!SDL_OpenURL(folder.c_str())) set_status(false, "Couldn't open " + folder + ".");
}

inline void muted(const char* text) {
    ImGui::PushStyleColor(ImGuiCol_Text, acww_ui_color(1));
    ImGui::TextWrapped("%s", text);
    ImGui::PopStyleColor();
}

inline void row(const char* label, const std::string& value) {
    ImGui::TableNextRow();
    ImGui::TableNextColumn();
    ImGui::TextColored(acww_ui_color(1), "%s", label);
    ImGui::TableNextColumn();
    ImGui::TextUnformatted(value.c_str());
}

// The left card: the save the game will load, and the buttons.
inline void draw_save_card() {
    Page& p = page();
    if (acww_ui_begin_card("acww_save", 400.0f, true)) {
        acww_ui_heading("YOUR SAVE");
        if (p.current.valid && ImGui::BeginTable("acww_save_rows", 2)) {
            ImGui::TableSetupColumn("k", ImGuiTableColumnFlags_WidthFixed, 96.0f);
            ImGui::TableSetupColumn("v", ImGuiTableColumnFlags_WidthStretch);
            row("Player", p.current.player);
            row("Town", p.current.town);
            row("Bells", with_commas(p.current.bells));
            if (p.current.residents > 1) row("Residents", std::to_string(p.current.residents));
            row("Last saved", p.current.saved > 0 ? when_text(p.current.saved) : "?");
            ImGui::EndTable();
        } else if (!p.current.valid) {
            muted("No save yet. It starts when you make your town in the game.");
        }
        ImGui::Dummy(ImVec2(0, 12.0f));
        const ImVec2 button(-FLT_MIN, 34.0f);
        ImGui::BeginDisabled(!p.current.valid);
        if (ImGui::Button("Back Up Now", button)) {
            std::string error;
            if (backup_current(&error))
                set_status(true, "Copied your save into the backups folder.");
            else
                set_status(false, error + ".");
            refresh();
        }
        ImGui::EndDisabled();
        if (ImGui::Button("Import a Save...", button)) import_save();
        ImGui::BeginDisabled(!p.current.valid);
        if (ImGui::Button("Export Save...", button)) export_save();
        ImGui::EndDisabled();
        if (ImGui::Button("Open Backups Folder", button)) open_backups();
        if (!p.status.empty()) {
            ImGui::Dummy(ImVec2(0, 8.0f));
            ImGui::PushStyleColor(ImGuiCol_Text, acww_ui_color(p.status_ok ? 2 : 3));
            ImGui::TextWrapped("%s", p.status.c_str());
            ImGui::PopStyleColor();
        }
        ImGui::Dummy(ImVec2(0, 8.0f));
        muted("The game backs up your save each time it starts (Settings says how many "
              "backups to keep). Restoring or importing backs up your current save first.");
    }
    acww_ui_end_card();
}

// The right card: every backup, newest first.
inline void draw_backups_card() {
    Page& p = page();
    if (acww_ui_begin_card("acww_backups", 0.0f, true)) {
        acww_ui_heading("BACKUPS");
        if (p.backups.empty()) muted("No backups yet. The game makes one each time it starts.");
        if (!p.backups.empty() &&
            ImGui::BeginTable("acww_backup_rows", 5,
                              ImGuiTableFlags_SizingStretchProp | ImGuiTableFlags_BordersInnerH)) {
            ImGui::TableSetupColumn("Saved", ImGuiTableColumnFlags_WidthStretch, 1.5f);
            ImGui::TableSetupColumn("Player", ImGuiTableColumnFlags_WidthStretch, 1.0f);
            ImGui::TableSetupColumn("Town", ImGuiTableColumnFlags_WidthStretch, 1.0f);
            ImGui::TableSetupColumn("Bells", ImGuiTableColumnFlags_WidthStretch, 1.0f);
            ImGui::TableSetupColumn("", ImGuiTableColumnFlags_WidthFixed, 110.0f);
            ImGui::TableNextRow();
            for (const char* name : {"Saved", "Player", "Town", "Bells"}) {
                ImGui::TableNextColumn();
                ImGui::TextColored(acww_ui_color(1), "%s", name);
            }
            ImGui::TableNextColumn();
            for (size_t i = 0; i < p.backups.size(); ++i) {
                const Backup& b = p.backups[i];
                ImGui::PushID(static_cast<int>(i));
                ImGui::TableNextRow();
                ImGui::TableNextColumn();
                ImGui::AlignTextToFramePadding();
                if (!b.save.valid) {
                    ImGui::TextColored(acww_ui_color(1), "%s", b.path.filename().u8string().c_str());
                    ImGui::TableNextColumn();
                    ImGui::TextColored(acww_ui_color(1), "not a save the game can load");
                    ImGui::PopID();
                    continue;
                }
                ImGui::TextUnformatted(list_time(b.save.saved).c_str());
                ImGui::TableNextColumn();
                ImGui::TextUnformatted(b.save.player.c_str());
                ImGui::TableNextColumn();
                ImGui::TextUnformatted(b.save.town.c_str());
                ImGui::TableNextColumn();
                ImGui::TextUnformatted(with_commas(b.save.bells).c_str());
                ImGui::TableNextColumn();
                if (b.same) {
                    ImGui::TextColored(acww_ui_color(1), "Same as now");
                } else if (ImGui::Button("Restore", ImVec2(-FLT_MIN, 0))) {
                    ask_replace(b.path,
                                "Go back to the save from " + list_time(b.save.saved) + " (" +
                                    who(b.save) + ")?\n\nYour current save is copied into "
                                    "the backups folder first.",
                                "Restored the save from " + list_time(b.save.saved) +
                                    ". Your previous save is in the backups folder.");
                }
                ImGui::PopID();
            }
            ImGui::EndTable();
        }
    }
    acww_ui_end_card();
}

// "Replace your save?" with Replace / Cancel.
inline void draw_confirm() {
    Page& p = page();
    if (p.ask) {
        ImGui::OpenPopup(kConfirm);
        p.ask = false;
    }
    const ImVec2 centre = ImGui::GetMainViewport()->GetCenter();
    ImGui::SetNextWindowPos(centre, ImGuiCond_Appearing, ImVec2(0.5f, 0.5f));
    if (!ImGui::BeginPopupModal(kConfirm, nullptr,
                                ImGuiWindowFlags_AlwaysAutoResize | ImGuiWindowFlags_NoMove))
        return;
    ImGui::PushTextWrapPos(420.0f);
    ImGui::TextUnformatted(p.question.c_str());
    ImGui::PopTextWrapPos();
    ImGui::Dummy(ImVec2(0, 10.0f));
    if (ImGui::Button("Replace", ImVec2(150.0f, 34.0f))) {
        std::string error;
        if (replace_save(p.incoming, p.incoming_from, &error))
            set_status(true, p.done_text);
        else
            set_status(false, error);
        p.incoming.clear();
        refresh();
        ImGui::CloseCurrentPopup();
    }
    ImGui::SameLine(0, 10.0f);
    if (ImGui::Button("Cancel", ImVec2(150.0f, 34.0f))) {
        p.incoming.clear();
        ImGui::CloseCurrentPopup();
    }
    ImGui::EndPopup();
}

// The page, drawn every frame while it is open (recomp-ui calls this).
inline void draw() {
    Page& p = page();
    const int frame = ImGui::GetFrameCount();
    if (frame - p.last_frame > 1) {   // just opened: read everything again
        refresh();
        p.status.clear();
    }
    p.last_frame = frame;
    draw_save_card();
    ImGui::SameLine(0, 16.0f);
    draw_backups_card();
    draw_confirm();
}

}  // namespace saves
}  // namespace acww
