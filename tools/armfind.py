#!/usr/bin/env python3
"""Search the game's code images for constants and disassemble around them.

Reads the images tools/prepare_acww.py wrote to generated/inputs (main ARM9,
ARM7 and all 148 ARM9 overlays), so it works without the game running.

  find VALUE [VALUE ...]       where each 32-bit VALUE is stored, and which
                               instructions load it (literal-pool loads)
  dis IMAGE ADDR [--thumb]     disassemble the function around ADDR in IMAGE
                               (arm9, arm7 or ovNNN; find prints these lines;
                               --here starts exactly at ADDR, --count N)
  calls ADDR                   every BL/BLX in any image that calls ADDR

Needs capstone: py -3.12 -m pip install capstone==5.0.7
"""

from __future__ import annotations

import argparse
import json
import tomllib
from pathlib import Path

INPUTS = Path("generated/inputs")
FUNCTION_SEARCH = 0x300          # how far back dis looks for a function start
MAX_INSTRUCTIONS = 160


def load_images(inputs: Path) -> dict[str, tuple[int, bytes]]:
    images = {}
    for cpu in (9, 7):
        with (inputs / f"arm{cpu}.toml").open("rb") as handle:
            base = int(tomllib.load(handle)["program"]["load_address"])
        images[f"arm{cpu}"] = (base, (inputs / f"arm{cpu}.bin").read_bytes())
    for ov in json.loads((inputs / "overlays.json").read_text(encoding="utf-8")):
        images[f"ov{ov['id']:03d}"] = (int(ov["load_address"], 16),
                                       (inputs / "overlays" / ov["file"]).read_bytes())
    return images


def u16(data: bytes, off: int) -> int:
    return int.from_bytes(data[off:off + 2], "little")


def u32(data: bytes, off: int) -> int:
    return int.from_bytes(data[off:off + 4], "little")


def literal_target(data: bytes, base: int, off: int, thumb: bool) -> int | None:
    """Address a PC-relative LDR at off reads from, or None if it isn't one."""
    if thumb:
        insn = u16(data, off)
        if insn & 0xF800 != 0x4800:                 # ldr rd, [pc, #imm8*4]
            return None
        return ((base + off + 4) & ~3) + ((insn & 0xFF) << 2)
    insn = u32(data, off)
    if insn >> 28 == 0xF or insn & 0x0F7F0000 != 0x051F0000:   # ldr rd, [pc, #+-imm12]
        return None
    imm = insn & 0xFFF
    return base + off + 8 + (imm if insn & (1 << 23) else -imm)


def literal_loads(data: bytes, base: int) -> dict[int, list[tuple[int, bool]]]:
    """Map each literal address to the ARM or Thumb loads that read it."""
    index: dict[int, list[tuple[int, bool]]] = {}
    for off in range(0, len(data) - 1, 2):
        for thumb in (True, False):
            if not thumb and (off % 4 or off + 4 > len(data)):
                continue
            target = literal_target(data, base, off, thumb)
            if target is not None:
                index.setdefault(target, []).append((base + off, thumb))
    return index


def cmd_find(images: dict, values: list[int]) -> None:
    indexes: dict[str, dict] = {}
    for value in values:
        word = (value & 0xFFFFFFFF).to_bytes(4, "little")
        print(f"\n{value} (0x{value & 0xFFFFFFFF:08X}):")
        hits = 0
        for name, (base, data) in images.items():
            if word not in data:
                continue
            if name not in indexes:
                indexes[name] = literal_loads(data, base)
            pos = data.find(word)
            while pos != -1:
                if pos % 4 == 0:
                    hits += 1
                    addr = base + pos
                    loads = indexes[name].get(addr, [])
                    if loads:
                        print(f"  {name:5} 0x{addr:08X}  stored here, loaded by:")
                        for at, thumb in loads:
                            mode = " --thumb" if thumb else ""
                            print(f"      dis {name} 0x{at:08X}{mode}")
                    else:
                        print(f"  {name:5} 0x{addr:08X}  stored here, no direct loads "
                              f"(part of a table? try: find 0x{addr:08X})")
                pos = data.find(word, pos + 1)
        if not hits:
            print("  not found in any image")


def is_function_start(data: bytes, off: int, thumb: bool) -> bool:
    if thumb:
        return u16(data, off) & 0xFF00 == 0xB500                 # push {..., lr}
    return u32(data, off) & 0xFFFF4000 == 0xE92D4000             # stmdb sp!, {..., lr}


def called_here(data: bytes, base: int, addr: int) -> int:
    """How many BL/BLX instructions in this image call addr."""
    return sum(1 for off in range(0, len(data) - 3, 2) for thumb in (True, False)
               if (thumb or off % 4 == 0)
               and (hit := branch_target(data, base, off, thumb)) and hit[0] == addr)


