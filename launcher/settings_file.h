// settings.toml and the mod files, read and written line by line (launcher).
//
// Only what those files use: [sections], [[arrays]], key = value with plain
// strings, booleans and whole numbers, and # comments. Writing changes just
// the value, so comments and layout stay as the player left them.
#pragma once

#include <cstdint>
#include <filesystem>
#include <fstream>
#include <string>
#include <vector>

namespace acww {

inline std::string trim(const std::string& s) {
    const size_t a = s.find_first_not_of(" \t");
    if (a == std::string::npos) return "";
    return s.substr(a, s.find_last_not_of(" \t") - a + 1);
}

// Where a line's value ends: at a # comment outside quotes, or the line's end.
inline size_t value_end(const std::string& line, size_t from) {
    bool quoted = false;
    for (size_t i = from; i < line.size(); ++i) {
        if (quoted && line[i] == '\\') ++i;   // \" and \\ inside a string
        else if (line[i] == '"') quoted = !quoted;
        else if (line[i] == '#' && !quoted) return i;
    }
    return line.size();
}

// A "string" without its quotes, with \\ and \" turned back into \ and ".
inline std::string unquote(const std::string& v) {
    if (v.size() < 2 || v.front() != '"' || v.back() != '"') return v;
    std::string out;
    for (size_t i = 1; i + 1 < v.size(); ++i) {
        if (v[i] == '\\' && i + 2 < v.size()) ++i;
        out += v[i];
    }
    return out;
}

// "[mod]" -> "mod", "[[option.patch]]" -> "option.patch"
inline std::string section_name(const std::string& t) {
    const size_t a = t.find_first_not_of('[');
    const size_t b = t.find(']', a);
    return trim(t.substr(a, b == std::string::npos ? std::string::npos : b - a));
}

class SettingsFile {
public:
    bool load(const std::filesystem::path& path) {
        lines_.clear();
        std::ifstream file(path, std::ios::binary);
        if (!file) return false;
        std::string line;
        while (std::getline(file, line)) {
            if (!line.empty() && line.back() == '\r') line.pop_back();
            lines_.push_back(line);
        }
        return true;
    }

    bool save(const std::filesystem::path& path) const {
        std::ofstream file(path, std::ios::binary | std::ios::trunc);
        for (const std::string& line : lines_) file << line << "\n";
        return static_cast<bool>(file);
    }

    std::string get(const std::string& section, const std::string& key,
                    const std::string& fallback) const {
        size_t at = 0;
        if (!find(section, key, &at)) return fallback;
        const std::string& line = lines_[at];
        const size_t start = line.find('=') + 1;
        return unquote(trim(line.substr(start, value_end(line, start) - start)));
    }

    bool get_bool(const std::string& section, const std::string& key, bool fallback) const {
        const std::string v = get(section, key, "");
        return v == "true" ? true : v == "false" ? false : fallback;
    }

    int get_int(const std::string& section, const std::string& key, int fallback) const {
        const std::string v = get(section, key, "");
        try {
            size_t used = 0;
            const int n = std::stoi(v, &used);
            if (used == v.size()) return n;
        } catch (...) {
        }
        return fallback;
    }

    // value goes in as written: text("xbr"), flag(true), std::to_string(3).
    void set(const std::string& section, const std::string& key, const std::string& value) {
        size_t at = 0;
        if (find(section, key, &at)) {
            std::string& line = lines_[at];
            size_t start = line.find('=') + 1;
            while (start < line.size() && line[start] == ' ') ++start;
            const size_t end = value_end(line, start);
            const std::string comment = line.substr(end);
            std::string middle = value;
            if (!comment.empty()) {   // keep the comment in its column
                const size_t room = end - start;
                middle += std::string(room > value.size() ? room - value.size() : 1, ' ');
            }
            line = line.substr(0, start) + middle + comment;
            return;
        }
        size_t insert_at = lines_.size();
        bool have_section = false;
        std::string current;
        for (size_t i = 0; i < lines_.size(); ++i) {
            const std::string t = trim(lines_[i]);
            if (!t.empty() && t[0] == '[') {
                current = section_name(t);
                if (current == section) {
                    have_section = true;
                    insert_at = i + 1;
                }
            } else if (current == section && !t.empty() && t[0] != '#') {
                insert_at = i + 1;
            }
        }
        if (!have_section) {
            if (!lines_.empty() && !trim(lines_.back()).empty()) lines_.push_back("");
            lines_.push_back("[" + section + "]");
            insert_at = lines_.size();
        }
        lines_.insert(lines_.begin() + static_cast<std::ptrdiff_t>(insert_at), key + " = " + value);
    }

    // A TOML string: Windows paths need their backslashes doubled.
    static std::string text(const std::string& s) {
        std::string out = "\"";
        for (char c : s) {
            if (c == '\\' || c == '"') out += '\\';
            out += c;
        }
        return out + "\"";
    }
    static std::string flag(bool b) { return b ? "true" : "false"; }

private:
    bool find(const std::string& section, const std::string& key, size_t* at) const {
        std::string current;
        for (size_t i = 0; i < lines_.size(); ++i) {
            const std::string t = trim(lines_[i]);
            if (t.empty() || t[0] == '#') continue;
            if (t[0] == '[') {
                current = section_name(t);
                continue;
            }
            const size_t eq = t.find('=');
            if (current == section && eq != std::string::npos && trim(t.substr(0, eq)) == key) {
                *at = i;
                return true;
            }
        }
        return false;
    }

    std::vector<std::string> lines_;
};

// A mod in mods\: its name, the comment at the top of the file as its
// description, its own defaults, and the names of its [[option]] tables.
struct ModFile {
    std::string id;
    std::string name;
    std::string description;
    bool enabled = false;
    std::string setting;
    std::vector<std::string> options;
};

inline bool read_mod_file(const std::filesystem::path& path, ModFile* mod) {
    std::ifstream file(path, std::ios::binary);
    if (!file) return false;
    mod->id = path.stem().string();
    mod->name = mod->id;
    std::string line, section;
    bool in_header = true;
    while (std::getline(file, line)) {
        if (!line.empty() && line.back() == '\r') line.pop_back();
        const std::string t = trim(line);
        if (in_header) {
            if (t.size() > 1 && t[0] == '#') {
                if (!mod->description.empty()) mod->description += ' ';
                mod->description += trim(t.substr(1));
                continue;
            }
            in_header = false;   // the first paragraph only
        }
        if (t.empty() || t[0] == '#') continue;
        if (t[0] == '[') {
            section = section_name(t);
            if (section == "option") mod->options.emplace_back();
            continue;
        }
        const size_t eq = t.find('=');
        if (eq == std::string::npos) continue;
        const std::string key = trim(t.substr(0, eq));
        const std::string value = unquote(trim(t.substr(eq + 1, value_end(t, eq + 1) - eq - 1)));
        if (section == "mod" && key == "name") mod->name = value;
        else if (section == "mod" && key == "enabled") mod->enabled = value == "true";
        else if (section == "mod" && key == "setting") mod->setting = value;
        else if (section == "option" && key == "name" && !mod->options.empty())
            mod->options.back() = value;
    }
    return true;
}

}  // namespace acww
