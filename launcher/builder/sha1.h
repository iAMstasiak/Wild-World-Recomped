// SHA-1, for checking the player's ROM and naming what the build writes
// (WildWorldBuild). Small and dependency-free; not for anything secret.
#pragma once

#include <cstdint>
#include <cstdio>
#include <string>
#include <vector>

namespace wwbuild {

inline std::string sha1_hex(const uint8_t* data, size_t size) {
    uint32_t h[5] = {0x67452301u, 0xEFCDAB89u, 0x98BADCFEu, 0x10325476u, 0xC3D2E1F0u};
    const auto rol = [](uint32_t v, int n) { return (v << n) | (v >> (32 - n)); };
    const auto block = [&](const uint8_t* p) {
        uint32_t w[80];
        for (int i = 0; i < 16; ++i)
            w[i] = uint32_t(p[i * 4]) << 24 | uint32_t(p[i * 4 + 1]) << 16 |
                   uint32_t(p[i * 4 + 2]) << 8 | uint32_t(p[i * 4 + 3]);
        for (int i = 16; i < 80; ++i) w[i] = rol(w[i - 3] ^ w[i - 8] ^ w[i - 14] ^ w[i - 16], 1);
        uint32_t a = h[0], b = h[1], c = h[2], d = h[3], e = h[4];
        for (int i = 0; i < 80; ++i) {
            uint32_t f, k;
            if (i < 20) { f = (b & c) | (~b & d); k = 0x5A827999u; }
            else if (i < 40) { f = b ^ c ^ d; k = 0x6ED9EBA1u; }
            else if (i < 60) { f = (b & c) | (b & d) | (c & d); k = 0x8F1BBCDCu; }
            else { f = b ^ c ^ d; k = 0xCA62C1D6u; }
            const uint32_t t = rol(a, 5) + f + e + k + w[i];
            e = d; d = c; c = rol(b, 30); b = a; a = t;
        }
        h[0] += a; h[1] += b; h[2] += c; h[3] += d; h[4] += e;
    };
    size_t whole = size / 64 * 64;
    for (size_t i = 0; i < whole; i += 64) block(data + i);
    uint8_t tail[128] = {};
    const size_t rest = size - whole;
    for (size_t i = 0; i < rest; ++i) tail[i] = data[whole + i];
    tail[rest] = 0x80;
    const size_t tail_len = rest < 56 ? 64 : 128;
    const uint64_t bits = uint64_t(size) * 8;
    for (int i = 0; i < 8; ++i) tail[tail_len - 1 - i] = uint8_t(bits >> (8 * i));
    block(tail);
    if (tail_len == 128) block(tail + 64);
    char out[41];
    for (int i = 0; i < 5; ++i) std::snprintf(out + i * 8, 9, "%08x", h[i]);
    return std::string(out, 40);
}

inline std::string sha1_hex(const std::vector<uint8_t>& data) {
    return sha1_hex(data.data(), data.size());
}

}  // namespace wwbuild
