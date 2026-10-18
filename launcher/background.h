// The launcher's background (launcher).
//
// A pattern of little icons on white, made by a fan artist and used with
// their permission (launcher/assets/background.jpg; credited on the Credits
// page). Its white paper is lifted off so only the icons are left, the result
// is written beside the box art in %LOCALAPPDATA%\Wild World Recomped, and
// recomp-ui draws it faintly over the dark ground, scaled to cover the window
// (patch_recompui.py).
#pragma once

#include <algorithm>
#include <cstdint>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <string>
#include <vector>

#include "layout.h"
#include "launcher_gl.h"

namespace acww {

struct Background {
    std::string path;             // "" = none
    const char* mode = "cover";   // or "tile" for a small repeating tile
};

// White paper becomes see-through: how far a pixel is from white decides its
// alpha, and its colour goes back to what it was before it met the white.
// Pixels that already have their own alpha (a PNG like ours) stay as they are.
inline void lift_off_white(std::vector<uint8_t>& rgba) {
    for (size_t i = 0; i + 3 < rgba.size(); i += 4) {
        uint8_t* p = &rgba[i];
        if (p[3] < 255) continue;
        const int d = std::max({255 - p[0], 255 - p[1], 255 - p[2]});
        const int a = std::clamp((d - 10) * 3, 0, 255);   // JPEG specks near white vanish
        if (a == 0) {
            p[0] = p[1] = p[2] = p[3] = 0;
            continue;
        }
        for (int c = 0; c < 3; ++c)
            p[c] = static_cast<uint8_t>(std::clamp(255 - (255 - p[c]) * 255 / a, 0, 255));
        p[3] = static_cast<uint8_t>(a);
    }
}

// An uncompressed 32-bit TGA, top row first.
inline bool write_rgba_tga(const std::filesystem::path& path, const std::vector<uint8_t>& rgba,
                           int w, int h) {
    std::vector<uint8_t> data(18 + rgba.size(), 0);
    data[2] = 2;
    data[12] = w & 255; data[13] = (w >> 8) & 255;
    data[14] = h & 255; data[15] = (h >> 8) & 255;
    data[16] = 32;
    data[17] = 0x28;
    for (size_t i = 0; i + 3 < rgba.size(); i += 4) {   // R, G, B, A -> B, G, R, A
        data[18 + i] = rgba[i + 2];
        data[19 + i] = rgba[i + 1];
        data[20 + i] = rgba[i];
        data[21 + i] = rgba[i + 3];
    }
    std::error_code ec;
    std::filesystem::create_directories(path.parent_path(), ec);
    std::ofstream file(path, std::ios::binary | std::ios::trunc);
    file.write(reinterpret_cast<const char*>(data.data()), static_cast<std::streamsize>(data.size()));
    return static_cast<bool>(file);
}

inline Background make_background() {
    Background bg;
    int w = 0, h = 0;
    unsigned char* pixels = launcher_image_load_rgba("launcher\\assets\\background.jpg", &w, &h);
    if (!pixels) return {};
    std::vector<uint8_t> rgba(pixels, pixels + static_cast<size_t>(w) * h * 4);
    launcher_image_free(pixels);
    lift_off_white(rgba);
    const wchar_t* local = _wgetenv(L"LOCALAPPDATA");
    const std::filesystem::path folder = local && local[0]
        ? std::filesystem::path(local) / "Wild World Recomped"
        : std::filesystem::absolute("generated");
    const std::filesystem::path out = folder / "background.tga";
    if (!write_rgba_tga(out, rgba, w, h)) return {};
    bg.path = ascii_path(out).u8string();
    return bg;
}

}  // namespace acww