def cmd_dis(images: dict, name: str, addr: int, thumb: bool, limit: int, here: bool) -> None:
    from capstone import CS_ARCH_ARM, CS_MODE_ARM, CS_MODE_THUMB, Cs

    if name not in images:
        raise SystemExit(f"no image called {name!r}: use arm9, arm7 or ovNNN")
    base, data = images[name]
    target = addr - base
    if not 0 <= target < len(data):
        raise SystemExit(f"0x{addr:08X} is outside {name} "
                         f"(0x{base:08X}-0x{base + len(data):08X})")
    step = 2 if thumb else 4
    target -= target % step
    start = target
    if not here and not is_function_start(data, target, thumb):
        if called_here(data, base, base + target):
            print("(something calls this address, so the function starts here)")
        else:
            while start > 0 and target - start < FUNCTION_SEARCH and not is_function_start(data, start, thumb):
                start -= step
            if not is_function_start(data, start, thumb):
                start = max(0, target - 0x40)
                print("(no function start found nearby; starting 0x40 bytes early)")

    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB if thumb else CS_MODE_ARM)
    print(f"{name} {'thumb' if thumb else 'arm'} from 0x{base + start:08X}")
    off, count = start, 0
    while off + step <= len(data):
        insn = next(md.disasm(data[off:off + 4], base + off, count=1), None)
        size = insn.size if insn else step
        mark = ">>" if off <= target < off + size else "  "
        if insn is None:                            # data, not an instruction
            word = u16(data, off) if thumb else u32(data, off)
            print(f"{mark} 0x{base + off:08X}  {'.data':8} 0x{word:0{size * 2}X}")
        else:
            note = ""
            lit = literal_target(data, base, off, thumb)
            if lit is not None and 0 <= lit - base <= len(data) - 4:
                value = u32(data, lit - base)
                note = f"   ; = 0x{value:08X} ({value})"
            print(f"{mark} 0x{insn.address:08X}  {insn.mnemonic:8} {insn.op_str}{note}")
        off += size
        count += 1
        if count >= limit:
            print(f"(stopped after {limit} instructions; add --count N for more)")
            break
        if off > target and off + 4 <= len(data) and is_function_start(data, off, thumb):
            break                                   # the next function starts here


def sign_extend(value: int, bits: int) -> int:
    return value - (1 << bits) if value & (1 << (bits - 1)) else value


def branch_target(data: bytes, base: int, off: int, thumb: bool) -> tuple[int, str] | None:
    """Target and kind of a BL/BLX at off, or None if it isn't one."""
    pc = base + off
    if thumb:
        if off + 4 > len(data):
            return None
        hi, lo = u16(data, off), u16(data, off + 2)
        if hi & 0xF800 != 0xF000 or lo & 0xE800 != 0xE800:
            return None
        dest = pc + 4 + (sign_extend(hi & 0x7FF, 11) << 12) + ((lo & 0x7FF) << 1)
        if lo & 0xF800 == 0xF800:
            return dest, "bl"
        return dest & ~3, "blx"                     # blx: switches to ARM
    insn = u32(data, off)
    if insn >> 25 == 0x7D:                          # blx imm: switches to Thumb
        return pc + 8 + (sign_extend(insn & 0xFFFFFF, 24) << 2) + ((insn >> 23) & 2), "blx"
    if insn >> 28 != 0xF and insn & 0x0F000000 == 0x0B000000:
        return pc + 8 + (sign_extend(insn & 0xFFFFFF, 24) << 2), "bl"
    return None


def cmd_calls(images: dict, addr: int) -> None:
    found = 0
    for name, (base, data) in images.items():
        for off in range(0, len(data) - 3, 2):
            for thumb in (True, False):
                if not thumb and off % 4:
                    continue
                hit = branch_target(data, base, off, thumb)
                if hit and hit[0] == (addr & ~1):
                    found += 1
                    mode = " --thumb" if thumb else ""
                    print(f"  {hit[1]:3} from {name:5} 0x{base + off:08X}   "
                          f"->  dis {name} 0x{base + off:08X}{mode}")
    if not found:
        print("  no direct calls found (it may be called through a pointer)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--inputs", type=Path, default=INPUTS)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("find")
    p.add_argument("values", nargs="+", type=lambda s: int(s, 0))
    p = sub.add_parser("dis")
    p.add_argument("image")
    p.add_argument("addr", type=lambda s: int(s, 0))
    p.add_argument("--thumb", action="store_true")
    p.add_argument("--count", type=int, default=MAX_INSTRUCTIONS)
    p.add_argument("--here", action="store_true", help="start exactly at ADDR")
    p = sub.add_parser("calls")
    p.add_argument("addr", type=lambda s: int(s, 0))
    args = parser.parse_args()

    images = load_images(args.inputs)
    if args.command == "find":
        cmd_find(images, args.values)
    elif args.command == "calls":
        cmd_calls(images, args.addr)
    else:
        cmd_dis(images, args.image, args.addr, args.thumb, args.count, args.here)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
