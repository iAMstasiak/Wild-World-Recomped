// acwwrecomp: backups, mods and Discord inside the runner (copied in by
// tools/patch_game.py; edit tools/acww_game.h).
//
// What play.ps1, tools/mods.py and tools/presence.py did from outside, so
// players don't need Python. Before the save is loaded it is copied into
// backups\. Once the game's code is in memory the mods chosen in the [mods]
// section of settings.toml are written into it, and written again if the
// game reloads that code. Every few seconds the room, names and bells are
// read and shown on the player's Discord profile. ACWW_NO_MODS=1 and
// ACWW_NO_DISCORD=1 switch the last two off (play.ps1 -NoMods, -NoDiscord).
#pragma once

#include <algorithm>
#include <cctype>
#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <ctime>
#include <filesystem>
#include <fstream>
#include <mutex>
#include <regex>
#include <sstream>
#include <string>
#include <thread>
#include <vector>

#ifdef _WIN32
#include <fcntl.h>
// The runner has its own io.h (the DS's I/O registers), which hides the C
// library's <io.h>, so the four functions used here are declared directly.
extern "C" {
int _open(const char* path, int flags, ...);
int _read(int fd, void* buffer, unsigned int count);
int _write(int fd, const void* buffer, unsigned int count);
int _close(int fd);
}
#include <process.h>
#endif

#include "runtime_arm.h"   // bus_write_u8_slow, g_nds_active
#include "state.h"         // bus_debug_read8
#include "toml.hpp"

