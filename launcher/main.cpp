// Wild World Recomped launcher (launcher/main.cpp).
//
// Opens recomp-ui's launcher window with its Nintendo DS profile. Its
// Settings page and Mods page read and write settings.toml, and Play starts
// the game the same way play.ps1 does. It is a windowed program with no
// console: what the game prints goes to generated\logs\last-run.log. With
// "Skip launcher on boot" ticked it goes straight to the game; hold Shift
// while it starts (or run it with --launcher) to get the window back.
//
// A player's copy builds the game on its first start: until then the window
// shows the setup page (setup_page.h) instead of the dashboard. On the
// developer's PC, --setup goes through that in generated\setup-test.

#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>
#include <filesystem>
#include <string>
#include <vector>

#include "background.h"
#include "controls.h"
#include "game_options.h"
#include "launcher_profile.h"
#include "recomp_launcher.h"
#include "rom_art.h"
#include "settings_file.h"
#include "layout.h"
#include "saves_page.h"
#include "setup_page.h"
#include "town.h"

#ifndef NOMINMAX   // MinGW's C++ library already defines it
#define NOMINMAX
#endif
#define WIN32_LEAN_AND_MEAN
#include <windows.h>

namespace {

// The one dump the game is built for: Animal Crossing: Wild World (USA, Rev 1).
const char* const kSha1[] = {"77fde3e30e1e6068395d1f96ea63be569b61c351"};
const char* const kRomPatterns[] = {"*.nds"};
const char* const kResolutionLabels[] = {"Native (256x192)", "2x (512x384)",
                                         "3x (768x576)", "4x (1024x768)"};
const int kResolutionValues[] = {1, 2, 3, 4};
const char* const kFullscreen[] = {"off", "borderless", "exclusive"};
const char* const kLayoutLabels[] = {"Stacked (one window)", "Separate windows"};
const char* const kLayouts[] = {"stacked", "separate"};

const char* const kCredits =
    "Wild World Recomped\n"
    "Developed by Mieszko (M.Stasiak)\n"
    "\n"
    "Animal Crossing: Wild World recompiled to run natively on PC. You need "
    "your own copy of the game (USA, Rev 1).\n"
    "\n"
    "Built on ndsrecomp (static recompilation for the Nintendo DS), the melonDS "
    "device models, recomp-ui (this launcher) and Dear ImGui. The launcher's font "
    "is Nunito by the Nunito Project Authors (SIL Open Font License). The background "
    "pattern is by usrkitt (alphacoders.com/users/profile/247170/usrkitt).\n"
    "\n"
    "Animal Crossing is a trademark of Nintendo. This project is not affiliated "
    "with or endorsed by Nintendo.";

// There's no console to print to, so problems go in a message box.
void tell(const std::string& message) {
    MessageBoxA(nullptr, message.c_str(), "Wild World Recomped", MB_OK | MB_ICONWARNING);
}

int start_game(const acww::Layout& layout, const std::string& rom) {
    char stamp[32];
    const std::time_t now = std::time(nullptr);
    std::strftime(stamp, sizeof(stamp), "run-%Y%m%d-%H%M%S", std::localtime(&now));
    const std::string runner = layout.runner.u8string();
    std::vector<std::string> args = {
        runner, "bios", "--rom", acww::ascii_path(std::filesystem::u8path(rom)).u8string(),
        "--config", "game.toml", "--interactive",
        "--freebios", "--generated-firmware", "--boot", "direct", "--rtc-host",
        "--save-path", "acww.sav", "--firmware-state-path", "bios\\firmware-state.bin"};
    if (layout.setup) {
        // A game built by setup: none of the developer's diagnostics or coverage.
        args.insert(args.end(), {"--diagnostics", "off", "--no-coverage-manifest"});
    } else {
        args.insert(args.end(), {"--diagnostics-dir", "generated\\diagnostics", "--coverage-manifest",
                                 std::string("generated\\coverage\\") + stamp + ".json"});
        // This runner needs MSYS2's DLLs (SDL3, the C++ runtime). play.ps1 puts
        // them on PATH; a shortcut doesn't, so do the same here. (A game built
        // by setup has SDL3.dll beside it.)
        std::string dlls = ACWW_DLL_DIR;
        std::replace(dlls.begin(), dlls.end(), '/', '\\');
        const char* path = std::getenv("PATH");
        SetEnvironmentVariableA("PATH", (dlls + ";" + (path ? path : "")).c_str());
    }
    // One command line, each argument quoted the way the game will read it
    // back (a ROM in "OneDrive\Documents\..." has spaces).
    std::wstring command;
    for (const std::string& arg : args)
        command += (command.empty() ? L"" : L" ") + wwbuild::quote_arg(wwbuild::widen(arg));

    // What the game prints goes to the log instead of a console window.
    const std::filesystem::path logs = layout.release ? "logs" : "generated\\logs";
    const std::string log_path = (logs / "last-run.log").u8string();
    std::error_code ec;
    std::filesystem::create_directories(logs, ec);
    std::filesystem::create_directories("bios", ec);   // where the game keeps its DS settings
    SECURITY_ATTRIBUTES inherit{sizeof(inherit), nullptr, TRUE};
    HANDLE log_file = CreateFileW((logs / "last-run.log").c_str(), GENERIC_WRITE,
                                  FILE_SHARE_READ, &inherit, CREATE_ALWAYS,
                                  FILE_ATTRIBUTE_NORMAL, nullptr);
    STARTUPINFOW startup{};
    startup.cb = sizeof(startup);
    if (log_file != INVALID_HANDLE_VALUE) {
        startup.dwFlags = STARTF_USESTDHANDLES;
        startup.hStdOutput = log_file;
        startup.hStdError = log_file;
    }
    PROCESS_INFORMATION game{};
    std::vector<wchar_t> line(command.begin(), command.end());
    line.push_back(L'\0');
    const BOOL started = CreateProcessW(layout.runner.c_str(), line.data(), nullptr, nullptr, TRUE,
                                        CREATE_NO_WINDOW, nullptr, nullptr, &startup, &game);
    const DWORD why = GetLastError();
    if (log_file != INVALID_HANDLE_VALUE) CloseHandle(log_file);
    if (!started) {
        tell("The game couldn't start (Windows error " + std::to_string(why) + "):\n" + runner);
        return 1;
    }
    WaitForSingleObject(game.hProcess, INFINITE);
    DWORD code = 0;
    GetExitCodeProcess(game.hProcess, &code);
    CloseHandle(game.hThread);
    CloseHandle(game.hProcess);
    if (code != 0) {
        char hex[16];
        std::snprintf(hex, sizeof(hex), "0x%08lX", static_cast<unsigned long>(code));
        tell(std::string("The game stopped with an error (") + hex + "). What it printed is in " +
             log_path + ".");
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
    bool force_window = (GetAsyncKeyState(VK_SHIFT) & 0x8000) != 0;
    bool setup_test = false;
    for (int i = 1; i < argc; ++i) {
        if (std::strcmp(argv[i], "--launcher") == 0) force_window = true;
        if (std::strcmp(argv[i], "--setup") == 0) setup_test = true;
    }
    // settings.toml, game.toml, the ROM and the save all live in the game's
    // folder (layout.h): on the developer's PC, the project.
    const acww::Layout layout = acww::find_layout(setup_test);
    if (!acww::is_ascii(layout.root)) {
        tell("Wild World Recomped can't run from this folder:\n" + layout.root.u8string() +
             "\n\nIts path has letters the tools that build the game can't read. Move the Wild "
             "World Recomped folder somewhere whose path has only English letters and numbers, "
             "such as C:\\Games.");
        return 1;
    }
    std::error_code ec;
    std::filesystem::current_path(layout.root, ec);
    if (ec) {
        tell("Can't open the game's folder:\n" + layout.root.u8string());
        return 1;
    }
    acww::setup::init(layout, ACWW_VERSION);
    if (acww::setup::needed()) force_window = true;   // the game has to be built first

    acww::SettingsFile file;
    file.load("settings.toml");
    if (file.get_bool("launcher", "skip", false) && !force_window)
        return start_game(layout, file.get("launcher", "rom", "acww.nds"));

    acww::GameOptions options;
    options.load(file, read_mods());
    const RecompLauncherCModProvider provider = options.provider();

    RecompLauncherCGameInfo game;
    std::memset(&game, 0, sizeof(game));
    launcher_profile_apply("nds", &game);   // theme, DS art, the DS's settings
    game.theme = "acww";                    // Wild World colours (tools\patch_recompui.py)
    // The subtitle under the title. Not GameInfo.platform: recomp-ui picks the
    // console profile by that, so it stays "NINTENDO DS" (patch_recompui.py).
    _putenv("ACWW_LAUNCHER_SUBTITLE=Animal Crossing: Wild World  \u00B7  v" ACWW_VERSION);
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
    game.display_layout_labels = kLayoutLabels;
    game.num_display_layouts = 2;
    game.credits_text = kCredits;
    game.mods = &provider;
    game.assist_binding_labels = nullptr;   // the stylus keys are set in game.toml for now
    game.assist_binding_count = 0;

    RecompLauncherCSettings settings;
    std::memset(&settings, 0, sizeof(settings));
    settings.player_src[0] = 1;   // keyboard
    settings.enable_audio = 1;
    settings.volume = 100;
    settings.internal_resolution = std::clamp(file.get_int("graphics", "resolution", 3), 1, 4);
    const std::string fullscreen = file.get("display", "fullscreen", "off");
    settings.fullscreen = fullscreen == "borderless" ? 1 : fullscreen == "exclusive" ? 2 : 0;
    settings.display_layout = file.get("display", "screen_layout", "stacked") == "separate";
    settings.skip_launcher = 0;

    // The Configure page edits these; keybinds.ini keeps them (controls.h).
    acww::Controls controls = acww::read_controls("keybinds.ini");
    std::error_code no_file;
    if (!std::filesystem::exists("keybinds.ini", no_file))
        acww::write_controls("keybinds.ini", controls);   // before recomp-ui writes its own
    for (int b = 0; b < acww::kDsButtons; ++b) {
        settings.player_key_bind[0][b] = controls.key[b];
        settings.player_pad_bind[0][b] = controls.pad[b];
    }
    // Settings' Restore Defaults and Configure's Reset to Defaults use these.
    RecompLauncherCSettings defaults = settings;
    defaults.internal_resolution = 3;
    defaults.fullscreen = 0;
    defaults.display_layout = 0;
    const acww::Controls game_controls = acww::default_controls();
    for (int b = 0; b < acww::kDsButtons; ++b) {
        defaults.player_key_bind[0][b] = game_controls.key[b];
        defaults.player_pad_bind[0][b] = game_controls.pad[b];
    }
    game.default_settings = &defaults;

    const std::string last_rom = file.get("launcher", "rom", "acww.nds");
    const std::string box_art = acww::make_box_art(last_rom);
    if (!box_art.empty()) {
        game.boxart_path = box_art.c_str();
        _putenv(("ACWW_LAUNCHER_BRAND=" + box_art).c_str());   // the leaf in the corner too
    }
    // The game card shows the ROM's own name instead of Region/File rows.
    const acww::RomTitle title = acww::read_banner_title(last_rom);
    if (!title.name.empty()) {
        _putenv(("ACWW_LAUNCHER_GAME_TITLE=" + title.name).c_str());
        const std::string detail = title.publisher.empty()
            ? std::string(game.region) : title.publisher + "  \u00B7  " + game.region;
        _putenv(("ACWW_LAUNCHER_GAME_DETAIL=" + detail).c_str());
    }
    acww::set_town_card(acww::saves::kSave);   // the Save Info card, from the save itself
    acww_saves_page = acww::saves::draw;        // the Saves page (saves_page.h)
    if (layout.setup) {                          // the setup page, until the game is built
        acww_setup_needed = acww::setup::needed;
        acww_setup_page = acww::setup::draw;
    }
    const acww::Background background = acww::make_background();
    if (!background.path.empty()) {
        _putenv(("ACWW_LAUNCHER_BACKGROUND=" + background.path).c_str());
        _putenv((std::string("ACWW_LAUNCHER_BACKGROUND_MODE=") + background.mode).c_str());
    }
    char rom[1024] = {0};
    const int result = recomp_launcher_run_window("Wild World Recomped", &settings, &game,
                                                  "assets", last_rom.c_str(), rom, sizeof(rom));

    // Whichever way the window closed, keep what the player changed.
    file.load("settings.toml");   // in case it was edited by hand meanwhile
    if (settings.internal_resolution >= 1 && settings.internal_resolution <= 4)
        file.set("graphics", "resolution", std::to_string(settings.internal_resolution));
    file.set("display", "fullscreen",
             acww::SettingsFile::text(kFullscreen[std::clamp(settings.fullscreen, 0, 2)]));
    file.set("display", "screen_layout",
             acww::SettingsFile::text(kLayouts[settings.display_layout == 1 ? 1 : 0]));
    file.set("launcher", "skip", acww::SettingsFile::flag(settings.skip_launcher != 0));
    options.store(file);
    for (int b = 0; b < acww::kDsButtons; ++b) {
        controls.key[b] = settings.player_key_bind[0][b];
        controls.pad[b] = settings.player_pad_bind[0][b];
    }
    if (!acww::write_controls("keybinds.ini", controls))
        tell("Your controls couldn't be saved to keybinds.ini.");
    const std::string chosen = rom[0] ? rom : last_rom;
    if (result != RECOMP_LAUNCHER_RESULT_QUIT) file.set("launcher", "rom", acww::SettingsFile::text(chosen));
    if (!file.save("settings.toml"))
        tell("Your settings couldn't be saved to settings.toml.");

    if (result == RECOMP_LAUNCHER_RESULT_QUIT) return 0;
    if (acww::setup::needed()) {
        tell("The game hasn't been built yet. Open the launcher again and press Set Up.");
        return 1;
    }
    return start_game(layout, chosen);   // also when the window couldn't open at all
}
