#include "framework/golden.h"

#include <cstdio>
#include <cstdlib>
#include <map>

#include "framework/sha256.h"

#ifndef TWWE_REPO_ROOT
#error "TWWE_REPO_ROOT must be defined by the build - the goldens are found relative to it, not to cwd"
#endif

namespace tww_engine {
namespace testing {
namespace {

std::string repo_root() { return std::string(TWWE_REPO_ROOT); }
std::string goldens_dir() { return repo_root() + "/tests/goldens"; }

[[noreturn]] void die(const std::string& why) {
    // A golden that cannot be loaded is fatal, not a skip.
    std::fprintf(stderr, "\nGOLDEN: %s\n", why.c_str());
    std::exit(2);
}

/// An unknown tier word is fatal rather than defaulted to a tier.
Tier tier_of(const std::string& word) {
    if (word == "console") {
        return Tier::Console;
    }
    if (word == "sim") {
        return Tier::Sim;
    }
    if (word == "disc") {
        return Tier::Disc;
    }
    die("manifest tier '" + word + "' is not console, sim or disc");
}

struct Store {
    Json manifest;
    std::vector<GoldenInfo> rows;
    int out_of_scope = 0;
    std::map<std::string, Json> files;
    std::vector<GoldenInfo> loaded;

    Store() {
        std::string err;
        const std::string path = goldens_dir() + "/manifest.json";
        if (!Json::load(path, &manifest, &err)) {
            die(err);
        }
        const Json& list = manifest["goldens"];
        for (size_t i = 0; i < list.size(); i++) {
            const Json& r = list[i];
            GoldenInfo info;
            info.name = r["name"].str;
            if (r["copied"].boolean) {
                info.tier = tier_of(r["tier"].str);
                info.source = r["source"].str;
                info.evidence = r["evidence"].str;
            } else {
                out_of_scope++;
                info.source = "not copied: " + r["subsystem"].str;
            }
            rows.push_back(info);
        }
    }

    const Json& load(const std::string& name) {
        auto it = files.find(name);
        if (it != files.end()) {
            return it->second;
        }

        const Json& list = manifest["goldens"];
        const Json* row = nullptr;
        for (size_t i = 0; i < list.size(); i++) {
            if (list[i]["name"].str == name) {
                row = &list[i];
                break;
            }
        }
        if (!row) {
            die(name + " is not in the manifest. Add it with its tier and the evidence that "
                       "settled the tier.");
        }
        if (!(*row)["copied"].boolean) {
            die(name + " is catalogued but not copied into this repo: " + (*row)["subsystem"].str +
                ".");
        }

        const std::string path = goldens_dir() + "/" + name;
        std::FILE* f = std::fopen(path.c_str(), "rb");
        if (!f) {
            die("cannot open " + path);
        }
        std::string text;
        char buf[1 << 16];
        size_t n;
        while ((n = std::fread(buf, 1, sizeof buf, f)) > 0) {
            text.append(buf, n);
        }
        std::fclose(f);

        const std::string got = sha256_hex(text);
        const std::string want = (*row)["sha256"].str;
        if (got != want) {
            die(name + " does not match the manifest's digest.\n  manifest " + want + "\n  file     " +
                got + "\n  A golden is data, copied unchanged. Either it was edited here - which "
                "moves the target instead of fixing the engine - or the old repo's copy changed "
                "and the manifest needs re-deriving.");
        }

        Json parsed;
        std::string err;
        if (!Json::parse(text, &parsed, &err)) {
            die(path + ": " + err);
        }

        GoldenInfo info;
        info.name = name;
        info.tier = tier_of((*row)["tier"].str);
        info.source = (*row)["source"].str;
        info.evidence = (*row)["evidence"].str;
        loaded.push_back(info);

        return files.emplace(name, std::move(parsed)).first->second;
    }
};

Store& store() {
    static Store s;
    return s;
}

}  // namespace

const Json& golden(const std::string& name) { return store().load(name); }
Tier golden_tier(const std::string& name) {
    for (const GoldenInfo& g : store().loaded) {
        if (g.name == name) {
            return g.tier;
        }
    }
    die(name + " has not been loaded by this run, so it has no tier here. Tier is a property of "
               "an oracle this run actually read.");
}

const std::vector<GoldenInfo>& loaded() { return store().loaded; }
const std::vector<GoldenInfo>& manifest_rows() { return store().rows; }
int manifest_out_of_scope_count() { return store().out_of_scope; }

}  // namespace testing
}  // namespace tww_engine