namespace acww_game {

constexpr const char* kClientId = "1559911813724766218";
constexpr const char* kCredit = "Developed by Mieszko (M.Stasiak)";
constexpr uint32_t kRoom = 0x020E4170;        // u32: 0 town, 1 house, 9 town hall, 29 shop
constexpr uint32_t kSave = 0x021D7350;        // the save image in RAM
constexpr uint32_t kTownName = kSave + 0x0004;
constexpr uint32_t kPlayerName = kSave + 0x228E;
constexpr uint32_t kBells = kSave + 0x1B4C;
constexpr uint32_t kShopWord = 0x021ED15E;    // bits 9-10: shop stage
constexpr const char* kShops[4] = {"Nook's Cranny", "Nook 'n' Go", "Nookway", "Nookington's"};

// The game's character set (tools/textfind.py), as UTF-8.
constexpr const char* kText[] = {
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

struct Patch {
    uint32_t addr = 0;
    std::vector<uint8_t> original;
    std::vector<uint8_t> patched;
};

struct Mod {
    std::string label;
    std::vector<Patch> active;
    bool applied = false;
    bool given_up = false;
};

struct Presence {
    std::mutex lock;
    std::condition_variable wake;
    std::string wanted;   // the activity as JSON; empty until the first one
};

struct State {
    bool started = false;
    std::filesystem::path folder;
    std::vector<Mod> mods;
    bool presence_on = false;
    bool show_names = true;
    bool show_bells = true;
    Presence* presence = nullptr;   // never freed: its thread may outlive main
    std::string last_activity;
    std::vector<uint32_t> unnamed_rooms;
    long long started_at = 0;
    uint64_t frames = 0;
};

inline State& state() {
    static State s;
    return s;
}

inline bool env_on(const char* name) {
    const char* v = std::getenv(name);
    return v && *v && std::string(v) != "0";
}

// ---- reading the game -------------------------------------------------------

inline uint8_t peek(uint32_t addr) { return bus_debug_read8(9, addr); }

inline uint32_t peek32(uint32_t addr) {
    return peek(addr) | peek(addr + 1) << 8 | peek(addr + 2) << 16 |
           static_cast<uint32_t>(peek(addr + 3)) << 24;
}

inline std::string game_text(uint32_t addr, int length) {
    std::string out;
    for (int i = 0; i < length; ++i) {
        const uint8_t c = peek(addr + static_cast<uint32_t>(i));
        if (c == 0) break;
        out += c < sizeof(kText) / sizeof(kText[0]) ? kText[c] : "?";
    }
    while (!out.empty() && out.back() == ' ') out.pop_back();
    while (!out.empty() && out.front() == ' ') out.erase(out.begin());
    return out;
}

// ---- backups ----------------------------------------------------------------

inline void backup_save(const std::string& save_path, bool on, int keep) {
    namespace fs = std::filesystem;
    std::error_code ec;
    if (!on || save_path.empty() || !fs::exists(save_path, ec)) return;
    const fs::path save(save_path);
    const fs::path folder = save.parent_path() / "backups";
    fs::create_directories(folder, ec);
    const std::time_t now = std::time(nullptr);
    char stamp[32];
    std::strftime(stamp, sizeof(stamp), "%Y%m%d-%H%M%S", std::localtime(&now));
    const std::string prefix = save.stem().string() + "-";
    const fs::path copy = folder / (prefix + stamp + save.extension().string());
    fs::copy_file(save, copy, fs::copy_options::overwrite_existing, ec);
    if (ec) {
        std::fprintf(stderr, "[acwwrecomp] could not back up the save: %s\n",
                     ec.message().c_str());
        return;
    }
    std::vector<fs::path> old;
    for (const auto& entry : fs::directory_iterator(folder, ec)) {
        const std::string name = entry.path().filename().string();
        if (name.rfind(prefix, 0) == 0 && entry.path().extension() == save.extension())
            old.push_back(entry.path());
    }
    std::sort(old.begin(), old.end(), std::greater<>());
    for (size_t i = static_cast<size_t>(std::max(keep, 1)); i < old.size(); ++i)
        fs::remove(old[i], ec);
    std::fprintf(stderr, "[acwwrecomp] save backed up to backups\\%s\n",
                 copy.filename().string().c_str());
}

// ---- mods -------------------------------------------------------------------

inline bool hex_bytes(const std::string& text, std::vector<uint8_t>* out) {
    std::string digits;
    for (char c : text)
        if (!std::isspace(static_cast<unsigned char>(c))) digits += c;
    if (digits.size() % 2) return false;
    out->clear();
    for (size_t i = 0; i < digits.size(); i += 2) {
        char* end = nullptr;
        const std::string pair = digits.substr(i, 2);
        const long v = std::strtol(pair.c_str(), &end, 16);
        if (!end || *end) return false;
        out->push_back(static_cast<uint8_t>(v));
    }
    return true;
}

inline bool read_patches(const toml::array* list, std::vector<Patch>* out) {
    if (!list) return true;
    for (const auto& node : *list) {
        const toml::table* t = node.as_table();
        if (!t) return false;
        Patch p;
        const auto addr = (*t)["addr"].value<int64_t>();
        const auto original = (*t)["original"].value<std::string>();
        const auto patched = (*t)["patched"].value<std::string>();
        if (!addr || !original || !patched || !hex_bytes(*original, &p.original) ||
            !hex_bytes(*patched, &p.patched) || p.original.size() != p.patched.size() ||
            p.original.empty())
            return false;
        p.addr = static_cast<uint32_t>(*addr);
        out->push_back(std::move(p));
    }
    return true;
}

// The same rules as tools/mods.py: settings.toml's [mods] choice ("on",
// "off" or an option) wins over the mod file's own enabled and setting.
inline void load_mods(State& s, const toml::table* choices) {
    namespace fs = std::filesystem;
    std::error_code ec;
    std::vector<fs::path> files;
    for (const auto& entry : fs::directory_iterator(s.folder / "mods", ec))
        if (entry.path().extension() == ".toml") files.push_back(entry.path());
    std::sort(files.begin(), files.end());
    for (const fs::path& file : files) {
        const std::string id = file.stem().string();
        toml::table data;
        try {
            data = toml::parse_file(file.string());
        } catch (const toml::parse_error& e) {
            std::fprintf(stderr, "[mods] %s: %s; skipped\n", file.filename().string().c_str(),
                         std::string(e.description()).c_str());
            continue;
        }
        const toml::table* info = data["mod"].as_table();
        std::string name = info ? (*info)["name"].value_or(id) : id;
        bool enabled = info ? (*info)["enabled"].value_or(false) : false;
        std::string setting = info ? (*info)["setting"].value_or(std::string()) : std::string();
        std::vector<std::pair<std::string, std::vector<Patch>>> options;
        std::vector<Patch> base;
        bool ok = read_patches(data["patch"].as_array(), &base);
        if (const toml::array* list = data["option"].as_array()) {
            for (const auto& node : *list) {
                const toml::table* t = node.as_table();
                if (!t) { ok = false; break; }
                std::vector<Patch> patches;
                ok = ok && read_patches((*t)["patch"].as_array(), &patches);
                options.emplace_back((*t)["name"].value_or(std::string()), std::move(patches));
            }
        }
        if (!ok) {
            std::fprintf(stderr, "[mods] %s: a patch is malformed; skipped\n",
                         file.filename().string().c_str());
            continue;
        }
        auto find_option = [&](const std::string& n) {
            return std::find_if(options.begin(), options.end(),
                                [&](const auto& o) { return o.first == n; });
        };
        if (choices) {
            if (const auto choice = (*choices)[id].value<std::string>()) {
                if (*choice == "on" || *choice == "off") {
                    enabled = *choice == "on";
                } else if (find_option(*choice) != options.end()) {
                    enabled = true;
                    setting = *choice;
                } else {
                    std::fprintf(stderr, "[mods] settings.toml: mods.%s = \"%s\" is not on, "
                                 "off or one of its options; using its default\n",
                                 id.c_str(), choice->c_str());
                }
            }
        }
        if (!enabled) {
            std::fprintf(stderr, "[mods] %s is off\n", name.c_str());
            continue;
        }
        Mod mod;
        mod.label = options.empty() ? name : name + " (" + setting + ")";
        mod.active = base;
        if (!options.empty()) {
            const auto chosen = find_option(setting);
            if (chosen == options.end()) {
                std::fprintf(stderr, "[mods] %s: setting \"%s\" is not one of its options; "
                             "skipped\n", file.filename().string().c_str(), setting.c_str());
                continue;
            }
            mod.active.insert(mod.active.end(), chosen->second.begin(), chosen->second.end());
        }
        if (mod.active.empty()) {
            std::fprintf(stderr, "[mods] %s: nothing to change\n", mod.label.c_str());
            continue;
        }
        s.mods.push_back(std::move(mod));
    }
}

inline bool live_is(const Patch& p, const std::vector<uint8_t>& bytes) {
    for (size_t i = 0; i < bytes.size(); ++i)
        if (peek(p.addr + static_cast<uint32_t>(i)) != bytes[i]) return false;
    return true;
}

// Writes go through the bus like the debug port's write_mem, which drops the
// recompiled copy of the code they change.
inline void poke(uint32_t addr, const std::vector<uint8_t>& bytes) {
    const NdsCpu old = g_nds_active;
    g_nds_active = NDS_ARM9;
    for (size_t i = 0; i < bytes.size(); ++i)
        bus_write_u8_slow(addr + static_cast<uint32_t>(i), bytes[i]);
    g_nds_active = old;
}

inline void mods_frame(State& s) {
    for (Mod& mod : s.mods) {
        if (mod.given_up) continue;
        bool all_patched = true;
        bool known = true;   // every place holds the original or the patched bytes
        for (const Patch& p : mod.active) {
            const bool patched = live_is(p, p.patched);
            all_patched = all_patched && patched;
            known = known && (patched || live_is(p, p.original));
        }
        if (all_patched) continue;
        if (!known) {
            // Before the game's code is loaded memory holds something else;
            // after 30 seconds it is the wrong ROM or another mod.
            if (!mod.applied && s.frames > 30 * 60) {
                mod.given_up = true;
                std::fprintf(stderr, "[mods] SKIPPED %s: the code there is not what this mod "
                             "expects (different ROM, or another mod changed it)\n",
                             mod.label.c_str());
            }
            continue;
        }
        for (const Patch& p : mod.active)
            if (!live_is(p, p.patched)) poke(p.addr, p.patched);
        std::fprintf(stderr, "[mods] %s %s\n", mod.applied ? "applied again" : "applied",
                     mod.label.c_str());
        mod.applied = true;
    }
}

// ---- Discord ----------------------------------------------------------------

inline std::string json_text(const std::string& text) {
    std::string out = "\"";
    for (unsigned char c : text) {
        if (c == '"' || c == '\\') {
            out += '\\';
            out += static_cast<char>(c);
        } else if (c < 0x20) {
            char buf[8];
            std::snprintf(buf, sizeof(buf), "\\u%04x", c);
            out += buf;
        } else {
            out += static_cast<char>(c);
        }
    }
    return out + "\"";
}

inline std::string with_commas(uint32_t n) {
    std::string digits = std::to_string(n);
    for (int i = static_cast<int>(digits.size()) - 3; i > 0; i -= 3)
        digits.insert(static_cast<size_t>(i), ",");
    return digits;
}

// Room names from tools/presence_rooms.json ({"0": "In town", ...}), which
// presence.py label writes; read again whenever a room has no name yet.
inline std::string room_name(State& s, uint32_t room, const std::string& shop) {
    std::string name;
    std::ifstream file(s.folder / "tools" / "presence_rooms.json", std::ios::binary);
    if (file) {
        std::stringstream text;
        text << file.rdbuf();
        const std::string json = text.str();
        const std::regex entry("\"(\\d+)\"\\s*:\\s*\"((?:[^\"\\\\]|\\\\.)*)\"");
        for (std::sregex_iterator it(json.begin(), json.end(), entry), end; it != end; ++it) {
            if (std::stoul((*it)[1].str()) != room) continue;
            const std::string raw = (*it)[2].str();
            for (size_t i = 0; i < raw.size(); ++i) {
                if (raw[i] != '\\' || i + 1 >= raw.size()) {
                    name += raw[i];
                } else if (raw[i + 1] == 'u' && i + 5 < raw.size()) {
                    const unsigned cp = std::stoul(raw.substr(i + 2, 4), nullptr, 16);
                    if (cp < 0x80) name += static_cast<char>(cp);
                    else if (cp < 0x800) {
                        name += static_cast<char>(0xC0 | cp >> 6);
                        name += static_cast<char>(0x80 | (cp & 0x3F));
                    } else {
                        name += static_cast<char>(0xE0 | cp >> 12);
                        name += static_cast<char>(0x80 | (cp >> 6 & 0x3F));
                        name += static_cast<char>(0x80 | (cp & 0x3F));
                    }
                    i += 5;
                } else {
                    name += raw[++i] == 'n' ? '\n' : raw[i];
                }
            }
            break;
        }
    } else {
        static const char* const defaults[][2] = {
            {"0", "In town"}, {"1", "At home"}, {"9", "At the town hall"},
            {"29", "Shopping at {shop}"}};
        for (const auto& d : defaults)
            if (std::to_string(room) == d[0]) name = d[1];
    }
    if (name.empty()) {
        if (std::find(s.unnamed_rooms.begin(), s.unnamed_rooms.end(), room) ==
            s.unnamed_rooms.end()) {
            s.unnamed_rooms.push_back(room);
            std::fprintf(stderr, "[presence] room %u has no name yet; while you're there run: "
                         "py -3.12 tools\\presence.py label \"At the ...\"\n", room);
        }
        return "Playing";
    }
    if (const size_t at = name.find("{shop}"); at != std::string::npos)
        name.replace(at, 6, shop);
    return name;
}

inline std::string activity(State& s) {
    const uint32_t room = peek32(kRoom);
    const uint16_t shop_word = static_cast<uint16_t>(peek(kShopWord) | peek(kShopWord + 1) << 8);
    const std::string where = room_name(s, room, kShops[(shop_word >> 9) & 3]);
    const std::string player = game_text(kPlayerName, 8);
    const std::string town = game_text(kTownName, 8);
    std::string state;
    if (s.show_names && !player.empty() && !town.empty()) state = player + " of " + town;
    if (s.show_bells) {
        if (!state.empty()) state += " \xc2\xb7 ";
        state += with_commas(peek32(kBells)) + " bells";
    }
    std::string json = "{\"details\":" + json_text(where);
    if (!state.empty()) json += ",\"state\":" + json_text(state);
    json += ",\"timestamps\":{\"start\":" + std::to_string(s.started_at) + "}";
    json += ",\"assets\":{\"large_image\":\"icon\",\"large_text\":" + json_text(kCredit) + "}}";
    return json;
}

#ifdef _WIN32
// The Discord app's local pipe: an 8-byte header (op, length), then JSON.
inline bool pipe_send(int fd, uint32_t op, const std::string& json) {
    std::string frame(8, '\0');
    const uint32_t length = static_cast<uint32_t>(json.size());
    for (int i = 0; i < 4; ++i) {
        frame[i] = static_cast<char>(op >> (8 * i));
        frame[4 + i] = static_cast<char>(length >> (8 * i));
    }
    frame += json;
    return _write(fd, frame.data(), static_cast<unsigned>(frame.size())) ==
           static_cast<int>(frame.size());
}

inline bool pipe_read(int fd, char* out, size_t n) {
    while (n) {
        const int got = _read(fd, out, static_cast<unsigned>(n));
        if (got <= 0) return false;
        out += got;
        n -= static_cast<size_t>(got);
    }
    return true;
}

inline bool pipe_recv(int fd, std::string* json) {
    unsigned char header[8];
    if (!pipe_read(fd, reinterpret_cast<char*>(header), 8)) return false;
    const uint32_t length = header[4] | header[5] << 8 | header[6] << 16 |
                            static_cast<uint32_t>(header[7]) << 24;
    if (length > (1u << 20)) return false;
    json->assign(length, '\0');
    return pipe_read(fd, json->data(), length);
}

inline int discord_connect() {
    for (int i = 0; i < 10; ++i) {
        const std::string name = "\\\\.\\pipe\\discord-ipc-" + std::to_string(i);
        const int fd = _open(name.c_str(), _O_RDWR | _O_BINARY);
        if (fd < 0) continue;
        std::string reply;
        if (pipe_send(fd, 0, std::string("{\"v\":1,\"client_id\":\"") + kClientId + "\"}") &&
            pipe_recv(fd, &reply) && reply.find("\"READY\"") != std::string::npos)
            return fd;
        std::fprintf(stderr, "[presence] Discord said no: %s\n", reply.c_str());
        _close(fd);
        return -1;
    }
    return -1;
}

inline void discord_thread(Presence* p) {
    using clock = std::chrono::steady_clock;
    int fd = -1;
    std::string sent;
    unsigned nonce = 0;
    auto next_try = clock::now();
    bool told_error = false;
    for (;;) {
        std::string want;
        {
            std::unique_lock<std::mutex> lock(p->lock);
            p->wake.wait_for(lock, std::chrono::seconds(5));
            want = p->wanted;
        }
        if (want.empty() || (fd >= 0 && want == sent)) continue;
        if (fd < 0) {
            if (clock::now() < next_try) continue;
            fd = discord_connect();
            if (fd < 0) {
                next_try = clock::now() + std::chrono::seconds(30);
                continue;
            }
            std::fprintf(stderr, "[presence] connected to Discord\n");
            sent.clear();
        }
        const std::string message =
            "{\"cmd\":\"SET_ACTIVITY\",\"nonce\":\"" + std::to_string(++nonce) +
            "\",\"args\":{\"pid\":" + std::to_string(_getpid()) + ",\"activity\":" + want + "}}";
        std::string reply;
        if (!pipe_send(fd, 1, message) || !pipe_recv(fd, &reply)) {
            _close(fd);
            fd = -1;
            next_try = clock::now() + std::chrono::seconds(30);
            continue;
        }
        if (reply.find("\"ERROR\"") != std::string::npos && !told_error) {
            told_error = true;
            std::fprintf(stderr, "[presence] Discord didn't take it: %s\n", reply.c_str());
        }
        sent = want;
    }
}
#endif

inline void presence_frame(State& s) {
    const std::string now = activity(s);
    if (now == s.last_activity) return;
    s.last_activity = now;
    {
        std::lock_guard<std::mutex> lock(s.presence->lock);
        s.presence->wanted = now;
    }
    s.presence->wake.notify_one();
}

// ---- hooks --------------------------------------------------------------------

// Once, before the save is loaded: folder holds game.toml and settings.toml.
inline void start(const std::string& config_path, const std::string& save_path) {
    State& s = state();
    if (s.started) return;
    s.started = true;
    s.folder = std::filesystem::path(config_path).parent_path();
    if (s.folder.empty()) s.folder = ".";
    s.started_at = static_cast<long long>(std::time(nullptr));

    toml::table settings;
    std::error_code ec;
    const std::filesystem::path path = s.folder / "settings.toml";
    if (std::filesystem::exists(path, ec)) {
        try {
            settings = toml::parse_file(path.string());
        } catch (const toml::parse_error&) {
            // patch_settings.py's reader already said what is wrong with it.
        }
    }
    const toml::table* saves = settings["saves"].as_table();
    backup_save(save_path, saves ? (*saves)["backup_on_launch"].value_or(true) : true,
                saves ? static_cast<int>((*saves)["keep_backups"].value_or(int64_t{30})) : 30);

    if (env_on("ACWW_NO_MODS"))
        std::fprintf(stderr, "[mods] off for this run (ACWW_NO_MODS)\n");
    else
        load_mods(s, settings["mods"].as_table());

    const toml::table* discord = settings["discord"].as_table();
    s.presence_on = discord ? (*discord)["presence"].value_or(true) : true;
    s.show_names = discord ? (*discord)["show_names"].value_or(true) : true;
    s.show_bells = discord ? (*discord)["show_bells"].value_or(true) : true;
    if (env_on("ACWW_NO_DISCORD")) s.presence_on = false;
#ifdef _WIN32
    if (s.presence_on) {
        s.presence = new Presence;
        std::thread(discord_thread, s.presence).detach();
    }
#else
    s.presence_on = false;
#endif
}

// Every frame, at the safe point between frames where the debug port's
// commands also run.
inline void frame() {
    State& s = state();
    if (!s.started) return;
    ++s.frames;
    if (s.frames % 15 == 0 && !s.mods.empty()) mods_frame(s);
    if (s.presence_on && s.frames % 300 == 120) presence_frame(s);
}

}  // namespace acww_game
