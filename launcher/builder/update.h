// Updating Wild World Recomped (WildWorldBuild): which release is the newest
// on GitHub, and putting a downloaded one in place of the program files while
// leaving the player's own (save, settings, controls, backups, the compiler
// pack and the build) alone. The launcher then rebuilds the game, because
// game\built.txt names the old version.
#pragma once

#include <chrono>
#include <cstdint>
#include <cstdlib>
#include <filesystem>
#include <string>
#include <system_error>
#include <thread>
#include <vector>

#include "process.h"

namespace wwbuild {

struct Release {
    std::string version;   // the tag without its "v"
    std::string url;       // the release's zip
    uint64_t size = 0;
};

// The newest release from GitHub's answer to /releases/latest: its tag and
// its first .zip. Empty version when there's none.
inline Release parse_latest(const std::string& json) {
    Release r;
    const auto string_after = [&](const std::string& key, size_t from, size_t* at) {
        const size_t k = json.find("\"" + key + "\"", from);
        if (k == std::string::npos) return std::string();
        const size_t open = json.find('"', json.find(':', k) + 1);
        const size_t close = json.find('"', open + 1);
        if (open == std::string::npos || close == std::string::npos) return std::string();
        if (at) *at = k;
        return json.substr(open + 1, close - open - 1);
    };
    std::string tag = string_after("tag_name", 0, nullptr);
    if (!tag.empty() && (tag[0] == 'v' || tag[0] == 'V')) tag.erase(0, 1);
    for (size_t from = 0;;) {
        size_t at = 0;
        const std::string url = string_after("browser_download_url", from, &at);
        if (url.empty()) break;
        from = at + 1;
        if (url.size() < 4 || url.compare(url.size() - 4, 4, ".zip") != 0) continue;
        // An asset's "size" comes before its download address.
        const size_t size_key = json.rfind("\"size\"", at);
        if (size_key != std::string::npos)
            r.size = std::strtoull(json.c_str() + json.find(':', size_key) + 1, nullptr, 10);
        r.url = url;
        break;
    }
    if (!r.url.empty()) r.version = tag;
    return r;
}

// Whether version a ("0.10") is newer than b ("0.9").
inline bool newer_version(const std::string& a, const std::string& b) {
    size_t i = 0, j = 0;
    while (i < a.size() || j < b.size()) {
        const unsigned long x = i < a.size() ? std::strtoul(a.c_str() + i, nullptr, 10) : 0;
        const unsigned long y = j < b.size() ? std::strtoul(b.c_str() + j, nullptr, 10) : 0;
        if (x != y) return x > y;
        i = a.find('.', i);
        j = b.find('.', j);
        i = i == std::string::npos ? a.size() : i + 1;
        j = j == std::string::npos ? b.size() : j + 1;
    }
    return false;
}

#ifdef _WIN32
// Waits (up to a minute) for the launcher to close, so its files can be replaced.
inline void wait_for_process(unsigned long pid) {
    if (HANDLE p = OpenProcess(SYNCHRONIZE, FALSE, pid)) {
        WaitForSingleObject(p, 60000);
        CloseHandle(p);
    }
}
#endif

// Copies from over to, a few times if a file is still held open for a moment.
inline bool copy_over(const std::filesystem::path& from, const std::filesystem::path& to, std::string* error) {
    namespace fs = std::filesystem;
    std::error_code ec;
    const bool folder = fs::is_directory(from, ec);
    for (int attempt = 0; attempt < 20; ++attempt) {
        ec.clear();
        fs::create_directories(to.parent_path(), ec);
        if (folder) {
            fs::copy(from, to, fs::copy_options::recursive | fs::copy_options::overwrite_existing, ec);
        } else {
            fs::copy_file(from, to, fs::copy_options::overwrite_existing, ec);
        }
        if (!ec) return true;
        std::this_thread::sleep_for(std::chrono::milliseconds(500));
    }
    *error = "can't replace " + to.u8string() + " (" + ec.message() + ")";
    return false;
}

// Puts the release unpacked in from (the folder holding WildWorldRecomped.exe)
// in place in into. kit\ and assets\ are replaced whole; mods\ and tools\ only
// get their files written over, so mods the player added stay.
inline bool apply_release(const std::filesystem::path& from, const std::filesystem::path& into,
                          std::string* error) {
    namespace fs = std::filesystem;
    std::error_code ec;
    std::vector<fs::path> items;   // listed first: kit\ and assets\ move out as it goes
    for (const auto& item : fs::directory_iterator(from, ec)) items.push_back(item.path());
    for (const fs::path& item : items) {
        const std::string name = item.filename().u8string();
        const fs::path target = into / item.filename();
        if (name == "kit" || name == "assets") {
            fs::remove_all(target, ec);
            fs::rename(item, target, ec);
            if (!ec) continue;
        }
        if (!copy_over(item, target, error)) return false;
    }
    return true;
}

}  // namespace wwbuild
