// Which banks to recompile, and their configs (WildWorldBuild). A port of
// plan_banks() and write_config() in tools/make_banks.py, for the banks a
// player's build can make from their own ROM: the main ARM9 and ARM7 code at
// their own addresses and at every alias base the coverage saw, and each
// overlay the coverage saw resident. (Runtime-only pages are left out: their
// bytes came from the developer's play, not the ROM.)
//
// The entry points come from the ingest's seed files (seeds\*.toml, shipped
// with the release): addresses and ARM/Thumb modes only, no game bytes.
#pragma once

#include <algorithm>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <map>
#include <regex>
#include <set>
#include <string>
#include <utility>
#include <vector>

#include "nds_rom.h"
#include "sha1.h"

namespace wwbuild {

using Entry = std::pair<uint32_t, std::string>;   // address, "arm" or "thumb"

struct Bank {
    std::string bank, name, image;   // image: arm9.bin, arm7.bin or overlays/...
    int cpu = 9;
    uint32_t load = 0, size = 0;
    std::string sha1;
    std::vector<Entry> entries;
    bool overlay = false;
    uint32_t overlay_id = 0, bss = 0, static_init_start = 0, static_init_end = 0;
    int shards = 2;
};

// The [[entry_point]] tables of a seed file: their addr and mode.
inline std::vector<Entry> read_seeds(const std::filesystem::path& path) {
    std::vector<Entry> out;
    std::ifstream file(path);
    std::string line, mode;
    long long addr = -1;
    const auto flush = [&]() {
        if (addr >= 0 && !mode.empty()) out.emplace_back(static_cast<uint32_t>(addr), mode);
        addr = -1;
        mode.clear();
    };
    while (std::getline(file, line)) {
        if (!line.empty() && line.back() == '\r') line.pop_back();
        const size_t start = line.find_first_not_of(" \t");
        if (start == std::string::npos || line[start] == '#') continue;
        const std::string t = line.substr(start);
        if (t.rfind("[", 0) == 0) {
            flush();
            continue;
        }
        const size_t eq = t.find('=');
        if (eq == std::string::npos) continue;
        std::string key = t.substr(0, eq);
        key.erase(key.find_last_not_of(" \t") + 1);
        std::string value = t.substr(eq + 1);
        value.erase(0, value.find_first_not_of(" \t"));
        if (const size_t hash = value.find('#'); hash != std::string::npos && value[0] != '"')
            value.erase(hash);
        value.erase(value.find_last_not_of(" \t") + 1);
        if (key == "addr") addr = std::stoll(value, nullptr, 0);
        else if (key == "mode" && value.size() >= 2 && value.front() == '"')
            mode = value.substr(1, value.find('"', 1) - 1);
    }
    flush();
    return out;
}

inline int shards_for(size_t size) {
    // The runner only picks up shard files named <bank>_NN.c, so never 1.
    return static_cast<int>(std::max<size_t>(2, std::min<size_t>(16, (size + 0x7FFF) / 0x8000)));
}

// The banks to build, in make_banks.py's order (seed files by name).
inline std::vector<Bank> plan_banks(const Rom& rom, const std::filesystem::path& seeds_dir,
                                    std::string* report) {
    static const std::regex kSeedFile(
        "^arm(9|7)_(arm9|arm7|arm9_overlay_(\\d{3}))_([0-9a-f]{8})$");
    static const std::regex kUnresolved("^arm(9|7)_unresolved$");
    std::vector<std::filesystem::path> files;
    std::error_code ec;
    for (const auto& item : std::filesystem::directory_iterator(seeds_dir, ec))
        if (item.path().extension() == ".toml") files.push_back(item.path());
    std::sort(files.begin(), files.end());

    std::vector<Bank> banks;
    std::map<int, std::vector<Entry>> unresolved;
    for (const auto& path : files) {
        const std::string stem = path.stem().string();
        std::smatch m;
        if (std::regex_match(stem, m, kUnresolved)) {
            const std::vector<Entry> seeds = read_seeds(path);
            auto& list = unresolved[std::stoi(m[1])];
            list.insert(list.end(), seeds.begin(), seeds.end());
            continue;
        }
        if (!std::regex_match(stem, m, kSeedFile)) continue;
        Bank b;
        b.cpu = std::stoi(m[1]);
        b.load = static_cast<uint32_t>(std::stoul(m[4].str(), nullptr, 16));
        b.entries = read_seeds(path);
        const Bytes* data = nullptr;
        if (m[3].matched) {
            const std::string id = m[3];
            const auto ov = std::find_if(rom.overlays.begin(), rom.overlays.end(),
                [&](const Overlay& o) { return o.id == static_cast<uint32_t>(std::stoi(id)); });
            if (ov == rom.overlays.end()) continue;
            data = &ov->data;
            b.bank = "acww_arm9_ov" + id;
            b.name = "ACWW ARM9 overlay " + id;
            b.image = "overlays/arm9_overlay_" + id + ".bin";
            b.overlay = true;
            b.overlay_id = ov->id;
            b.bss = ov->bss;
            b.static_init_start = ov->static_init_start;
            b.static_init_end = ov->static_init_end;
        } else {
            const bool arm9 = b.cpu == 9;
            data = arm9 ? &rom.arm9 : &rom.arm7;
            b.image = arm9 ? "arm9.bin" : "arm7.bin";
            const uint32_t declared = arm9 ? rom.arm9_ram : rom.arm7_ram;
            const std::string cpu = std::to_string(b.cpu);
            if (b.load == declared) {
                b.bank = "acww_arm" + cpu;
                b.name = "ACWW ARM" + cpu + " main";
                b.entries.emplace_back(arm9 ? rom.arm9_entry : rom.arm7_entry, "arm");
            } else {
                char tail[64];
                std::snprintf(tail, sizeof(tail), "_alias_%08x", b.load);
                b.bank = "acww_arm" + cpu + tail;
                std::snprintf(tail, sizeof(tail), " main @ alias base 0x%08X", b.load);
                b.name = "ACWW ARM" + cpu + tail;
            }
        }
        b.size = static_cast<uint32_t>(data->size());
        b.sha1 = sha1_hex(*data);
        b.shards = b.bank == "acww_arm9" ? 16 : b.bank == "acww_arm7" ? 4 : shards_for(data->size());
        banks.push_back(std::move(b));
    }

    size_t routed = 0;
    for (const auto& [cpu, seeds] : unresolved)
        for (const Entry& e : seeds)
            for (Bank& b : banks)
                if (b.cpu == cpu && b.load <= e.first && e.first < uint64_t(b.load) + b.size) {
                    b.entries.push_back(e);
                    ++routed;
                }
    char line[160];
    std::snprintf(line, sizeof(line),
                  "unresolved seeds: %zu arm9 + %zu arm7, offered to covering banks %zu times",
                  unresolved[9].size(), unresolved[7].size(), routed);
    *report = line;
    return banks;
}

// The recompiler's config for one bank, as make_banks.py writes it (apart
// from the first comment line); empty when no entry point is inside it.
inline std::string bank_config(const Bank& b) {
    std::set<Entry> unique(b.entries.begin(), b.entries.end());
    std::vector<Entry> inside;
    for (const Entry& e : unique)
        if (b.load <= e.first && e.first < uint64_t(b.load) + b.size) inside.push_back(e);
    if (inside.empty()) return "";
    std::string s;
    char buf[160];
    const auto add = [&](const std::string& text) { s += text + "\n"; };
    add("# AUTO-GENERATED by WildWorldBuild; do not commit.");
    add("[program]");
    add("name = \"" + b.name + "\"");
    add("id = \"" + b.bank + "\"");
    add("cpu = \"arm" + std::to_string(b.cpu) + "\"");
    add(std::string("isa = \"") + (b.cpu == 9 ? "armv5te" : "armv4t") + "\"");
    std::snprintf(buf, sizeof(buf), "load_address = 0x%08x", b.load); add(buf);
    std::snprintf(buf, sizeof(buf), "size = 0x%08x", b.size); add(buf);
    std::snprintf(buf, sizeof(buf), "entry_pc = 0x%08x", inside[0].first); add(buf);
    add("authoritative_entry_points = false");
    add("");
    add("[identity]");
    add("sha1 = \"" + b.sha1 + "\"");
    add("");
    if (b.overlay) {
        add("[overlay]");
        add("id = " + std::to_string(b.overlay_id));
        std::snprintf(buf, sizeof(buf), "bss_size = 0x%08x", b.bss); add(buf);
        std::snprintf(buf, sizeof(buf), "static_init_start = 0x%08x", b.static_init_start); add(buf);
        std::snprintf(buf, sizeof(buf), "static_init_end = 0x%08x", b.static_init_end); add(buf);
        add("");
    }
    for (const Entry& e : inside) {
        add("[[entry_point]]");
        std::snprintf(buf, sizeof(buf), "addr = 0x%08x", e.first); add(buf);
        add("mode = \"" + e.second + "\"");
        add("kind = \"runtime_observed\"");
        add("");
    }
    s.pop_back();   // make_banks.py joins its lines with "\n": no newline after the last
    return s;
}

}  // namespace wwbuild
