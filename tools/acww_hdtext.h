#pragma once
// acwwrecomp: HD letters (copied in by tools/patch_hdtext.py; edit tools/acww_hdtext.h).
//
// Wild World paints its letters, one colour on a plain background, into the
// tiles of a 2D background layer. Whenever such a layer changes, this reads
// the letters back off it by matching them exactly against the game's own
// font (font/fontA in the player's ROM), and draws each one again at the HD
// scale as a smooth round-pen stroke through the original pixels. The compute
// host gets two pictures per screen: a native-size mask of the pixels the HD
// letters own, and the HD letters themselves. A pixel is only owned while the
// finished DS frame still shows exactly the colour the letter expects there,
// so sprites, fades and anything else drawn on top always win.

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <string>
#include <vector>

#include "gpu2d.h"
#include "vram.h"
#include "melonds_compute/ComputeHost.h"

namespace acww_hdtext {

constexpr int kCell = 16;          // fontA draws every letter in a 16x16 cell
constexpr int kScreenH = 192;
constexpr float kPen = 0.55f;      // pen radius in native pixels ("r55")

struct Glyph {
    uint16_t code = 0;
    int lb = 0, rb = -1;           // first and last column with ink
    uint16_t col[kCell]{};         // bit r: row r of that column has ink
    uint16_t row[kCell]{};         // bit c: column c of that row has ink
};

struct Font {
    bool tried = false;
    bool ok = false;
    std::vector<Glyph> glyphs;     // widest ink first, so the widest match wins
    int cov_scale = 0;
    std::vector<std::vector<uint8_t>> cov;  // per glyph: (16*s)^2 pen coverage
};

struct Found {
    int x = 0, y = 0;              // cell origin in the layer's own pixels
    int glyph = 0;
    uint16_t ink = 0, bg = 0;      // DS 15-bit colours
    uint16_t cls = 0;              // (palette, background, ink) of its tiles
};

struct LayerScan {
    std::vector<uint8_t> sig;      // map + tiles + palette the result came from
    std::vector<Found> found;
};

struct Owned {
    int sx, sy, glyph, r, c;
    uint16_t ink, bg;
};

struct ScreenOut {
    bool on = false;
    uint64_t hash = 0;
    int width = 0, scale = 0;
    std::vector<uint8_t> mask;
    std::vector<uint32_t> hd;
};

inline Font g_font;
inline LayerScan g_scan[2][4];
inline ScreenOut g_out[2];

inline uint16_t le16(const uint8_t* p) { return static_cast<uint16_t>(p[0] | p[1] << 8); }
inline uint32_t le32(const uint8_t* p) {
    return p[0] | p[1] << 8 | p[2] << 16 | static_cast<uint32_t>(p[3]) << 24;
}

inline bool read_at(std::ifstream& f, uint32_t offset, void* dst, size_t n) {
    f.clear();
    f.seekg(offset);
    return static_cast<bool>(f.read(static_cast<char*>(dst), static_cast<std::streamsize>(n)));
}

// One file from the ROM's own filesystem (NitroFS), by its path.
inline bool rom_file(std::ifstream& f, const std::vector<uint8_t>& fnt,
                     uint32_t fat, const std::string& path,
                     std::vector<uint8_t>& out) {
    uint16_t dir = 0xF000;
    size_t start = 0;
    while (true) {
        const size_t slash = path.find('/', start);
        const bool want_dir = slash != std::string::npos;
        const std::string part = path.substr(start, want_dir ? slash - start : std::string::npos);
        const size_t entry = static_cast<size_t>(dir & 0x0FFFu) * 8u;
        if (entry + 8 > fnt.size()) return false;
        size_t p = le32(&fnt[entry]);
        uint16_t id = le16(&fnt[entry + 4]);
        bool descended = false;
        while (p < fnt.size()) {
            const uint8_t len = fnt[p++];
            if (len == 0) break;
            const bool is_dir = (len & 0x80u) != 0;
            const size_t n = len & 0x7Fu;
            if (p + n + (is_dir ? 2u : 0u) > fnt.size()) return false;
            const std::string name(reinterpret_cast<const char*>(&fnt[p]), n);
            p += n;
            uint16_t sub = 0;
            if (is_dir) {
                sub = le16(&fnt[p]);
                p += 2;
            }
            if (name == part && is_dir == want_dir) {
                if (is_dir) {
                    dir = sub;
                    descended = true;
                    break;
                }
                uint8_t span[8];
                if (!read_at(f, fat + id * 8u, span, sizeof(span))) return false;
                const uint32_t a = le32(span), b = le32(span + 4);
                if (b < a || b - a > (16u << 20)) return false;
                out.resize(b - a);
                return read_at(f, a, out.data(), out.size());
            }
            if (!is_dir) ++id;
        }
        if (!descended) return false;
        start = slash + 1;
    }
}

// Nintendo LZ77 (type 0x10), with or without the "LZ77" tag in front.
inline bool unpack(const std::vector<uint8_t>& in, std::vector<uint8_t>& out) {
    if (in.size() < 4 || std::memcmp(in.data(), "LZ77", 4) != 0) {
        out = in;
        return !in.empty();
    }
    size_t i = 4;
    if (in.size() < i + 4 || in[i] != 0x10) return false;
    const uint32_t size = in[i + 1] | in[i + 2] << 8 | in[i + 3] << 16;
    i += 4;
    out.clear();
    out.reserve(size);
    while (out.size() < size && i < in.size()) {
        const uint8_t flags = in[i++];
        for (int b = 0; b < 8 && out.size() < size; ++b) {
            if (flags & (0x80u >> b)) {
                if (i + 1 >= in.size()) return false;
                const int n = (in[i] >> 4) + 3;
                const size_t back = static_cast<size_t>((in[i] & 15) << 8 | in[i + 1]) + 1;
                i += 2;
                if (back > out.size()) return false;
                for (int k = 0; k < n && out.size() < size; ++k)
                    out.push_back(out[out.size() - back]);
            } else {
                if (i >= in.size()) return false;
                out.push_back(in[i++]);
            }
        }
    }
    return out.size() == size;
}

inline bool load_font(const char* rom_path, Font& font) {
    if (!rom_path || !*rom_path) return false;
    std::ifstream f(rom_path, std::ios::binary);
    if (!f) return false;
    uint8_t header[0x50];
    if (!read_at(f, 0, header, sizeof(header))) return false;
    const uint32_t fnt_offset = le32(header + 0x40), fnt_size = le32(header + 0x44);
    const uint32_t fat = le32(header + 0x48);
    if (fnt_size == 0 || fnt_size > (4u << 20)) return false;
    std::vector<uint8_t> fnt(fnt_size);
    if (!read_at(f, fnt_offset, fnt.data(), fnt.size())) return false;
    std::vector<uint8_t> head, attr_raw, img_raw, attr, img;
    if (!rom_file(f, fnt, fat, "font/fontA_head.bin", head) ||
        !rom_file(f, fnt, fat, "font/fontA_attr.bin", attr_raw) ||
        !rom_file(f, fnt, fat, "font/fontA_img.bin", img_raw) ||
        head.size() < 8 || !unpack(attr_raw, attr) || !unpack(img_raw, img))
        return false;
    const uint32_t count = le32(head.data());
    if (le16(&head[4]) != kCell || le16(&head[6]) != kCell || count == 0 ||
        count > 1024 || attr.size() < count * 4u || img.size() < count * 32u)
        return false;
    font.glyphs.clear();
    for (uint32_t g = 0; g < count; ++g) {
        Glyph glyph;
        glyph.code = le16(&attr[g * 4]);
        for (int y = 0; y < kCell; ++y) {
            const unsigned bits = img[g * 32 + y * 2] << 8 | img[g * 32 + y * 2 + 1];
            for (int x = 0; x < kCell; ++x) {
                if (bits & (0x8000u >> x)) {
                    glyph.col[x] = static_cast<uint16_t>(glyph.col[x] | 1u << y);
                    glyph.row[y] = static_cast<uint16_t>(glyph.row[y] | 1u << x);
                }
            }
        }
        for (int x = 0; x < kCell; ++x) {
            if (!glyph.col[x]) continue;
            if (glyph.rb < 0) glyph.lb = x;
            glyph.rb = x;
        }
        if (glyph.rb >= 0) font.glyphs.push_back(glyph);   // spaces never match
    }
    std::stable_sort(font.glyphs.begin(), font.glyphs.end(),
                     [](const Glyph& a, const Glyph& b) {
                         return a.rb - a.lb > b.rb - b.lb;
                     });
    return !font.glyphs.empty();
}

// A round pen of radius kPen drawn through the centre of every ink pixel and
// along each run to its neighbours (diagonals only where the pixels touch at
// a corner alone), sampled s x s per native pixel.
inline void build_coverage(Font& font, int s) {
    const int W = kCell * s;
    font.cov.assign(font.glyphs.size(), std::vector<uint8_t>());
    std::vector<float> c(static_cast<size_t>(W) * W);
    for (size_t g = 0; g < font.glyphs.size(); ++g) {
        const Glyph& gl = font.glyphs[g];
        std::fill(c.begin(), c.end(), 0.0f);
        auto ink = [&](int x, int y) {
            return x >= 0 && y >= 0 && x < kCell && y < kCell &&
                   ((gl.row[y] >> x) & 1u) != 0;
        };
        auto pen = [&](float ax, float ay, float bx, float by) {
            const int x0 = std::max(0, static_cast<int>((std::min(ax, bx) - kPen - 1.0f) * s));
            const int x1 = std::min(W, static_cast<int>((std::max(ax, bx) + kPen + 1.0f) * s));
            const int y0 = std::max(0, static_cast<int>((std::min(ay, by) - kPen - 1.0f) * s));
            const int y1 = std::min(W, static_cast<int>((std::max(ay, by) + kPen + 1.0f) * s));
            const float dx = bx - ax, dy = by - ay, l2 = dx * dx + dy * dy;
            for (int py = y0; py < y1; ++py) {
                const float fy = (py + 0.5f) / s;
                for (int px = x0; px < x1; ++px) {
                    const float fx = (px + 0.5f) / s;
                    float t = l2 > 0.0f ? ((fx - ax) * dx + (fy - ay) * dy) / l2 : 0.0f;
                    t = std::clamp(t, 0.0f, 1.0f);
                    const float d = std::hypot(fx - (ax + t * dx), fy - (ay + t * dy));
                    const float v = std::clamp((kPen - d) * s + 0.5f, 0.0f, 1.0f);
                    float& out = c[static_cast<size_t>(py) * W + px];
                    if (v > out) out = v;
                }
            }
        };
        for (int y = 0; y < kCell; ++y) {
            for (int x = 0; x < kCell; ++x) {
                if (!ink(x, y)) continue;
                const float cx = x + 0.5f, cy = y + 0.5f;
                pen(cx, cy, cx, cy);
                if (ink(x + 1, y)) pen(cx, cy, cx + 1.0f, cy);
                if (ink(x, y + 1)) pen(cx, cy, cx, cy + 1.0f);
                if (ink(x + 1, y + 1) && !ink(x + 1, y) && !ink(x, y + 1))
                    pen(cx, cy, cx + 1.0f, cy + 1.0f);
                if (ink(x - 1, y + 1) && !ink(x - 1, y) && !ink(x, y + 1))
                    pen(cx, cy, cx - 1.0f, cy + 1.0f);
            }
        }
        std::vector<uint8_t>& out = font.cov[g];
        out.resize(c.size());
        for (size_t i = 0; i < c.size(); ++i)
            out[i] = static_cast<uint8_t>(std::lround(c[i] * 255.0f));
    }
    font.cov_scale = s;
}

// Copies BG VRAM a 16 KB chunk at a time where the renderer maps it directly.
inline void vram_copy(const NdsVramRendererView* view, int engine, uint32_t addr,
                      uint8_t* dst, size_t n) {
    while (n) {
        const uint32_t chunk = (addr >> 14) & (engine ? 7u : 31u);
        const size_t room = std::min<size_t>(n, 0x4000u - (addr & 0x3FFFu));
        if (view && view->bg[chunk]) {
            std::memcpy(dst, view->bg[chunk] + (addr & 0x3FFFu), room);
        } else {
            for (size_t i = 0; i < room; ++i)
                dst[i] = static_cast<uint8_t>(nds_vram_read_bg(engine, addr + static_cast<uint32_t>(i), 1));
        }
        dst += room;
        addr += static_cast<uint32_t>(room);
        n -= room;
    }
}

// Reads the letters off one text layer (4 bits per pixel), in its own
// coordinates, and keeps the answer until the layer's tiles, map or colours
// change.
inline void scan_layer(int engine, int bg, uint32_t dispcnt, uint16_t cnt,
                       const uint8_t* palette, const NdsVramRendererView* view,
                       LayerScan& scan, int& W, int& H) {
    (void)bg;
    W = (cnt & 0x4000u) ? 512 : 256;
    H = (cnt & 0x8000u) ? 512 : 256;
    uint32_t char_base = ((cnt >> 2) & 15u) * 0x4000u;
    uint32_t map_base = ((cnt >> 8) & 31u) * 0x800u;
    if (engine == 0) {
        char_base += ((dispcnt >> 24) & 7u) * 0x10000u;
        map_base += ((dispcnt >> 27) & 7u) * 0x10000u;
    }
    const int tw = W / 8, th = H / 8;
    std::vector<uint8_t> raw_map(static_cast<size_t>(tw) * th * 2);
    vram_copy(view, engine, map_base, raw_map.data(), raw_map.size());
    std::vector<uint16_t> map(static_cast<size_t>(tw) * th);
    unsigned top_tile = 0;
    for (int ty = 0; ty < th; ++ty) {
        for (int tx = 0; tx < tw; ++tx) {
            // 32x32 screen blocks follow each other: across first, then down.
            const size_t block = static_cast<size_t>((tx >> 5) + (ty >> 5) * (W > 256 ? 2 : 1));
            const uint16_t e = le16(&raw_map[block * 0x800u + static_cast<size_t>(((ty & 31) * 32 + (tx & 31)) * 2)]);
            map[static_cast<size_t>(ty) * tw + tx] = e;
            top_tile = std::max(top_tile, e & 0x3FFu);
        }
    }
    std::vector<uint8_t> sig;
    sig.reserve(map.size() * 2 + (top_tile + 1) * 32 + 512 + 4);
    sig.push_back(static_cast<uint8_t>(cnt));
    sig.push_back(static_cast<uint8_t>(cnt >> 8));
    sig.push_back(static_cast<uint8_t>(dispcnt >> 24));
    for (uint16_t e : map) {
        sig.push_back(static_cast<uint8_t>(e));
        sig.push_back(static_cast<uint8_t>(e >> 8));
    }
    const size_t tiles_at = sig.size();
    sig.resize(tiles_at + (top_tile + 1) * 32u);
    vram_copy(view, engine, char_base, sig.data() + tiles_at, (top_tile + 1) * 32u);
    sig.insert(sig.end(), palette, palette + 512);
    if (sig == scan.sig) return;
    scan.sig.swap(sig);
    scan.found.clear();
    const uint8_t* tiles = scan.sig.data() + tiles_at;

    // Text tiles hold exactly the background index, or the background plus
    // one ink index (the rarer of the two); anything else is artwork. Each
    // ink pixel remembers its tile's (palette, background, ink) "class", so
    // the edge of a frame next to the text never counts as part of a letter.
    std::vector<uint16_t> ink(static_cast<size_t>(W) * H, 0);
    for (int ty = 0; ty < th; ++ty) {
        for (int tx = 0; tx < tw; ++tx) {
            const uint16_t e = map[static_cast<size_t>(ty) * tw + tx];
            const uint8_t* t = tiles + (e & 0x3FFu) * 32u;
            int count[16] = {};
            for (int i = 0; i < 32; ++i) {
                ++count[t[i] & 15];
                ++count[t[i] >> 4];
            }
            if (count[0]) continue;
            int a = -1, b = -1;
            bool art = false;
            for (int i = 1; i < 16 && !art; ++i) {
                if (!count[i]) continue;
                if (a < 0) a = i;
                else if (b < 0) b = i;
                else art = true;
            }
            if (art || b < 0) continue;   // artwork, or a blank text tile
            const int bg_index = count[a] >= count[b] ? a : b;
            const int ink_index = bg_index == a ? b : a;
            const uint16_t cls = static_cast<uint16_t>(0x8000u | (e >> 12) << 8 |
                                                       bg_index << 4 | ink_index);
            const bool hf = (e & 0x400u) != 0, vf = (e & 0x800u) != 0;
            for (int y = 0; y < 8; ++y) {
                for (int x = 0; x < 8; ++x) {
                    const int sx = hf ? 7 - x : x, sy = vf ? 7 - y : y;
                    const uint8_t v = t[sy * 4 + sx / 2];
                    if (((sx & 1) ? v >> 4 : v & 15) == ink_index)
                        ink[static_cast<size_t>(ty * 8 + y) * W + tx * 8 + x] = cls;
                }
            }
        }
    }
    auto colour = [&](int pal, int index) {
        return le16(palette + (pal * 16 + index) * 2);
    };

    // Lines start on tile rows. A letter matches where its ink, column by
    // column over all 16 rows, is exactly what the layer shows in one class,
    // and the rows just above and below it are clear of that class (so half
    // a line never matches). A line only counts when its letters explain
    // nearly all of that class's ink there, which rules out stray shapes in
    // two-colour artwork.
    std::vector<uint16_t> colmask(W), colcls(W);
    std::vector<uint8_t> outside(W);
    std::vector<Found> line;
    for (int y0 = 0; y0 + kCell <= H; y0 += 8) {
        bool any = false;
        for (int x = 0; x < W; ++x) {
            uint16_t cls = 0, m = 0;
            for (int r = 0; r < kCell; ++r) {
                const uint16_t c = ink[static_cast<size_t>(y0 + r) * W + x];
                if (!c) continue;
                if (!cls) cls = c;
                if (c == cls) m = static_cast<uint16_t>(m | 1u << r);
            }
            colmask[x] = m;
            colcls[x] = cls;
            any = any || m;
            outside[x] = static_cast<uint8_t>(
                cls && ((y0 > 0 && ink[static_cast<size_t>(y0 - 1) * W + x] == cls) ||
                        (y0 + kCell < H && ink[static_cast<size_t>(y0 + kCell) * W + x] == cls)));
        }
        if (!any) continue;
        line.clear();
        for (int x = 0; x < W;) {
            if (!colmask[x]) {
                ++x;
                continue;
            }
            const uint16_t cls = colcls[x];
            int best = -1;
            for (size_t g = 0; g < g_font.glyphs.size(); ++g) {
                const Glyph& gl = g_font.glyphs[g];
                if (x + (gl.rb - gl.lb) >= W) continue;
                bool ok = true;
                for (int c = gl.lb; c <= gl.rb && ok; ++c) {
                    const int px = x + c - gl.lb;
                    ok = colmask[px] == gl.col[c] &&
                         (!gl.col[c] || (colcls[px] == cls && !outside[px]));
                }
                if (ok) {
                    best = static_cast<int>(g);
                    break;
                }
            }
            if (best < 0) {
                ++x;
                continue;
            }
            const Glyph& gl = g_font.glyphs[static_cast<size_t>(best)];
            Found f;
            f.x = x - gl.lb;
            f.y = y0;
            f.glyph = best;
            f.ink = colour(cls >> 8 & 15, cls & 15);
            f.bg = colour(cls >> 8 & 15, cls >> 4 & 15);
            f.cls = cls;
            line.push_back(f);
            x = f.x + gl.rb + 1;
        }
        // Keep each class's letters only if they explain its ink in the band.
        std::vector<std::pair<uint16_t, int>> total, explained;
        auto bump = [](std::vector<std::pair<uint16_t, int>>& v, uint16_t k, int n) {
            for (auto& p : v) if (p.first == k) { p.second += n; return; }
            v.push_back({k, n});
        };
        auto get = [](const std::vector<std::pair<uint16_t, int>>& v, uint16_t k) {
            for (const auto& p : v) if (p.first == k) return p.second;
            return 0;
        };
        for (int r = 0; r < kCell; ++r)
            for (int x = 0; x < W; ++x)
                if (const uint16_t c = ink[static_cast<size_t>(y0 + r) * W + x]) bump(total, c, 1);
        std::vector<std::pair<uint16_t, int>> letters;
        for (const Found& f : line) {
            const Glyph& gl = g_font.glyphs[static_cast<size_t>(f.glyph)];
            int n = 0;
            for (int c = gl.lb; c <= gl.rb; ++c) n += __builtin_popcount(gl.col[c]);
            bump(explained, f.cls, n);
            bump(letters, f.cls, 1);
        }
        for (const Found& f : line) {
            const int t = get(total, f.cls), e = get(explained, f.cls);
            if (e * 10 < t * 9 || (get(letters, f.cls) < 2 && e < 12)) continue;
            scan.found.push_back(f);
            const Glyph& gl = g_font.glyphs[static_cast<size_t>(f.glyph)];
            for (int c = gl.lb; c <= gl.rb; ++c)
                for (int r = 0; r < kCell; ++r)
                    if ((gl.col[c] >> r) & 1u)
                        ink[static_cast<size_t>(y0 + r) * W + f.x + c] = 0;
        }
    }
}

inline bool near5(uint32_t argb, uint16_t c15) {
    const int r = static_cast<int>((argb >> 16) & 255u) >> 3;
    const int g = static_cast<int>((argb >> 8) & 255u) >> 3;
    const int b = static_cast<int>(argb & 255u) >> 3;
    return std::abs(r - (c15 & 31)) <= 1 && std::abs(g - ((c15 >> 5) & 31)) <= 1 &&
           std::abs(b - ((c15 >> 10) & 31)) <= 1;
}

// The same 5 -> 6 -> 8 bit steps the 2D renderer takes, so an owned pixel's
// background matches its neighbours exactly.
inline unsigned to8(unsigned c5) {
    const unsigned c6 = c5 << 1;
    return (c6 << 2) | (c6 >> 4);
}

inline uint32_t mix(uint16_t bg, uint16_t ink, unsigned t) {
    uint32_t out = 0xFF000000u;
    for (int ch = 0; ch < 3; ++ch) {
        const unsigned a = to8((bg >> (ch * 5)) & 31u), b = to8((ink >> (ch * 5)) & 31u);
        const unsigned v = (a * (255u - t) + b * t + 127u) / 255u;
        out |= v << ((2 - ch) * 8);   // ARGB: red in bits 16-23
    }
    return out;
}

inline void disable(int screen) {
    ScreenOut& out = g_out[screen & 1];
    if (!out.on) return;
    out.on = false;
    out.hash = 0;
    nds_compute_host_set_hd_text(screen & 1, nullptr, nullptr, 0, 0);
}

// Reads the letters on the engine shown on this screen and hands the HD
// version to the compute host. True while the screen shows HD letters.
inline bool update(int screen, int engine, const uint32_t* native, int width, int scale) {
    screen &= 1;
    if (!g_font.tried) {
        g_font.tried = true;
        g_font.ok = load_font(g_acww_rom_path, g_font);
        if (g_font.ok)
            std::fprintf(stderr, "[acwwrecomp] HD letters: fontA read from the ROM (%zu letters)\n",
                         g_font.glyphs.size());
        else
            std::fprintf(stderr, "[acwwrecomp] HD letters: could not read fontA from the ROM\n");
    }
    if (!g_font.ok || !native || scale < 2 || width <= 0 || width > 448) {
        disable(screen);
        return false;
    }
    if (g_font.cov_scale != scale) build_coverage(g_font, scale);

    nds_gpu2d_read_fence();
    uint32_t dispcnt = 0;
    uint16_t bgcnt[4] = {}, bgx[4] = {}, bgy[4] = {};
    nds_gpu2d_text_regs(engine, &dispcnt, bgcnt, bgx, bgy);
    const uint8_t* palette = nds_vram_renderer_palette(engine);
    const NdsVramRendererView* view = nds_vram_renderer_view(engine);
    const uint32_t mode = dispcnt & 7u;

    std::vector<Owned> owned;
    int order[4] = {0, 1, 2, 3};   // back to front, so the front layer wins
    std::sort(order, order + 4, [&](int a, int b) {
        const int pa = bgcnt[a] & 3, pb = bgcnt[b] & 3;
        return pa != pb ? pa > pb : a > b;
    });
    for (int k = 0; k < 4; ++k) {
        const int bg = order[k];
        LayerScan& scan = g_scan[engine & 1][bg];
        const bool text_mode = bg < 2 || (bg == 2 && mode <= 1) || (bg == 3 && mode == 0);
        const bool shown = (dispcnt & (0x100u << bg)) != 0 && !(dispcnt & 0x80u);
        const bool is_3d = engine == 0 && bg == 0 && (dispcnt & 8u);
        if (!palette || !shown || !text_mode || is_3d || (bgcnt[bg] & 0x80u) ||
            (bgcnt[bg] & 0x40u)) {
            scan.sig.clear();
            scan.found.clear();
            continue;
        }
        int W = 256, H = 256;
        scan_layer(engine, bg, dispcnt, bgcnt[bg], palette, view, scan, W, H);
        for (const Found& f : scan.found) {
            const Glyph& gl = g_font.glyphs[static_cast<size_t>(f.glyph)];
            for (int r = 0; r < kCell; ++r) {
                const int sy = ((f.y + r - bgy[bg]) % H + H) % H;
                if (sy >= kScreenH) continue;
                for (int c = gl.lb; c <= gl.rb; ++c) {
                    const int sx = ((f.x + c - bgx[bg]) % W + W) % W;
                    if (sx >= width) continue;
                    const bool on = ((gl.row[r] >> c) & 1u) != 0;
                    if (!near5(native[static_cast<size_t>(sy) * width + sx], on ? f.ink : f.bg))
                        continue;
                    owned.push_back({sx, sy, f.glyph, r, c, f.ink, f.bg});
                }
            }
        }
    }
    if (owned.empty()) {
        disable(screen);
        return false;
    }

    uint64_t hash = 1469598103934665603ull ^ static_cast<uint64_t>(width * 131 + scale);
    for (const Owned& o : owned) {
        const uint64_t v = static_cast<uint64_t>(o.sx) | static_cast<uint64_t>(o.sy) << 9 |
                           static_cast<uint64_t>(o.glyph) << 17 | static_cast<uint64_t>(o.r) << 27 |
                           static_cast<uint64_t>(o.c) << 31 | static_cast<uint64_t>(o.ink) << 35 |
                           static_cast<uint64_t>(o.bg) << 50;
        hash = (hash ^ v) * 1099511628211ull;
    }
    ScreenOut& out = g_out[screen];
    if (out.on && out.hash == hash && out.width == width && out.scale == scale) return true;

    const int hw = width * scale;
    out.mask.assign(static_cast<size_t>(width) * kScreenH, 0);
    out.hd.assign(static_cast<size_t>(hw) * kScreenH * scale, 0);
    const int cw = kCell * scale;
    for (const Owned& o : owned) {
        out.mask[static_cast<size_t>(o.sy) * width + o.sx] = 1;
        const std::vector<uint8_t>& cov = g_font.cov[static_cast<size_t>(o.glyph)];
        for (int v = 0; v < scale; ++v) {
            const uint8_t* src = &cov[static_cast<size_t>(o.r * scale + v) * cw + o.c * scale];
            uint32_t* dst = &out.hd[static_cast<size_t>(o.sy * scale + v) * hw + o.sx * scale];
            for (int u = 0; u < scale; ++u) dst[u] = mix(o.bg, o.ink, src[u]);
        }
    }
    out.on = true;
    out.hash = hash;
    out.width = width;
    out.scale = scale;
    nds_compute_host_set_hd_text(screen, out.mask.data(), out.hd.data(), width, scale);
    return true;
}

}  // namespace acww_hdtext
