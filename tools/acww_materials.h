// Material tags (runner): which of the game's textures are water or a
// waterfall, so the HD renderer can draw them with effects of its own
// (tools/patch_materials.py), and the settings for how those look.
//
// A texture is known by a hash of its texels (not its palette or where it
// sits in VRAM), so a tag keeps working wherever and whenever the game loads
// that texture. The tags and settings live in materials.toml:
//
//   [look]
//   tint = 0.85
//   [water]
//   1a2b3c4d5e6f7081 = "64x64, format 3"
//   [waterfall]
//   ...
//
// The texture picker writes that file: with ACWW_TEXTURE_PICK=1 (play.ps1
// -Pick), [ and ] step through the textures on screen, largest first, and
// the chosen one flashes; M marks it as water, F as a waterfall, H as hidden
// and B as under the water: our water covers it completely instead of letting
// see-through of it show (again to unmark). O turns the effects off and on to
// compare, and R reads
// materials.toml again, so the [look] numbers can be changed while playing.
// While picking, a texture of the same size and format drawn in exactly the
// same place as tagged water the frame before is tagged too (learn), which
// finds the water's other animation frames: stand still by the water for a
// few seconds. A layer of another size or format is marked by hand.
// ACWW_MATERIALS names another file, and ACWW_WATER=off starts with the
// effects off.
//
// The renderer calls these on its own thread; the frontend only queues key
// presses and takes the notice to show.
#pragma once

#include <algorithm>
#include <atomic>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <map>
#include <mutex>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <vector>

