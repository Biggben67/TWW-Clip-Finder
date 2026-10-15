// Generated from the zeldaret/tww decomp. Do not hand-edit.
// daPy_flags.inc - the mNoResetFlg0 / mNoResetFlg1 / mResetFlg0 bits the ported bodies
// name, picked from d_a_player.h by name. Each enum keeps its type, because the decomp's
// setters are typed.

#ifndef TWW_PORT_DAPY_FLAGS_INC
#define TWW_PORT_DAPY_FLAGS_INC

/// mNoResetFlg0
enum daPy_FLG0 {
    daPyFlg0_UNK4 = 0x00000004,
    daPyFlg0_UNK8 = 0x00000008,
    daPyFlg0_UNK80 = 0x00000080,
    daPyFlg0_CUT_AT_FLG = 0x00000040,
    daPyFlg0_UNK10000 = 0x00010000,
    daPyFlg0_UNK20000000 = 0x20000000,
    daPyFlg0_UNK80000000 = 0x80000000,
};

/// mNoResetFlg1
enum daPy_FLG1 {
    daPyFlg1_UNK200000 = 0x00200000,
    daPyFlg1_UNK4000000 = 0x04000000,
    daPyFlg1_NPC_CALL_COMMAND = 0x00000002,
    daPyFlg1_FORCE_VOMIT_JUMP = 0x00000010,
    daPyFlg1_FORCE_VOMIT_JUMP_SHORT = 0x00010000,
    daPyFlg1_UNK100000 = 0x00100000,
    daPyFlg1_UNK80 = 0x00000080,
    daPyFlg1_CONFUSE = 0x00000100,
    daPyFlg1_UNK800000 = 0x00800000,
    daPyFlg1_UNK1000000 = 0x01000000,
    daPyFlg1_UNK10000000 = 0x10000000,
    daPyFlg1_SOUP_POWER_UP = 0x00008000,
};

/// mResetFlg0, cleared every frame in execute()
enum daPy_RFLG0 {
    daPyRFlg0_UNK1 = 0x00000001,
    daPyRFlg0_UNK2 = 0x00000002,
    daPyRFlg0_UNK8 = 0x00000008,
    daPyRFlg0_UNK10 = 0x00000010,
    daPyRFlg0_UNK80 = 0x00000080,
    daPyRFlg0_RIGHT_FOOT_ON_GROUND = 0x00000400,
    daPyRFlg0_LEFT_FOOT_ON_GROUND = 0x00000800,
    daPyRFlg0_UNK40000 = 0x00040000,
    daPyRFlg0_SUBJECT_ACCEPT = 0x04000000,
    daPyRFlg0_NOT_ATTACKING = 0x08000000,
    daPyRFlg0_CRAWL_AUTO_MOVE = 0x00001000,
    daPyRFlg0_ORIGINAL_HAT_ANIM = 0x00800000,
};

#endif
