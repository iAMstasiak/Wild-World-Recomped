// Reading the game's code out of a DS ROM (WildWorldBuild): the main ARM9
// and ARM7 programs and every ARM9 overlay, decompressed. A port of what
// tools/prepare_acww.py gets from ndspy 4.2.0 (rom.py, code.py and
// codeCompression.decompress), so both give the same bytes.
#pragma once

#include <cstdint>
#include <stdexcept>
#include <string>
#include <vector>

namespace wwbuild {

using Bytes = std::vector<uint8_t>;

inline uint32_t read32(const Bytes& d, size_t at) {
    if (at + 4 > d.size()) throw std::runtime_error("read past the end of the ROM");
    return d[at] | d[at + 1] << 8 | d[at + 2] << 16 | uint32_t(d[at + 3]) << 24;
}

// data[from, from + length), cut short at the end like a Python slice.
inline Bytes slice(const Bytes& d, size_t from, size_t length) {
    if (from >= d.size()) return {};
    const size_t end = length > d.size() - from ? d.size() : from + length;
    return Bytes(d.begin() + static_cast<long>(from), d.begin() + static_cast<long>(end));
}

// ndspy's _detectAppendedData: how many bytes follow the compression
// footer, or false when the data doesn't look compressed.
inline bool appended_amount(const Bytes& d, size_t* amount) {
    for (size_t amt = 0; amt < 0x20; amt += 4) {
        if (d.size() < amt + 8) return false;
        const uint32_t word = read32(d, d.size() - amt - 8);
        if ((word >> 24) < 8) continue;               // header length
        if ((word & 0xFFFFFF) > d.size()) continue;   // compressed length
        *amount = amt;
        return true;
    }
    return false;
}

// "Code compression" (backwards LZ), decompressed exactly as ndspy does it.
inline Bytes code_decompress(const Bytes& input) {
    size_t appended = 0;
    if (!appended_amount(input, &appended)) return input;   // not compressed
    const Bytes data(input.begin(), input.end() - static_cast<long>(appended));
    const Bytes tail(input.end() - static_cast<long>(appended), input.end());
    const size_t len = data.size();
    if (read32(data, len - 4) == 0) return data;   // extra size 0: stored as is

    const uint32_t word = read32(data, len - 8);
    const size_t header_len = word >> 24;
    size_t compressed_len = word & 0xFFFFFF;
    const size_t extra = read32(data, len - 4);
    if (len < header_len) throw std::runtime_error("compressed file too small for its header");
    for (size_t i = len - header_len; i < len - 8; ++i)
        if (data[i] != 0xFF) throw std::runtime_error("compression header padding isn't 0xFF");
    if (compressed_len >= len) compressed_len = len;

    const size_t passthrough = len - compressed_len;
    const Bytes comp(data.begin() + static_cast<long>(passthrough),
                     data.begin() + static_cast<long>(passthrough + compressed_len - header_len));
    Bytes out(len + extra - passthrough);
    const size_t out_len = out.size();
    size_t written = 0, read = 0;
    unsigned flags = 0, mask = 1;
    const auto next_in = [&]() -> uint8_t {
        if (read >= comp.size()) throw std::runtime_error("not enough data to decompress");
        return comp[comp.size() - 1 - read++];
    };
    const auto put = [&](uint8_t v) {
        if (written >= out_len) throw std::runtime_error("decompressed data overran its size");
        out[out_len - 1 - written++] = v;
    };
    while (written < out_len) {
        if (mask == 1) {
            if (read >= compressed_len) throw std::runtime_error("not enough data to decompress");
            flags = next_in();
            mask = 0x80;
        } else {
            mask >>= 1;
        }
        if (flags & mask) {
            const uint8_t b1 = next_in(), b2 = next_in();
            const size_t length = (b1 >> 4) + 3;
            size_t disp = ((b1 & 0x0F) << 8 | b2) + 3;
            if (disp > written) {
                if (written < 2) throw std::runtime_error("compressed data points before its start");
                disp = 2;   // ndspy's rule for this case
            }
            size_t from = written - disp;
            for (size_t i = 0; i < length; ++i) {
                const uint8_t v = out[out_len - 1 - from++];
                put(v);
            }
        } else {
            put(next_in());
        }
    }
    Bytes result(data.begin(), data.begin() + static_cast<long>(passthrough));
    result.insert(result.end(), out.begin(), out.end());
    result.insert(result.end(), tail.begin(), tail.end());
    return result;
}

struct Overlay {
    uint32_t id = 0, ram = 0, ram_size = 0, bss = 0;
    uint32_t static_init_start = 0, static_init_end = 0, file_id = 0, flags = 0;
    Bytes data;   // decompressed
};

struct Rom {
    uint32_t arm9_entry = 0, arm9_ram = 0, arm7_entry = 0, arm7_ram = 0;
    Bytes arm9;   // decompressed
    Bytes arm7;
    std::vector<Overlay> overlays;   // ARM9 overlays, in table order
};

inline Rom read_rom(const Bytes& data) {
    Rom rom;
    const uint32_t arm9_off = read32(data, 0x20), arm9_len = read32(data, 0x2C);
    const uint32_t arm7_off = read32(data, 0x30), arm7_len = read32(data, 0x3C);
    rom.arm9_entry = read32(data, 0x24);
    rom.arm9_ram = read32(data, 0x28);
    rom.arm7_entry = read32(data, 0x34);
    rom.arm7_ram = read32(data, 0x38);

    const Bytes arm9_stored = slice(data, arm9_off, arm9_len);
    rom.arm9 = code_decompress(arm9_stored);
    if (rom.arm9.size() < arm9_stored.size()) rom.arm9 = arm9_stored;
    rom.arm7 = slice(data, arm7_off, arm7_len);

    const Bytes fat = slice(data, read32(data, 0x48), read32(data, 0x4C));
    const Bytes table = slice(data, read32(data, 0x50), read32(data, 0x54));
    for (size_t i = 0; i + 32 <= table.size(); i += 32) {
        Overlay ov;
        ov.id = read32(table, i);
        ov.ram = read32(table, i + 4);
        ov.ram_size = read32(table, i + 8);
        ov.bss = read32(table, i + 12);
        ov.static_init_start = read32(table, i + 16);
        ov.static_init_end = read32(table, i + 20);
        ov.file_id = read32(table, i + 24);
        ov.flags = read32(table, i + 28) >> 24;
        if (size_t(ov.file_id) * 8 + 8 > fat.size())
            throw std::runtime_error("overlay " + std::to_string(ov.id) + " has no file");
        const uint32_t start = read32(fat, ov.file_id * 8u), end = read32(fat, ov.file_id * 8u + 4);
        const Bytes stored = end > start ? slice(data, start, end - start) : Bytes();
        ov.data = (ov.flags & 1) ? code_decompress(stored) : stored;
        if (ov.data.size() != ov.ram_size)
            throw std::runtime_error("overlay " + std::to_string(ov.id) + " unpacked to " +
                                     std::to_string(ov.data.size()) + " bytes, expected " +
                                     std::to_string(ov.ram_size));
        rom.overlays.push_back(std::move(ov));
    }
    return rom;
}

}  // namespace wwbuild
