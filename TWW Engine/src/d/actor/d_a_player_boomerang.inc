// Generated from the zeldaret/tww decomp. Do not hand-edit.
// d_a_player_boomerang.inc - checkBoomerangAnime (d_a_player_boomerang.inc:18-21).


/* 8014956C-80149590       .text checkBoomerangAnime__9daPy_lk_cCFv */
BOOL daPy_lk_c::checkBoomerangAnime() const {
    return checkBoomerangReadyAnime() || checkBoomerangThrowAnime();
}
