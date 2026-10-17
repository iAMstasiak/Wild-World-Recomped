// acwwrecomp: one save-file write per in-game save (runner).
//
// The game saves by sending the backup chip a run of page writes (18 for an
// ordinary save), and the runner used to rewrite the whole 256 KB acww.sav
// after every one of them, waiting for the disk each time. Now each write just
// marks the save as changed, and tick(), called every frame, writes the file
// once the game has gone quiet for a moment: one complete save, written once.
// The runner still writes any unsaved change when it closes.
#pragma once

#include <atomic>
#include <chrono>
#include <cstdint>

namespace acww_saves {

// How long the game must stop writing before the file is written.
constexpr std::chrono::milliseconds kQuiet{750};

inline std::atomic<bool>& pending() {
    static std::atomic<bool> value{false};
    return value;
}

inline std::atomic<int64_t>& last_write() {   // steady_clock ticks
    static std::atomic<int64_t> value{0};
    return value;
}

inline int64_t now() { return std::chrono::steady_clock::now().time_since_epoch().count(); }

// The game finished one write to the backup chip.
inline void written() {
    last_write().store(now());
    pending().store(true);
}

// Every frame: write acww.sav once the game has stopped saving.
inline void tick() {
    if (!pending().load()) return;
    const auto quiet = std::chrono::duration_cast<std::chrono::steady_clock::duration>(kQuiet);
    if (now() - last_write().load() < quiet.count()) return;
    pending().store(false);
    nds_io_flush_cartridge_save();   // io.h
}

}  // namespace acww_saves
