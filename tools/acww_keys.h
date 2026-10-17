// acwwrecomp: the player's controls, from keybinds.ini (runner).
//
// The launcher's Configure page saves keybinds.ini beside settings.toml. Its
// [player1] section gives each DS button (a, b, x, y, l, r, start, select,
// up, down, left, right) a keyboard key by SDL name ("Z", "Return", "None");
// [pad1] gives each a controller button or axis ("a", "dpup",
// "leftshoulder", "lefttrigger+", "leftx-", "None"). key_bit() and
// controller_bit() in frontend.cpp ask here first, and the frame's stick poll
// adds the axes; with no keybinds.ini the game keeps its built-in controls.
// The game's own shortcuts (G, T, Tab, Escape, F1-F12) win over a DS button
// put on the same key.
//
// Included by frontend.cpp after SDL, so SDL's key names are known here.
#pragma once

#include <array>
#include <cctype>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <string>
#include <vector>

namespace acww_keys {

// Controller buttons and axes by SDL's standard numbers (the same in SDL2
// and SDL3), with the names keybinds.ini uses. The launcher has the same
// list (launcher/controls.h).
inline const char* const kPadButtons[] = {
    "a", "b", "x", "y", "back", "guide", "start", "leftstick", "rightstick",
    "leftshoulder", "rightshoulder", "dpup", "dpdown", "dpleft", "dpright",
};
inline const char* const kPadAxes[] = {
    "leftx", "lefty", "rightx", "righty", "lefttrigger", "righttrigger",
};

struct Axis {
    int axis;
    bool positive;
    uint16_t bit;
};

struct Map {
    bool loaded = false;                 // keybinds.ini had a [player1] section
    bool pad_loaded = false;             // ... and a [pad1] section
    std::array<uint16_t, 512> keys{};    // SDL scancode -> DS button bits
    std::array<uint16_t, 32> buttons{};  // controller button -> DS button bits
    std::vector<Axis> axes;              // controller axes held past halfway

