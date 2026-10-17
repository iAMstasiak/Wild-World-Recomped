// The Play page's picture: the game's own DS menu icon, read from the
// player's ROM (launcher). It is written to %LOCALAPPDATA%\Wild World
// Recomped each time, beside the shortcut's icon, so none of Nintendo's art
// ships with the project or lands in git.
#pragma once

#include <algorithm>
#include <cstdint>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <string>
#include <vector>

namespace acww {

// The 32x32 DS menu icon as RGBA (alpha 0 = see-through), or nothing if the
// file isn't a DS game with a banner.
inline std::vector<uint8_t> read_banner_icon(const std::string& rom) {
    std::ifstream file(rom, std::ios::binary);
    uint8_t header[0x6C];
    if (!file.read(reinterpret_cast<char*>(header), sizeof(header))) return {};
    const uint32_t banner = header[0x68] | header[0x69] << 8 | header[0x6A] << 16 |
                            static_cast<uint32_t>(header[0x6B]) << 24;
    if (banner == 0) return {};
    uint8_t icon[0x220];   // 512 bytes of 4-bit tiles, then 16 colours
    file.seekg(banner + 0x20);
    if (!file.read(reinterpret_cast<char*>(icon), sizeof(icon))) return {};

    uint8_t palette[16][4];
    for (int i = 0; i < 16; ++i) {
        const int c = icon[0x200 + i * 2] | icon[0x201 + i * 2] << 8;
        const auto expand = [](int v) { return static_cast<uint8_t>(v << 3 | v >> 2); };
        palette[i][0] = expand(c & 31);
        palette[i][1] = expand(c >> 5 & 31);
        palette[i][2] = expand(c >> 10 & 31);
        palette[i][3] = i == 0 ? 0 : 255;   // colour 0 is see-through
    }
    std::vector<uint8_t> rgba(32 * 32 * 4);
    for (int y = 0; y < 32; ++y)
        for (int x = 0; x < 32; ++x) {
            const uint8_t pair = icon[((y / 8) * 4 + x / 8) * 32 + (y % 8) * 4 + (x % 8) / 2];
            const uint8_t* p = palette[(x & 1) ? pair >> 4 : pair & 15];
            std::copy(p, p + 4, &rgba[(y * 32 + x) * 4]);
        }
    return rgba;
}

// An uncompressed 32-bit TGA with each pixel drawn as a scale x scale block:
// the launcher smooths the pictures it shows, so it gets big crisp pixels.
inline bool write_tga(const std::filesystem::path& path, const std::vector<uint8_t>& rgba,
                      int side, int scale) {
    const int out = side * scale;
    std::vector<uint8_t> data(18 + static_cast<size_t>(out) * out * 4, 0);
    data[2] = 2;                                   // uncompressed, true colour
    data[12] = out & 255; data[13] = out >> 8;     // width
    data[14] = out & 255; data[15] = out >> 8;     // height
    data[16] = 32;                                 // bits per pixel
    data[17] = 0x28;                               // 8 alpha bits, top row first
    uint8_t* px = &data[18];
    for (int y = 0; y < out; ++y)
        for (int x = 0; x < out; ++x) {
            const uint8_t* s = &rgba[((y / scale) * side + x / scale) * 4];
            *px++ = s[2]; *px++ = s[1]; *px++ = s[0]; *px++ = s[3];   // B, G, R, A
        }
    std::error_code ec;
    std::filesystem::create_directories(path.parent_path(), ec);
    std::ofstream file(path, std::ios::binary | std::ios::trunc);
    file.write(reinterpret_cast<const char*>(data.data()), static_cast<std::streamsize>(data.size()));
    return static_cast<bool>(file);
}

// The game's English name and publisher from the ROM's banner, e.g.
// "Animal Crossing\nWild World\nNintendo" -> {"Animal Crossing: Wild World",
// "Nintendo"}. Empty when the file isn't a DS game with a banner.
struct RomTitle {
    std::string name;
    std::string publisher;
};

inline RomTitle read_banner_title(const std::string& rom) {
    std::ifstream file(rom, std::ios::binary);
    uint8_t header[0x6C];
    if (!file.read(reinterpret_cast<char*>(header), sizeof(header))) return {};
    const uint32_t banner = header[0x68] | header[0x69] << 8 | header[0x6A] << 16 |
                            static_cast<uint32_t>(header[0x6B]) << 24;
    if (banner == 0) return {};
    uint8_t raw[0x100];   // the English title: 128 UTF-16 characters
    file.seekg(banner + 0x340);
    if (!file.read(reinterpret_cast<char*>(raw), sizeof(raw))) return {};
    std::vector<std::string> lines(1);
    for (int i = 0; i < 0x100; i += 2) {
        const unsigned c = raw[i] | raw[i + 1] << 8;
        if (c == 0) break;
        if (c == '\n') {
            lines.emplace_back();
        } else if (c < 0x80) {
            lines.back() += static_cast<char>(c);
        } else if (c < 0x800) {
            lines.back() += static_cast<char>(0xC0 | c >> 6);
            lines.back() += static_cast<char>(0x80 | (c & 0x3F));
        } else {
            lines.back() += static_cast<char>(0xE0 | c >> 12);
            lines.back() += static_cast<char>(0x80 | ((c >> 6) & 0x3F));
            lines.back() += static_cast<char>(0x80 | (c & 0x3F));
        }
    }
    RomTitle title;
    if (lines.size() >= 2) {
        title.publisher = lines.back();
        lines.pop_back();
    }
    for (const std::string& line : lines)
        title.name += (title.name.empty() ? "" : ": ") + line;
    return title;
}

// The box art for this ROM, written fresh; its full path, or "" when the
// ROM isn't there yet or has no icon (the launcher then draws a cartridge).
inline std::string make_box_art(const std::string& rom) {
    const std::vector<uint8_t> icon = read_banner_icon(rom);
    if (icon.empty()) return "";
    const char* local = std::getenv("LOCALAPPDATA");
    const std::filesystem::path folder = local && local[0]
        ? std::filesystem::path(local) / "Wild World Recomped"
        : std::filesystem::absolute("generated");
    const std::filesystem::path path = folder / "boxart.tga";
    return write_tga(path, icon, 32, 8) ? path.string() : "";
}

}  // namespace acww
