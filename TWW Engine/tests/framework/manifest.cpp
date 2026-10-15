#include "framework/manifest.h"

#include <algorithm>
#include <cctype>
#include <cstdio>
#include <map>
#include <string>
#include <vector>

#include "framework/json.h"

#ifndef TWWE_REPO_ROOT
#error "TWWE_REPO_ROOT must be defined by the build - the port list is found relative to the repo."
#endif

namespace tww_engine {
namespace testing {
namespace {

struct Cover {
    int console_frames = 0;
    int console_bits = 0;
    int console_ints = 0;
    int sim_frames = 0;
    int sim_bits = 0;
    int sim_ints = 0;
};

bool g_armed = false;
std::map<int, Cover>& cover() {
    static std::map<int, Cover> c;
    return c;
}

std::vector<std::string>& linked_mut() {
    static std::vector<std::string> v;
    return v;
}

std::vector<std::string>& linked_other_mut() {
    static std::vector<std::string> v;
    return v;
}

std::vector<std::string>& extracted_mut() {
    static std::vector<std::string> v;
    return v;
}

std::map<std::string, std::pair<Tier, std::string>>& sub_cover() {
    static std::map<std::string, std::pair<Tier, std::string>> m;
    return m;
}

//: Every credit a case made, in run order; `sub_cover()` keeps only the last per row.
std::vector<std::pair<std::string, std::string>>& sub_claims() {
    static std::vector<std::pair<std::string, std::string>> v;
    return v;
}

std::vector<std::string>& sub_carried_mut() {
    static std::vector<std::string> v;
    return v;
}

std::vector<std::string>& sub_extracted_mut() {
    static std::vector<std::string> v;
    return v;
}

const char* short_enum(const std::string& e) {
    // `daPyProc_FRONT_ROLL_e` -> `FRONT_ROLL`, for a column that fits next to the numbers.
    static std::string buf;
    buf = e;
    const std::string pre = "daPyProc_";
    if (buf.compare(0, pre.size(), pre) == 0) {
        buf = buf.substr(pre.size());
    }
    if (buf.size() > 2 && buf.compare(buf.size() - 2, 2, "_e") == 0) {
        buf = buf.substr(0, buf.size() - 2);
    }
    return buf.c_str();
}

bool linked_anywhere(const std::string& name) {
    return std::find(linked_mut().begin(), linked_mut().end(), name) != linked_mut().end() ||
           std::find(linked_other_mut().begin(), linked_other_mut().end(), name) !=
               linked_other_mut().end();
}

/// The subsystem rows: the engine surface beside the proc dispatch.
///
///   `reached`    instructions this subsystem's decomp files contribute to the DOL closure from
///                the procs; `+n` is what only an extra root (not reached by any proc) adds.
///   `extracted`  spans copied out of those files.
///   `compiles`   at least one of them odr-used by this binary.
///   `0 ULP vs`   the case that credited the row via `ledger_record_subsystem`.
///
/// A row with no decomp file (the FP toolchain, the finder's own layers) prints `-`.
int print_subsystems(const Json& subs) {
    const Json& rows = subs["rows"];
    std::printf("\n-- and the engine surface beside them: what a real finder run enters --\n");
    std::printf("   %-22s %-4s %12s %7s  %-9s %-8s %s\n", "subsystem", "runs", "reached",
                "lines", "extracted", "compiles", "0 ULP vs");

    int done = 0;
    for (size_t i = 0; i < rows.size(); i++) {
        const Json& row = rows[i];

        // In the generator's own run order, which is the order the runs happened.
        std::string runs;
        for (size_t k = 0; k < row["entered_in"].size(); k++) {
            const std::string& r = row["entered_in"][k].str;
            runs += char(std::toupper(r.empty() ? '?' : r[0]));
        }

        int extracted = 0, carried = 0, compiles_extracted = 0, compiles_carried = 0;
        for (size_t k = 0; k < row["extracted"].size(); k++) {
            extracted++;
            if (linked_anywhere(row["extracted"][k].str)) {
                compiles_extracted++;
            }
        }
        // A row whose decomp bodies are `asm {}` has nothing to extract, so it reads `carried`.
        for (size_t k = 0; k < row["carried"].size(); k++) {
            carried++;
            if (linked_anywhere(row["carried"][k].str)) {
                compiles_carried++;
            }
        }
        const int compiles = compiles_extracted + compiles_carried;

        // Credited only by a case that ran the code (`ledger_record_subsystem`), never inferred
        // from the DOL closure: the port stubs some paths the DOL takes and calls others directly,
        // so its call graph is not the DOL's. `compiles > 0` still gates the credit.
        std::string gated = "-";
        std::map<std::string, std::pair<Tier, std::string>>::const_iterator sc =
            sub_cover().find(row["name"].str);
        if (compiles > 0 && sc != sub_cover().end()) {
            gated = (sc->second.first == Tier::Console ? "console, " : "old sim, ") +
                    sc->second.second;
            done++;
        }

        // `N` is what the procs reach; `N +M` adds what only an extra root reaches.
        char budget[64];
        const long long all = row["reached_instr"].as_int();
        const long long from_procs = row["reached_instr_procs"].as_int();
        if (row["decomp"].size() == 0) {
            std::snprintf(budget, sizeof budget, "%s", "-");
        } else if (all != from_procs) {
            std::snprintf(budget, sizeof budget, "%lld +%lld", from_procs, all - from_procs);
        } else {
            std::snprintf(budget, sizeof budget, "%lld", all);
        }

        char lines[32];
        if (row["decomp"].size() == 0) {
            std::snprintf(lines, sizeof lines, "%s", "-");
        } else {
            std::snprintf(lines, sizeof lines, "%lld", row["decomp_lines"].as_int());
        }

        std::printf("   %-22s %-4s %12s %7s  %-9s %-8s %s\n", row["name"].str.c_str(),
                    runs.c_str(), budget, lines,
                    extracted ? "yes" : (carried ? "carried" : ""), compiles ? "yes" : "",
                    gated.c_str());
    }

    const Json& res = subs["residual"];
    std::printf("   reached is instructions in the decomp files this row owns, off the DOL "
                "closure from the 22 procs;\n   `+n` is what only a root no proc reaches adds "
                "(%zu such root(s) - see extra_roots). A row with `-`\n   has no decomp file at "
                "all: the toolchain's arithmetic, and the finder's own layers.\n",
                subs["extra_roots"].size());
    std::printf("   %lld more instruction(s) over %lld decomp file(s) are reached and claimed by "
                "no row above:\n   audio, particles, rendering, the heap. The old sim models "
                "none of them and holds 0 ULP.\n",
                res["instr"].as_int(), res["files"].as_int());
    return done;
}

}  // namespace

/// The port list, loaded once. A missing file aborts: an empty manifest would read like success.
const Json& port_list() {
    static Json doc;
    static bool done = false;
    if (!done) {
        const std::string path = std::string(TWWE_REPO_ROOT) + "/tests/port_list.json";
        std::string err;
        if (!Json::load(path, &doc, &err)) {
            std::printf("FATAL: the port list will not load: %s\n"
                        "  It is the manifest's only source of rows. Without it this run cannot "
                        "say what is left.\n", err.c_str());
            std::fflush(stdout);
            std::abort();
        }
        for (size_t i = 0; i < doc["procs"].size(); i++) {
            const Json& row = doc["procs"][i];
            for (size_t k = 0; k < row["extracted"].size(); k++) {
                extracted_mut().push_back(row["extracted"][k].str);
            }
        }
        const Json& rows = doc["subsystems"]["rows"];
        for (size_t i = 0; i < rows.size(); i++) {
            for (size_t k = 0; k < rows[i]["extracted"].size(); k++) {
                sub_extracted_mut().push_back(rows[i]["extracted"][k].str);
            }
            for (size_t k = 0; k < rows[i]["carried"].size(); k++) {
                sub_carried_mut().push_back(rows[i]["carried"][k].str);
            }
        }
        done = true;
    }
    return doc;
}


void ledger_arm(bool armed) { g_armed = armed; }

void ledger_record_subsystem(const std::string& subsystem, Tier tier, const std::string& what) {
    if (!g_armed) {
        return;
    }
    sub_cover()[subsystem] = std::make_pair(tier, what);
    sub_claims().push_back(std::make_pair(subsystem, what));
}

std::vector<std::string> subsystems_credited_more_than_once() {
    std::map<std::string, int> n;
    for (size_t i = 0; i < sub_claims().size(); i++) {
        n[sub_claims()[i].first]++;
    }
    std::vector<std::string> out;
    for (std::map<std::string, int>::const_iterator it = n.begin(); it != n.end(); ++it) {
        if (it->second > 1) {
            out.push_back(it->first);
        }
    }
    return out;
}

std::vector<std::string> subsystem_claims(const std::string& subsystem) {
    std::vector<std::string> out;
    for (size_t i = 0; i < sub_claims().size(); i++) {
        if (sub_claims()[i].first == subsystem) {
            out.push_back(sub_claims()[i].second);
        }
    }
    return out;
}

void ledger_record(int proc, Tier tier, int bits, int ints) {
    if (!g_armed) {
        return;
    }
    Cover& c = cover()[proc];
    if (tier == Tier::Console) {
        c.console_frames++;
        c.console_bits += bits;
        c.console_ints += ints;
    } else {
        c.sim_frames++;
        c.sim_bits += bits;
        c.sim_ints += ints;
    }
}

void linked_publish(const std::vector<std::string>& names) { linked_mut() = names; }

void linked_other_publish(const std::vector<std::string>& names) { linked_other_mut() = names; }

const std::vector<std::string>& extracted_functions() {
    port_list();
    return extracted_mut();
}

const std::vector<std::string>& subsystem_carried_functions() {
    port_list();
    return sub_carried_mut();
}

const std::vector<std::string>& subsystem_extracted_functions() {
    port_list();
    return sub_extracted_mut();
}

const std::vector<std::string>& linked_functions() { return linked_mut(); }

const std::vector<std::string>& linked_other_functions() { return linked_other_mut(); }

void linked_odr_use(const void* addr, unsigned long size) {
    // Accumulated so the optimizer cannot drop the argument; only the call site's relocation
    // matters.
    static volatile unsigned long sink = 0;
    const unsigned char* p = static_cast<const unsigned char*>(addr);
    unsigned long acc = 0;
    for (unsigned long i = 0; i < size; i++) {
        acc += p[i];
    }
    sink = sink + acc;
}

bool linked_never_taken() { return false; }

bool port_list_has_proc(int proc) {
    const Json& procs = port_list()["procs"];
    for (size_t i = 0; i < procs.size(); i++) {
        if (int(procs[i]["id"].as_int()) == proc) {
            return true;
        }
    }
    return false;
}

int print_manifest() {
    const Json& doc = port_list();
    const Json& procs = doc["procs"];

    std::printf("\n-- the port manifest: what the finder's catalog asks for, and how far this "
                "repo has got --\n");
    std::printf("   %zu block(s) over %zu seed(s), stepped through the old sim at %s\n",
                size_t(doc["blocks_stepped"].as_int()), doc["seeds"].size(),
                doc["provenance"]["old_sim_commit"].str.c_str());
    std::printf("   %-6s %-18s %-20s %7s  %-9s %-8s %s\n",
                "id", "proc", "function", "blocks", "extracted", "compiles", "0 ULP vs");

    int done = 0;
    for (size_t i = 0; i < procs.size(); i++) {
        const Json& row = procs[i];
        const int id = int(row["id"].as_int());
        const std::string fn = row["fn"].str;

        const bool extracted = row["extracted"].size() > 0;
        const bool compiles =
            std::find(linked_mut().begin(), linked_mut().end(), fn) != linked_mut().end();

        std::string gated = "-";
        std::map<int, Cover>::const_iterator it = cover().find(id);
        if (it != cover().end()) {
            char buf[128];
            if (it->second.console_frames > 0) {
                std::snprintf(buf, sizeof buf, "console %d frame(s), %d bit(s)",
                              it->second.console_frames, it->second.console_bits);
            } else {
                std::snprintf(buf, sizeof buf, "OLD SIM %d frame(s), %d bit(s)",
                              it->second.sim_frames, it->second.sim_bits);
            }
            gated = buf;
            done++;
        }

        std::printf("   0x%02X   %-18s %-20s %7d  %-9s %-8s %s\n", id, short_enum(row["enum"].str),
                    fn.c_str(), int(row["blocks"].as_int()), extracted ? "yes" : "",
                    compiles ? "yes" : "", gated.c_str());
    }

    const int subs_done = print_subsystems(doc["subsystems"]);
    const size_t n_subs = doc["subsystems"]["rows"].size();

    std::printf("\n   %d of %zu proc(s) and %d of %zu subsystem(s) held to an oracle by this "
                "run.\n   What is left is the rows with no oracle.\n",
                done, procs.size(), subs_done, n_subs);
    std::printf("   %zu more proc(s) the old sim models were NOT dispatched by this catalog "
                "sweep;\n   it runs from a standstill on flat ground with no walls, so a "
                "collision-only proc cannot appear.\n", doc["not_reached"].size());
    return int(procs.size());
}

}  // namespace testing
}  // namespace tww_engine
