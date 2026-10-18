// Getting the compiler pack (WildWorldBuild): w64devkit (GCC, with CMake and
// Ninja) and SDL3's MinGW files, from the projects' own GitHub releases. Each
// download is checked against the SHA-256 it had when this version was made,
// then unpacked into the pack folder build_runner.h compiles with.
#pragma once

#include <cstdint>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <functional>
#include <string>
#include <vector>

#include "files.h"
#include "process.h"
#include "sha256.h"

#ifdef _WIN32
#include <winhttp.h>
#endif

namespace wwbuild {

struct PackFile {
    const char* name;     // as its project names it
    const char* url;
    const char* sha256;
    uint64_t size;
};

// The versions Wild World Recomped was tested with.
constexpr const char* kPackVersion = "w64devkit 2.10.1, SDL 3.4.18";
inline const std::vector<PackFile>& pack_files() {
    static const std::vector<PackFile> files = {
        {"w64devkit-x64-2.10.1.7z.exe",
         "https://github.com/skeeto/w64devkit/releases/download/v2.10.1/w64devkit-x64-2.10.1.7z.exe",
         "add1edf984ce4d473cfeb7c52e0ab38db73a855bba6c7f564d5e16648eb2896a", 67263552},
        {"SDL3-devel-3.4.18-mingw.zip",
         "https://github.com/libsdl-org/SDL/releases/download/release-3.4.18/SDL3-devel-3.4.18-mingw.zip",
         "cd98158c8d025a816f430a600b4e9526524e6219ee884ec72bd498b80fd3bf58", 5472877},
    };
    return files;
}

// True when pack.txt in the folder says this version's files are unpacked there.
inline bool pack_ready(const std::filesystem::path& pack) {
    const std::vector<uint8_t> text = read_file(pack / "pack.txt");
    return std::string(text.begin(), text.end()) == std::string(kPackVersion) + "\n";
}

#ifdef _WIN32
// Downloads url into path, calling on_bytes with the total so far. False and
// *error when it fails.
inline bool download(const std::string& url, const std::filesystem::path& path,
                     const std::function<void(uint64_t)>& on_bytes, std::string* error) {
    struct Handle {
        HINTERNET h = nullptr;
        ~Handle() { if (h) WinHttpCloseHandle(h); }
    } session, connection, request;
    const std::wstring wide = widen(url);
    URL_COMPONENTS parts{};
    parts.dwStructSize = sizeof(parts);
    parts.dwHostNameLength = parts.dwUrlPathLength = parts.dwExtraInfoLength = static_cast<DWORD>(-1);
    if (!WinHttpCrackUrl(wide.c_str(), 0, 0, &parts)) {
        *error = "can't read the address " + url;
        return false;
    }
    const std::wstring host(parts.lpszHostName, parts.dwHostNameLength);
    const std::wstring target(parts.lpszUrlPath, parts.dwUrlPathLength + parts.dwExtraInfoLength);
#ifdef WINHTTP_ACCESS_TYPE_AUTOMATIC_PROXY
    session.h = WinHttpOpen(L"WildWorldBuild", WINHTTP_ACCESS_TYPE_AUTOMATIC_PROXY, WINHTTP_NO_PROXY_NAME,
                            WINHTTP_NO_PROXY_BYPASS, 0);
#endif
    if (!session.h)
        session.h = WinHttpOpen(L"WildWorldBuild", WINHTTP_ACCESS_TYPE_DEFAULT_PROXY, WINHTTP_NO_PROXY_NAME,
                                WINHTTP_NO_PROXY_BYPASS, 0);
    if (session.h) WinHttpSetTimeouts(session.h, 0, 60000, 60000, 60000);
    if (session.h) connection.h = WinHttpConnect(session.h, host.c_str(), parts.nPort, 0);
    if (connection.h)
        request.h = WinHttpOpenRequest(connection.h, L"GET", target.c_str(), nullptr, WINHTTP_NO_REFERER,
                                       WINHTTP_DEFAULT_ACCEPT_TYPES,
                                       parts.nScheme == INTERNET_SCHEME_HTTPS ? WINHTTP_FLAG_SECURE : 0);
    if (!request.h ||
        !WinHttpSendRequest(request.h, WINHTTP_NO_ADDITIONAL_HEADERS, 0, WINHTTP_NO_REQUEST_DATA, 0, 0, 0) ||
        !WinHttpReceiveResponse(request.h, nullptr)) {
        *error = "can't connect to " + std::string(host.begin(), host.end()) + " (Windows error " +
                 std::to_string(GetLastError()) + "); check the internet connection";
        return false;
    }
    DWORD status = 0, size = sizeof(status);
    WinHttpQueryHeaders(request.h, WINHTTP_QUERY_STATUS_CODE | WINHTTP_QUERY_FLAG_NUMBER,
                        WINHTTP_HEADER_NAME_BY_INDEX, &status, &size, WINHTTP_NO_HEADER_INDEX);
    if (status != 200) {
        *error = "the download of " + url + " was refused (HTTP " + std::to_string(status) + ")";
        return false;
    }
    std::ofstream out(path, std::ios::binary | std::ios::trunc);
    std::vector<char> buffer(1 << 16);
    uint64_t got = 0;
    for (;;) {
        DWORD n = 0;
        if (!WinHttpReadData(request.h, buffer.data(), static_cast<DWORD>(buffer.size()), &n)) {
            *error = "the download of " + url + " stopped (Windows error " + std::to_string(GetLastError()) +
                     "); try again";
            return false;
        }
        if (n == 0) break;
        out.write(buffer.data(), n);
        got += n;
        on_bytes(got);
    }
    if (!out) {
        *error = "can't write " + path.u8string();
        return false;
    }
    return true;
}
#endif

// Gets each file of the pack (from the folder `from` when it has it there,
// else from its release), checks it, and unpacks it into pack, printing
// "[step] download|unpack" and "[progress] N/M MB". False and *error when
// anything failed.
inline bool get_pack(const std::filesystem::path& pack, const std::filesystem::path& from, std::string* error) {
    namespace fs = std::filesystem;
    std::error_code ec;
    const fs::path downloads = pack / "downloads", logs = pack / "logs";
    fs::create_directories(downloads, ec);
    fs::create_directories(logs, ec);
    fs::remove(pack / "pack.txt", ec);

    std::printf("[step] download\n");
    std::fflush(stdout);
    uint64_t total = 0, before = 0;
    for (const PackFile& f : pack_files()) total += f.size;
    int last_mb = -1;
    const int total_mb = static_cast<int>((total + (1 << 20) - 1) >> 20);
    const auto show = [&](uint64_t done) {
        const int mb = done >= total ? total_mb : static_cast<int>(done >> 20);
        if (mb == last_mb) return;
        last_mb = mb;
        std::printf("[progress] %d/%d MB\n", mb, total_mb);
        std::fflush(stdout);
    };
    std::vector<fs::path> got;
    for (const PackFile& f : pack_files()) {
        const fs::path file = downloads / f.name;
        const fs::path offline = from.empty() ? fs::path() : from / f.name;
        const auto good = [&](const fs::path& p) {
            return fs::exists(p, ec) && fs::file_size(p, ec) == f.size && sha256_hex(read_file(p)) == f.sha256;
        };
        if (good(file)) {
            // Downloaded by an earlier try.
        } else if (!offline.empty() && good(offline)) {
            fs::copy_file(offline, file, fs::copy_options::overwrite_existing, ec);
        } else {
#ifdef _WIN32
            const fs::path part = downloads / (std::string(f.name) + ".part");
            if (!download(f.url, part, [&](uint64_t n) { show(before + n); }, error)) return false;
            fs::remove(file, ec);
            fs::rename(part, file, ec);
            if (!good(file)) {
                *error = std::string("the download of ") + f.name + " doesn't match the file this version "
                         "was made with; try again";
                fs::remove(file, ec);
                return false;
            }
#else
            *error = std::string("put ") + f.name + " in the folder given with --from";
            return false;
#endif
        }
        before += f.size;
        show(before);
        got.push_back(file);
    }

    std::printf("[step] unpack\n");
    std::fflush(stdout);
#ifdef _WIN32
    // w64devkit's installer unpacks itself into <pack>\w64devkit.
    fs::remove_all(pack / "w64devkit", ec);
    if (run_process({got[0].u8string(), "-o" + pack.u8string(), "-y"}, (logs / "w64devkit.log").u8string()) != 0 ||
        !fs::exists(pack / "w64devkit" / "bin" / "gcc.exe", ec)) {
        *error = "unpacking w64devkit into " + pack.u8string() + " failed";
        return false;
    }
    // Windows' own tar unpacks zips; SDL3's goes in <pack>\SDL3.
    wchar_t windows[MAX_PATH] = L"C:\\Windows";
    GetSystemWindowsDirectoryW(windows, MAX_PATH);
    const fs::path tar = fs::path(windows) / "System32" / "tar.exe";
    fs::remove_all(pack / "SDL3", ec);
    fs::create_directories(pack / "SDL3", ec);
    if (run_process({tar.u8string(), "-xf", got[1].u8string(), "-C", (pack / "SDL3").u8string()},
                    (logs / "sdl3.log").u8string()) != 0) {
        *error = "unpacking SDL3 into " + pack.u8string() + " failed";
        return false;
    }
#else
    *error = "unpacking the pack only works on Windows";
    return false;
#endif
    const std::string version = std::string(kPackVersion) + "\n";
    write_file(pack / "pack.txt", std::vector<uint8_t>(version.begin(), version.end()));
    fs::remove_all(downloads, ec);
    return true;
}

}  // namespace wwbuild
