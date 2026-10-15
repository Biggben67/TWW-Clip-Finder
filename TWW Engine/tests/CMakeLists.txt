# The suite: one binary, so a run prints one tier split over every golden it loaded.
add_executable(tww_engine_tests
  framework/runner.cpp
  framework/json.cpp
  framework/sha256.cpp
  framework/golden.cpp
  framework/manifest.cpp
  link_disc.cpp
  player_rig.cpp
  roll_replay.cpp
  test_roll_replay.cpp
  cut_replay.cpp
  test_cut_a.cpp
  cut_turn_replay.cpp
  test_cut_turn.cpp
  cut_turn_charge_replay.cpp
  test_cut_turn_charge.cpp
  cut_oracle_replay.cpp
  test_cut_oracle.cpp
  test_cut_ender.cpp
  cut_turn_move_replay.cpp
  test_cut_turn_move.cpp
  jump_land_replay.cpp
  test_back_jump.cpp
  test_jump_cut.cpp
  crawl_replay.cpp
  test_crawl.cpp
  test_crawl_pos.cpp
  turn_atn_replay.cpp
  test_turn_atn.cpp
  test_free_wait.cpp
  test_calc_pla.cpp
  test_ground_cross.cpp
  test_roof_chk.cpp
  room_dzb.cpp
  recorded_list.cpp
  test_ground_walk.cpp
  test_poly_through.cpp
  test_wall_correct.cpp
  wall_probes.cpp
  wall_walk.cpp
  test_wall_walk.cpp
  line_walk.cpp
  test_line_check.cpp
  test_crr_pos.cpp
  test_ground_pos.cpp
  test_anm_track.cpp
  test_anm_joints.cpp
  test_quat.cpp
  test_tr_matrix.cpp
  test_calc_anm_mtx.cpp
  test_foot_term.cpp
  test_foot_ik.cpp
  test_walk_slope.cpp
  test_stairs_roll.cpp
  test_seed_by_a_wall.cpp
  test_ps_inverse.cpp
  test_cam_next_mode.cpp
  test_cam_mode_machine.cpp
  test_cam_boundary_census.cpp
  test_cam_csangle.cpp
  test_cam_subject_entry.cpp
  test_cam_subject_exit.cpp
  test_cam_l_held.cpp
  test_cam_turnarounds.cpp
  test_session_camera.cpp
  test_threads.cpp
)
# Optional; absent from a public checkout.
if(EXISTS ${CMAKE_CURRENT_SOURCE_DIR}/test_port_manifest.cpp)
  target_sources(tww_engine_tests PRIVATE test_port_manifest.cpp)
endif()
# test_threads.cpp needs -pthread on g++ and clang.
find_package(Threads REQUIRED)
target_link_libraries(tww_engine_tests PRIVATE tww_engine_port Threads::Threads)
target_include_directories(tww_engine_tests PRIVATE ${CMAKE_CURRENT_SOURCE_DIR})

# Goldens are found relative to the repo, not the working directory.
target_compile_definitions(tww_engine_tests PRIVATE
  TWWE_REPO_ROOT="${CMAKE_CURRENT_SOURCE_DIR}/..")

add_test(NAME suite COMMAND tww_engine_tests)

# Kept out of the suite: `cam_exit_probe` runs the camera past the end of the first-person view,
# an arm known to crash.
add_executable(cam_exit_probe EXCLUDE_FROM_ALL cam_exit_probe.cpp)
target_link_libraries(cam_exit_probe PRIVATE tww_engine_port)
target_include_directories(cam_exit_probe PRIVATE ${CMAKE_CURRENT_SOURCE_DIR})
if(WIN32)
  target_link_libraries(cam_exit_probe PRIVATE dbghelp)
endif()
