cmake_minimum_required(VERSION 3.20)
project(tww_engine CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# ---------------------------------------------------------------------------------------------
# Floating-point contract. The game's arithmetic is Gekko single precision as mwcc emitted it:
# fused only where the disassembly shows `fmadds` (spelled out in `engine/ppc_fp.h`). A compiler
# that contracts changes the bits with no diagnostic, so an unknown compiler is refused.
#   MSVC       /fp:precise (the default; set so it is a contract)
#   gcc/clang  -ffp-contract=off (clang contracts by default; ARM64 has FMA in the baseline)
# ---------------------------------------------------------------------------------------------
if(MSVC)
  add_compile_options(/fp:precise /EHsc)
elseif(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
  add_compile_options(-ffp-contract=off)
else()
  message(FATAL_ERROR
    "Unknown compiler '${CMAKE_CXX_COMPILER_ID}'. This project's arithmetic depends on the "
    "compiler not contracting multiply-adds, and there is no portable way to ask for that. "
    "Teach this file the flag for your compiler.")
endif()

# -------------------------------------------------------------------------------- the engine
# A character-identical copy of the decomp, so it stays in the global namespace;
# `namespace tww_engine` is for this repo's own code on top of it.
add_library(tww_engine_port STATIC
  src/d/actor/d_a_player_main.cpp
  src/JSystem/J3DGraphAnimator/J3DAnimation.cpp
  src/JSystem/J3DGraphBase/J3DTransform.cpp
  src/JSystem/JMath/JMath.cpp
  src/SSystem/SComponent/c_lib.cpp
  src/SSystem/SComponent/c_m3d.cpp
  src/SSystem/SComponent/c_m2d.cpp
  src/SSystem/SComponent/c_math.cpp
  src/SSystem/SComponent/c_angle.cpp
  src/d/d_cam_param.cpp
  src/d/d_cam_style.cpp
  src/d/d_cam_type.cpp
  src/d/d_camera.cpp
  src/d/d_camera_collision.cpp
  src/m_Do/m_Do_mtx.cpp
  src/SSystem/SComponent/c_m3d_g_cyl.cpp
  src/SSystem/SComponent/c_bg_w.cpp
  src/SSystem/SComponent/c_bg_s_lin_chk.cpp
  src/d/d_bg_s_lin_chk.cpp
  src/SSystem/SComponent/c_bg_s_gnd_chk.cpp
  src/d/d_bg_w.cpp
  src/SSystem/SComponent/c_bg_s.cpp
  src/SSystem/SComponent/c_bg_s_chk.cpp
  src/d/d_bg_s.cpp
  src/d/d_bg_s_acch.cpp
  src/d/d_bg_s_spl_grp_chk.cpp
  src/d/d_bg_s_wtr_chk.cpp
  src/JSystem/J3DGraphAnimator/J3DNode.cpp
  src/JSystem/J3DGraphAnimator/J3DJoint.cpp
  src/JSystem/J3DGraphAnimator/J3DModel.cpp
  src/JSystem/J3DGraphLoader/J3DJointFactory.cpp
  src/m_Do/m_Do_ext.cpp
  engine/link_model.cpp
  engine/link_assets.cpp
  boundary/stubs.cpp
  engine/jma_console_table.cpp
  engine/j3d_hermite.cpp
  engine/ps_vec.cpp
  engine/ps_mtx.cpp
  engine/room.cpp
  engine/session.cpp
  src/SSystem/SComponent/c_m3d_g_aab.cpp
)
# The decomp is C++98. `GXColor color = {tevStr.mColorC0.r, ...}` in d_a_player_sword.inc
# (procCutTurn_init) narrows s16 to u8: clang refuses it, g++ and MSVC warn (-Wnarrowing, C4838).
# The warning is left visible; clang gets this one diagnostic off, on the port target only.
if(CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  target_compile_options(tww_engine_port PRIVATE -Wno-c++11-narrowing)
endif()
# Include roots:
#   include/    the decomp's headers at the decomp's own paths
#   generated/  extracted tables
#   src/        so an .inc resolves at the path the decomp includes it by
#               (d_a_player_main.cpp:110; the decomp's configure.py passes `-i src`). Build-only:
#               only .cpp files in the archive include those .inc files.
#   ${CMAKE_CURRENT_SOURCE_DIR}  for `engine/` and `boundary/`
# CMAKE_CURRENT_SOURCE_DIR, not CMAKE_SOURCE_DIR, so an `add_subdirectory` consumer resolves them.
target_include_directories(tww_engine_port PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/generated>
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/src>
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}>
  $<INSTALL_INTERFACE:include>)
# GZLJ01: the only region with a generated HIO table. The others are named in include/global.h.
target_compile_definitions(tww_engine_port PUBLIC VERSION=1)

# The FP contract also covers the consumer's code that computes the initial conditions it hands
# to `Session`. A generator expression, since the compiler that matters is the consumer's.
target_compile_options(tww_engine_port INTERFACE
  $<$<CXX_COMPILER_ID:MSVC>:/fp:precise>
  $<$<CXX_COMPILER_ID:GNU,Clang,AppleClang>:-ffp-contract=off>)

# Tests only when top level. PROJECT_IS_TOP_LEVEL is CMake 3.21; the fallback covers 3.20.
if(CMAKE_VERSION VERSION_GREATER_EQUAL 3.21)
  set(TWWE_TOP_LEVEL ${PROJECT_IS_TOP_LEVEL})
elseif(CMAKE_SOURCE_DIR STREQUAL CMAKE_CURRENT_SOURCE_DIR)
  set(TWWE_TOP_LEVEL ON)
else()
  set(TWWE_TOP_LEVEL OFF)
endif()
if(TWWE_TOP_LEVEL)
  enable_testing()
  add_subdirectory(tests)
endif()

# ------------------------------------------------------------------------- the installed package
# `find_package(tww_engine)`, alongside `add_subdirectory`. The decomp headers are installed as
# public headers because `Session::state()` returns a `const daPy_lk_c&`. Off by default for a
# subdirectory consumer, so its own `cmake --install` does not scatter these headers.
option(TWW_ENGINE_INSTALL "Generate install rules for tww_engine" ${TWWE_TOP_LEVEL})
if(TWW_ENGINE_INSTALL)
include(GNUInstallDirs)
include(CMakePackageConfigHelpers)

install(TARGETS tww_engine_port
  EXPORT tww_engineTargets
  ARCHIVE DESTINATION ${CMAKE_INSTALL_LIBDIR})

# include/ and generated/ merge into one directory; no path appears in both.
install(DIRECTORY include/ generated/
  DESTINATION ${CMAKE_INSTALL_INCLUDEDIR}
  FILES_MATCHING PATTERN "*.h" PATTERN "*.inc")
install(DIRECTORY engine/ DESTINATION ${CMAKE_INSTALL_INCLUDEDIR}/engine FILES_MATCHING PATTERN "*.h")
install(DIRECTORY boundary/ DESTINATION ${CMAKE_INSTALL_INCLUDEDIR}/boundary FILES_MATCHING PATTERN "*.h")

install(EXPORT tww_engineTargets
  FILE tww_engineTargets.cmake
  NAMESPACE tww_engine::
  DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/tww_engine)

configure_package_config_file(
  ${CMAKE_CURRENT_SOURCE_DIR}/cmake/tww_engineConfig.cmake.in
  ${CMAKE_CURRENT_BINARY_DIR}/tww_engineConfig.cmake
  INSTALL_DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/tww_engine)

# No version file: the project ships by git SHA.
install(FILES ${CMAKE_CURRENT_BINARY_DIR}/tww_engineConfig.cmake
  DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/tww_engine)
endif()
