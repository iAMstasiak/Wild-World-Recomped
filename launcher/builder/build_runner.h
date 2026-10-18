// Compiling the game (WildWorldBuild): ndsrecomp's runner, built with the
// compiler pack (w64devkit's GCC, CMake, Ninja and SDL3) from the banks the
// recompile step wrote, with the settings worked out on the developer's PC:
// -O1 for the game's banks, no compiler cache, FreeBIOS only.
#pragma once

#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <deque>
#include <filesystem>
#include <string>
#include <thread>
#include <vector>

#include "process.h"

#ifndef _WIN32
#include <unistd.h>
#endif

namespace wwbuild {

struct BuildOptions {
    std::filesystem::path work;       // recomp\ and gen\ from the recompile step; runner\ and logs\ go here
    std::filesystem::path ndsrecomp;  // ndsrecomp's folder (its runner\ is built)
    std::filesystem::path recomp_ui;  // recomp-ui's folder
    std::filesystem::path pack;       // the compiler pack: w64devkit, cmake, ninja and SDL3
    std::filesystem::path out;        // where the game goes
    std::string rom_sha1;
    int jobs = 0;                     // compiles at once; 0 to choose from the memory
};

#ifdef _WIN32
constexpr const char* kExe = ".exe";
constexpr char kPathSeparator = ';';
#else
constexpr const char* kExe = "";
constexpr char kPathSeparator = ':';
#endif

// The PC's memory in MB.
inline uint64_t memory_mb() {
#ifdef _WIN32
    MEMORYSTATUSEX status{};
    status.dwLength = sizeof(status);
    if (!GlobalMemoryStatusEx(&status)) return 0;
    return status.ullTotalPhys >> 20;
#else
    const long pages = sysconf(_SC_PHYS_PAGES), size = sysconf(_SC_PAGE_SIZE);
    return pages > 0 && size > 0 ? (uint64_t(pages) * uint64_t(size)) >> 20 : 0;
#endif
}

// One compile per 4 GB (the biggest bank files take about that at once),
// and no more than the processor's threads.
inline int compile_jobs() {
    const uint64_t mb = memory_mb();
    const int threads = static_cast<int>(std::max(1u, std::thread::hardware_concurrency()));
    if (mb == 0) return std::min(4, threads);
    return std::max(1, std::min(threads, static_cast<int>((mb + 1024) / 4096)));
}

// SDL3's CMake config in the pack: the 64-bit MinGW one in SDL3-devel's
// layout (x86_64-w64-mingw32\lib\cmake\SDL3), or the first one found.
inline std::filesystem::path find_sdl3_config(const std::filesystem::path& root) {
    namespace fs = std::filesystem;
    std::error_code ec;
    fs::path found;
    for (fs::recursive_directory_iterator it(root, ec), end; !ec && it != end; it.increment(ec)) {
        const fs::path dir = it->path().parent_path();
        if (it->path().filename() != "SDL3Config.cmake" || dir.filename() != "SDL3" ||
            dir.parent_path().filename() != "cmake")
            continue;
        if (dir.u8string().find("x86_64") != std::string::npos) return dir;
        if (found.empty()) found = dir;
    }
    return found;
}

// A tool in the pack: the file with that name nearest the top of root (so a
// zip unpacked into a folder of its own inside root works too), or empty.
inline std::filesystem::path find_tool(const std::filesystem::path& root, const std::string& name) {
    namespace fs = std::filesystem;
    std::error_code ec;
    fs::path found;
    int depth = 1 << 30;
    for (fs::recursive_directory_iterator it(root, ec), end; !ec && it != end; it.increment(ec))
        if (it.depth() < depth && it->path().filename() == name) {
            found = it->path();
            depth = it.depth();
        }
    return found;
}

// The pack's tools first on PATH and nothing else of the player's (another
// GCC or MSYS2 there could get picked up instead), and no compiler settings
// left in the environment.
inline void use_pack_environment(const std::vector<std::filesystem::path>& bins) {
    std::string path;
    for (const auto& dir : bins) path += dir.u8string() + kPathSeparator;
    const char* cleared[] = {"CC", "CXX", "CFLAGS", "CXXFLAGS", "CPPFLAGS", "LDFLAGS", "CPATH",
                             "C_INCLUDE_PATH", "CPLUS_INCLUDE_PATH", "LIBRARY_PATH", "CMAKE_GENERATOR",
                             "CMAKE_TOOLCHAIN_FILE", "MAKEFLAGS"};
#ifdef _WIN32
    wchar_t windows[MAX_PATH] = L"C:\\Windows";
    GetSystemWindowsDirectoryW(windows, MAX_PATH);
    const std::wstring w = windows;
    const std::wstring full = widen(path) + w + L"\\System32;" + w;
    SetEnvironmentVariableW(L"PATH", full.c_str());
    SetEnvironmentVariableW(L"NINJA_STATUS", L"[%f/%t] ");
    for (const char* name : cleared) SetEnvironmentVariableW(widen(name).c_str(), nullptr);
#else
    setenv("PATH", (path + "/usr/bin:/bin").c_str(), 1);
    setenv("NINJA_STATUS", "[%f/%t] ", 1);
    for (const char* name : cleared) unsetenv(name);
#endif
}

// "[12/345] Building C object .../acww_arm9_03.c.obj" -> 12, 345 and
// "acww_arm9_03.c"; false for any other line.
inline bool ninja_status(const std::string& line, int* done, int* total, std::string* what) {
    if (line.empty() || line[0] != '[') return false;
    const size_t slash = line.find('/'), close = line.find(']');
    if (slash == std::string::npos || close == std::string::npos || slash > close) return false;
    const std::string a = line.substr(1, slash - 1), b = line.substr(slash + 1, close - slash - 1);
    if (a.empty() || b.empty() || a.find_first_not_of("0123456789") != std::string::npos ||
        b.find_first_not_of("0123456789") != std::string::npos)
        return false;
    *done = std::atoi(a.c_str());
    *total = std::atoi(b.c_str());
    *what = close + 2 <= line.size() ? line.substr(close + 2) : "";
    const size_t object = what->find(" object ");
    if (what->rfind("Building ", 0) == 0 && object != std::string::npos) {
        std::string file = what->substr(object + 8);
        file = file.substr(file.find_last_of("/\\") + 1);
        for (const std::string ext : {".obj", ".o"})
            if (file.size() > ext.size() && file.compare(file.size() - ext.size(), ext.size(), ext) == 0) {
                file.resize(file.size() - ext.size());
                break;
            }
        *what = file;
    }
    return true;
}

// The lines worth showing when something fails.
inline bool error_line(const std::string& line) {
    return line.find("error") != std::string::npos || line.find("Error") != std::string::npos ||
           line.rfind("FAILED:", 0) == 0 || line.find("No space left") != std::string::npos;
}

// Configures and builds the runner, printing "[progress] N/M file" as Ninja
// goes, then copies the game (and SDL3.dll) into o.out. False and *error
// (with the log's error lines in *details) when anything failed.
inline bool build_runner(const BuildOptions& o, std::string* error, std::vector<std::string>* details) {
    namespace fs = std::filesystem;
    std::error_code ec;
    const fs::path build = o.work / "runner", logs = o.work / "logs";
    fs::create_directories(logs, ec);
    const fs::path sdl3 = find_sdl3_config(o.pack / "SDL3");
    // w64devkit comes with CMake and Ninja; separate cmake and ninja folders are a fallback.
    const fs::path gcc = find_tool(o.pack / "w64devkit", std::string("gcc") + kExe);
    fs::path cmake = find_tool(o.pack / "w64devkit", std::string("cmake") + kExe);
    if (cmake.empty()) cmake = find_tool(o.pack / "cmake", std::string("cmake") + kExe);
    fs::path ninja = find_tool(o.pack / "w64devkit", std::string("ninja") + kExe);
    if (ninja.empty()) ninja = find_tool(o.pack / "ninja", std::string("ninja") + kExe);
    const char* missing = gcc.empty() ? "GCC (in w64devkit)" : cmake.empty() ? "CMake"
                        : ninja.empty() ? "Ninja" : nullptr;
    if (missing) {
        *error = "the compiler pack in " + o.pack.u8string() + " has no " + missing;
        return false;
    }
    if (sdl3.empty()) {
        *error = "the compiler pack has no SDL3 in " + (o.pack / "SDL3").u8string();
        return false;
    }
    if (!fs::exists(o.work / "recomp", ec) || !fs::exists(o.work / "gen" / "freebios_arm9.c", ec)) {
        *error = "the game hasn't been recompiled into " + o.work.u8string() + " yet";
        return false;
    }
    use_pack_environment({gcc.parent_path(), cmake.parent_path(), ninja.parent_path()});
    const int jobs = o.jobs > 0 ? o.jobs : compile_jobs();
    std::printf("compiling %d at a time (%llu MB of memory)\n", jobs,
                static_cast<unsigned long long>(memory_mb()));
    std::fflush(stdout);

    std::deque<std::string> errors;
    const auto collect = [&](const std::string& line) {
        if (!error_line(line)) return;
        errors.push_back(line);
        if (errors.size() > 12) errors.pop_front();
    };
    const auto fail = [&](const std::string& what, const fs::path& log) {
        *error = what + "; the full log is " + log.u8string();
        details->assign(errors.begin(), errors.end());
        return false;
    };
    const std::vector<std::string> configure = {
        cmake.u8string(), "-G", "Ninja", "-S", (o.ndsrecomp / "runner").generic_u8string(),
        "-B", build.generic_u8string(),
        "-DCMAKE_BUILD_TYPE=Release",
        "-DCMAKE_C_COMPILER=" + gcc.generic_u8string(),
        "-DCMAKE_CXX_COMPILER=" + (gcc.parent_path() / (std::string("g++") + kExe)).generic_u8string(),
        "-DCMAKE_MAKE_PROGRAM=" + ninja.generic_u8string(),
        "-DSDL3_DIR=" + sdl3.generic_u8string(),
        "-DNDSRECOMP_COMPILER_CACHE=OFF",
        "-DNDSRECOMP_COMPILE_JOBS=" + std::to_string(jobs),
        "-DNDS_SDL_BACKEND=SDL3",
        "-DNDS_ENABLE_COMPUTE_RENDERER=ON",
        "-DNDS_BOOTSTRAP_FIRMWARE=ON",
        "-DNDS_RECOMP_UI_ROOT=" + o.recomp_ui.generic_u8string(),
        "-DNDS_GENERATED_DIR=" + (o.work / "gen").generic_u8string(),
        "-DNDS_TITLE_BANK_DIR=" + (o.work / "recomp").generic_u8string(),
        "-DNDS_TITLE_ROM_SHA1=" + o.rom_sha1,
        "-DNDS_TITLE_BANK_OPT=-O1"};
    const fs::path configure_log = logs / "configure.log";
    std::printf("[step] configure\n");
    std::fflush(stdout);
    if (run_process_lines(configure, configure_log.u8string(), collect) != 0) {
        // A build folder from another place or another pack: start it again.
        errors.clear();
        fs::remove_all(build, ec);
        if (run_process_lines(configure, configure_log.u8string(), collect) != 0)
            return fail("setting up the compile failed", configure_log);
    }

    errors.clear();
    const fs::path compile_log = logs / "compile.log";
    std::printf("[step] compile\n");
    std::fflush(stdout);
    int last = -1;
    const auto progress = [&](const std::string& line) {
        int done = 0, total = 0;
        std::string what;
        if (!ninja_status(line, &done, &total, &what)) {
            collect(line);
            return;
        }
        // Ninja checks CMake's file lists first, as a little build of its own.
        if (done == 0 || done == last || what.rfind("Re-checking", 0) == 0) return;
        last = done;
        std::printf("[progress] %d/%d %s\n", done, total, what.c_str());
        std::fflush(stdout);
    };
    if (run_process_lines({cmake.u8string(), "--build", build.u8string(), "--target", "nds_runner"},
                          compile_log.u8string(), progress) != 0)
        return fail("compiling the game failed", compile_log);

    std::printf("[step] install\n");
    std::fflush(stdout);
    const std::string exe = std::string("nds_runner") + kExe;
    fs::create_directories(o.out, ec);
    if (!fs::copy_file(build / exe, o.out / exe, fs::copy_options::overwrite_existing, ec)) {
        *error = "can't copy the game into " + o.out.u8string() + " (is it still running?)";
        return false;
    }
#ifdef _WIN32
    // SDL3_DIR is <SDL3>\lib\cmake\SDL3, and the DLL is in <SDL3>\bin.
    const fs::path dll = sdl3.parent_path().parent_path().parent_path() / "bin" / "SDL3.dll";
    if (!fs::copy_file(dll, o.out / "SDL3.dll", fs::copy_options::overwrite_existing, ec)) {
        *error = "can't copy " + dll.u8string() + " into " + o.out.u8string();
        return false;
    }
#endif
    return true;
}

}  // namespace wwbuild
