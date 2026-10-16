// The launcher's Mods page: Wild World's own options (launcher).
//
// recomp-ui draws the page from "features", each with an on/off switch and
// its own options. These come from settings.toml (graphics extras, Discord,
// backups) and from the mods in mods\, and go back into settings.toml when
// the launcher closes, so the game reads them exactly as before.
#pragma once

#include <algorithm>
#include <cctype>
#include <cstdint>
#include <cstdio>
#include <string>
#include <utility>
#include <vector>

#include "recomp_launcher.h"
#include "settings_file.h"

namespace acww {

struct Option {
    std::string id, label, description;
    int type = RECOMP_MOD_OPTION_BOOLEAN;
    std::string value, default_value;
    int64_t min = 0, max = 0, step = 1;
    std::vector<std::pair<std::string, std::string>> choices;   // value, label
};

struct Feature {
    std::string package, package_name, id, name, description, group;
    bool enabled = false;
    std::vector<Option> options;
};

class GameOptions {
public:
    void load(const SettingsFile& s, const std::vector<ModFile>& mods) {
        const std::string me = "acww", mine = "Wild World Recomped";
        add({me, mine, "smoothing_2d", "Sharp 2D smoothing",
             "Smooths menus, text and the sky with sharp xBR instead of showing the "
             "original pixels. G switches it while playing.", "Graphics",
             s.get("graphics", "smoothing_2d", "xbr") == "xbr", {}});
        add({me, mine, "hd_letters", "HD letters",
             "Redraws the game's letters as smooth strokes in chats, name tags and "
             "the pockets. T switches it while playing.", "Graphics",
             s.get_bool("graphics", "hd_letters", true), {}});
        const int strength = s.get_int("graphics", "texture_smoothing", 2);
        Option how{"strength", "Strength", "4x is sharper and costs more.",
                   RECOMP_MOD_OPTION_CHOICE, strength == 4 ? "4" : "2", "2", 0, 0, 1,
                   {{"2", "2x"}, {"4", "4x"}}};
        add({me, mine, "texture_smoothing", "Texture smoothing",
             "Smooths the textures on the 3D town, houses and characters.", "Graphics",
             strength > 1, {how}});

        Option names{"show_names", "Show player and town",
                     "\"Name of Town\" under where you are.", RECOMP_MOD_OPTION_BOOLEAN,
                     SettingsFile::flag(s.get_bool("discord", "show_names", true)), "true"};
        Option bells{"show_bells", "Show bells", "The bells in your wallet.",
                     RECOMP_MOD_OPTION_BOOLEAN,
                     SettingsFile::flag(s.get_bool("discord", "show_bells", true)), "true"};
        add({me, mine, "discord", "Discord presence",
             "Shows where you are in town and how long you have been playing on your "
             "Discord profile, while the Discord app is open.", "Discord",
             s.get_bool("discord", "presence", true), {names, bells}});

        const int keep = std::clamp(s.get_int("saves", "keep_backups", 30), 1, 100);
        Option count{"keep", "Backups to keep", "Older ones are deleted.",
                     RECOMP_MOD_OPTION_INTEGER, std::to_string(keep), "30", 1, 100, 1};
        add({me, mine, "backups", "Save backups",
             "Copies acww.sav into the backups folder every time the game starts.",
             "Saves", s.get_bool("saves", "backup_on_launch", true), {count}});

        for (const ModFile& mod : mods) {
            const std::string choice = s.get("mods", mod.id, "");
            Feature f{mod.id, mod.name, mod.id, mod.name, mod.description, "Gameplay",
                      mod.enabled, {}};
            std::string setting = mod.setting;
            if (choice == "on" || choice == "off") {
                f.enabled = choice == "on";
            } else if (std::find(mod.options.begin(), mod.options.end(), choice) !=
                       mod.options.end()) {
                f.enabled = true;
                setting = choice;
            }
            if (!mod.options.empty()) {
                if (std::find(mod.options.begin(), mod.options.end(), setting) ==
                    mod.options.end())
                    setting = mod.options.front();
                Option pick{"setting", "Setting", "", RECOMP_MOD_OPTION_CHOICE, setting,
                            mod.setting.empty() ? mod.options.front() : mod.setting};
                for (const std::string& name : mod.options) {
                    std::string label = name;
                    if (!label.empty()) label[0] = static_cast<char>(std::toupper(label[0]));
                    pick.choices.emplace_back(name, label);
                }
                f.options.push_back(pick);
            }
            add(f);
        }
    }

    void store(SettingsFile& s) const {
        for (const Feature& f : features_) {
            if (f.package != "acww") {
                std::string value = f.enabled ? "on" : "off";
                if (f.enabled && !f.options.empty()) value = f.options.front().value;
                s.set("mods", f.id, SettingsFile::text(value));
            } else if (f.id == "smoothing_2d") {
                s.set("graphics", "smoothing_2d", SettingsFile::text(f.enabled ? "xbr" : "off"));
            } else if (f.id == "hd_letters") {
                s.set("graphics", "hd_letters", SettingsFile::flag(f.enabled));
            } else if (f.id == "texture_smoothing") {
                s.set("graphics", "texture_smoothing", f.enabled ? f.options[0].value : "1");
            } else if (f.id == "discord") {
                s.set("discord", "presence", SettingsFile::flag(f.enabled));
                s.set("discord", "show_names", f.options[0].value);
                s.set("discord", "show_bells", f.options[1].value);
            } else if (f.id == "backups") {
                s.set("saves", "backup_on_launch", SettingsFile::flag(f.enabled));
                s.set("saves", "keep_backups", f.options[0].value);
            }
        }
    }

