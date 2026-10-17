// The Play page's Save Info card (launcher): who, where and how many bells,
// read from acww.sav itself (save_file.h), so it is right straight after the
// Saves page restores or imports a save. recomp-ui draws the card under the
// controller card from ACWW_LAUNCHER_TOWN (its heading) and
// ACWW_LAUNCHER_TOWN_1, _2, ... ("Label<tab>Value", or a line of text); see
// tools/patch_recompui.py.
#pragma once

#include <cmath>
#include <cstdlib>
#include <ctime>
#include <string>

#include "save_file.h"

namespace acww {

inline std::string with_commas(long long n) {
    std::string digits = std::to_string(n);
    for (int i = static_cast<int>(digits.size()) - 3; i > 0; i -= 3)
        digits.insert(static_cast<size_t>(i), ",");
    return digits;
}

// Whole calendar days from `then` to now (0 = today), counted at midday.
inline long days_ago(std::time_t then_t) {
    const std::time_t now_t = std::time(nullptr);
    std::tm then = *std::localtime(&then_t);
    std::tm now = *std::localtime(&now_t);
    then.tm_hour = now.tm_hour = 12;
    then.tm_min = now.tm_min = then.tm_sec = now.tm_sec = 0;
    then.tm_isdst = now.tm_isdst = -1;
    return std::lround(std::difftime(std::mktime(&now), std::mktime(&then)) / 86400.0);
}

inline std::string date_text(const std::tm& t, bool year) {
    static const char* const kMonths[] = {"Jan", "Feb", "Mar", "Apr", "May", "Jun",
                                          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"};
    return std::to_string(t.tm_mday) + " " + kMonths[t.tm_mon % 12] +
           (year ? " " + std::to_string(t.tm_year + 1900) : std::string());
}

// "Today at 12:43", "Yesterday at 18:02", "3 days ago", "12 Oct 2026".
inline std::string when_text(long long saved) {
    const std::time_t then_t = static_cast<std::time_t>(saved);
    const std::tm then = *std::localtime(&then_t);
    char clock[8];
    std::strftime(clock, sizeof(clock), "%H:%M", &then);
    const long days = days_ago(then_t);
    if (days <= 0) return std::string("Today at ") + clock;   // or a clock that went back
    if (days == 1) return std::string("Yesterday at ") + clock;
    if (days < 7) return std::to_string(days) + " days ago";
    return date_text(then, true);
}

// Sets the card's environment variables; called before the launcher window
// opens and again whenever the Saves page changes the save.
inline void set_town_card(const char* save_path) {
    const SaveSummary save = read_save(save_path);
    _putenv("ACWW_LAUNCHER_TOWN=SAVE INFO");
    for (int i = 1; i <= 8; ++i)   // empty rows end the card
        _putenv(("ACWW_LAUNCHER_TOWN_" + std::to_string(i) + "=").c_str());
    if (!save.valid) {
        _putenv("ACWW_LAUNCHER_TOWN_1=Your save info shows up here once the game has saved.");
        return;
    }
    const std::string rows[] = {
        "Player\t" + save.player,
        "Town\t" + save.town,
        "Bells\t" + with_commas(save.bells),
        save.saved > 0 ? "Last saved\t" + when_text(save.saved) : std::string(),
    };
    int n = 0;
    for (const std::string& row : rows)
        if (!row.empty())
            _putenv(("ACWW_LAUNCHER_TOWN_" + std::to_string(++n) + "=" + row).c_str());
}

}  // namespace acww
