// Where Wild World Recomped's files are (launcher). A player's copy keeps
// everything in the folder they unzipped it to, and builds the game there on
// first start (setup_page.h). On the developer's PC the launcher uses the
// project and the runner built there, unless it's started with --setup, which
// goes through a player's first start in generated\setup-test instead.
#pragma once

#include <filesystem>
#include <string>
#include <system_error>
#include <vector>

#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>

namespace acww {

struct Layout {
    std::filesystem::path root;     // settings.toml, the save, game.toml, mods
    std::filesystem::path runner;   // the game
    bool release = false;           // a player's copy
    bool setup = false;             // the game is built here, by WildWorldBuild

    // What the build uses and makes (when setup is true).
    std::filesystem::path builder;      // WildWorldBuild.exe
    std::filesystem::path seeds;        // the entry points, from the coverage
    std::filesystem::path recompiler;   // nds_recompile.exe
    std::filesystem::path ndsrecomp;    // ndsrecomp's source (the runner's)
    std::filesystem::path recomp_ui;    // recomp-ui's source
    std::filesystem::path pack;         // the compiler pack, downloaded
    std::filesystem::path work;         // the build folder
    std::filesystem::path game;         // where the built game goes
};

// The folder the launcher's .exe is in.
inline std::filesystem::path exe_folder() {
    std::vector<wchar_t> buffer(MAX_PATH);
    for (;;) {
        const DWORD n = GetModuleFileNameW(nullptr, buffer.data(), static_cast<DWORD>(buffer.size()));
        if (n < buffer.size()) return std::filesystem::path(std::wstring(buffer.data(), n)).parent_path();
        buffer.resize(buffer.size() * 2);
    }
}

inline Layout find_layout(bool setup_test) {
    namespace fs = std::filesystem;
    Layout l;
    const fs::path exe = exe_folder();
    std::error_code ec;
    if (fs::exists(exe / "kit", ec)) {   // a release: kit\ holds what the build needs
        l.release = l.setup = true;
        l.root = exe;
        l.builder = exe / "WildWorldBuild.exe";
        l.seeds = exe / "kit" / "seeds";
        l.recompiler = exe / "kit" / "nds_recompile.exe";
        l.ndsrecomp = exe / "kit" / "ndsrecomp";
        l.recomp_ui = exe / "kit" / "recomp-ui";
        l.pack = exe / "pack";
        l.work = exe / "build";
        l.game = exe / "game";
        l.runner = l.game / "nds_runner.exe";
        return l;
    }
    l.root = fs::u8path(ACWW_ROOT);
    l.runner = fs::u8path(ACWW_RUNNER);
    if (setup_test) {
        const fs::path test = l.root / "generated" / "setup-test";
        l.setup = true;
        l.builder = exe / "WildWorldBuild.exe";
        l.seeds = l.root / "generated" / "ingest" / "seeds";
        l.recompiler = fs::u8path(ACWW_RECOMPILER);
        l.ndsrecomp = fs::u8path(ACWW_NDSRECOMP);
        l.recomp_ui = fs::u8path(ACWW_RECOMP_UI);
        l.pack = test / "pack";
        l.work = test / "build";
        l.game = test / "game";
        l.runner = l.game / "nds_runner.exe";
    }
    return l;
}

}  // namespace acww