    uint16_t key(int scancode) const {
        return scancode > 0 && scancode < static_cast<int>(keys.size()) ? keys[scancode] : 0;
    }
    uint16_t button(int code) const {
        return code >= 0 && code < static_cast<int>(buttons.size()) ? buttons[code] : 0;
    }
    uint16_t operator()(SDL_Scancode sc) const { return key(static_cast<int>(sc)); }
};

inline std::string trim(const std::string& s) {
    const size_t a = s.find_first_not_of(" \t");
    if (a == std::string::npos) return "";
    return s.substr(a, s.find_last_not_of(" \t") - a + 1);
}

inline std::string lower(std::string s) {
    for (char& c : s) c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
    return s;
}

// SDL's own key names, plus the short ones keybinds.ini also accepts.
inline int scancode(const std::string& name) {
    const SDL_Scancode sc = SDL_GetScancodeFromName(name.c_str());
    if (sc != SDL_SCANCODE_UNKNOWN) return static_cast<int>(sc);
    const std::string n = lower(name);
    if (n == "enter") return SDL_SCANCODE_RETURN;
    if (n == "lshift") return SDL_SCANCODE_LSHIFT;
    if (n == "rshift") return SDL_SCANCODE_RSHIFT;
    if (n == "lctrl") return SDL_SCANCODE_LCTRL;
    if (n == "rctrl") return SDL_SCANCODE_RCTRL;
    if (n == "esc") return SDL_SCANCODE_ESCAPE;
    return 0;   // "None" too
}

// "dpup" -> button 11; "lefttrigger+" -> axis 4 positive; "button16" -> 16.
inline bool pad_input(const std::string& value, int* button, Axis* axis) {
    const std::string v = lower(value);
    for (int i = 0; i < static_cast<int>(sizeof(kPadButtons) / sizeof(kPadButtons[0])); ++i)
        if (v == kPadButtons[i]) return *button = i, true;
    if (v.rfind("button", 0) == 0 && v.size() > 6) {
        *button = std::atoi(v.c_str() + 6);
        return true;
    }
    if (v.size() > 1 && (v.back() == '+' || v.back() == '-')) {
        const std::string name = v.substr(0, v.size() - 1);
        for (int i = 0; i < static_cast<int>(sizeof(kPadAxes) / sizeof(kPadAxes[0])); ++i)
            if (name == kPadAxes[i]) {
                axis->axis = i;
                axis->positive = v.back() == '+';
                return true;
            }
    }
    return false;   // "None" too
}

inline Map load(const char* path) {
    // The DS buttons in KEYINPUT/EXTKEYIN order, as key_bit() returns them.
    static const struct { const char* name; uint16_t bit; } kDs[] = {
        {"a", 1u << 0},      {"b", 1u << 1},     {"select", 1u << 2}, {"start", 1u << 3},
        {"right", 1u << 4},  {"left", 1u << 5},  {"up", 1u << 6},     {"down", 1u << 7},
        {"r", 1u << 8},      {"l", 1u << 9},     {"x", 1u << 10},     {"y", 1u << 11},
    };
    Map map;
    std::ifstream file(path);
    if (!file) return map;
    std::string line, section;
    int keys = 0, pads = 0;
    while (std::getline(file, line)) {
        if (!line.empty() && line.back() == '\r') line.pop_back();
        const std::string t = trim(line);
        if (t.empty() || t[0] == '#' || t[0] == ';') continue;
        if (t[0] == '[') {
            section = lower(t);
            if (section == "[player1]") map.loaded = true;
            if (section == "[pad1]") map.pad_loaded = true;
            continue;
        }
        const size_t eq = t.find('=');
        if (eq == std::string::npos) continue;
        const std::string name = lower(trim(t.substr(0, eq)));
        const std::string value = trim(t.substr(eq + 1));
        for (const auto& ds : kDs) {
            if (name != ds.name) continue;
            if (section == "[player1]") {
                const int sc = scancode(value);
                if (sc > 0 && sc < static_cast<int>(map.keys.size())) {
                    map.keys[sc] |= ds.bit;
                    ++keys;
                }
            } else if (section == "[pad1]") {
                int button = -1;
                Axis axis{-1, true, ds.bit};
                if (!pad_input(value, &button, &axis)) continue;
                if (axis.axis >= 0) {
                    map.axes.push_back(axis);
                    ++pads;
                } else if (button >= 0 && button < static_cast<int>(map.buttons.size())) {
                    map.buttons[button] |= ds.bit;
                    ++pads;
                }
            }
        }
    }
    if (map.loaded)
        std::fprintf(stderr, "[acwwrecomp] controls: %s (%d of 12 DS buttons on keys, "
                     "%d on the controller)\n", path, keys, map.pad_loaded ? pads : -1);
    return map;
}

// Read once, the first time it's needed. The game runs from the project
// folder, where the launcher keeps keybinds.ini.
inline const Map& current() {
    static const Map map = load("keybinds.ini");
    return map;
}

// The startup message's list of keys: what keybinds.ini puts on each DS
// button ("A=Z B=X ..."), or the built-in keys when there is no keybinds.ini.
inline std::string describe() {
    const Map& map = current();
    if (!map.loaded)
        return "arrows=D-pad | Z=A X=B | A=Y S=X | Q=L W=R | Enter=Start Backspace=Select";
    static const struct { const char* name; uint16_t bit; } kDs[] = {
        {"Up", 1u << 6}, {"Down", 1u << 7}, {"Left", 1u << 5}, {"Right", 1u << 4},
        {"A", 1u << 0},  {"B", 1u << 1},    {"X", 1u << 10},   {"Y", 1u << 11},
        {"L", 1u << 9},  {"R", 1u << 8},    {"Start", 1u << 3}, {"Select", 1u << 2},
    };
    std::string out = "keybinds.ini:";
    for (const auto& ds : kDs) {
        std::string keys;
        for (int sc = 1; sc < static_cast<int>(map.keys.size()); ++sc) {
            if (!(map.keys[static_cast<size_t>(sc)] & ds.bit)) continue;
            const char* name = SDL_GetScancodeName(static_cast<SDL_Scancode>(sc));
            if (!keys.empty()) keys += "/";
            keys += name && name[0] ? name : "?";
        }
        out += std::string(" ") + ds.name + "=" + (keys.empty() ? "none" : keys);
    }
    return out;
}

// Called once per frame with the controller's axes (-1..1, triggers 0..1)
// and the frame's stick helper, dir(value, bit, positive).
template <class GetAxis, class Dir>
void poll_axes(GetAxis&& get_axis, Dir&& dir) {
    for (const Axis& a : current().axes) dir(get_axis(a.axis), a.bit, a.positive);
}

}  // namespace acww_keys
