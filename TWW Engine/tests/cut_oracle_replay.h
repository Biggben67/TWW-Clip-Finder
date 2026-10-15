// cut_oracle_replay.h - drive each cut proc across the old sim's scenarios, one cut and one
// scenario at a time.
//
// Five procs over two decomp bodies: procCutL / procCutF / procCutR share one body over three HIO
// rows, procCutEA / procCutEB a second over two. Only `CutSpec::has_aim` forks on the shape. The
// claims live in test_cut_oracle.cpp (basic cuts) and test_cut_ender.cpp (enders).
//
// The oracle is the old sim, not the console: no banked capture has a frame in procs 0x42-0x44.
// Agreement means "the C++ reproduces the Python", not evidence about the console, and a misreading
// both share from the one decomp is invisible here. What it does catch is what is not copied
// arithmetic: the anim clock's seeding and attribute, the boundary's answers, the HIO row indexed,
// and the exit dispatch. A disagreement is a finding about the old sim first.
//
// Seeded from the entry row itself: none of these inits writes current.angle.y or a speed, so the
// entry row's shape_angle.y, current.angle.y and mNormalSpeed are what the init saw.
//
// Pad lead is 0: the old sim takes the pad as arguments to the frame that acts on it, so row i's
// `msd` / `target_angle` / `btn_*` are what row i's proc read. `wrong_pad_lead` is the control.

#ifndef TWW_ENGINE_TESTS_CUT_ORACLE_REPLAY_H
#define TWW_ENGINE_TESTS_CUT_ORACLE_REPLAY_H

#include <cstdint>
#include <string>
#include <vector>

#include "framework/json.h"

