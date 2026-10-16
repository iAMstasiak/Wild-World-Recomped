// Wild World Recomped launcher (launcher/main.cpp).
//
// Opens recomp-ui's launcher window with its Nintendo DS profile. Its
// Settings page and Mods page read and write settings.toml, and Play starts
// the game the same way play.ps1 does, in this console window. With "Skip
// launcher on boot" ticked it goes straight to the game; run it with
// --launcher to get the window back.

#include <algorithm>
#include <cerrno>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <ctime>
#include <filesystem>
#include <string>
#include <vector>

#include <process.h>

#include "game_options.h"
#include "launcher_profile.h"
#include "recomp_launcher.h"
#include "settings_file.h"

namespace {

// The one dump the game is built for: Animal Crossing: Wild World (USA, Rev 1).
const char* const kSha1[] = {"77fde3e30e1e6068395d1f96ea63be569b61c351"};
const char* const kRomPatterns[] = {"*.nds"};
const char* const kResolutionLabels[] = {"Native (256x192)", "2x (512x384)",
                                         "3x (768x576)", "4x (1024x768)"};
const int kResolutionValues[] = {1, 2, 3, 4};
const char* const kFullscreen[] = {"off", "borderless", "exclusive"};

const char* const kCredits =
    "Wild World Recomped\n"
    "Developed by Mieszko (M.Stasiak)\n"
    "\n"
    "Animal Crossing: Wild World recompiled to run natively on PC. You need "
    "your own copy of the game (USA, Rev 1).\n"
    "\n"
    "Built on ndsrecomp (static recompilation for the Nintendo DS), the melonDS "
    "device models, recomp-ui (this launcher) and Dear ImGui.\n"
    "\n"
    "Animal Crossing is a trademark of Nintendo. This project is not affiliated "
    "with or endorsed by Nintendo.";

// _spawnv joins the arguments with spaces as they are, so any with a space
// in them (a ROM in "OneDrive\Documents\...") need quotes.
std::string quoted(const std::string& arg) {
    if (!arg.empty() && arg.find_first_of(" \t\"") == std::string::npos) return arg;
    std::string out = "\"";
    for (char c : arg) {
        if (c == '"') out += '\\';
        out += c;
    }
    return out + "\"";
}

int start_game(const std::string& rom) {
    char stamp[32];
    const std::time_t now = std::time(nullptr);
    std::strftime(stamp, sizeof(stamp), "run-%Y%m%d-%H%M%S", std::localtime(&now));
    const std::vector<std::string> args = {
        ACWW_RUNNER, "bios", "--rom", rom, "--config", "game.toml", "--interactive",
        "--freebios", "--generated-firmware", "--boot", "direct", "--rtc-host",
        "--save-path", "acww.sav", "--firmware-state-path", "bios\\firmware-state.bin",
        "--diagnostics-dir", "generated\\diagnostics",
        "--coverage-manifest", std::string("generated\\coverage\\") + stamp + ".json"};
    std::vector<std::string> quoted_args;
    for (const std::string& arg : args) quoted_args.push_back(quoted(arg));
    std::vector<const char*> argv;
    for (const std::string& arg : quoted_args) argv.push_back(arg.c_str());
    argv.push_back(nullptr);
    std::fflush(stdout);
    std::fflush(stderr);
    const intptr_t code = _spawnv(_P_WAIT, ACWW_RUNNER, argv.data());
    if (code == -1) {
        std::fprintf(stderr, "[launcher] could not start %s: %s\n", ACWW_RUNNER,
                     std::strerror(errno));
        return 1;
    }
    return static_cast<int>(code);
}

std::vector<acww::ModFile> read_mods() {
    std::vector<std::filesystem::path> files;
    std::error_code ec;
    for (const auto& entry : std::filesystem::directory_iterator("mods", ec))
        if (entry.path().extension() == ".toml") files.push_back(entry.path());
    std::sort(files.begin(), files.end());
    std::vector<acww::ModFile> mods;
    for (const auto& file : files) {
        acww::ModFile mod;
        if (acww::read_mod_file(file, &mod)) mods.push_back(mod);
    }
    return mods;
}

}  // namespace

