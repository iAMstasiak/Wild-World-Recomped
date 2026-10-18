// WildWorldBuild: builds Wild World Recomped from the player's own ROM.
//
// The launcher runs this on first start (and after an update); it does what
// prepare_acww.py, make_banks.py and the runner build do on the developer's
// PC, with no Python. The launcher runs it twice:
//
//   WildWorldBuild pack --pack DIR [--from DIR] [--force]
//
// downloads the compiler pack (w64devkit and SDL3, from their own releases,
// or from --from when the files are already there), checks each file's
// SHA-256 and unpacks it into --pack; it does nothing if it's already there.
//
//   WildWorldBuild build --rom acww.nds --seeds DIR --recompiler EXE
//       --ndsrecomp DIR --recomp-ui DIR --pack DIR --work DIR --out DIR [--jobs N]
//
// checks the ROM, recompiles it into C (work\recomp, work\gen), compiles that
// into the game with the compiler pack (work\runner) and copies the game into
// --out. Its output for the launcher: "[step] recompile|configure|compile|
// install", "[progress] N/M what", "[error] message" (on stderr, after any
// "[log] line" from the log) and "[done] path to the game".
//
// Each step can also be run on its own, to check it against the developer's
// pipeline:
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
//
//   WildWorldBuild recompile --rom acww.nds --seeds generated\ingest\seeds
//       --recompiler C:\acww\ndsrecomp\recompiler\build\nds_recompile.exe
//       --work generated\build-check [--ndsrecomp C:\acww\ndsrecomp]
//       [--jobs 8] [--compare generated\recomp]
//
// also recompiles every bank into C (and FreeBIOS, given --ndsrecomp), several
// at once, and with --compare checks the game's C files against an earlier set.
//
//   WildWorldBuild compile --ndsrecomp DIR --recomp-ui DIR --pack DIR
//       --work DIR --out DIR [--jobs N]
//
// compiles what recompile left in --work into the game.
#include <algorithm>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <string>
#include <thread>
#include <vector>

#include "build_runner.h"
#include "files.h"
#include "nds_rom.h"
#include "pack.h"
#include "plan.h"
#include "recompile.h"
#include "sha1.h"

#ifdef _WIN32
#include <shellapi.h>
#endif

namespace fs = std::filesystem;
using wwbuild::Bytes;