namespace tww_engine {
namespace testing {

//: Ordered by reach in the port list.
enum class CutKind { L, F, R, EA, EB };

//: Everything that differs between the five procs. The replay switches on `kind` only through
//: this and `run_init`.
struct CutSpec {
    CutKind kind;
    const char* golden;      //: golden file name
    const char* fn;          //: "procCutL" - used in every failure message
    int proc_id;             //: daPyProc_CUT_*_e
    int cut_type;            //: the daPy_CUT_TYPE setNormalCutAtParam is handed
    int sword_anm;           //: the .bck checkNormalSwordEquip's true arm asks for
    int sword_anm_ms;        //: ...and its false arm's, which no scenario here takes
    //: The blur buffer setBlurPosResource loads, or -1 for procCutF, whose init does not call it.
    //: -1 is also what the boundary's recorder reads when nothing asked.
    int blur_pos;
    //: The MOVE0 clock's end: field_0x2 on the basic cuts (18 for CUT_L, 19 for F and R), field_0x0
    //: on the enders (19 for both).
    int anim_end;
    //: What `wrong_anim_end` forces instead: another cut's own field_0x2.
    int wrong_end;
    //: What `wrong_anim_rate` forces: another shipped row's field_0x4. 1.0 for the basic cuts
    //: (against their 1.2); each ender takes the other's (0.9 for EA, 1.0 for EB), since 1.0 would
    //: be inert on procCutEA.
    //: `float` rather than `f32` so this header does not include the port's types.
    float wrong_rate;
    int exit_dir;            //: DIR_LEFT for procCutL and procCutEB, DIR_RIGHT for the other three
    //: What the decomp's body writes into m34C5: 4 / 2 / 3 for the basic cuts (the oracle writes 1
    //: for every cut type), 0 for the enders, which have no `swordTrigger() && m34C5 != 5` line.
    int m34C5_decomp;
    bool sets_cutf_tex;      //: procCutF alone drives mpCutfBpk / mpCutfBtk
    //: Whether the init takes changeCutProc's `sVar2`. The enders do not: changeCutProc drops it on
    //: the ender arm (d_a_player_sword.inc:425). No aim means no `cut_target` seed and no
    //: `wrong_init_aim` control.
    bool has_aim;
    //: The enders' post-anim countdown `mProcVar0.m34D0 = field_0x2`. Both shipped rows are 0.
    int hold;
};

//: Defined in the .cpp so the constants come from the port's headers.
const CutSpec& cut_spec(CutKind kind);

struct CutOracleOptions {
    //: Deliberately wrong twins, one at a time.
    //:
    //: speedF fed from the current row instead of the previous one. posMove writes speedF after the
    //: dispatch, so frame N's proc reads what posMove left at the end of N-1.
    bool wrong_speedf_lead = false;
    //: the stick and buttons taken from the previous row - the console replays' alignment, wrong
    //: against this oracle.
    bool wrong_pad_lead = false;
    //: the B hold dropped. Live in `b_held` (daPyFlg0_UNK4 routes it into CUT_TURN_CHARGE instead
    //: of WAIT), inert elsewhere.
    bool no_b_hold = false;
    //: the R hold dropped. Live in `r_at_the_exit`, where it makes checkNextMode(1) bail before the
    //: anim clock runs out.
    bool no_r_hold = false;
    //: entered with no sword equipped, which shuts checkNextActionFromButton's sword arm.
    bool no_sword_equipped = false;
    //: the init's aim taken from the stick target instead of the recorded `cut_target` - the other
    //: side of changeCutProc's `checkAttentionLock() || mStickDistance <= 0.05f ? shape_angle.y :
    //: m34E8`. Inert on the enders, so test_cut_ender.cpp does not register it.
    bool wrong_init_aim = false;
    //: the dispatch run before animeUpdate, so the exit test and checkPass read the previous
    //: frame's clock.
    bool proc_before_anim = false;
    //: the MOVE0 clock's end forced to `CutSpec::wrong_end`, applied after the init.
    bool wrong_anim_end = false;
    //: ...and its rate forced to `CutSpec::wrong_rate`.
    bool wrong_anim_rate = false;
    //: changeCutReverseProc answers true (the sword bounce), which returns before any compared
    //: column is written. The stub's default is false.
    bool cut_reverse_true = false;
};

struct CutOracleFrame {
    int frame = 0;
    int proc = 0;
    uint32_t nspeed_bits = 0;
    uint32_t anim_bits = 0;     //: MOVE0's J3DFrameCtrl frame - the golden's `anim_frame_hex`
    uint32_t rate_bits = 0;     //: ...its rate. No oracle column.
    int end = 0;                //: ...its end. No oracle column.
    int shape_angle_y = 0;
    int travel_angle = 0;
    //: The frame procCutF's body handed its two blade-flash animators. The old sim does not model
    //: them; they are held to the same row's MOVE0 clock, the decomp's own argument. -1 on the
    //: other cuts.
    uint32_t cutf_bpk_bits = 0;
    uint32_t cutf_btk_bits = 0;
};

//: One scenario, entry to exit.
struct CutOracleRun {
    std::string cut;            //: "procCutL"
    std::string name;
    std::string covers;
    int entry = 0;
    int exit = 0;
    std::vector<CutOracleFrame> rows;
    //: The proc on the frame the oracle left the cut: the one the port entered, or the one it
    //: named through a proc-init stub.
    int exit_proc = -1;
    bool exit_was_named = false;

    int unreached_called = 0;
    int precondition_broken = 0;
    int rnd_draws = 0;
    int rnd_draws_compared = 0;
    int anm_meta_missing = 0;
    //: What the init's boundary recorded.
    int sword_anim_idx = -1;
    int blur_pos_idx = -1;
    int cut_at_param_type = -1;
    int sword_cut_se = -1;
    uint32_t player_status0 = 0;
    //: The blade-flash animators as the init left them. procCutF's init seeds both from field_0x8
    //: (4.0); the other inits do not touch them.
    uint32_t cutf_bpk_init_bits = 0;
    uint32_t cutf_btk_init_bits = 0;
    //: The post-anim countdown as the init left it: field_0x2 on an ender, untouched on a basic cut.
    int hold_after_init = -1;
    //: The MOVE0 controller's attribute as setSingleMoveAnime left it, checked against the .bck's
    //: parsed header the golden carries.
    int anim_attribute = -1;
    //: The controller's start and end; `end` is field_0x2 and decides the run's length.
    int anim_start = -1;
    int anim_end = -1;

    //: m34C5 as the body left it, held to the decomp (4 / 2 / 3), never to the oracle (1).
    int m34C5 = -1;
};

std::vector<CutOracleRun> run_cut_oracle_replay(CutKind kind, const Json& golden,
                                                const CutOracleOptions& opt);

}  // namespace testing
}  // namespace tww_engine

#endif  // TWW_ENGINE_TESTS_CUT_ORACLE_REPLAY_H
