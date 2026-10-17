// Recompiling the planned banks into C (WildWorldBuild): what make_banks.py
// does after planning, with several nds_recompile runs at once, plus the two
// FreeBIOS banks ndsrecomp's runner needs (its vendor/freebios/README.md).
#pragma once

#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstdio>
#include <filesystem>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

#include "files.h"
#include "nds_rom.h"
#include "plan.h"
#include "process.h"

namespace wwbuild {

struct RecompileOptions {
    std::filesystem::path work;        // inputs\, banks\, recomp\, gen\ and logs\ go here
    std::filesystem::path recompiler;  // nds_recompile(.exe)
    std::filesystem::path ndsrecomp;   // ndsrecomp's folder, for FreeBIOS; empty to skip
    int jobs = 4;
};

// The images, the configs and then the C: work\recomp holds the game's banks,
// work\gen the FreeBIOS banks. Progress lines go to stdout as
// "[progress] N/M bank (seconds)"; false and *error when anything failed.
inline bool recompile_banks(const Rom& rom, const std::vector<Bank>& banks,
                            const RecompileOptions& o, std::string* error) {
    namespace fs = std::filesystem;
    struct Job {
        std::string name;
        std::vector<std::string> args;
        size_t weight = 0;
        int code = 0;
        bool emitted = false;
    };
    std::error_code ec;
    const fs::path inputs = o.work / "inputs", configs = o.work / "banks";
    const fs::path out = o.work / "recomp", gen = o.work / "gen", logs = o.work / "logs";
    for (const fs::path& dir : {out, gen}) fs::remove_all(dir, ec);   // stale shards would get linked
    for (const fs::path& dir : {inputs, configs, out, gen, logs}) fs::create_directories(dir, ec);

    if (!write_file(inputs / "arm9.bin", rom.arm9) || !write_file(inputs / "arm7.bin", rom.arm7)) {
        *error = "can't write into " + inputs.u8string();
        return false;
    }
    for (const Overlay& ov : rom.overlays) {
        char name[48];
        std::snprintf(name, sizeof(name), "arm9_overlay_%03u.bin", ov.id);
        write_file(inputs / "overlays" / name, ov.data);
    }

    std::vector<Job> jobs;
    for (const Bank& b : banks) {
        const std::string text = bank_config(b);
        if (text.empty()) continue;
        const fs::path config = configs / (b.bank + ".toml");
        if (!write_file(config, std::vector<uint8_t>(text.begin(), text.end()))) {
            *error = "can't write " + config.u8string();
            return false;
        }
        Job job;
        job.name = b.bank;
        job.weight = b.entries.size();
        job.args = {o.recompiler.u8string(), "--config", config.u8string(),
                    "--bin", (inputs / fs::u8path(b.image)).u8string(), "--out", out.u8string(),
                    "--bank", b.bank, "--shards", std::to_string(b.shards),
                    "--stable-address-shards", "--max-function-bytes", "512",
                    "--validate-live-bytes", "--coalesce-fallthroughs"};
        jobs.push_back(std::move(job));
    }
    if (!o.ndsrecomp.empty()) {
        for (const char* cpu : {"9", "7"}) {
            Job job;
            job.name = std::string("freebios_arm") + cpu;
            job.args = {o.recompiler.u8string(), "--config",
                        (o.ndsrecomp / "bios" / (std::string("freebios") + cpu + ".toml")).u8string(),
                        "--bin",
                        (o.ndsrecomp / "third_party" / "freebios" /
                         (std::string("drastic_bios_arm") + cpu + ".bin")).u8string(),
                        "--out", gen.u8string(), "--bank", job.name};
            jobs.push_back(std::move(job));
        }
    }
    // The biggest first, so the last few to finish are small ones.
    std::stable_sort(jobs.begin(), jobs.end(),
                     [](const Job& a, const Job& b) { return a.weight > b.weight; });

    std::atomic<size_t> next{0};
    std::mutex printing;
    size_t done = 0;
    const auto worker = [&]() {
        for (size_t i = next++; i < jobs.size(); i = next++) {
            Job& job = jobs[i];
            const auto started = std::chrono::steady_clock::now();
            const fs::path log = logs / (job.name + ".log");
            job.code = run_process(job.args, log.u8string());
            const std::vector<uint8_t> text = read_file(log);
            job.emitted = std::string(text.begin(), text.end()).find("[emit] bank") != std::string::npos;
            const double s = std::chrono::duration<double>(std::chrono::steady_clock::now() - started).count();
            std::lock_guard<std::mutex> lock(printing);
            std::printf("[progress] %zu/%zu %s (%.1f s)%s\n", ++done, jobs.size(), job.name.c_str(), s,
                        job.code == 0 && job.emitted ? "" : "  FAILED");
            std::fflush(stdout);
        }
    };
    std::vector<std::thread> threads;
    for (int t = 0; t < std::max(1, o.jobs); ++t) threads.emplace_back(worker);
    for (std::thread& t : threads) t.join();

    std::string failed;
    for (const Job& job : jobs)
        if (job.code != 0 || !job.emitted)
            failed += (failed.empty() ? "" : ", ") + job.name + " (exit " + std::to_string(job.code) + ")";
    if (!failed.empty()) {
        *error = "the recompiler failed for " + failed + "; its logs are in " + logs.u8string();
        return false;
    }
    return true;
}

}  // namespace wwbuild
