// Generated from the zeldaret/tww decomp. Do not hand-edit.
// player_status.inc - daPy__PlayerStatus0 and daPy__PlayerStatus1, whole
// (d_com_inf_game.h:37-77, 79-100).

#ifndef TWW_PORT_PLAYER_STATUS_INC
#define TWW_PORT_PLAYER_STATUS_INC

enum daPy__PlayerStatus0 {
    daPyStts0_UNK1_e           = 0x00000001,
    daPyStts0_UNK2_e           = 0x00000002,
    daPyStts0_UNK4_e           = 0x00000004,
    daPyStts0_UNK10_e          = 0x00000010,
    daPyStts0_UNK20_e          = 0x00000020,
    daPyStts0_UNK40_e          = 0x00000040,
    daPyStts0_UNK80_e          = 0x00000080, // Maybe inside a Baba Bud before being spat out?
    daPyStts0_HANG_e           = 0x00000100,
    daPyStts0_UNK200_e         = 0x00000200,
    daPyStts0_UNK400_e         = 0x00000400,
    daPyStts0_UNK800_e         = 0x00000800,
    daPyStts0_BOW_AIM_e        = 0x00001000,
    daPyStts0_SUBJECT_e        = 0x00002000, // First person
    daPyStts0_HOOKSHOT_AIM_e   = 0x00004000,
    daPyStts0_SWORD_SWING_e    = 0x00008000,
    daPyStts0_SHIP_RIDE_e      = 0x00010000,
    daPyStts0_ROPE_AIM_e       = 0x00020000,
    daPyStts0_UNK40000_e       = 0x00040000,
    daPyStts0_BOOMERANG_AIM_e  = 0x00080000,
    daPyStts0_SWIM_e           = 0x00100000,
    daPyStts0_TELESCOPE_LOOK_e = 0x00200000,
    daPyStts0_BOOMERANG_WAIT_e = 0x00400000,
    daPyStts0_UNK800000_e      = 0x00800000,
    daPyStts0_UNK1000000_e     = 0x01000000,
    daPyStts0_UNK2000000_e     = 0x02000000,
    daPyStts0_UNK4000000_e     = 0x04000000,
    daPyStts0_CRAWL_e          = 0x08000000,
    daPyStts0_UNK10000000_e    = 0x10000000,
    daPyStts0_UNK20000000_e    = 0x20000000,
    daPyStts0_SPIN_ATTACK_e    = 0x40000000,
    daPyStts0_UNK80000000_e    = 0x80000000,

    // This is some combination of flags which is seemingly related to "judgement", used in dAttention_c
    daPyStts0_UNK37a02371_e    = daPyStts0_UNK1_e | daPyStts0_UNK10_e | daPyStts0_UNK20_e
                                 | daPyStts0_UNK40_e | daPyStts0_HANG_e | daPyStts0_UNK200_e
                                 | daPyStts0_SUBJECT_e| daPyStts0_TELESCOPE_LOOK_e
                                 | daPyStts0_UNK800000_e | daPyStts0_UNK1000000_e
                                 | daPyStts0_UNK2000000_e | daPyStts0_UNK4000000_e
                                 | daPyStts0_UNK10000000_e | daPyStts0_UNK20000000_e
};

enum daPy__PlayerStatus1 {
    daPyStts1_WIND_WAKER_CONDUCT_e = 0x00000001,
    daPyStts1_UNK2_e               = 0x00000002,
    daPyStts1_UNK4_e               = 0x00000004,
    daPyStts1_PICTO_BOX_AIM_e      = 0x00000008,
    daPyStts1_UNK10_e              = 0x00000010,
    daPyStts1_DEKU_LEAF_FLY_e      = 0x00000020,
    daPyStts1_DEKU_LEAF_FAN_e      = 0x00000040,
    daPyStts1_UNK80_e              = 0x00000080,
    daPyStts1_UNK100_e             = 0x00000100,
    daPyStts1_UNK200_e             = 0x00000200,
    daPyStts1_SAIL_e               = 0x00000400,
    daPyStts1_UNK800_e             = 0x00000800,
    daPyStts1_UNK1000_e            = 0x00001000,
    daPyStts1_UNK2000_e            = 0x00002000,
    daPyStts1_UNK4000_e            = 0x00004000,
    daPyStts1_UNK8000_e            = 0x00008000,
    daPyStts1_UNK10000_e           = 0x00010000,
    daPyStts1_UNK20000_e           = 0x00020000,
    daPyStts1_UNK40000_e           = 0x00040000,
    daPyStts1_UNK80000_e           = 0x00080000,
};

#endif
