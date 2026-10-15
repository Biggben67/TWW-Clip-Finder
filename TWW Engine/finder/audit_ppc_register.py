"""Inspect callee-saved FPR writes/calls in the JP executable (read-only)."""
import argparse
import re
import struct
from pathlib import Path


def inspect(iso, symbols, names, register=27):
    functions = {}
    for line in Path(symbols).read_text().splitlines():
        match = re.match(r"(\S+) = \.text:0x([0-9A-Fa-f]+);.*size:0x([0-9A-Fa-f]+)", line)
        if match:
            functions[int(match[2], 16)] = (match[1], int(match[3], 16))
    with open(iso, "rb") as rom:
        rom.seek(0x420)
        dol = struct.unpack(">I", rom.read(4))[0]
        rom.seek(dol)
        header = rom.read(0x100)
        sections = list(zip(struct.unpack_from(">7I", header),
                            struct.unpack_from(">7I", header, 0x48),
                            struct.unpack_from(">7I", header, 0x90)))
        for address, (name, size) in functions.items():
            if not any(part in name for part in names):
                continue
            print("\n%s %08x size %x" % (name, address, size))
            offset, base, _ = next(s for s in sections if s[1] <= address < s[1] + s[2])
            rom.seek(dol + offset + address - base)
            words = struct.unpack(">%dI" % (size // 4), rom.read(size))
            for i, word in enumerate(words):
                pc = address + 4 * i
                op, rd = word >> 26, (word >> 21) & 31
                if op in (48, 50, 59, 63) and rd == register:
                    print("%08x %08x op=%d ra=%d rb=%d xo=%d" % (
                        pc, word, op, (word >> 16) & 31, (word >> 11) & 31, (word >> 1) & 1023))
                if op == 18 and word & 1:
                    delta = word & 0x03FFFFFC
                    if delta & 0x02000000:
                        delta -= 0x04000000
                    target = delta if word & 2 else pc + delta
                    print("%08x call %08x %s" % (pc, target, functions.get(target, ("?",))[0]))
                if op == 19 and (word >> 1) & 1023 == 528:
                    print("%08x indirect call" % pc)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("iso")
    parser.add_argument("symbols")
    parser.add_argument("names", nargs="+")
    parser.add_argument("--register", type=int, default=27)
    args = parser.parse_args()
    inspect(args.iso, args.symbols, args.names, args.register)