namespace {

constexpr const char* kRomSha1 = "77fde3e30e1e6068395d1f96ea63be569b61c351";
constexpr size_t kRomSize = 32u * 1024 * 1024;

using wwbuild::read_file;
using wwbuild::write_file;

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

bool has_flag(int argc, char** argv, const std::string& name) {
    for (int i = 2; i < argc; ++i)
        if (argv[i] == name) return true;
    return false;
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

int recompile(int argc, char** argv) {
    const std::string rom_path = arg_value(argc, argv, "--rom");
    const std::string seeds_arg = arg_value(argc, argv, "--seeds");
    const std::string compare_arg = arg_value(argc, argv, "--compare");
    const std::string jobs_arg = arg_value(argc, argv, "--jobs");
    wwbuild::RecompileOptions o;
    o.work = fs::u8path(arg_value(argc, argv, "--work"));
    o.recompiler = fs::u8path(arg_value(argc, argv, "--recompiler"));
    o.ndsrecomp = fs::u8path(arg_value(argc, argv, "--ndsrecomp"));
    o.jobs = jobs_arg.empty() ? static_cast<int>(std::min(8u, std::max(1u, std::thread::hardware_concurrency())))
                              : std::max(1, std::atoi(jobs_arg.c_str()));
    if (rom_path.empty() || seeds_arg.empty() || o.work.empty() || o.recompiler.empty()) {
        std::fprintf(stderr, "usage: WildWorldBuild recompile --rom FILE --seeds DIR --recompiler EXE "
                             "--work DIR [--ndsrecomp DIR] [--jobs N] [--compare DIR]\n");
        return 2;
    }
    const auto started = std::chrono::steady_clock::now();
    wwbuild::Rom rom;
    if (!load_rom(rom_path, &rom)) return 1;
    std::string report;
    const std::vector<wwbuild::Bank> banks = wwbuild::plan_banks(rom, fs::u8path(seeds_arg), &report);
    std::printf("%s\n%zu banks to recompile, %d at a time\n", report.c_str(), banks.size(), o.jobs);
    std::fflush(stdout);
    std::string error;
    if (!wwbuild::recompile_banks(rom, banks, o, &error)) {
        std::fprintf(stderr, "[error] %s\n", error.c_str());
        return 1;
    }
    size_t files = 0, bytes = 0, same = 0, missing = 0;
    std::vector<std::string> differ;
    std::error_code ec;
    for (const auto& item : fs::directory_iterator(o.work / "recomp", ec)) {
        ++files;
        bytes += static_cast<size_t>(item.file_size(ec));
        if (compare_arg.empty()) continue;
        const Bytes old = read_file(fs::u8path(compare_arg) / item.path().filename());
        if (old.empty()) ++missing;
        else if (old == read_file(item.path())) ++same;
        else differ.push_back(item.path().filename().u8string());
    }
    const double seconds = std::chrono::duration<double>(std::chrono::steady_clock::now() - started).count();
    std::printf("recompiled into %zu files (%zu MB) in %.0f s\n", files, bytes >> 20, seconds);
    if (!compare_arg.empty()) {
        std::printf("compared with %s: %zu the same, %zu different, %zu missing there\n",
                    compare_arg.c_str(), same, differ.size(), missing);
        for (size_t i = 0; i < differ.size() && i < 20; ++i) std::printf("  different: %s\n", differ[i].c_str());
    }
    return 0;
}

// A folder or file from the command line as a full path (CMake would take a
// relative one as inside its build folder), or empty if it isn't there.
fs::path full_path(int argc, char** argv, const std::string& name) {
    const std::string value = arg_value(argc, argv, name);
    std::error_code ec;
    return value.empty() ? fs::path() : fs::absolute(fs::u8path(value), ec).lexically_normal();
}

// The compile options from the command line; false when one is missing.
bool build_options(int argc, char** argv, wwbuild::BuildOptions* o) {
    o->work = full_path(argc, argv, "--work");
    o->ndsrecomp = full_path(argc, argv, "--ndsrecomp");
    o->recomp_ui = full_path(argc, argv, "--recomp-ui");
    o->pack = full_path(argc, argv, "--pack");
    o->out = full_path(argc, argv, "--out");
    o->rom_sha1 = kRomSha1;
    o->jobs = std::atoi(arg_value(argc, argv, "--jobs").c_str());
    return !o->work.empty() && !o->ndsrecomp.empty() && !o->recomp_ui.empty() && !o->pack.empty() &&
           !o->out.empty();
}

int compile_game(const wwbuild::BuildOptions& o, std::chrono::steady_clock::time_point started) {
    std::string error;
    std::vector<std::string> details;
    if (!wwbuild::build_runner(o, &error, &details)) {
        for (const std::string& line : details) std::fprintf(stderr, "[log] %s\n", line.c_str());
        std::fprintf(stderr, "[error] %s\n", error.c_str());
        return 1;
    }
    const double seconds = std::chrono::duration<double>(std::chrono::steady_clock::now() - started).count();
    std::printf("built in %d min %02d s\n[done] %s\n", static_cast<int>(seconds) / 60,
                static_cast<int>(seconds) % 60,
                (o.out / (std::string("nds_runner") + wwbuild::kExe)).u8string().c_str());
    return 0;
}

int compile(int argc, char** argv) {
    wwbuild::BuildOptions o;
    if (!build_options(argc, argv, &o)) {
        std::fprintf(stderr, "usage: WildWorldBuild compile --ndsrecomp DIR --recomp-ui DIR --pack DIR "
                             "--work DIR --out DIR [--jobs N]\n");
        return 2;
    }
    return compile_game(o, std::chrono::steady_clock::now());
}

// About what the pack takes once unpacked, with its downloads.
constexpr uintmax_t kPackSpaceNeeded = 1ull << 30;

int pack(int argc, char** argv) {
    const fs::path dir = full_path(argc, argv, "--pack");
    const fs::path from = full_path(argc, argv, "--from");
    if (dir.empty()) {
        std::fprintf(stderr, "usage: WildWorldBuild pack --pack DIR [--from DIR] [--force]\n");
        return 2;
    }
    if (wwbuild::pack_ready(dir) && !has_flag(argc, argv, "--force")) {
        std::printf("the compiler pack (%s) is already in %s\n[done] %s\n", wwbuild::kPackVersion,
                    dir.u8string().c_str(), dir.u8string().c_str());
        return 0;
    }
    std::error_code ec;
    fs::create_directories(dir, ec);
    const fs::space_info space = fs::space(dir, ec);
    if (!ec && space.available < kPackSpaceNeeded) {
        std::fprintf(stderr, "[error] the compiler pack needs about 1 GB free on the drive with %s, "
                             "and there's %.1f GB\n",
                     dir.u8string().c_str(), static_cast<double>(space.available) / (1 << 30));
        return 1;
    }
    const auto started = std::chrono::steady_clock::now();
    std::string error;
    if (!wwbuild::get_pack(dir, from, &error)) {
        std::fprintf(stderr, "[error] %s\n", error.c_str());
        return 1;
    }
    const double seconds = std::chrono::duration<double>(std::chrono::steady_clock::now() - started).count();
    std::printf("the compiler pack (%s) is ready, in %.0f s\n[done] %s\n", wwbuild::kPackVersion, seconds,
                dir.u8string().c_str());
    return 0;
}

// About what a build takes: the C, the compiled code and a second copy of
// the C while a rebuild swaps it in.
constexpr uintmax_t kSpaceNeeded = 4ull << 30;

int build(int argc, char** argv) {
    const auto started = std::chrono::steady_clock::now();
    const std::string rom_path = arg_value(argc, argv, "--rom");
    const std::string seeds_arg = arg_value(argc, argv, "--seeds");
    wwbuild::BuildOptions o;
    wwbuild::RecompileOptions r;
    r.recompiler = full_path(argc, argv, "--recompiler");
    if (!build_options(argc, argv, &o) || rom_path.empty() || seeds_arg.empty() || r.recompiler.empty()) {
        std::fprintf(stderr, "usage: WildWorldBuild build --rom FILE --seeds DIR --recompiler EXE "
                             "--ndsrecomp DIR --recomp-ui DIR --pack DIR --work DIR --out DIR [--jobs N]\n");
        return 2;
    }
    r.work = o.work;
    r.ndsrecomp = o.ndsrecomp;
    r.jobs = static_cast<int>(std::min(8u, std::max(1u, std::thread::hardware_concurrency())));
    std::error_code ec;
    fs::create_directories(o.work, ec);
    const fs::space_info space = fs::space(o.work, ec);
    if (!ec && space.available < kSpaceNeeded) {
        std::fprintf(stderr, "[error] building the game needs about %llu GB free on the drive with %s, "
                             "and there's %.1f GB\n",
                     static_cast<unsigned long long>(kSpaceNeeded >> 30), o.work.u8string().c_str(),
                     static_cast<double>(space.available) / (1 << 30));
        return 1;
    }

    std::printf("[step] recompile\n");
    std::fflush(stdout);
    wwbuild::Rom rom;
    if (!load_rom(rom_path, &rom)) return 1;
    std::string report, error;
    const std::vector<wwbuild::Bank> banks = wwbuild::plan_banks(rom, fs::u8path(seeds_arg), &report);
    if (banks.empty()) {
        std::fprintf(stderr, "[error] no seed files in %s\n", seeds_arg.c_str());
        return 1;
    }
    std::printf("%s\n%zu banks to recompile, %d at a time\n", report.c_str(), banks.size(), r.jobs);
    std::fflush(stdout);
    if (!wwbuild::recompile_banks(rom, banks, r, &error)) {
        std::fprintf(stderr, "[error] %s\n", error.c_str());
        return 1;
    }
    return compile_game(o, started);
}

}  // namespace

int main(int argc, char** argv) {
#ifdef _WIN32
    // Windows hands main() its arguments in the ANSI code page, and a folder
    // name can have letters that has no room for; everything here takes UTF-8.
    std::vector<std::string> utf8;
    std::vector<char*> utf8_argv;
    int n = 0;
    if (wchar_t** wide = CommandLineToArgvW(GetCommandLineW(), &n)) {
        for (int i = 0; i < n; ++i) {
            const int len = WideCharToMultiByte(CP_UTF8, 0, wide[i], -1, nullptr, 0, nullptr, nullptr);
            std::string arg(len > 1 ? static_cast<size_t>(len - 1) : 0, '\0');
            if (len > 1) WideCharToMultiByte(CP_UTF8, 0, wide[i], -1, arg.data(), len, nullptr, nullptr);
            utf8.push_back(arg);
        }
        LocalFree(wide);
        for (std::string& arg : utf8) utf8_argv.push_back(arg.data());
        utf8_argv.push_back(nullptr);
        argc = n;
        argv = utf8_argv.data();
    }
#endif
    const std::string command = argc > 1 ? argv[1] : "";
    if (command == "unpack") return unpack(argc, argv);
    if (command == "plan") return plan(argc, argv);
    if (command == "recompile") return recompile(argc, argv);
    if (command == "compile") return compile(argc, argv);
    if (command == "pack") return pack(argc, argv);
    if (command == "build") return build(argc, argv);
    std::fprintf(stderr,
                 "WildWorldBuild: builds Wild World Recomped from your own ROM.\n"
                 "  WildWorldBuild pack --pack DIR [--from DIR] [--force]\n"
                 "  WildWorldBuild build --rom acww.nds --seeds DIR --recompiler EXE --ndsrecomp DIR\n"
                 "      --recomp-ui DIR --pack DIR --work DIR --out DIR [--jobs N]\n"
                 "  WildWorldBuild unpack --rom acww.nds --out DIR [--compare DIR]\n"
                 "  WildWorldBuild plan --rom acww.nds --seeds DIR --out DIR [--compare DIR]\n"
                 "  WildWorldBuild recompile --rom acww.nds --seeds DIR --recompiler EXE --work DIR\n"
                 "      [--ndsrecomp DIR] [--jobs N] [--compare DIR]\n"
                 "  WildWorldBuild compile --ndsrecomp DIR --recomp-ui DIR --pack DIR --work DIR\n"
                 "      --out DIR [--jobs N]\n");
    return 2;
}
