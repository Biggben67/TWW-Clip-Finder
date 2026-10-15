// manifest.h - the port manifest: one row per proc the setup finder needs, and how far this
// repo has got with it.
//
//   rows, `extracted`  the generated port list: the procs the finder's block catalog enters.
//   `compiles`         `TWWE_LINKED` below; an odr-use, so an undefined name fails to link.
//   0-ULP columns      the ledger, filled by the comparison loops, keyed by the frame's proc
//                      (from the console capture) and the golden's tier.
//
// The ledger is armed only for cases expected to pass, so a red control cannot add coverage.

#ifndef TWW_ENGINE_TESTS_MANIFEST_H
#define TWW_ENGINE_TESTS_MANIFEST_H

#include <string>
#include <vector>

#include "framework/golden.h"

namespace tww_engine {
namespace testing {

/// Open or close the ledger. `run_all` arms it for Green cases and closes it for Red ones.
void ledger_arm(bool armed);

/// One frame of one proc held to one oracle. `bits` counts bit comparisons; integer comparisons
/// are counted separately so they do not inflate the bit total.
void ledger_record(int proc, Tier tier, int bits, int ints);

/// Publish the list `TWWE_LINKED` proved links. Called once at static init, so `compiles`
/// describes the binary rather than the cases that ran.
void linked_publish(const std::vector<std::string>& names);

/// The same, for functions that are not procs - the subsystem rows' `compiles` column.
/// A separate list because the proc list must equal what is extracted from
/// `d_a_player_main.cpp`, while this one need only be a subset of the subsystem rows.
void linked_other_publish(const std::vector<std::string>& names);

/// The port list: the procs the finder's block catalog dispatches, with their `extracted` column.
const Json& port_list();

/// Is `proc` a row of the port list - a proc the finder's block catalog actually enters?
bool port_list_has_proc(int proc);

/// The manifest table, printed after every run. Returns the number of rows (procs) it holds.
int print_manifest();

/// `procX` for every port-list row whose `extracted` column is non-empty; compared against what
/// actually linked.
const std::vector<std::string>& extracted_functions();

/// Every function name the subsystem rows say is extracted.
const std::vector<std::string>& subsystem_extracted_functions();

/// Every function name the subsystem rows say is carried rather than extracted: the decomp body
/// is assembly, so the C++ was transcribed by hand and is checked only by its own 0-ULP gate.
const std::vector<std::string>& subsystem_carried_functions();

/// Credit a subsystem with console evidence that is not proc-shaped (e.g. plane normals read
/// from live RAM for a function no replayed frame enters). `what` is printed verbatim. Armed
/// with the frame ledger.
void ledger_record_subsystem(const std::string& subsystem, Tier tier, const std::string& what);

/// Subsystem rows credited by more than one case. The ledger is a map, so a second credit
/// replaces the first; this lets the suite fail on that instead of hiding it.
std::vector<std::string> subsystems_credited_more_than_once();

/// Every `what` handed to `ledger_record_subsystem` for one row, in run order.
std::vector<std::string> subsystem_claims(const std::string& subsystem);

/// What actually linked, by name.
const std::vector<std::string>& linked_functions();

/// What `linked_other_publish` was handed.
const std::vector<std::string>& linked_other_functions();

/// Make a function's address escape, so the linker has to resolve it. `(void)&C::f` alone is
/// optimized away with no relocation, so an undefined or never-pulled-in function would still
/// read `compiles yes`. Defined out of line so the compiler cannot see the argument is unused.
void linked_odr_use(const void* addr, unsigned long size);

/// Always false, defined out of line so no caller can see it. Guards the dead call in
/// `TWWE_LINKED_VIRTUAL`, which the linker must still resolve.
bool linked_never_taken();

}  // namespace testing
}  // namespace tww_engine

//: Prove one ported function is defined in the linked binary, and append its name to `sink`.
//: Takes the address (an odr-use) rather than `sizeof`, so a declared-but-undefined proc fails
//: to link. The sink is the caller's so a red control cannot pollute the shared manifest.
#define TWWE_LINKED(sink, name)                                                                 \
    do {                                                                                        \
        auto fn_ = &daPy_lk_c::name;                                                            \
        tww_engine::testing::linked_odr_use(&fn_, sizeof(fn_));                                 \
        (sink).push_back(#name);                                                                \
    } while (0)

//: The same for a function that is not `daPy_lk_c`'s (`cLib_addCalc`, `J3DFrameCtrl::update`).
//: `name` is the manifest's key; `expr` is how C++ spells it.
#define TWWE_LINKED_OTHER(sink, name, expr)                                                     \
    do {                                                                                        \
        auto fn_ = expr;                                                                        \
        tww_engine::testing::linked_odr_use(&fn_, sizeof(fn_));                                 \
        (sink).push_back(name);                                                                 \
    } while (0)

//: The same for a virtual function. `&C::f` on a virtual yields a vcall thunk with no relocation,
//: so instead a qualified call (no virtual dispatch, direct relocation) is written against a null
//: pointer and guarded by `linked_never_taken()` - never executed, but the linker must resolve it.
#define TWWE_LINKED_VIRTUAL(sink, name, call)                                                       do {                                                                                                if (tww_engine::testing::linked_never_taken()) {                                                    (void)(call);                                                                               }                                                                                               (sink).push_back(name);                                                                     } while (0)

#endif  // TWW_ENGINE_TESTS_MANIFEST_H
