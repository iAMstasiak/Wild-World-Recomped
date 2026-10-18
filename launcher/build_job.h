// Building the game from the launcher (setup_page.h): runs WildWorldBuild's
// pack and build in the background and turns what they print into one
// progress bar. Cancelling, or closing the launcher, stops the build and
// everything it started; the next try carries on from where it stopped.
#pragma once

#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <map>
#include <mutex>
#include <string>
#include <system_error>
#include <thread>
#include <vector>

#include "builder/process.h"
#include "layout.h"

namespace acww {

struct BuildStatus {
    enum State { kIdle, kRunning, kFailed, kDone };
    State state = kIdle;
    std::string phase;             // what it's doing, for the line above the bar
    std::string detail;            // the file or the amount, under the bar
    float fraction = 0.0f;         // of the whole setup
    double elapsed = 0.0;          // seconds since Set Up
    double left = -1.0;            // seconds still to go; below 0 when not known yet
    std::string error;             // what failed
    std::vector<std::string> log;  // the lines from the log that say why
    std::string note;              // after a stop
};

// What the tools print, turned into a BuildStatus.
class BuildProgress {
public:
    explicit BuildProgress(std::filesystem::path work = {}) : work_(std::move(work)) {}

    // Each tool's share of the bar, and each step's within it.
    void begin_tool(bool pack) { pack_ = pack; }

    void line(const std::string& text, BuildStatus* s) {
        const auto rest = [&](const char* prefix) { return text.substr(std::char_traits<char>::length(prefix)); };
        if (text.rfind("[step] ", 0) == 0) step(rest("[step] "), s);
        else if (text.rfind("[progress] ", 0) == 0) progress(rest("[progress] "), s);
        else if (text.rfind("[error] ", 0) == 0) s->error = rest("[error] ");
        else if (text.rfind("[log] ", 0) == 0) {
            s->log.push_back(rest("[log] "));
            if (s->log.size() > 12) s->log.erase(s->log.begin());
        } else if (text.rfind("[done]", 0) == 0) {
            s->fraction = pack_ ? kPackEnd : 1.0f;
            s->left = -1.0;
        } else {
            tail_.push_back(text);   // what it said last, in case it stops without an [error]
            if (tail_.size() > 8) tail_.erase(tail_.begin());
        }
    }

    const std::vector<std::string>& tail() const { return tail_; }

    // Seconds since the compile started, for the estimate. The small files
    // finish first, so it waits for a quarter of the compile: a guess before
    // the big ones are done comes out far too long.
    void tick(double compile_seconds, BuildStatus* s) const {
        if (step_ != "compile" || compile_fraction_ < 0.25f || compile_seconds < 60.0) return;
        s->left = compile_seconds * (1.0 - compile_fraction_) / compile_fraction_;
    }

    bool compiling() const { return step_ == "compile"; }

private:
    static constexpr float kPackEnd = 0.05f;
    struct Range { const char* name; const char* phase; float from, to; };

    static const Range* range(const std::string& name) {
        static const Range ranges[] = {
            {"download", "Downloading the compiler", 0.0f, 0.045f},
            {"unpack", "Unpacking the compiler", 0.045f, kPackEnd},
            {"recompile", "Recompiling the game into C", kPackEnd, 0.09f},
            {"configure", "Getting the compile ready", 0.09f, 0.11f},
            {"compile", "Compiling the game", 0.11f, 0.995f},
            {"install", "Putting the game in place", 0.995f, 1.0f},
        };
        for (const Range& r : ranges)
            if (name == r.name) return &r;
        return nullptr;
    }

    void step(const std::string& name, BuildStatus* s) {
        step_ = name;
        const Range* r = range(name);
        if (!r) return;
        s->phase = r->phase;
        s->detail.clear();
        s->fraction = std::max(s->fraction, r->from);
        if (name == "compile") load_sizes();
    }

    // The game's C files and their sizes: the biggest take longest to compile.
    void load_sizes() {
        namespace fs = std::filesystem;
        sizes_.clear();
        bank_bytes_ = 0;
        std::error_code ec;
        for (const char* dir : {"recomp", "gen"})
            for (const auto& item : fs::directory_iterator(work_ / dir, ec))
                if (item.path().extension() == ".c") {
                    const uint64_t size = item.file_size(ec);
                    sizes_[item.path().filename().u8string()] = size;
                    bank_bytes_ += size;
                }
        done_weight_ = 0.0;
        weighted_ = -1;
        compile_fraction_ = 0.0f;
    }

