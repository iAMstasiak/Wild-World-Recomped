// The Configure page's controls, kept in keybinds.ini (launcher).
//
// recomp-ui's DS profile leaves the controls to the host: they come and go
// in Settings.player_key_bind and player_pad_bind, one per DS button in the
// profile's order. We keep them in keybinds.ini, which the game reads too
// (tools/acww_keys.h): [player1] has a key for each DS button by SDL name,
// [pad1] a controller button or axis. With no file, the game's own controls.
#pragma once

#include <cctype>
#include <cstdlib>
#include <fstream>
#include <string>

#include <SDL3/SDL_keyboard.h>

#include "recomp_launcher.h"
#include "settings_file.h"

namespace acww {

constexpr int kDsButtons = 12;

// The DS profile's button order.
inline const char* const kDsNames[kDsButtons] = {
    "up", "down", "left", "right", "a", "b", "x", "y", "l", "r", "start", "select"};

// Controller buttons and axes by SDL's standard numbers, with the names
// keybinds.ini uses. The game has the same list (tools/acww_keys.h).
inline const char* const kPadButtons[] = {
    "a", "b", "x", "y", "back", "guide", "start", "leftstick", "rightstick",
    "leftshoulder", "rightshoulder", "dpup", "dpdown", "dpleft", "dpright",
};
inline const char* const kPadAxes[] = {
    "leftx", "lefty", "rightx", "righty", "lefttrigger", "righttrigger",
};
constexpr int kPadButtonNames = sizeof(kPadButtons) / sizeof(kPadButtons[0]);
constexpr int kPadAxisNames = sizeof(kPadAxes) / sizeof(kPadAxes[0]);

struct Controls {
    int key[kDsButtons];   // SDL scancodes, 0 = none
    int pad[kDsButtons];   // RECOMP_LAUNCHER_PAD_* values, 0 = none
};

// What the game has always used (key_bit and controller_bit in the runner).
inline Controls default_controls() {
    const auto button = [](int code) { return RECOMP_LAUNCHER_PAD_BUTTON(code); };
    return {
        {SDL_SCANCODE_UP, SDL_SCANCODE_DOWN, SDL_SCANCODE_LEFT, SDL_SCANCODE_RIGHT,
         SDL_SCANCODE_Z, SDL_SCANCODE_X, SDL_SCANCODE_S, SDL_SCANCODE_A,
         SDL_SCANCODE_Q, SDL_SCANCODE_W, SDL_SCANCODE_RETURN, SDL_SCANCODE_BACKSPACE},
        {button(11), button(12), button(13), button(14),     // the D-pad
         button(0), button(1), button(2), button(3),         // A, B, X, Y
         button(9), button(10), button(6), button(4)},       // shoulders, Start, Back
    };
}

inline std::string lower(std::string s) {
    for (char& c : s) c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
    return s;
}

inline std::string key_name(int scancode) {
    const char* name = scancode ? SDL_GetScancodeName(static_cast<SDL_Scancode>(scancode)) : "";
    return name && name[0] ? name : "None";
}

inline std::string pad_name(int value) {
    if (RECOMP_LAUNCHER_PAD_IS_BUTTON(value)) {
        const int code = RECOMP_LAUNCHER_PAD_BUTTON_CODE(value);
        return code < kPadButtonNames ? kPadButtons[code] : "button" + std::to_string(code);
    }
    if (RECOMP_LAUNCHER_PAD_IS_AXIS(value)) {
        const int code = RECOMP_LAUNCHER_PAD_AXIS_CODE(value);
        if (code < kPadAxisNames)
            return std::string(kPadAxes[code]) + (RECOMP_LAUNCHER_PAD_AXIS_POSITIVE(value) ? "+" : "-");
    }
    return "None";   // also a two-button combination, which the game can't use
}

inline int pad_value(const std::string& text) {
    const std::string v = lower(text);
    for (int i = 0; i < kPadButtonNames; ++i)
        if (v == kPadButtons[i]) return RECOMP_LAUNCHER_PAD_BUTTON(i);
    if (v.rfind("button", 0) == 0 && v.size() > 6)
        return RECOMP_LAUNCHER_PAD_BUTTON(std::atoi(v.c_str() + 6));
    if (v.size() > 1 && (v.back() == '+' || v.back() == '-'))
        for (int i = 0; i < kPadAxisNames; ++i)
            if (v.substr(0, v.size() - 1) == kPadAxes[i])
                return RECOMP_LAUNCHER_PAD_AXIS(i, v.back() == '+');
    return 0;
}

// The defaults, with whatever keybinds.ini sets on top.
inline Controls read_controls(const char* path) {
    Controls c = default_controls();
    std::ifstream file(path);
    std::string line, section;
    while (std::getline(file, line)) {
        if (!line.empty() && line.back() == '\r') line.pop_back();
        const std::string t = trim(line);
        if (t.empty() || t[0] == '#' || t[0] == ';') continue;
        if (t[0] == '[') {
            section = lower(t);
            continue;
        }
        const size_t eq = t.find('=');
        if (eq == std::string::npos) continue;
        const std::string name = lower(trim(t.substr(0, eq)));
        const std::string value = trim(t.substr(eq + 1));
        for (int b = 0; b < kDsButtons; ++b) {
            if (name != kDsNames[b]) continue;
            if (section == "[player1]")
                c.key[b] = static_cast<int>(SDL_GetScancodeFromName(value.c_str()));
            else if (section == "[pad1]")
                c.pad[b] = pad_value(value);
        }
    }
    return c;
}

inline bool write_controls(const char* path, const Controls& c) {
    std::ofstream file(path, std::ios::trunc);
    file << "# Wild World Recomped controls, set in the launcher's Configure page.\n"
            "# [player1]: a keyboard key for each DS button, by SDL name.\n"
            "# [pad1]: a controller button (a, b, x, y, back, start, leftshoulder,\n"
            "# rightshoulder, leftstick, rightstick, dpup, dpdown, dpleft, dpright)\n"
            "# or axis (lefttrigger+, righttrigger+, leftx-, leftx+, lefty-, ...).\n"
            "# \"None\" leaves a button off. The game reads this when it starts.\n"
            "\n[player1]\n";
    for (int b = 0; b < kDsButtons; ++b)
        file << kDsNames[b] << std::string(8 - std::string(kDsNames[b]).size(), ' ')
             << "= " << key_name(c.key[b]) << "\n";
    file << "\n[pad1]\n";
    for (int b = 0; b < kDsButtons; ++b)
        file << kDsNames[b] << std::string(8 - std::string(kDsNames[b]).size(), ' ')
             << "= " << pad_name(c.pad[b]) << "\n";
    return static_cast<bool>(file);
}

}  // namespace acww
