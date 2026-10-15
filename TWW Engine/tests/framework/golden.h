// golden.h - loading a golden, and recording what kind of oracle it is.
//
//   CONSOLE   a capture of the running game: the correctness tier.
//   SIM       the old sim's own output, frozen: the regression tier, bugs included. Not evidence
//             of correctness.
//   DISC      the game's own shipped data (a room's .dzb): an input, not an oracle.
//
// The tier and each file's sha256 live in the manifest, one row per file with the evidence that
// settled it; the digest is checked at load. The runner prints the tier split every run.

#ifndef TWW_ENGINE_TESTS_GOLDEN_H
#define TWW_ENGINE_TESTS_GOLDEN_H

#include <string>
#include <vector>

#include "framework/json.h"

namespace tww_engine {
namespace testing {

enum class Tier {
    Console,  //: captured off the running game - the correctness tier
    Sim,      //: the old sim's own output, frozen - the regression tier
    Disc,     //: the game's own shipped data - an input, not an oracle
};

struct GoldenInfo {
    std::string name;
    Tier tier = Tier::Sim;
    std::string source;    //: `console@<anchor>` or `sim@<commit>`
    std::string evidence;  //: what settled the tier, quoted from the producer
};

/// Load a golden by manifest name. Aborts with a named reason on any failure (missing file, bad
/// digest, unknown name), so a skipped golden cannot report green.
const Json& golden(const std::string& name);

/// The tier of a golden this run has already loaded; dies if it has not.
Tier golden_tier(const std::string& name);

/// What the run loaded, in load order; the runner's tier split comes from this.
const std::vector<GoldenInfo>& loaded();

/// Every row of the manifest, including files that are catalogued but not copied here.
const std::vector<GoldenInfo>& manifest_rows();

/// Rows the manifest marks as belonging to a subsystem this repo does not contain.
int manifest_out_of_scope_count();

}  // namespace testing
}  // namespace tww_engine

#endif  // TWW_ENGINE_TESTS_GOLDEN_H
