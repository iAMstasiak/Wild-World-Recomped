// acwwrecomp: settings.toml (copied in by tools/patch_settings.py; edit tools/acww_settings.h).
//
// settings.toml holds the player's own choices and sits beside game.toml,
// which describes the game itself. The launcher will write it; until then it
// is edited by hand. Order of precedence, weakest first: game.toml,
// settings.toml, the NDS_* and ACWW_* environment variables, the command line.
// Sections the runner does not read yet ([mods], [saves], [discord]) are left
// to the tools that handle them.
#pragma once

#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <string>

#include "frontend.h"
#include "perf_governor.h"
#include "toml.hpp"

namespace acww_settings {

// The frontend reads these switches at startup; a value already in the
// environment (set by hand or by play.ps1) wins over the file.
inline void set_default_env(const char* name, const char* value) {
    if (const char* now = std::getenv(name); now && *now) return;
#ifdef _WIN32
    _putenv_s(name, value);
#else
    setenv(name, value, 0);
#endif
}

inline void complain(const char* key, const char* expected) {
    std::fprintf(stderr, "[acwwrecomp] settings.toml: %s should be %s; ignored\n",
                 key, expected);
}

// Reads settings.toml from the folder game.toml is in. A missing file leaves
// everything as it was; a broken one is reported and ignored.
inline void load(const std::string& config_path, NdsFrontendOptions* options) {
    namespace fs = std::filesystem;
    const fs::path path = fs::path(config_path).parent_path() / "settings.toml";
    std::error_code ec;
    if (!options || !fs::exists(path, ec)) return;
    toml::table root;
    try {
        root = toml::parse_file(path.string());
    } catch (const toml::parse_error& e) {
        std::fprintf(stderr, "[acwwrecomp] settings.toml line %u: %s; using the defaults\n",
                     static_cast<unsigned>(e.source().begin.line),
                     std::string(e.description()).c_str());
        return;
    }

    if (const toml::table* graphics = root["graphics"].as_table()) {
        if (const auto value = (*graphics)["resolution"].value<int64_t>()) {
            if (!nds_parse_internal_resolution(std::to_string(*value),
                                               &options->internal_resolution))
                complain("graphics.resolution", "1, 2, 3 or 4");
        }
        if (const auto value = (*graphics)["texture_smoothing"].value<int64_t>()) {
            if (!nds_parse_texture_upscale(std::to_string(*value),
                                           &options->texture_upscale))
                complain("graphics.texture_smoothing", "1, 2 or 4");
        }
        if (const auto value = (*graphics)["smoothing_2d"].value<std::string>()) {
            if (*value == "xbr" || *value == "off")
                set_default_env("ACWW_SMOOTH_2D", value->c_str());
            else
                complain("graphics.smoothing_2d", "\"xbr\" or \"off\"");
        }
        if (const auto value = (*graphics)["hd_letters"].value<bool>())
            set_default_env("ACWW_HD_TEXT", *value ? "on" : "off");
        if (const auto value = (*graphics)["show_fps"].value<bool>())
            set_default_env("ACWW_SHOW_FPS", *value ? "1" : "0");
    }

    if (const toml::table* display = root["display"].as_table()) {
        if (const auto value = (*display)["screen_layout"].value<std::string>()) {
            if (!nds_parse_screen_layout(*value, &options->screen_layout))
                complain("display.screen_layout", "\"stacked\" or \"separate\"");
        }
        if (const auto value = (*display)["fullscreen"].value<std::string>()) {
            if (!nds_parse_fullscreen_mode(*value, &options->fullscreen))
                complain("display.fullscreen", "\"off\", \"borderless\" or \"exclusive\"");
        }
    }

    // Above 1x the performance governor is held at its first step: its second
    // step drops the resolution back to the DS's own.
    if (options->internal_resolution > 1)
        options->perf_governor_mode = NdsPerfGovernorMode::ForceStage1;

    std::fprintf(stderr, "[acwwrecomp] settings.toml: resolution %ux, texture smoothing %ux\n",
                 static_cast<unsigned>(options->internal_resolution),
                 static_cast<unsigned>(options->texture_upscale));
}

}  // namespace acww_settings
