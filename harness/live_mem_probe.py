"""Windows probe for a running Dolphin MEM1 mapping.

This is a fallback for local investigations when the usual ../tools/dolphin_mem.py
wrapper is unavailable. Writes are opt-in and are used only by live setup tools.
"""
from __future__ import annotations

import ctypes
import struct
import sys
import time
from ctypes import wintypes


PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010
PROCESS_VM_WRITE = 0x0020
PROCESS_VM_OPERATION = 0x0008
MEM_COMMIT = 0x1000
PAGE_NOACCESS = 0x01
PAGE_GUARD = 0x100

K32 = ctypes.WinDLL("kernel32", use_last_error=True)


class MEMORY_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BaseAddress", ctypes.c_void_p),
        ("AllocationBase", ctypes.c_void_p),
        ("AllocationProtect", wintypes.DWORD),
        ("RegionSize", ctypes.c_size_t),
        ("State", wintypes.DWORD),
        ("Protect", wintypes.DWORD),
        ("Type", wintypes.DWORD),
    ]


K32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
K32.OpenProcess.restype = wintypes.HANDLE
K32.CloseHandle.argtypes = [wintypes.HANDLE]
K32.ReadProcessMemory.argtypes = [
    wintypes.HANDLE,
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.c_size_t,
    ctypes.POINTER(ctypes.c_size_t),
]
K32.ReadProcessMemory.restype = wintypes.BOOL
K32.WriteProcessMemory.argtypes = [
    wintypes.HANDLE,
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.c_size_t,
    ctypes.POINTER(ctypes.c_size_t),
]
K32.WriteProcessMemory.restype = wintypes.BOOL
K32.VirtualQueryEx.argtypes = [
    wintypes.HANDLE,
    ctypes.c_void_p,
    ctypes.POINTER(MEMORY_BASIC_INFORMATION),
    ctypes.c_size_t,
]
K32.VirtualQueryEx.restype = ctypes.c_size_t


def _pid_from_args(argv: list[str]) -> int:
    for arg in argv[1:]:
        if arg.startswith("pid="):
            return int(arg.split("=", 1)[1], 0)
    return 25332


def _arg(argv: list[str], name: str, default=None):
    prefix = name + "="
    for arg in argv[1:]:
        if arg.startswith(prefix):
            return arg.split("=", 1)[1]
    return default


class ProcReader:
    def __init__(self, pid: int, writable: bool = False):
        self.pid = pid
        access = PROCESS_QUERY_INFORMATION | PROCESS_VM_READ
        if writable:
            access |= PROCESS_VM_WRITE | PROCESS_VM_OPERATION
        self.handle = K32.OpenProcess(access, False, pid)
        if not self.handle:
            raise OSError(ctypes.get_last_error(), "OpenProcess failed")
        self.mem1_base = self._find_mem1_base()

    def close(self) -> None:
        if self.handle:
            K32.CloseHandle(self.handle)
            self.handle = None

    def _read_host(self, addr: int, n: int) -> bytes:
        buf = (ctypes.c_ubyte * n)()
        got = ctypes.c_size_t()
        ok = K32.ReadProcessMemory(
            self.handle, ctypes.c_void_p(addr), buf, n, ctypes.byref(got)
        )
        if not ok or got.value != n:
            raise OSError(ctypes.get_last_error(), f"ReadProcessMemory failed at 0x{addr:X}")
        return bytes(buf)

    def _find_mem1_base(self) -> int:
        mbi = MEMORY_BASIC_INFORMATION()
        addr = 0
        needle = b"GZLJ"
        while K32.VirtualQueryEx(
            self.handle, ctypes.c_void_p(addr), ctypes.byref(mbi), ctypes.sizeof(mbi)
        ):
            base = int(mbi.BaseAddress or 0)
            size = int(mbi.RegionSize)
            protect = int(mbi.Protect)
            readable = (
                mbi.State == MEM_COMMIT
                and not (protect & PAGE_NOACCESS)
                and not (protect & PAGE_GUARD)
                and size >= 0x01800000
            )
            if readable:
                try:
                    head = self._read_host(base, 0x100)
                    if head.startswith(needle):
                        return base
                except OSError:
                    pass
            addr = base + size
            if addr <= base:
                break
        raise RuntimeError("could not locate MEM1 base by GZLJ header")

    def read_bytes(self, gc_addr: int, n: int) -> bytes:
        if not 0x80000000 <= gc_addr < 0x81800000:
            raise ValueError(f"not a MEM1 address: 0x{gc_addr:X}")
        return self._read_host(self.mem1_base + (gc_addr - 0x80000000), n)

    def write_bytes(self, gc_addr: int, data: bytes) -> None:
        if not 0x80000000 <= gc_addr < 0x81800000:
            raise ValueError(f"not a MEM1 address: 0x{gc_addr:X}")
        buf = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
        wrote = ctypes.c_size_t()
        ok = K32.WriteProcessMemory(
            self.handle,
            ctypes.c_void_p(self.mem1_base + (gc_addr - 0x80000000)),
            buf,
            len(data),
            ctypes.byref(wrote),
        )
        if not ok or wrote.value != len(data):
            raise OSError(ctypes.get_last_error(), f"WriteProcessMemory failed at 0x{gc_addr:X}")

    def block(self, addr: int, n: int) -> bytes:
        """Compatibility surface used by the live DZB collision readers."""
        return self.read_bytes(addr, n)

    def u8(self, addr: int) -> int:
        return self.read_bytes(addr, 1)[0]

    def s8(self, addr: int) -> int:
        return struct.unpack(">b", self.read_bytes(addr, 1))[0]

    def u16(self, addr: int) -> int:
        return struct.unpack(">H", self.read_bytes(addr, 2))[0]

    def s16(self, addr: int) -> int:
        return struct.unpack(">h", self.read_bytes(addr, 2))[0]

    def u32(self, addr: int) -> int:
        return struct.unpack(">I", self.read_bytes(addr, 4))[0]

    def s32(self, addr: int) -> int:
        return struct.unpack(">i", self.read_bytes(addr, 4))[0]

    def f32(self, addr: int) -> float:
        return struct.unpack(">f", self.read_bytes(addr, 4))[0]


