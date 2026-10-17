// The Play page's town card (launcher): who, where and how many bells, from
// generated\town.toml, which the game writes each time it saves
// (tools/acww_game.h). recomp-ui draws the card under the controller card
// from ACWW_LAUNCHER_TOWN (its heading) and ACWW_LAUNCHER_TOWN_1, _2, ...
// ("Label<tab>Value", or a line of text); see tools/patch_recompui.py.
#pragma once

#include <cmath>
#include <cstdlib>
#include <ctime>
#include <string>

#include "settings_file.h"

namespace acww {

inline std::string with_commas(long long n) {
    std::string digits = std::to_string(n);
    for (int i = static_cast<int>(digits.size()) - 3; i > 0; i -= 3)
        digits.insert(static_cast<size_t>(i), ",");
    return digits;
}

// "Today at 12:43", "Yesterday at 18:02", "3 days ago", "12 Oct 2026".
inline std::string when_text(long long saved) {
    static const char* const kMonths[] = {"Jan", "Feb", "Mar", "Apr", "May", "Jun",
                                          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"};
    const std::time_t then_t = static_cast<std::time_t>(saved);
    const std::time_t now_t = std::time(nullptr);
    std::tm then = *std::localtime(&then_t);
    std::tm now = *std::localtime(&now_t);
    char clock[8];
    std::strftime(clock, sizeof(clock), "%H:%M", &then);
    const std::string date = std::to_string(then.tm_mday) + " " + kMonths[then.tm_mon % 12] +
                             " " + std::to_string(then.tm_year + 1900);
    // Whole calendar days between the two, counted at midday.
    then.tm_hour = now.tm_hour = 12;
    then.tm_min = now.tm_min = then.tm_sec = now.tm_sec = 0;
    then.tm_isdst = now.tm_isdst = -1;
    const long days = std::lround(std::difftime(std::mktime(&now), std::mktime(&then)) / 86400.0);
    if (days <= 0) return std::string("Today at ") + clock;   // or a clock that went back
    if (days == 1) return std::string("Yesterday at ") + clock;
    if (days < 7) return std::to_string(days) + " days ago";
    return date;
}

// Sets the card's environment variables before the launcher window opens.
inline void set_town_card(const char* path) {
    SettingsFile file;
    const bool found = file.load(path);
    const std::string player = file.get("", "player", "");
    const std::string town = file.get("", "town", "");
    _putenv("ACWW_LAUNCHER_TOWN=SAVE INFO");
    if (!found || player.empty() || town.empty()) {
        _putenv("ACWW_LAUNCHER_TOWN_1=Your save info shows up here after you next save in the game.");
        return;
    }
    long long saved = 0;
    try {
        saved = std::stoll(file.get("", "saved", "0"));
    } catch (...) {
    }
    const std::string rows[] = {
        "Player\t" + player,
        "Town\t" + town,
        "Bells\t" + with_commas(file.get_int("", "bells", 0)),
        saved > 0 ? "Last saved\t" + when_text(saved) : std::string(),
    };
    int n = 0;
    for (const std::string& row : rows)
        if (!row.empty())
            _putenv(("ACWW_LAUNCHER_TOWN_" + std::to_string(++n) + "=" + row).c_str());
}

}  // namespace acww