int main(int argc, char** argv) {
    // settings.toml, game.toml, the ROM and the save all live in the project.
    std::error_code ec;
    std::filesystem::current_path(ACWW_ROOT, ec);
    if (ec) {
        std::fprintf(stderr, "[launcher] can't open %s: %s\n", ACWW_ROOT, ec.message().c_str());
        return 1;
    }
    bool force_window = false;
    for (int i = 1; i < argc; ++i)
        if (std::strcmp(argv[i], "--launcher") == 0) force_window = true;

    acww::SettingsFile file;
    file.load("settings.toml");
    if (file.get_bool("launcher", "skip", false) && !force_window)
        return start_game(file.get("launcher", "rom", "acww.nds"));

    acww::GameOptions options;
    options.load(file, read_mods());
    const RecompLauncherCModProvider provider = options.provider();

    RecompLauncherCGameInfo game;
    std::memset(&game, 0, sizeof(game));
    launcher_profile_apply("nds", &game);   // theme, DS art, the DS's settings
    game.name = "Wild World Recomped";
    game.region = "USA";
    game.known_sha1_hex = kSha1;
    game.num_known_sha1 = 1;
    game.rom_patterns = kRomPatterns;
    game.num_rom_patterns = 1;
    game.config_path = "launcher.ini";      // where the launcher keeps its window size
    game.has_bios = 0;                      // the game runs on FreeBIOS, no dumps needed
    game.has_antialiasing = 0;              // the higher resolution smooths edges already
    game.has_virtual_stylus = 0;            // set in game.toml for now
    game.internal_resolution_labels = kResolutionLabels;
    game.internal_resolution_values = kResolutionValues;
    game.num_internal_resolutions = 4;
    game.internal_resolution_note = "3x is recommended. Lower it if the game stutters.";
    game.credits_text = kCredits;
    game.mods = &provider;

    RecompLauncherCSettings settings;
    std::memset(&settings, 0, sizeof(settings));
    settings.player_src[0] = 1;   // keyboard
    settings.enable_audio = 1;
    settings.volume = 100;
    settings.internal_resolution = std::clamp(file.get_int("graphics", "resolution", 3), 1, 4);
    const std::string fullscreen = file.get("display", "fullscreen", "off");
    settings.fullscreen = fullscreen == "borderless" ? 1 : fullscreen == "exclusive" ? 2 : 0;
    settings.skip_launcher = 0;

    const std::string last_rom = file.get("launcher", "rom", "acww.nds");
    char rom[1024] = {0};
    const int result = recomp_launcher_run_window("Wild World Recomped", &settings, &game,
                                                  "assets", last_rom.c_str(), rom, sizeof(rom));

    // Whichever way the window closed, keep what the player changed.
    file.load("settings.toml");   // in case it was edited by hand meanwhile
    if (settings.internal_resolution >= 1 && settings.internal_resolution <= 4)
        file.set("graphics", "resolution", std::to_string(settings.internal_resolution));
    file.set("display", "fullscreen",
             acww::SettingsFile::text(kFullscreen[std::clamp(settings.fullscreen, 0, 2)]));
    file.set("launcher", "skip", acww::SettingsFile::flag(settings.skip_launcher != 0));
    options.store(file);
    const std::string chosen = rom[0] ? rom : last_rom;
    if (result != RECOMP_LAUNCHER_RESULT_QUIT) file.set("launcher", "rom", acww::SettingsFile::text(chosen));
    if (!file.save("settings.toml"))
        std::fprintf(stderr, "[launcher] could not save settings.toml\n");

    if (result == RECOMP_LAUNCHER_RESULT_QUIT) return 0;
    if (result == RECOMP_LAUNCHER_RESULT_UNAVAILABLE)
        std::fprintf(stderr, "[launcher] the launcher window couldn't open; starting the game\n");
    return start_game(chosen);
}
