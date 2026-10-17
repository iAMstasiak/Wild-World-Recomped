// WildWorldBuild: builds Wild World Recomped from the player's own ROM.
//
// The launcher runs this on first start (and after an update); it does what
// prepare_acww.py, make_banks.py and the runner build do on the developer's
// PC, with no Python. So far, two of its steps:
//
//   WildWorldBuild unpack --rom acww.nds --out generated\inputs-check
//       [--compare generated\inputs]
//
// writes arm9.bin, arm7.bin and overlays\arm9_overlay_NNN.bin, the same files
// prepare_acww.py writes, and with --compare checks them byte for byte
// against an earlier set.
//
//   WildWorldBuild plan --rom acww.nds --seeds generated\ingest\seeds
//       --out generated\banks-check [--compare generated\banks]
//
// writes the recompiler's config for each bank, as make_banks.py does (minus
// the runtime-only pages), and with --compare checks them against its own.
#include <algorithm>
#include <chrono>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <string>
#include <vector>

#include "nds_rom.h"
#include "plan.h"
#include "sha1.h"

namespace fs = std::filesystem;
using wwbuild::Bytes;

namespace {

constexpr const char* kRomSha1 = "77fde3e30e1e6068395d1f96ea63be569b61c351";
constexpr size_t kRomSize = 32u * 1024 * 1024;

Bytes read_file(const fs::path& path) {
    std::ifstream file(path, std::ios::binary);
    if (!file) return {};
    return Bytes(std::istreambuf_iterator<char>(file), std::istreambuf_iterator<char>());
}

bool write_file(const fs::path& path, const Bytes& data) {
    std::error_code ec;
    fs::create_directories(path.parent_path(), ec);
    std::ofstream file(path, std::ios::binary | std::ios::trunc);
    file.write(reinterpret_cast<const char*>(data.data()), static_cast<std::streamsize>(data.size()));
    return static_cast<bool>(file);
}

// The supported dump, or a sentence saying what is wrong with it.
std::string check_rom(const Bytes& rom) {
    if (rom.empty()) return "the ROM file can't be read";
    if (rom.size() != kRomSize)
        return "the ROM is " + std::to_string(rom.size()) + " bytes, not 32 MB";
    if (std::string(rom.begin() + 0x0C, rom.begin() + 0x10) != "ADME")
        return "this isn't Animal Crossing: Wild World (USA)";
    if (rom[0x1E] != 1) return "this is revision " + std::to_string(rom[0x1E]) + ", not revision 1";
    const std::string sha = wwbuild::sha1_hex(rom);
    if (sha != kRomSha1) return "the ROM's SHA-1 is " + sha + ", not the expected " + kRomSha1;
    return "";
}

std::string arg_value(int argc, char** argv, const std::string& name) {
    for (int i = 2; i + 1 < argc; ++i)
        if (argv[i] == name) return argv[i + 1];
    return "";
}

// The player's ROM, checked and unpacked; false (and a message) if it isn't
// the supported dump.
bool load_rom(const std::string& rom_path, wwbuild::Rom* rom) {
    const Bytes rom_bytes = read_file(fs::u8path(rom_path));
    const std::string problem = check_rom(rom_bytes);
    if (!problem.empty()) {
        std::fprintf(stderr, "[error] %s\n", problem.c_str());
        return false;
    }
    std::printf("ROM verified: Animal Crossing: Wild World (USA, revision 1)\n");
    try {
        *rom = wwbuild::read_rom(rom_bytes);
    } catch (const std::exception& e) {
        std::fprintf(stderr, "[error] unpacking the ROM: %s\n", e.what());
        return false;
    }
    std::sort(rom->overlays.begin(), rom->overlays.end(),
              [](const wwbuild::Overlay& a, const wwbuild::Overlay& b) { return a.id < b.id; });
    return true;
}

int unpack(int argc, char** argv) {
    const std::string rom_path = arg_value(argc, argv, "--rom");
    const std::string out_arg = arg_value(argc, argv, "--out");
    const std::string compare_arg = arg_value(argc, argv, "--compare");
    if (rom_path.empty() || out_arg.empty()) {
        std::fprintf(stderr, "usage: WildWorldBuild unpack --rom FILE --out DIR [--compare DIR]\n");
        return 2;
    }
    const auto started = std::chrono::steady_clock::now();
    wwbuild::Rom rom;
    if (!load_rom(rom_path, &rom)) return 1;

    std::vector<std::pair<std::string, const Bytes*>> files = {
        {"arm9.bin", &rom.arm9}, {"arm7.bin", &rom.arm7}};
    for (const wwbuild::Overlay& ov : rom.overlays) {
        char name[48];
        std::snprintf(name, sizeof(name), "overlays/arm9_overlay_%03u.bin", ov.id);
        files.emplace_back(name, &ov.data);
    }

    const fs::path out = fs::u8path(out_arg);
    for (const auto& [name, data] : files) {
        if (!write_file(out / name, *data)) {
            std::fprintf(stderr, "[error] can't write %s\n", (out / name).u8string().c_str());
            return 1;
        }
    }
    std::printf("ARM9: %zu bytes at 0x%08X (entry 0x%08X), SHA-1 %s\n", rom.arm9.size(),
                rom.arm9_ram, rom.arm9_entry, wwbuild::sha1_hex(rom.arm9).c_str());
    std::printf("ARM7: %zu bytes at 0x%08X (entry 0x%08X), SHA-1 %s\n", rom.arm7.size(),
                rom.arm7_ram, rom.arm7_entry, wwbuild::sha1_hex(rom.arm7).c_str());
    size_t packed = 0;
    for (const wwbuild::Overlay& ov : rom.overlays) packed += (ov.flags & 1) ? 1 : 0;
    std::printf("ARM9 overlays: %zu (%zu were compressed)\n", rom.overlays.size(), packed);

    if (!compare_arg.empty()) {
        const fs::path against = fs::u8path(compare_arg);
        size_t same = 0, missing = 0;
        std::vector<std::string> differ;
        for (const auto& [name, data] : files) {
            const Bytes old = read_file(against / name);
            if (old.empty() && !data->empty()) ++missing;
            else if (old == *data) ++same;
            else differ.push_back(name);
        }
        std::printf("compared with %s: %zu the same, %zu different, %zu missing there\n",
                    against.u8string().c_str(), same, differ.size(), missing);
        for (const std::string& name : differ) std::printf("  different: %s\n", name.c_str());
    }
    const double seconds = std::chrono::duration<double>(std::chrono::steady_clock::now() - started).count();
    std::printf("unpacked %zu files into %s in %.1f s\n", files.size(), out.u8string().c_str(), seconds);
    return 0;
}

// Everything after the first line (the comment naming the tool).
std::string body(const std::string& text) {
    const size_t nl = text.find('\n');
    return nl == std::string::npos ? "" : text.substr(nl + 1);
}

int plan(int argc, char** argv) {
    const std::string rom_path = arg_value(argc, argv, "--rom");
    const std::string seeds_arg = arg_value(argc, argv, "--seeds");
    const std::string out_arg = arg_value(argc, argv, "--out");
    const std::string compare_arg = arg_value(argc, argv, "--compare");
    if (rom_path.empty() || seeds_arg.empty() || out_arg.empty()) {
        std::fprintf(stderr, "usage: WildWorldBuild plan --rom FILE --seeds DIR --out DIR [--compare DIR]\n");
        return 2;
    }
    wwbuild::Rom rom;
    if (!load_rom(rom_path, &rom)) return 1;
    std::string report;
    const std::vector<wwbuild::Bank> banks = wwbuild::plan_banks(rom, fs::u8path(seeds_arg), &report);
    std::printf("%s\n", report.c_str());
    const fs::path out = fs::u8path(out_arg);
    size_t written = 0, same = 0, missing = 0;
    std::vector<std::string> differ;
    for (const wwbuild::Bank& b : banks) {
        const std::string text = wwbuild::bank_config(b);
        if (text.empty()) {
            std::printf("  %s: no entry point inside it; left out\n", b.bank.c_str());
            continue;
        }
        const Bytes data(text.begin(), text.end());
        if (!write_file(out / (b.bank + ".toml"), data)) {
            std::fprintf(stderr, "[error] can't write into %s\n", out.u8string().c_str());
            return 1;
        }
        ++written;
        std::printf("  %-28s 0x%08X %8u bytes  %2d shards\n", b.bank.c_str(), b.load, b.size, b.shards);
        if (!compare_arg.empty()) {
            const Bytes old = read_file(fs::u8path(compare_arg) / (b.bank + ".toml"));
            if (old.empty()) ++missing;
            else if (body(std::string(old.begin(), old.end())) == body(text)) ++same;
            else differ.push_back(b.bank);
        }
    }
    std::printf("%zu bank configs written to %s\n", written, out.u8string().c_str());
    if (!compare_arg.empty()) {
        std::printf("compared with %s: %zu the same, %zu different, %zu missing there\n",
                    compare_arg.c_str(), same, differ.size(), missing);
        for (const std::string& name : differ) std::printf("  different: %s\n", name.c_str());
    }
    return 0;
}

}  // namespace

int main(int argc, char** argv) {
    const std::string command = argc > 1 ? argv[1] : "";
    if (command == "unpack") return unpack(argc, argv);
    if (command == "plan") return plan(argc, argv);
    std::fprintf(stderr,
                 "WildWorldBuild: builds Wild World Recomped from your own ROM.\n"
                 "  WildWorldBuild unpack --rom acww.nds --out DIR [--compare DIR]\n"
                 "  WildWorldBuild plan --rom acww.nds --seeds DIR --out DIR [--compare DIR]\n");
    return 2;
}
