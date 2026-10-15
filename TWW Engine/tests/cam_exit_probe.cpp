// cam_exit_probe.cpp - an instrument, not a gate: prints the camera frame by frame as the
// first-person view ends. Its own binary because the exit can end the process (a mode change
// re-seeds `m100`, and followCamera's `m100 == 0` entry arm has not run in this port).
//
//   1. Which mode the finder runs: Session::seatCamera sets mode 12, but Run re-runs nextMode
//      every frame, and its case 12 gives the manual camera up (`m144 = 1`, `next_mode = 0`) once
//      the C-stick is centred and `mDirection.R()` is inside `mCamSetup.m098`; both are printed.
//   2. What leaving the view does: the entry, then the yaw each frame with the status down - the
//      frames cup_turn_camera_live.json's `exits` capture.
//   3. `--tape`: a console case from stdin (replay_tape).
//
// Prints and asserts nothing.

#include <cstdio>
#include <cstdlib>
#include <cstring>

#include "engine/session.h"

#include "d/actor/d_a_player_main.h"
#include "m_Do/m_Do_controller_pad.h"

#ifdef _WIN32
#include <windows.h>
// After <windows.h>, and only there.
#include <dbghelp.h>
#endif

namespace {

#ifdef _WIN32
/// Names the faulting function. Vectored so it runs before any unwinding; prints and exits.
LONG WINAPI report_the_fault(EXCEPTION_POINTERS* info) {
    if (info->ExceptionRecord->ExceptionCode != EXCEPTION_ACCESS_VIOLATION &&
        info->ExceptionRecord->ExceptionCode != EXCEPTION_STACK_OVERFLOW) {
        return EXCEPTION_CONTINUE_SEARCH;
    }
    std::printf("\n!! exception 0x%08lx at %p, operand %p\n",
                static_cast<unsigned long>(info->ExceptionRecord->ExceptionCode),
                info->ExceptionRecord->ExceptionAddress,
                info->ExceptionRecord->NumberParameters > 1
                    ? reinterpret_cast<void*>(info->ExceptionRecord->ExceptionInformation[1])
                    : NULL);
    std::fflush(stdout);
    HANDLE proc = GetCurrentProcess();
    SymSetOptions(SYMOPT_DEFERRED_LOADS | SYMOPT_UNDNAME | SYMOPT_LOAD_LINES);
    SymInitialize(proc, NULL, TRUE);
    void* frame[48];
    const USHORT n = CaptureStackBackTrace(0, 48, frame, NULL);
    unsigned char room[sizeof(SYMBOL_INFO) + 512];
    SYMBOL_INFO* sym = reinterpret_cast<SYMBOL_INFO*>(room);
    sym->SizeOfStruct = sizeof(SYMBOL_INFO);
    sym->MaxNameLen = 511;
    for (USHORT i = 0; i < n; ++i) {
        const DWORD64 at = reinterpret_cast<DWORD64>(frame[i]);
        DWORD64 off = 0;
        IMAGEHLP_LINE64 line;
        line.SizeOfStruct = sizeof(line);
        DWORD line_off = 0;
        const bool named = SymFromAddr(proc, at, &off, sym) != FALSE;
        const bool located = SymGetLineFromAddr64(proc, at, &line_off, &line) != FALSE;
        std::printf("   %2d  %-52s %s:%lu\n", i, named ? sym->Name : "?",
                    located ? line.FileName : "?", located ? line.LineNumber : 0UL);
    }
    std::fflush(stdout);
    std::exit(3);
    return EXCEPTION_CONTINUE_SEARCH;
}
#endif

tww_engine::RunOptions flat_options(int yaw) {
    tww_engine::RunOptions opts;
    opts.ground = tww_engine::RunOptions::Ground::Supplied;
    opts.floor_y = 0.0f;
    opts.camera = true;
    opts.camera_yaw = static_cast<s16>(yaw);
    return opts;
}

tww_engine::Init standing(int facing) {
    tww_engine::Init init;
    init.pos.set(0.0f, 0.0f, 0.0f);
    init.shape_angle_y = static_cast<s16>(facing);
    init.travel_angle_y = static_cast<s16>(facing);
    init.normal_speed = 0.0f;
    init.speed_f = 0.0f;
    init.proc = daPy_lk_c::daPyProc_WAIT_e;
    return init;
}

void header(const char* what) {
    std::printf("\n== %s\n", what);
    std::printf("%5s %5s %5s %6s %7s %7s %6s %6s %9s %9s %8s\n", "frame", "mode", "next", "style",
                "m100", "m108", "m144", "m184", "yaw", "radius", "gate");
    std::fflush(stdout);
}

void row(int frame, const tww_engine::Session::CameraFacts& f) {
    std::printf("%5d %5d %5d %6d %7d %7d %6d %6d %9d %9.3f %8.3f  eye(%g %g %g) centre(%g %g %g)\n",
                frame, f.mode, f.next_mode, f.style, f.entry_done, f.entry_frame,
                f.manual_given_up, f.cstick_latch, f.yaw & 0xFFFF, static_cast<double>(f.radius),
                static_cast<double>(f.gate_radius), static_cast<double>(f.eye[0]),
                static_cast<double>(f.eye[1]), static_cast<double>(f.eye[2]),
                static_cast<double>(f.center[0]), static_cast<double>(f.center[1]),
                static_cast<double>(f.center[2]));
    std::fflush(stdout);
}

/// Question one: the mode the finder runs, with nothing raised or pressed.
void which_mode(int facing, int frames) {
    tww_engine::Session session(standing(facing), NULL, flat_options(facing));
    header("a seated camera, run with nothing raised - which mode does the finder have");
    row(0, session.cameraFacts());
    for (int i = 1; i <= frames; ++i) {
        session.runCamera(1);
        row(i, session.cameraFacts());
    }
}

/// Question two: the exit, after the entry, one frame at a time with the status down.
void the_exit(int facing, int frames) {
    tww_engine::Session session(standing(facing), NULL, flat_options(facing));
    header("the first-person entry, then the frames after it - the console's `exits`");
    row(0, session.cameraFacts());
    const int entry = session.runFirstPersonCamera(20);
    std::printf("      -- the entry took %d frame(s); the status is down from here\n", entry);
    std::fflush(stdout);
    row(entry, session.cameraFacts());
    for (int i = 1; i <= frames; ++i) {
        std::printf("      -- about to run exit frame %d\n", i);
        std::fflush(stdout);
        session.runCamera(1);
        row(entry + i, session.cameraFacts());
    }
}

/// Question three: a console case from stdin, one `facing stick_x in_view` line per frame. The
/// facing is the capture's, the stick is what CalcSubjectAngle reads, and `in_view` raises the
/// first-person status as the player's proc does. Prints the yaw per frame, to be held against
/// the capture's csangle.
int replay_tape() {
    tww_engine::Session session(standing(0), NULL, flat_options(0));
    session.bind();
    int facing = 0, in_view = 0;
    float stick_x = 0.0f;
    int frame = 0;
    while (std::scanf("%d %f %d", &facing, &stick_x, &in_view) == 3) {
        session.lk.shape_angle.y = static_cast<s16>(facing);
        session.lk.current.angle.y = static_cast<s16>(facing);
        g_mDoCPd_cpadInfo[PAD_1].mMainStickPosX = stick_x;
        if (in_view) {
            session.lk.stub_player_status0 |= daPyStts0_SUBJECT_e;
        } else {
            session.lk.stub_player_status0 &= ~daPyStts0_SUBJECT_e;
        }
        session.runCamera(1);
        const tww_engine::Session::CameraFacts f = session.cameraFacts();
        std::printf("%d %d %d %d\n", frame, f.yaw & 0xFFFF, f.mode, f.entry_done);
        frame++;
    }
    std::fflush(stdout);
    return 0;
}

}  // namespace

int main(int argc, char** argv) {
    // A facing off zero, since a camera on north and one answering its own seed read the same.
    // 9170 is the console's `+14` row, one whose exit keeps moving.
    const int facing = argc > 1 ? std::atoi(argv[1]) : 9170;
    const int frames = argc > 2 ? std::atoi(argv[2]) : 24;
#ifdef _WIN32
    // Stack room first: a stack overflow's handler cannot run on the overflowed stack.
    ULONG guarantee = 256 * 1024;
    SetThreadStackGuarantee(&guarantee);
    // Vectored, so it runs ahead of anything the CRT installs.
    AddVectoredExceptionHandler(1, report_the_fault);
#endif
    if (argc > 1 && std::strcmp(argv[1], "--tape") == 0) {
        return replay_tape();
    }
    std::printf("facing %d, %d frame(s) after the view\n", facing, frames);
    which_mode(facing, 8);
    the_exit(facing, frames);
    std::printf("\nboth probes ran to the end\n");
    return 0;
}