    void progress(const std::string& text, BuildStatus* s) {
        const size_t slash = text.find('/'), space = text.find(' ', slash);
        if (slash == std::string::npos) return;
        const double n = std::atof(text.substr(0, slash).c_str());
        const double m = std::atof(text.substr(slash + 1, space - slash - 1).c_str());
        const std::string what = space == std::string::npos ? "" : text.substr(space + 1);
        if (m <= 0) return;
        const Range* r = range(step_);
        if (!r) return;
        double f = n / m;
        if (step_ == "download") {
            s->detail = text.substr(0, space) + " MB";   // "12/70 MB"
            s->detail.replace(s->detail.find('/'), 1, " of ");
        } else if (step_ == "recompile") {
            s->detail = what.substr(0, what.find(' '));   // the bank, without its time
        } else if (step_ == "compile") {
            s->detail = what;
            // A full build is weighted by the size of each file; a rebuild of
            // a few files just counts them.
            if (weighted_ < 0) weighted_ = m >= static_cast<double>(sizes_.size()) ? 1 : 0;
            if (weighted_) {
                const auto it = sizes_.find(what);
                done_weight_ += it != sizes_.end() ? static_cast<double>(it->second) : kOtherWeight;
                const double total = static_cast<double>(bank_bytes_) +
                                     std::max(0.0, m - static_cast<double>(sizes_.size())) * kOtherWeight;
                f = std::min(1.0, done_weight_ / std::max(1.0, total));
            }
            compile_fraction_ = static_cast<float>(f);
        }
        s->fraction = std::max(s->fraction, r->from + static_cast<float>(f) * (r->to - r->from));
    }

    // A compile step that isn't one of the game's C files (the runner's own
    // code, a link), counted as about as long as a 1 MB C file.
    static constexpr double kOtherWeight = 1024.0 * 1024.0;

    std::filesystem::path work_;
    bool pack_ = false;
    std::string step_;
    std::map<std::string, uint64_t> sizes_;
    uint64_t bank_bytes_ = 0;
    double done_weight_ = 0.0;
    int weighted_ = -1;
    float compile_fraction_ = 0.0f;
    std::vector<std::string> tail_;
};

#ifdef _WIN32
class BuildJob {
public:
    ~BuildJob() {
        cancel();
        if (thread_.joinable()) thread_.join();
        if (job_) CloseHandle(job_);
    }

    bool running() const { return running_; }

    void start(const Layout& layout, const std::string& rom) {
        if (running_) return;
        if (thread_.joinable()) thread_.join();
        {
            std::lock_guard<std::mutex> lock(mutex_);
            status_ = BuildStatus();
            status_.state = BuildStatus::kRunning;
            status_.phase = "Starting";
        }
        if (!job_) {
            // Everything the build starts goes in this job, and goes when it does.
            job_ = CreateJobObjectW(nullptr, nullptr);
            JOBOBJECT_EXTENDED_LIMIT_INFORMATION limits{};
            limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
            if (job_) SetInformationJobObject(job_, JobObjectExtendedLimitInformation, &limits, sizeof(limits));
        }
        cancelled_ = false;
        running_ = true;
        started_ = std::chrono::steady_clock::now();
        thread_ = std::thread([this, layout, rom]() { run(layout, rom); });
    }

    void cancel() {
        if (!running_) return;
        cancelled_ = true;
        if (job_) TerminateJobObject(job_, 1);
    }

