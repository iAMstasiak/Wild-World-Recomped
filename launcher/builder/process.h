// Running another program and waiting for it (WildWorldBuild): the
// recompiler and the compiler, with their output sent to a log file.
#pragma once

#include <fstream>
#include <functional>
#include <mutex>
#include <string>
#include <vector>

#ifdef _WIN32
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#else
#include <fcntl.h>
#include <spawn.h>
#include <sys/wait.h>
#include <unistd.h>
extern char** environ;
#endif

namespace wwbuild {

#ifdef _WIN32
inline std::wstring widen(const std::string& s) {
    if (s.empty()) return L"";
    const int n = MultiByteToWideChar(CP_UTF8, 0, s.c_str(), static_cast<int>(s.size()), nullptr, 0);
    std::wstring out(static_cast<size_t>(n), L'\0');
    MultiByteToWideChar(CP_UTF8, 0, s.c_str(), static_cast<int>(s.size()), out.data(), n);
    return out;
}

// One argument as the program's C runtime will split it back out.
inline std::wstring quote_arg(const std::wstring& arg) {
    if (!arg.empty() && arg.find_first_of(L" \t\"") == std::wstring::npos) return arg;
    std::wstring out = L"\"";
    size_t slashes = 0;
    for (wchar_t c : arg) {
        if (c == L'\\') {
            ++slashes;
            continue;
        }
        out.append(c == L'"' ? slashes * 2 + 1 : slashes, L'\\');
        slashes = 0;
        out += c;
    }
    out.append(slashes * 2, L'\\');
    return out + L"\"";
}
#endif

// Runs args[0] with the rest as its arguments, its output (stdout and
// stderr) going to log_path, and waits for it. Its exit code, or -1 if it
// couldn't be started. Safe to call from several threads at once.
inline int run_process(const std::vector<std::string>& args, const std::string& log_path) {
    static std::mutex starting;   // so no child inherits another job's log file
#ifdef _WIN32
    std::wstring command;
    for (const std::string& a : args) command += (command.empty() ? L"" : L" ") + quote_arg(widen(a));
    std::vector<wchar_t> line(command.begin(), command.end());
    line.push_back(L'\0');
    PROCESS_INFORMATION pi{};
    {
        std::lock_guard<std::mutex> lock(starting);
        SECURITY_ATTRIBUTES sa{sizeof(sa), nullptr, TRUE};
        HANDLE log = CreateFileW(widen(log_path).c_str(), GENERIC_WRITE, FILE_SHARE_READ, &sa,
                                 CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
        if (log == INVALID_HANDLE_VALUE) return -1;
        STARTUPINFOW si{};
        si.cb = sizeof(si);
        si.dwFlags = STARTF_USESTDHANDLES;
        si.hStdInput = GetStdHandle(STD_INPUT_HANDLE);
        si.hStdOutput = log;
        si.hStdError = log;
        const BOOL ok = CreateProcessW(nullptr, line.data(), nullptr, nullptr, TRUE, CREATE_NO_WINDOW,
                                       nullptr, nullptr, &si, &pi);
        CloseHandle(log);
        if (!ok) return -1;
    }
    WaitForSingleObject(pi.hProcess, INFINITE);
    DWORD code = 1;
    GetExitCodeProcess(pi.hProcess, &code);
    CloseHandle(pi.hThread);
    CloseHandle(pi.hProcess);
    return static_cast<int>(code);
#else
    std::vector<char*> argv;
    for (const std::string& a : args) argv.push_back(const_cast<char*>(a.c_str()));
    argv.push_back(nullptr);
    pid_t pid = 0;
    {
        std::lock_guard<std::mutex> lock(starting);
        posix_spawn_file_actions_t actions;
        posix_spawn_file_actions_init(&actions);
        posix_spawn_file_actions_addopen(&actions, 1, log_path.c_str(), O_WRONLY | O_CREAT | O_TRUNC, 0644);
        posix_spawn_file_actions_adddup2(&actions, 1, 2);
        const int err = posix_spawn(&pid, argv[0], &actions, nullptr, argv.data(), environ);
        posix_spawn_file_actions_destroy(&actions);
        if (err != 0) return -1;
    }
    int status = 0;
    if (waitpid(pid, &status, 0) < 0) return -1;
    return WIFEXITED(status) ? WEXITSTATUS(status) : -1;
#endif
}

// The same, but the output also comes back a line at a time while the
// program runs (for the compiler's progress).
inline int run_process_lines(const std::vector<std::string>& args, const std::string& log_path,
                             const std::function<void(const std::string&)>& on_line) {
    std::ofstream log(log_path, std::ios::binary | std::ios::trunc);
    std::string pending;
    const auto take = [&](const char* data, size_t n) {
        log.write(data, static_cast<std::streamsize>(n));
        for (size_t i = 0; i < n; ++i) {
            if (data[i] == '\n' || data[i] == '\r') {
                if (!pending.empty()) on_line(pending);
                pending.clear();
            } else {
                pending += data[i];
            }
        }
    };
#ifdef _WIN32
    std::wstring command;
    for (const std::string& a : args) command += (command.empty() ? L"" : L" ") + quote_arg(widen(a));
    std::vector<wchar_t> line(command.begin(), command.end());
    line.push_back(L'\0');
    PROCESS_INFORMATION pi{};
    HANDLE read_end = nullptr, write_end = nullptr;
    {
        static std::mutex starting;
        std::lock_guard<std::mutex> lock(starting);
        SECURITY_ATTRIBUTES sa{sizeof(sa), nullptr, TRUE};
        if (!CreatePipe(&read_end, &write_end, &sa, 0)) return -1;
        SetHandleInformation(read_end, HANDLE_FLAG_INHERIT, 0);
        STARTUPINFOW si{};
        si.cb = sizeof(si);
        si.dwFlags = STARTF_USESTDHANDLES;
        si.hStdInput = GetStdHandle(STD_INPUT_HANDLE);
        si.hStdOutput = write_end;
        si.hStdError = write_end;
        const BOOL ok = CreateProcessW(nullptr, line.data(), nullptr, nullptr, TRUE, CREATE_NO_WINDOW,
                                       nullptr, nullptr, &si, &pi);
        CloseHandle(write_end);
        if (!ok) {
            CloseHandle(read_end);
            return -1;
        }
    }
    char buf[4096];
    DWORD got = 0;
    while (ReadFile(read_end, buf, sizeof(buf), &got, nullptr) && got > 0) take(buf, got);
    CloseHandle(read_end);
    WaitForSingleObject(pi.hProcess, INFINITE);
    DWORD code = 1;
    GetExitCodeProcess(pi.hProcess, &code);
    CloseHandle(pi.hThread);
    CloseHandle(pi.hProcess);
    if (!pending.empty()) on_line(pending);
    return static_cast<int>(code);
#else
    int fds[2];
    if (pipe(fds) != 0) return -1;
    std::vector<char*> argv;
    for (const std::string& a : args) argv.push_back(const_cast<char*>(a.c_str()));
    argv.push_back(nullptr);
    posix_spawn_file_actions_t actions;
    posix_spawn_file_actions_init(&actions);
    posix_spawn_file_actions_adddup2(&actions, fds[1], 1);
    posix_spawn_file_actions_adddup2(&actions, fds[1], 2);
    posix_spawn_file_actions_addclose(&actions, fds[0]);
    pid_t pid = 0;
    const int err = posix_spawn(&pid, argv[0], &actions, nullptr, argv.data(), environ);
    posix_spawn_file_actions_destroy(&actions);
    close(fds[1]);
    if (err != 0) {
        close(fds[0]);
        return -1;
    }
    char buf[4096];
    ssize_t got = 0;
    while ((got = read(fds[0], buf, sizeof(buf))) > 0) take(buf, static_cast<size_t>(got));
    close(fds[0]);
    int status = 0;
    if (waitpid(pid, &status, 0) < 0) return -1;
    if (!pending.empty()) on_line(pending);
    return WIFEXITED(status) ? WEXITSTATUS(status) : -1;
#endif
}

}  // namespace wwbuild