namespace acww_materials {

enum : uint32_t { kNone = 0, kWater = 1, kFalls = 2, kHide = 3, kUnder = 4, kHighlight = 255 };

// The [look] settings, in the order the shader reads them (AcwwLook, four
// to a vec4). Colours are 0-255.
struct LookSetting {
    const char* name;
    float value;
    const char* note;
};
constexpr int kLookCount = 16;
inline const LookSetting kLookDefaults[kLookCount] = {
    {"swell", 1.0f, "how much the broad waves light and shade the water"},
    {"wave-size", 1.0f, "wave size: 2 is twice as big"},
    {"wave-speed", 1.0f, "how fast the water moves"},
    {"mirror", 0.25f, "how much sky the water reflects, more in the distance"},
    {"glints", 1.0f, "how bright the glints are"},
    {"glint-amount", 1.0f, "how many glints there are: 0 to about 2"},
    {"keep-texture", 0.0f, "how much of the game's own water pattern shows: 0 to 1"},
    {"tint", 0.85f, "how much the water takes the tint colour: 0 keeps the game's blue"},
    {"tint-red", 64.0f, "the tint colour"},
    {"tint-green", 124.0f, "the tint colour"},
    {"tint-blue", 128.0f, "the tint colour"},
    {"falls-streaks", 1.0f, "how strong the waterfall's streaks and foam are"},
    {"falls-speed", 0.6f, "how fast they fall; negative if they run the wrong way"},
    {"opacity", 1.0f, "how solid the water is: below 1 is clearer, above 1 hides what is under it"},
    {"see-through", 0.25f, "how much of what the game draws under the water shows: 0 to 1"},
    {"spare-3", 0.0f, "not used yet"},
};

struct Tag {
    uint32_t material = kNone;
    std::string note;   // what the picker saw: size and format
};

struct Seen {
    uint64_t hash;
    int width, height, format;   // a width of 0 is a polygon with no texture:
    long long area;   // screen pixels its polygons' boxes cover this frame
    int alpha = 0, id = 0;       // then these say which
    uint32_t colour = 0;
};

struct State {
    bool loaded = false;
    std::string path;
    std::map<uint64_t, Tag> tags;
    float look[kLookCount] = {};
    std::atomic<uint32_t> version{1};   // bumped when the tags change
    std::atomic<bool> effects{true};
    // the picker
    bool picker = false;
    uint64_t selected = 0;
    std::vector<Seen> frame;
    std::unordered_map<uint64_t, size_t> frame_index;
    std::atomic<int> step{0}, toggle{0}, reload{0};
    // learning: where water was drawn last frame, by polygon shape
    std::unordered_map<uint64_t, uint32_t> spots, last_spots;
    std::unordered_set<uint64_t> rejected;   // unmarked this session: never learned again
    int learned = 0;
    std::atomic<uint32_t> mark{kNone};
    std::mutex notice_mutex;
    std::string notice;
};

inline State& state() {
    static State s;
    return s;
}

inline const char* material_name(uint32_t m) {
    return m == kWater ? "water" : m == kFalls ? "waterfall" : m == kHide ? "hide"
         : m == kUnder ? "under-water" : "";
}

inline uint32_t material_from_name(const std::string& name) {
    return name == "water" ? kWater : name == "waterfall" ? kFalls : name == "hide" ? kHide
         : name == "under-water" ? kUnder : kNone;
}

// A polygon with no texture is known by its kind, alpha and polygon ID (its
// polygon attributes without the lighting and culling bits), with the top
// bit set so it can't be mistaken for a texture.
inline uint64_t plain_key(uint32_t attr) {
    return (uint64_t(1) << 63) | uint64_t(attr & 0x3F1F0030u);
}

inline std::string trim(const std::string& s) {
    size_t a = s.find_first_not_of(" \t\r\n");
    if (a == std::string::npos) return std::string();
    size_t b = s.find_last_not_of(" \t\r\n");
    return s.substr(a, b - a + 1);
}

// Reads materials.toml into the tags and the look settings.
inline void read_file() {
    State& s = state();
    s.tags.clear();
    for (int i = 0; i < kLookCount; ++i) s.look[i] = kLookDefaults[i].value;
    std::ifstream file(s.path);
    std::string line, section;
    while (std::getline(file, line)) {
        const size_t hash_mark = line.find('#');
        if (hash_mark != std::string::npos && line.find('"') == std::string::npos) line = line.substr(0, hash_mark);
        line = trim(line);
        if (line.empty() || line[0] == '#') continue;
        if (line[0] == '[') {
            const size_t end = line.find(']');
            section = trim(line.substr(1, end == std::string::npos ? std::string::npos : end - 1));
            continue;
        }
        const size_t eq = line.find('=');
        if (eq == std::string::npos) continue;
        const std::string key = trim(line.substr(0, eq));
        const std::string value = trim(line.substr(eq + 1));
        if (section == "look") {
            for (int i = 0; i < kLookCount; ++i)
                if (key == kLookDefaults[i].name) s.look[i] = std::strtof(value.c_str(), nullptr);
            continue;
        }
        const uint32_t material = material_from_name(section);
        if (material == kNone) continue;
        char* stop = nullptr;
        const uint64_t hash = std::strtoull(key.c_str(), &stop, 16);
        if (key.empty() || !stop || *stop != '\0' || hash == 0) continue;
        Tag tag;
        tag.material = material;
        tag.note = value;
        if (tag.note.size() >= 2 && tag.note.front() == '"' && tag.note.back() == '"')
            tag.note = tag.note.substr(1, tag.note.size() - 2);
        s.tags[hash] = tag;
    }
}

inline void load() {
    State& s = state();
    if (s.loaded) return;
    s.loaded = true;
    const char* path = std::getenv("ACWW_MATERIALS");
    s.path = path && path[0] ? path : "materials.toml";
    const char* pick = std::getenv("ACWW_TEXTURE_PICK");
    s.picker = pick && pick[0] && std::strcmp(pick, "0") != 0;
    const char* water = std::getenv("ACWW_WATER");
    if (water && (std::strcmp(water, "off") == 0 || std::strcmp(water, "0") == 0)) s.effects = false;
    read_file();
    std::fprintf(stderr, "[acwwrecomp] %zu material tag(s) from %s%s\n", s.tags.size(), s.path.c_str(),
                 s.picker ? "; texture picker on: [ and ] choose, M water, F waterfall, H hide, "
                            "O effects off/on, R reload" : "");
}

inline bool save() {
    State& s = state();
    std::FILE* f = std::fopen(s.path.c_str(), "wb");
    if (!f) return false;
    std::fputs("# Wild World Recomped material tags, written by the texture picker\n"
               "# (play.ps1 -Pick). [look] says how the effects look: change a number\n"
               "# and press R in the game to see it. The other lines are the game's\n"
               "# textures, by a hash of their texels, with their size and format.\n"
               "\n[look]\n", f);
    for (int i = 0; i < kLookCount; ++i)
        if (std::strncmp(kLookDefaults[i].name, "spare", 5) != 0)
            std::fprintf(f, "%s = %g   # %s\n", kLookDefaults[i].name, s.look[i], kLookDefaults[i].note);
    for (uint32_t material : {kWater, kFalls, kHide, kUnder}) {
        std::fprintf(f, "\n[%s]\n", material_name(material));
        for (const auto& [hash, tag] : s.tags)
            if (tag.material == material)
                std::fprintf(f, "%016llx = \"%s\"\n", static_cast<unsigned long long>(hash), tag.note.c_str());
    }
    std::fclose(f);
    return true;
}

inline uint32_t version() {
    load();
    return state().version.load();
}

inline uint32_t material_for(uint64_t hash) {
    load();
    const auto it = state().tags.find(hash);
    return it == state().tags.end() ? kNone : it->second.material;
}

inline float look(int i) {
    load();
    return state().look[i];
}

inline bool picker_enabled() {
    load();
    return state().picker;
}

inline bool effects_on() {
    return state().effects.load();
}

// Frontend: queue a key press for the renderer's next frame.
inline void press_step(int direction) { state().step += direction; }
inline void press_mark(uint32_t material = kWater) { state().mark = material; }
inline void press_toggle() { state().toggle += 1; }
inline void press_reload() { state().reload += 1; }

inline std::string take_notice() {
    State& s = state();
    std::lock_guard<std::mutex> lock(s.notice_mutex);
    std::string notice;
    notice.swap(s.notice);
    return notice;
}

inline void set_notice(const std::string& text) {
    State& s = state();
    std::lock_guard<std::mutex> lock(s.notice_mutex);
    s.notice = text;
}

// Renderer: the frame's polygons are noted between begin_frame and end_frame.
inline uint64_t begin_frame() {
    State& s = state();
    s.frame.clear();
    s.frame_index.clear();
    return s.picker ? s.selected : 0;
}

inline void note(uint64_t hash, int width, int height, int format, long long area) {
    State& s = state();
    const auto it = s.frame_index.find(hash);
    if (it != s.frame_index.end()) {
        s.frame[it->second].area += area;
        return;
    }
    s.frame_index[hash] = s.frame.size();
    s.frame.push_back(Seen{hash, width, height, format, area});
}

// Renderer, picker only: a polygon with no texture.
inline void note_plain(uint64_t key, int alpha, int id, int r, int g, int b, long long area) {
    State& s = state();
    const auto it = s.frame_index.find(key);
    if (it != s.frame_index.end()) {
        s.frame[it->second].area += area;
        return;
    }
    s.frame_index[key] = s.frame.size();
    Seen seen{key, 0, 0, 0, area};
    seen.alpha = alpha;
    seen.id = id;
    seen.colour = uint32_t((r & 63) << 12 | (g & 63) << 6 | (b & 63));
    s.frame.push_back(seen);
}

inline std::string describe(const Seen& seen) {
    char text[96];
    if (seen.width == 0)
        std::snprintf(text, sizeof(text), "no texture, alpha %d, ID %d, colour %d %d %d", seen.alpha, seen.id,
                      int(seen.colour >> 12) * 4, int((seen.colour >> 6) & 63) * 4, int(seen.colour & 63) * 4);
    else
        std::snprintf(text, sizeof(text), "%dx%d, format %d", seen.width, seen.height, seen.format);
    return text;
}

// Renderer, picker only: a polygon drawn exactly where water (or a waterfall)
// was drawn last frame, with an untagged texture of the same size and format,
// is the water's next animation frame, so its texture is tagged the same.
// (Any size and format catches the river banks too.) A texture unmarked with
// M or F isn't learned again. Returns the polygon's material.
inline uint32_t learn(int xmin, int xmax, int ytop, int ybot, int vertices, uint32_t size_format,
                      uint64_t hash, uint32_t material, int width, int height, int format) {
    State& s = state();
    if (!s.picker || !hash) return material;
    const uint64_t key = (uint64_t(xmin & 0xFFF)) | (uint64_t(xmax & 0xFFF) << 12) | (uint64_t(ytop & 0xFFF) << 24) |
                         (uint64_t(ybot & 0xFFF) << 36) | (uint64_t(vertices & 0xF) << 48) |
                         (uint64_t(size_format & 0x1FF) << 52);
    if (material == kWater || material == kFalls) {
        s.spots[key] = material;
        return material;
    }
    if (material != kNone) return material;
    const auto it = s.last_spots.find(key);
    if (it == s.last_spots.end() || s.rejected.count(hash)) return material;
    char note[64];
    std::snprintf(note, sizeof(note), "%dx%d, format %d, learned", width, height, format);
    s.tags[hash] = Tag{it->second, note};
    s.version += 1;
    s.learned += 1;
    s.spots[key] = it->second;
    return it->second;
}

inline void end_frame() {
    load();
    State& s = state();
    if (!s.picker) return;
    s.last_spots.swap(s.spots);
    s.spots.clear();
    if (s.learned) {
        char learned[96];
        std::snprintf(learned, sizeof(learned), "Learned %d more water texture(s)%s", s.learned,
                      save() ? "" : " (couldn't write materials.toml)");
        set_notice(learned);
        s.learned = 0;
    }
    std::sort(s.frame.begin(), s.frame.end(), [](const Seen& a, const Seen& b) { return a.area > b.area; });
    const int count = static_cast<int>(s.frame.size());
    int at = -1;
    for (int i = 0; i < count; ++i)
        if (s.frame[i].hash == s.selected) at = i;

    char text[160];
    if (const int step = s.step.exchange(0)) {
        // Past either end there's no choice, so nothing flashes.
        const int next = at < 0 ? (step > 0 ? step - 1 : count + step) : at + step;
        if (next < 0 || next >= count) {
            s.selected = 0;
            set_notice(count ? "No texture chosen" : "No textures on screen");
        } else {
            const Seen& seen = s.frame[next];
            s.selected = seen.hash;
            const uint32_t material = material_for(seen.hash);
            std::snprintf(text, sizeof(text), "Texture %d of %d: %s, %016llx%s%s", next + 1, count,
                          describe(seen).c_str(), static_cast<unsigned long long>(seen.hash),
                          material ? " - " : "", material_name(material));
            set_notice(text);
        }
    }
    if (const uint32_t mark = s.mark.exchange(kNone)) {
        if (!s.selected) {
            set_notice("Choose a texture with [ and ] first");
        } else {
            std::string note = "picked";
            for (const Seen& seen : s.frame)
                if (seen.hash == s.selected) note = describe(seen);
            const bool unmark = material_for(s.selected) == mark;
            if (unmark) {
                s.tags.erase(s.selected);
                s.rejected.insert(s.selected);
            } else {
                s.tags[s.selected] = Tag{mark, note};
                s.rejected.erase(s.selected);
            }
            s.version += 1;
            const bool saved = save();
            const std::string what = mark == kHide ? (unmark ? "Shown again" : "Hidden")
                                                   : std::string(unmark ? "Not " : "Marked as ") + material_name(mark);
            std::snprintf(text, sizeof(text), "%s: %016llx%s", what.c_str(),
                          static_cast<unsigned long long>(s.selected),
                          saved ? "" : " (couldn't write materials.toml)");
            set_notice(text);
        }
    }
    if (s.toggle.exchange(0)) {
        s.effects = !s.effects.load();
        set_notice(s.effects ? "Water effects: on" : "Water effects: off");
    }
    if (s.reload.exchange(0)) {
        read_file();
        s.version += 1;
        std::snprintf(text, sizeof(text), "Read %s again: %zu tag(s)", s.path.c_str(), s.tags.size());
        set_notice(text);
    }
}

}  // namespace acww_materials