    BuildStatus status() {
        std::lock_guard<std::mutex> lock(mutex_);
        BuildStatus s = status_;
        if (s.state == BuildStatus::kRunning) {
            const auto now = std::chrono::steady_clock::now();
            s.elapsed = std::chrono::duration<double>(now - started_).count();
            if (progress_.compiling())
                progress_.tick(std::chrono::duration<double>(now - compile_started_).count(), &s);
        }
        return s;
    }

private:
    void run(Layout l, std::string rom) {
        namespace fs = std::filesystem;
        std::error_code ec;
        fs::create_directories(l.work / "logs", ec);
        std::ofstream log(l.work / "logs" / "setup.log", std::ios::binary | std::ios::trunc);
        {
            std::lock_guard<std::mutex> lock(mutex_);
            progress_ = BuildProgress(l.work);
        }
        const auto u8 = [](const fs::path& p) { return p.u8string(); };
        bool ok = tool({u8(l.builder), "pack", "--pack", u8(l.pack)}, true, log);
        if (ok)
            ok = tool({u8(l.builder), "build", "--rom", rom, "--seeds", u8(l.seeds), "--recompiler",
                       u8(l.recompiler), "--ndsrecomp", u8(l.ndsrecomp), "--recomp-ui", u8(l.recomp_ui),
                       "--pack", u8(l.pack), "--work", u8(l.work), "--out", u8(l.game)},
                      false, log);
        std::lock_guard<std::mutex> lock(mutex_);
        if (cancelled_) {
            status_.state = BuildStatus::kIdle;
            status_.note = "Stopped. Set Up carries on from where it got to.";
        } else if (ok) {
            status_.state = BuildStatus::kDone;
            status_.fraction = 1.0f;
        } else {
            status_.state = BuildStatus::kFailed;
            if (status_.error.empty()) {
                status_.error = "WildWorldBuild stopped without saying why. The last thing it printed is below";
                status_.log = progress_.tail();
            }
        }
        running_ = false;
    }

    // Runs one WildWorldBuild command, reading what it prints as it goes.
    bool tool(const std::vector<std::string>& args, bool pack, std::ofstream& log) {
        if (cancelled_) return false;
        {
            std::lock_guard<std::mutex> lock(mutex_);
            progress_.begin_tool(pack);
        }
        std::wstring command;
        for (const std::string& a : args)
            command += (command.empty() ? L"" : L" ") + wwbuild::quote_arg(wwbuild::widen(a));
        std::vector<wchar_t> line(command.begin(), command.end());
        line.push_back(L'\0');
        SECURITY_ATTRIBUTES sa{sizeof(sa), nullptr, TRUE};
        HANDLE read_end = nullptr, write_end = nullptr;
        if (!CreatePipe(&read_end, &write_end, &sa, 0)) return fail("can't start WildWorldBuild");
        SetHandleInformation(read_end, HANDLE_FLAG_INHERIT, 0);
        STARTUPINFOW si{};
        si.cb = sizeof(si);
        si.dwFlags = STARTF_USESTDHANDLES;
        si.hStdOutput = write_end;
        si.hStdError = write_end;
        PROCESS_INFORMATION pi{};
        const BOOL started = CreateProcessW(nullptr, line.data(), nullptr, nullptr, TRUE,
                                            CREATE_NO_WINDOW | CREATE_SUSPENDED, nullptr, nullptr, &si, &pi);
        CloseHandle(write_end);
        if (!started) {
            CloseHandle(read_end);
            return fail("can't start " + args[0]);
        }
        if (job_) AssignProcessToJobObject(job_, pi.hProcess);
        ResumeThread(pi.hThread);
        std::string pending;
        char buffer[4096];
        DWORD got = 0;
        while (ReadFile(read_end, buffer, sizeof(buffer), &got, nullptr) && got > 0) {
            log.write(buffer, got);
            log.flush();
            for (DWORD i = 0; i < got; ++i) {
                if (buffer[i] == '\n' || buffer[i] == '\r') {
                    if (!pending.empty()) take(pending);
                    pending.clear();
                } else {
                    pending += buffer[i];
                }
            }
        }
        if (!pending.empty()) take(pending);
        CloseHandle(read_end);
        WaitForSingleObject(pi.hProcess, INFINITE);
        DWORD code = 1;
        GetExitCodeProcess(pi.hProcess, &code);
        CloseHandle(pi.hThread);
        CloseHandle(pi.hProcess);
        return code == 0 && !cancelled_;
    }

    void take(const std::string& text) {
        std::lock_guard<std::mutex> lock(mutex_);
        const bool was_compiling = progress_.compiling();
        progress_.line(text, &status_);
        if (!was_compiling && progress_.compiling()) compile_started_ = std::chrono::steady_clock::now();
    }

    bool fail(const std::string& why) {
        std::lock_guard<std::mutex> lock(mutex_);
        status_.error = why;
        return false;
    }

    std::mutex mutex_;
    BuildStatus status_;
    BuildProgress progress_;
    std::thread thread_;
    HANDLE job_ = nullptr;
    std::atomic<bool> cancelled_{false};
    std::atomic<bool> running_{false};
    std::chrono::steady_clock::time_point started_, compile_started_;
};
#endif

}  // namespace acww