    RecompLauncherCModProvider provider() {
        RecompLauncherCModProvider p{};
        p.ctx = this;
        p.package_count = [](void* c) { return static_cast<int>(self(c)->packages_.size()); };
        p.package_get = package_get;
        p.set_enabled = [](void* c, const char* package, int on) {
            for (Feature& f : self(c)->features_)
                if (f.package == package) f.enabled = on != 0;
            return 1;
        };
        p.install_archive = [](void* c, const char*) {
            self(c)->error_ = "Installing mod packages comes in a later version.";
            return 0;
        };
        p.commit = [](void*, const char*) { return 1; };   // saved when the launcher closes
        p.last_error = [](void* c) { return self(c)->error_.c_str(); };
        p.feature_count = [](void* c) { return static_cast<int>(self(c)->features_.size()); };
        p.feature_get = feature_get;
        p.feature_option_get = option_get;
        p.feature_choice_get = choice_get;
        p.feature_enable = [](void* c, const char* package, const char* id, int on) {
            Feature* f = self(c)->find(package, id);
            if (f) f->enabled = on != 0;
            return f ? 1 : 0;
        };
        p.feature_set_option = set_option;
        return p;
    }

private:
    static GameOptions* self(void* ctx) { return static_cast<GameOptions*>(ctx); }

    template <size_t N>
    static void copy(char (&out)[N], const std::string& in) {
        std::snprintf(out, N, "%s", in.c_str());
    }

    void add(const Feature& f) {
        features_.push_back(f);
        for (const auto& p : packages_)
            if (p.first == f.package) return;
        packages_.emplace_back(f.package, f.package_name);
    }

    Feature* find(const char* package, const char* id) {
        for (Feature& f : features_)
            if (f.package == package && f.id == id) return &f;
        return nullptr;
    }

    Option* find_option(const char* package, const char* id, const char* option) {
        Feature* f = find(package, id);
        if (!f) return nullptr;
        for (Option& o : f->options)
            if (o.id == option) return &o;
        return nullptr;
    }

    static int package_get(void* c, int i, RecompLauncherCModPackage* out) {
        const auto& list = self(c)->packages_;
        if (i < 0 || i >= static_cast<int>(list.size())) return 0;
        *out = RecompLauncherCModPackage{};
        copy(out->id, list[i].first);
        copy(out->name, list[i].second);
        copy(out->version, "1.0");
        copy(out->author, "Mieszko (M.Stasiak)");
        out->enabled = 1;
        return 1;
    }

    static int feature_get(void* c, int i, RecompLauncherCModFeature* out) {
        const auto& list = self(c)->features_;
        if (i < 0 || i >= static_cast<int>(list.size())) return 0;
        const Feature& f = list[i];
        *out = RecompLauncherCModFeature{};
        copy(out->id, f.id);
        copy(out->package_id, f.package);
        copy(out->package_version, "1.0");
        copy(out->package_name, f.package_name);
        copy(out->name, f.name);
        copy(out->author, "Mieszko (M.Stasiak)");
        copy(out->description, f.description);
        copy(out->group, f.group);
        out->enabled = f.enabled ? 1 : 0;
        out->option_count = static_cast<int>(f.options.size());
        return 1;
    }

    static int option_get(void* c, const char* package, const char* id, int i,
                          RecompLauncherCModOption* out) {
        Feature* f = self(c)->find(package, id);
        if (!f || i < 0 || i >= static_cast<int>(f->options.size())) return 0;
        const Option& o = f->options[i];
        *out = RecompLauncherCModOption{};
        copy(out->id, o.id);
        copy(out->label, o.label);
        copy(out->description, o.description);
        copy(out->value, o.value);
        copy(out->default_value, o.default_value);
        out->type = o.type;
        out->min_value = o.min;
        out->max_value = o.max;
        out->step = o.step;
        out->choice_count = static_cast<int>(o.choices.size());
        return 1;
    }

    static int choice_get(void* c, const char* package, const char* id, const char* option,
                          int i, RecompLauncherCModChoice* out) {
        Option* o = self(c)->find_option(package, id, option);
        if (!o || i < 0 || i >= static_cast<int>(o->choices.size())) return 0;
        *out = RecompLauncherCModChoice{};
        copy(out->value, o->choices[i].first);
        copy(out->label, o->choices[i].second);
        return 1;
    }

    static int set_option(void* c, const char* package, const char* id, const char* option,
                          const char* value) {
        Option* o = self(c)->find_option(package, id, option);
        if (!o || !value) return 0;
        const std::string v = value;
        if (o->type == RECOMP_MOD_OPTION_BOOLEAN && v != "true" && v != "false") return 0;
        if (o->type == RECOMP_MOD_OPTION_CHOICE &&
            std::none_of(o->choices.begin(), o->choices.end(),
                         [&](const auto& ch) { return ch.first == v; }))
            return 0;
        if (o->type == RECOMP_MOD_OPTION_INTEGER) {
            try {
                const long long n = std::stoll(v);
                if (n < o->min || n > o->max) {
                    self(c)->error_ = o->label + " goes from " + std::to_string(o->min) +
                                      " to " + std::to_string(o->max) + ".";
                    return 0;
                }
            } catch (...) {
                return 0;
            }
        }
        o->value = v;
        return 1;
    }

    std::vector<std::pair<std::string, std::string>> packages_;   // id, name
    std::vector<Feature> features_;
    std::string error_;
};

}  // namespace acww
