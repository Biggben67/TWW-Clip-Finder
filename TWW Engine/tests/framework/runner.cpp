#include "framework/runner.h"

#include <cstdio>
#include <cstring>
#include <string>

#include "framework/golden.h"
#include "framework/manifest.h"
#include "link_disc.h"

namespace tww_engine {
namespace testing {

void Case::check_bits(uint32_t got, uint32_t want, const std::string& where) {
    checks_++;
    bit_checks_++;
    if (got == want) {
        return;
    }
    char buf[256];
    std::snprintf(buf, sizeof buf, "  %s: 0x%08X, expected 0x%08X  (%.9g vs %.9g)\n",
                  where.c_str(), got, want, double(from_bits(got)), double(from_bits(want)));
    log_ += buf;
    failures_++;
}

void Case::check_int(long long got, long long want, const std::string& where) {
    checks_++;
    if (got == want) {
        return;
    }
    char buf[256];
    std::snprintf(buf, sizeof buf, "  %s: %lld, expected %lld\n", where.c_str(), got, want);
    log_ += buf;
    failures_++;
}

void Case::fail(const std::string& why) {
    log_ += "  " + why + "\n";
    failures_++;
}

void Case::known_gap(bool ok, const std::string& what) {
    checks_++;
    if (!ok) {
        return;  // still a gap: nothing to report
    }
    log_ += "  KNOWN GAP HAS CLOSED: " + what +
            "\n  It passes now. Unmark it (EXPECT_KNOWN_GAP -> REQUIRE_*) so it starts being "
            "gated instead of being excused.\n";
    failures_++;
}

std::vector<Registration>& registry() {
    static std::vector<Registration> r;
    return r;
}

int run_all(const char* filter) {
    auto& reg = registry();
    int ran = 0, green = 0, bad = 0, checks = 0, bit_checks = 0;

    std::printf("tww_engine suite - %zu case(s) registered\n\n", reg.size());

    for (const Registration& r : reg) {
        if (filter && *filter && !std::strstr(r.name, filter)) {
            continue;
        }
        Case c(r.name);
        // The coverage ledger counts only cases expected to pass, never red controls.
        ledger_arm(r.expect == Expect::Green);
        r.body(c);
        ledger_arm(false);
        ran++;
        checks += c.checks();
        bit_checks += c.bit_checks();

        const bool failed = c.failures() > 0;
        const bool want_red = r.expect == Expect::Red;

        if (want_red) {
            // A red control that fails is doing its job. Print its notes (measurements), not its
            // failure log (the injected value's own complaints).
            if (failed) {
                std::printf("REJECTED  %-38s %s\n", r.name, r.what);
                std::fputs(c.notes().c_str(), stdout);
                green++;
            } else {
                std::printf("ACCEPTED  %-38s %s\n", r.name, r.what);
                std::printf("  This control injects a value that is wrong and the suite did not "
                            "notice.\n  Nothing else in this run means anything until that is "
                            "fixed.\n");
                bad++;
            }
            continue;
        }

        if (!failed) {
            std::printf("PASS      %-38s %d assertion(s), %d of them bit comparisons\n",
                        r.name, c.checks(), c.bit_checks());
            std::fputs(c.notes().c_str(), stdout);
            green++;
        } else {
            std::printf("FAIL      %-38s %d of %d assertion(s)\n", r.name, c.failures(),
                        c.checks());
            std::printf("          %s\n", r.what);
            std::fputs(c.notes().c_str(), stdout);
            std::fputs(c.log().c_str(), stdout);
            bad++;
        }
    }

    // The tier split over the goldens this run loaded: agreeing with the Python sim is not
    // agreeing with the console.
    int console = 0, sim = 0, disc = 0;
    std::printf("\n-- the oracles this run was gated against --\n");
    for (const GoldenInfo& g : loaded()) {
        const char* t = g.tier == Tier::Console ? "console" : g.tier == Tier::Disc ? "disc" : "sim";
        std::printf("  %-8s %-38s %s\n", t, g.name.c_str(), g.source.c_str());
        (g.tier == Tier::Console ? console : g.tier == Tier::Disc ? disc : sim)++;
    }
    if (loaded().empty()) {
        std::printf("  (none)\n");
    }
    std::printf("  %d correctness-tier (console), %d regression-tier (old sim), %d input (disc, "
                "no claim).\n", console, sim, disc);
    if (sim > 0 && console == 0) {
        std::printf("  Every oracle in this run is the old sim's own output. This run can say the "
                    "C++\n  reproduces the Python, including its bugs. It cannot say the engine is "
                    "right.\n");
    }
    std::printf("  %d more golden(s) are catalogued and not copied - subsystems this repo does "
                "not contain.\n", manifest_out_of_scope_count());

    // A report, not a gate; `the_manifest_is_not_lying` gates it.
    print_manifest();

    std::printf("\n%d case(s), %d as expected, %d wrong; %d assertion(s), %d of them bit "
                "comparisons\n", ran, green, bad, checks, bit_checks);
    // A run of nothing (a mistyped filter) is not a pass.
    if (ran == 0) {
        std::printf("GATE RED  the filter %s matched no case. A run of nothing is not a pass.\n",
                    filter[0] == 0 ? "(none)" : filter);
        return 1;
    }
    std::printf("%s\n", bad == 0 ? "GATE GREEN" : "GATE RED");
    return bad == 0 ? 0 : 1;
}

}  // namespace testing
}  // namespace tww_engine

int main(int argc, char** argv) {
    const char* filter = argc > 1 ? argv[1] : "";
    // Link's model and animations come off the disc; without one the whole suite is skipped.
    tww_engine::LinkAssets assets;
    std::string why;
    if (!tww_engine::testing::read_link_assets(&assets, &why) ||
        !tww_engine::installLinkAssets(assets, &why)) {
        std::printf("tww_engine suite - SKIPPED: %s\n", why.c_str());
        std::printf("Put the path of a GZLJ01 disc image on the first line of %s.\n",
                    tww_engine::testing::iso_path_file().c_str());
        return 0;
    }
    // The goldens and the port list are not distributed; without them the whole suite is skipped.
    for (const char* rel : {"tests/goldens/manifest.json", "tests/port_list.json"}) {
        std::FILE* f = std::fopen((std::string(TWWE_REPO_ROOT) + "/" + rel).c_str(), "rb");
        if (!f) {
            std::printf("tww_engine suite - SKIPPED: %s is not here\n", rel);
            return 0;
        }
        std::fclose(f);
    }
    return tww_engine::testing::run_all(filter);
}