def main(argv: list[str]) -> int:
    pid = _pid_from_args(argv)
    rd = ProcReader(pid)
    try:
        samples = int(_arg(argv, "samples", "1"))
        interval = float(_arg(argv, "interval", "0.1"))
        player_mid = rd.u32(0x803AD860)
        actor = rd.u32(0x803BD910)
        print(
            f"pid={pid} mem1_base=0x{rd.mem1_base:X} "
            f"actor=0x{actor:08X} player_mid=0x{player_mid:08X}"
        )
        stage = rd.read_bytes(0x803BD23C, 11).split(b"\0")[0].decode("ascii", "replace")
        print(f"stage={stage}")
        def dump_actor(sample=None):
            prefix = "" if sample is None else f"[{sample:03d}] "
            # fopAc_ac_c current.pos is documented in the repo at actor +0x1F8.
            old_x = rd.f32(actor + 0x1E4)
            old_y = rd.f32(actor + 0x1E8)
            old_z = rd.f32(actor + 0x1EC)
            x = rd.f32(actor + 0x1F8)
            y = rd.f32(actor + 0x1FC)
            z = rd.f32(actor + 0x200)
            # Common actor angle block follows current.pos in fopAc_ac_c layouts.
            ax = rd.u16(actor + 0x20C)
            ay = rd.u16(actor + 0x20E)
            az = rd.u16(actor + 0x210)
            state = rd.u32(actor + 0x31D8)
            # J3DFrameCtrl: under slot 0 at class+0x302C. Its frame is +0x10,
            # end is +0x08, and rate is +0x0C.
            frame_old = rd.f32(actor + 0x303C)
            frame_installed = frame_old
            frame_len = rd.f32(actor + 0x3034)
            frame_inc = rd.f32(actor + 0x3038)
            target_facing = rd.u16(actor + 0x34E8)
            stick_dist = rd.f32(actor + 0x35B4)
            cc_move = tuple(rd.f32(actor + 0x3FE8 + 4 * i) for i in range(3))
            grab_id = rd.u32(actor + 0x318C)
            grab_actor = rd.u32(actor + 0x3190)
            left = tuple(rd.f32(actor + 0x2D4 + 4 * i) for i in range(3))
            right = tuple(rd.f32(actor + 0x2E0 + 4 * i) for i in range(3))
            hand_mid = tuple((left[i] + right[i]) * 0.5 for i in range(3))

            # daPy_lk_c::mCyl starts at class+0x4024. The cM3dGCyl geometry is
            # embedded inside dCcD_Cyl, so locate it by its R=30 field and a
            # center close to Link rather than relying on a build-specific
            # inner-class offset.
            cyl_candidates = []
            cyl_blob = rd.read_bytes(actor + 0x4024, 0x160)
            for off in range(0, len(cyl_blob) - 0x14, 4):
                cx, cy, cz, radius, height = struct.unpack_from(">fffff", cyl_blob, off)
                if (
                    abs(radius - 30.0) < 1e-4
                    and 1.0 < height < 300.0
                    and abs(cx - x) < 200.0
                    and abs(cz - z) < 200.0
                ):
                    cyl_candidates.append((off, cx, cy, cz, radius, height))
            print(
                prefix + "actor fields "
                f"old=({old_x:.6f},{old_y:.6f},{old_z:.6f}) "
                f"pos=({x:.6f},{y:.6f},{z:.6f}) angle=({ax},{ay},{az}) "
                f"state={state} frame_old={frame_old:.3f} "
                f"frame={frame_installed:.3f}/{frame_len:.3f}+{frame_inc:.3f} "
                f"target_facing={target_facing} stick_dist={stick_dist:.3f}"
            )
            print(
                prefix + "hands "
                f"left=({left[0]:.6f},{left[1]:.6f},{left[2]:.6f}) "
                f"right=({right[0]:.6f},{right[1]:.6f},{right[2]:.6f}) "
                f"mid=({hand_mid[0]:.6f},{hand_mid[1]:.6f},{hand_mid[2]:.6f})"
            )
            print(
                prefix + "drop trace "
                f"cc_move=({cc_move[0]:.9f},{cc_move[1]:.9f},{cc_move[2]:.9f}) "
                f"grab_id=0x{grab_id:08X} grab_actor=0x{grab_actor:08X}"
            )
            for off, cx, cy, cz, radius, height in cyl_candidates:
                print(
                    prefix + "link mCyl "
                    f"off=0x{0x4024 + off:04X} "
                    f"center=({cx:.9f},{cy:.9f},{cz:.9f}) "
                    f"r={radius:.6f} h={height:.6f}"
                )
            upper = []
            # mFrameCtrlUpper begins at class+0x3054; slots are 0x14 bytes.
            for slot in range(3):
                off = 0x3054 + slot * 0x14
                upper.append((slot, rd.f32(actor + off + 0x0C), rd.f32(actor + off + 0x10)))
            print(
                prefix + "upper frames "
                + " ".join(f"{slot}:rate={rate:.6f},frame={frame:.6f}" for slot, rate, frame in upper)
            )
            ratios = []
            for slot in range(3):
                off = 0x2FC4 + slot * 8
                ratios.append((slot, rd.u32(actor + off), rd.f32(actor + off + 4)))
            print(
                prefix + "upper ratios "
                + " ".join(
                    f"{slot}:anm=0x{anm:08X},ratio={ratio:.6f}"
                    for slot, anm, ratio in ratios
                )
            )
            print(
                prefix + "pose terms "
                f"shape_z={rd.s16(actor + 0x210)} "
                f"body=({rd.s16(actor + 0x2B4)},{rd.s16(actor + 0x2B6)},{rd.s16(actor + 0x2B8)}) "
                f"root_tilt=({rd.s16(actor + 0x34F2)},{rd.s16(actor + 0x34F4)})"
            )
            if 0x80000000 <= grab_actor < 0x81800000:
                gpos = tuple(rd.f32(grab_actor + 0x1F8 + 4 * i) for i in range(3))
                gold = tuple(rd.f32(grab_actor + 0x1E4 + 4 * i) for i in range(3))
                gshape_y = rd.u16(grab_actor + 0x20E)
                gspeed = tuple(rd.f32(grab_actor + 0x220 + 4 * i) for i in range(3))
                gspeed_f = rd.f32(grab_actor + 0x254)
                gstatus = rd.u32(grab_actor + 0x1C4)
                print(
                    prefix + "grab actor "
                    f"pos=({gpos[0]:.6f},{gpos[1]:.6f},{gpos[2]:.6f}) "
                    f"old=({gold[0]:.6f},{gold[1]:.6f},{gold[2]:.6f}) "
                    f"shape_y={gshape_y} speed=({gspeed[0]:.6f},{gspeed[1]:.6f},{gspeed[2]:.6f}) "
                    f"speedF={gspeed_f:.6f} status=0x{gstatus:08X}"
                )
            if samples == 1:
                for off in range(0x204, 0x220, 2):
                    val = rd.u16(actor + off)
                    if 25000 <= val <= 36000:
                        print(f"  actor+0x{off:03X} u16={val}")
                for off in (0x3034, 0x3038, 0x303C, 0x3080, 0x3084, 0x3088,
                            0x308C, 0x31D8, 0x34E8, 0x35B4):
                    try:
                        print(f"  actor+0x{off:04X} f32={rd.f32(actor + off):.6f} u16={rd.u16(actor + off)}")
                    except Exception as exc:
                        print(f"  actor+0x{off:04X} read failed: {exc}")

        if 0x80000000 <= actor < 0x81800000:
            for sample in range(samples):
                dump_actor(None if samples == 1 else sample)
                if sample + 1 < samples:
                    time.sleep(interval)
        return 0
    finally:
        rd.close()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

