// Updates (launcher). When a player's copy opens, WildWorldBuild latest asks
// GitHub for the newest release; if it's newer than this launcher, an Update
// button shows in the header (recomp-ui, as patched by tools/patch_recompui.py).
// Pressing it downloads the zip with WildWorldBuild fetch, then starts a copy
// of WildWorldBuild to put it in place once the launcher has closed, and
// closes the launcher. The new one opens by itself and rebuilds the game,
// since game\built.txt names the old version.
#pragma once

#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <mutex>
#include <string>
#include <system_error>
#include <thread>
#include <vector>

#include <SDL3/SDL_events.h>

#include "builder/process.h"
#include "builder/update.h"
#include "imgui.h"
#include "layout.h"
#include "setup_page.h"

// From recomp-ui, as patched by tools/patch_recompui.py.
extern void (*acww_header_extra)(float right, float y, float height);
ImVec4 acww_ui_color(int which);   // 0 text, 1 muted, 2 good, 3 warning, 4 heading

namespace acww {
namespace update {

namespace fs = std::filesystem;

// Where releases are published.
constexpr const char* kRepo = "iAMstasiak/Wild-World-Recomped";

struct State {
    std::mutex mutex;
    Layout layout;
    std::string version;             // this launcher's
    std::string latest, url, size;   // the newest release, once it's known to be newer
    enum Stage { kNone, kAvailable, kDownloading, kFailed, kReady, kApplying };
    Stage stage = kNone;
    int percent = -1;
    std::string error;
};

// Never freed: the checks run on threads of their own, which may still be
// waiting on the network when the launcher closes.
inline State& state() {
    static State* s = new State;
    return *s;
}

inline void start_check(const Layout& l, const std::string& version) {
    State& s = state();
    s.layout = l;
    s.version = version;
    if (const char* as = std::getenv("ACWW_UPDATE_AS"))   // for testing: act as an older version
        if (as[0]) s.version = as;
    std::error_code ec;
    const fs::path dir = l.root / "update";
    fs::create_directories(dir, ec);
    fs::remove(dir / "WildWorldUpdate.exe", ec);   // left by the last update
    std::thread([&s, dir]() {
        std::string answer;
        wwbuild::run_process_lines({s.layout.builder.u8string(), "latest", "--repo", kRepo},
                                   (dir / "check.log").u8string(), [&](const std::string& line) {
                                       if (line.rfind("[latest] ", 0) == 0) answer = line.substr(9);
                                   });
        // "0.2 https://.../Wild.World.Recomped.0.2.zip 12267890", or "none"
        const size_t a = answer.find(' '), b = answer.find(' ', a + 1);
        if (a == std::string::npos) return;
        const std::string latest = answer.substr(0, a);
        std::lock_guard<std::mutex> lock(s.mutex);
        if (!wwbuild::newer_version(latest, s.version)) return;
        s.latest = latest;
        s.url = answer.substr(a + 1, b == std::string::npos ? std::string::npos : b - a - 1);
        s.size = b == std::string::npos ? "" : answer.substr(b + 1);
        s.stage = State::kAvailable;
    }).detach();
}

inline void start_download() {
    State& s = state();
    {
        std::lock_guard<std::mutex> lock(s.mutex);
        s.stage = State::kDownloading;
        s.percent = -1;
        s.error.clear();
    }
    std::thread([&s]() {
        const fs::path dir = s.layout.root / "update";
        std::vector<std::string> args = {s.layout.builder.u8string(), "fetch", "--url", s.url,
                                         "--out", (dir / "release.zip").u8string()};
        if (!s.size.empty()) args.insert(args.end(), {"--size", s.size});
        std::string error;
        const int code = wwbuild::run_process_lines(args, (dir / "fetch.log").u8string(),
                                                    [&](const std::string& line) {
            int n = 0, m = 0;
            if (line.rfind("[progress] ", 0) == 0 && std::sscanf(line.c_str() + 11, "%d/%d", &n, &m) == 2 && m > 0) {
                std::lock_guard<std::mutex> lock(s.mutex);
                s.percent = n * 100 / m;
            } else if (line.rfind("[error] ", 0) == 0) {
                error = line.substr(8);
            }
        });
        std::lock_guard<std::mutex> lock(s.mutex);
        if (code == 0) {
            s.stage = State::kReady;
        } else {
            s.stage = State::kFailed;
            s.error = error.empty() ? "the download stopped" : error;
        }
    }).detach();
}

// Starts a copy of WildWorldBuild to put the download in place (the program
// itself is one of the files it replaces) and closes the launcher.
inline void apply_and_quit(State& s) {
    const fs::path dir = s.layout.root / "update";
    const fs::path copy = dir / "WildWorldUpdate.exe";
    std::error_code ec;
    fs::copy_file(s.layout.builder, copy, fs::copy_options::overwrite_existing, ec);
    std::wstring command;
    for (const std::string& a : {copy.u8string(), std::string("apply-update"), std::string("--zip"),
                                 (dir / "release.zip").u8string(), std::string("--into"), s.layout.root.u8string(),
                                 std::string("--wait"), std::to_string(GetCurrentProcessId()),
                                 std::string("--restart")})
        command += (command.empty() ? L"" : L" ") + wwbuild::quote_arg(wwbuild::widen(a));
    std::vector<wchar_t> line(command.begin(), command.end());
    line.push_back(L'\0');
    STARTUPINFOW si{};
    si.cb = sizeof(si);
    PROCESS_INFORMATION pi{};
    if (ec || !CreateProcessW(copy.c_str(), line.data(), nullptr, nullptr, FALSE, CREATE_NO_WINDOW, nullptr,
                              dir.c_str(), &si, &pi)) {
        s.stage = State::kFailed;
        s.error = "the updater couldn't start";
        return;
    }
    CloseHandle(pi.hThread);
    CloseHandle(pi.hProcess);
    s.stage = State::kApplying;
    SDL_Event quit{};
    quit.type = SDL_EVENT_QUIT;
    SDL_PushEvent(&quit);
}

// The Update button, drawn left of the header's buttons, ending at right.
inline void draw_header(float right, float y, float height) {
    State& s = state();
    std::unique_lock<std::mutex> lock(s.mutex);
    if (s.stage == State::kNone) return;
    if (s.stage == State::kReady) apply_and_quit(s);
    std::string label;
    switch (s.stage) {
        case State::kAvailable: label = "Update to " + s.latest; break;
        case State::kDownloading:
            label = s.percent >= 0 ? "Downloading " + std::to_string(s.percent) + "%" : "Downloading...";
            break;
        case State::kFailed: label = "Update Failed - Retry"; break;
        default: label = "Updating..."; break;
    }
    const bool building = setup::page().job.running();
    const bool busy = building || (s.stage != State::kAvailable && s.stage != State::kFailed);
    const float w = ImGui::CalcTextSize(label.c_str()).x + height;
    ImGui::SetCursorPos(ImVec2(right - w, y));
    ImGui::BeginDisabled(busy);
    ImGui::PushStyleColor(ImGuiCol_Text, acww_ui_color(s.stage == State::kFailed ? 3 : 2));
    const bool pressed = ImGui::Button(label.c_str(), ImVec2(w, height));
    ImGui::PopStyleColor();
    ImGui::EndDisabled();
    if (ImGui::IsItemHovered(ImGuiHoveredFlags_AllowWhenDisabled)) {
        if (building) ImGui::SetTooltip("Wait for setup to finish");
        else if (s.stage == State::kFailed) ImGui::SetTooltip("%s", s.error.c_str());
        else if (s.stage == State::kAvailable)
            ImGui::SetTooltip("Downloads version %s and restarts the launcher. Your save and settings stay "
                              "as they are, and the game is built again.", s.latest.c_str());
    }
    lock.unlock();
    if (pressed) start_download();
}

}  // namespace update
}  // namespace acww
