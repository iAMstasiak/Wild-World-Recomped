// Wild World save files (launcher): is a file one, and what is in it.
//
// A save file is 256 KB. The game's save (0x15FE0 bytes, laid out like the
// copy the game keeps in RAM) is in it twice, and the game accepts a copy
// whose 16-bit words add up to zero (tools/saveinfo.py shows all of this).
// The launcher's Save Info card and Saves page read files with this.
#pragma once

#include <chrono>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <string>
#include <vector>

namespace acww {

constexpr size_t kSaveSize = 0x40000;      // the whole file
constexpr size_t kSaveCopy = 0x15FE0;      // one copy of the game's save
constexpr size_t kTownName = 0x0004;       // 8 characters
constexpr size_t kPlayer = 0x000C;         // player 1; each player is 0x228C bytes
constexpr size_t kPlayerSize = 0x228C;
constexpr size_t kPlayerName = 0x2282;     // inside a player, 8 characters
constexpr size_t kPlayerBells = 0x1B40;    // inside a player: the wallet (u32)

// The game's character set as UTF-8 (the same table as tools/acww_game.h).
inline const char* const kSaveText[] = {
    "", "A", "B", "C", "D", "E", "F", "G",
    "H", "I", "J", "K", "L", "M", "N", "O",
    "P", "Q", "R", "S", "T", "U", "V", "W",
    "X", "Y", "Z", "a", "b", "c", "d", "e",
    "f", "g", "h", "i", "j", "k", "l", "m",
    "n", "o", "p", "q", "r", "s", "t", "u",
    "v", "w", "x", "y", "z", "0", "1", "2",
    "3", "4", "5", "6", "7", "8", "9", "\xe2\xa8\x8d",
    "\xe2\x93\xa2", "\xc5\x92", "\xc5\xbd", "\xc5\xa1", "\xc5\x93", "\xc5\xbe", "\xc5\xb8", "\xc3\x80",
    "\xc3\x81", "\xc3\x82", "\xc3\x83", "\xc3\x84", "\xc3\x85", "\xc3\x86", "\xc3\x87", "\xc3\x88",
    "\xc3\x89", "\xc3\x8a", "\xc3\x8b", "\xc3\x8c", "\xc3\x8d", "\xc3\x8e", "\xc3\x8f", "\xc4\x90",
    "\xc3\x91", "\xc3\x92", "\xc3\x93", "\xc3\x94", "\xc3\x95", "\xc3\x96", "\xc3\x98", "\xc3\x99",
    "\xc3\x9a", "\xc3\x9b", "\xc3\x9c", "\xc3\x9d", "\xc3\x9e", "\xce\xb2", "\xc3\xa0", "\xc3\xa1",
    "\xc3\xa2", "\xc3\xa3", "\xc3\xa4", "\xc3\xa5", "\xc3\xa6", "\xc3\xa7", "\xc3\xa8", "\xc3\xa9",
    "\xc3\xaa", "\xc3\xab", "\xc3\xac", "\xc3\xad", "\xc3\xae", "\xc3\xaf", "\xc3\xb0", "\xc3\xb1",
    "\xc3\xb2", "\xc3\xb3", "\xc3\xb4", "\xc3\xb5", "\xc3\xb6", "\xc3\xb8", "\xc3\xb9", "\xc3\xba",
    "\xc3\xbb", "\xc3\xbc", "\xc3\xbd", "\xc3\xbe", "\xc3\xbf", " ", " ", "!",
    "\"", "#", "$", "%", "&", "\xc2\xb4", "(", ")",
    "*", "+", ",", "-", ".", "/", ":", ";",
    "<", "=", ">", "?", "@", "[", "\\", "]",
    "^", "_", "\xc2\xb4", "{", "|", "}", "~", "\xe2\x82\xac",
    "\xe2\x80\x9a", "\xe2\x80\x9e", "\xe2\x80\xa6", "\xe2\x80\xa0", "\xe2\x80\xa1", "\xef\xbc\xbe", "\xe2\x80\xb0", "\xe2\x9f\xa8",
    "\xe2\x80\x98", "\xe2\x80\x99", "\xe2\x80\x9c", "\xe2\x80\x9d", "\xe2\x80\xa2", "\xe2\x80\x93", "\xe2\x80\x94", "\xcb\x9c",
    "\xe2\x84\xa2", "\xe2\x9f\xa9", "\xe2\x80\x81", "\xc2\xa1", "\xc2\xa2", "\xc2\xa3", "\xc2\xa4", "\xc2\xa5",
    "\xe2\x95\x8e", "\xc2\xa7", "\xc2\xa8", "\xc2\xa9", "\xc2\xaa", "\xc2\xab", "\xc2\xac", "-",
    "\xc2\xae", "\xe2\x80\xbe", "\xc2\xb0", "\xc2\xb1", "\xc2\xb2", "\xc2\xb3", "\xe2\x81\x84", "\xc2\xb5",
    "\xc2\xb6", "\xe2\x80\xa2", "\xc2\xb8", "\xc2\xb9", "\xc2\xba", "\xc2\xbb", "\xc2\xbc", "\xc2\xbd",
    "\xc2\xbe", "\xc2\xbf", "\xc3\x97", "\xc3\xb7", "\xe2\x98\x94", "\xe2\x98\x85", "\xe2\x9d\xa4", "\xe2\x99\xaa",
};

struct SaveSummary {
    bool valid = false;            // a Wild World save the game will accept
    std::string town;
    std::string player;            // player 1, the town's first resident
    int residents = 0;             // player slots in use
    uint32_t bells = 0;            // player 1's wallet
    long long saved = 0;           // the file's time (Unix seconds), 0 if unknown
};

inline std::string save_text(const uint8_t* p, size_t length) {
    std::string out;
    for (size_t i = 0; i < length && p[i]; ++i) out += kSaveText[p[i]];
    while (!out.empty() && out.back() == ' ') out.pop_back();
    return out;
}

inline bool save_copy_ok(const std::vector<uint8_t>& data, size_t base) {
    if (data.size() < base + kSaveCopy) return false;
    uint16_t sum = 0;
    for (size_t i = base; i < base + kSaveCopy; i += 2)
        sum = static_cast<uint16_t>(sum + (data[i] | data[i + 1] << 8));
    return sum == 0 && data[base + kTownName] != 0;
}

// What a save holds, from the first copy the game would accept.
inline SaveSummary summarize_save(const std::vector<uint8_t>& data) {
    SaveSummary s;
    const size_t base = save_copy_ok(data, 0) ? 0 : save_copy_ok(data, kSaveCopy) ? kSaveCopy : 1;
    if (base == 1) return s;
    const uint8_t* save = data.data() + base;
    s.valid = true;
    s.town = save_text(save + kTownName, 8);
    for (int i = 0; i < 4; ++i) {
        const uint8_t* player = save + kPlayer + i * kPlayerSize;
        const std::string name = save_text(player + kPlayerName, 8);
        if (name.empty()) continue;
        ++s.residents;
        if (i == 0) {
            s.player = name;
            const uint8_t* b = player + kPlayerBells;
            s.bells = b[0] | b[1] << 8 | b[2] << 16 | static_cast<uint32_t>(b[3]) << 24;
        }
    }
    return s;
}

// The first 256 KB of a file (a DeSmuME .dsv adds a footer, a flashcart may
// pad to 512 KB); empty when the file is shorter than a save.
inline std::vector<uint8_t> read_save_bytes(const std::filesystem::path& path) {
    std::ifstream file(path, std::ios::binary);
    std::vector<uint8_t> data(kSaveSize);
    if (!file.read(reinterpret_cast<char*>(data.data()), static_cast<std::streamsize>(kSaveSize)))
        return {};
    return data;
}

inline long long file_unix_time(const std::filesystem::path& path) {
    std::error_code ec;
    const auto t = std::filesystem::last_write_time(path, ec);
    if (ec) return 0;
    const auto now = std::chrono::system_clock::now() +
                     std::chrono::duration_cast<std::chrono::system_clock::duration>(
                         t - std::filesystem::file_time_type::clock::now());
    return std::chrono::duration_cast<std::chrono::seconds>(now.time_since_epoch()).count();
}

inline SaveSummary read_save(const std::filesystem::path& path) {
    SaveSummary s = summarize_save(read_save_bytes(path));
    if (s.valid) s.saved = file_unix_time(path);
    return s;
}

}  // namespace acww
