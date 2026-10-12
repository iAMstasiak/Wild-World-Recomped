#!/usr/bin/env python3
"""Search and edit the running game's memory through the runner's debug port.

The runner opens a debug port (127.0.0.1:19842 by default) whenever it runs.
This tool talks to it while you play:

  snap NAME                  save a snapshot of main RAM (4 MB)
  find NAME VALUE            addresses in a snapshot holding VALUE
  diff OLD NEW --delta N     addresses whose value went up by N (down if N<0)
  diff OLD NEW --changed     addresses whose value changed at all
  diff OLD NEW --same        addresses whose value did not change
  read ADDR [LEN]            hex dump of live memory
  write ADDR HEX             write bytes into live main RAM

find and diff save their matches as the candidate list; add --keep to a later
find or diff to narrow that list instead of starting over. Values are
little-endian unsigned integers of --width 1, 2 or 4 bytes (default 4).
"""

from __future__ import annotations

import argparse
import json
import socket
from pathlib import Path

RAM_START, RAM_END = 0x02000000, 0x02400000
CHUNK = 0x8000
SNAP_DIR = Path("generated/mem")
CANDIDATES = SNAP_DIR / "candidates.txt"


class Runner:
    def __init__(self, port: int):
        try:
            self.sock = socket.create_connection(("127.0.0.1", port), timeout=30)
        except OSError as exc:
            raise SystemExit(f"cannot reach the runner on port {port}: is the game running? ({exc})")
        self.buf = b""

    def call(self, **request) -> dict:
        self.sock.sendall((json.dumps(request) + "\n").encode())
        while b"\n" not in self.buf:
            data = self.sock.recv(1 << 20)
            if not data:
                raise SystemExit("the runner closed the connection")
            self.buf += data
        line, self.buf = self.buf.split(b"\n", 1)
        reply = json.loads(line)
        if "error" in reply:
            raise SystemExit(f"runner: {reply['error']}")
        return reply

    def read(self, addr: int, length: int) -> bytes:
        out = bytearray()
        while length > 0:
            n = min(CHUNK, length)
            reply = self.call(cmd="read_mem", cpu=9, addr=addr, len=n)
            out += bytes.fromhex(reply["hex"])
            addr += n
            length -= n
        return bytes(out)


def number(text: str) -> int:
    return int(text, 0)


def load_snap(name: str) -> bytes:
    path = SNAP_DIR / f"{name}.bin"
    if not path.is_file():
        raise SystemExit(f"no snapshot called {name!r}: take one with: snap {name}")
    return path.read_bytes()


def value_at(data: bytes, offset: int, width: int) -> int:
    return int.from_bytes(data[offset:offset + width], "little")


def offsets(width: int, keep: bool) -> list[int]:
    if keep:
        if not CANDIDATES.is_file():
            raise SystemExit("--keep needs an earlier find or diff")
        return [int(line.split()[0], 16) - RAM_START
                for line in CANDIDATES.read_text().splitlines() if line.strip()]
    return list(range(0, RAM_END - RAM_START - width + 1, width))


def report(matches: list[int], data: bytes, width: int, shown: int = 40) -> None:
    SNAP_DIR.mkdir(parents=True, exist_ok=True)
    CANDIDATES.write_text("".join(
        f"0x{RAM_START + o:08X} {value_at(data, o, width)}\n" for o in matches))
    print(f"{len(matches):,} candidate(s), saved to {CANDIDATES}")
    for o in matches[:shown]:
        print(f"  0x{RAM_START + o:08X} = {value_at(data, o, width)}")
    if len(matches) > shown:
        print(f"  ... {len(matches) - shown:,} more; narrow them with --keep")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=19842)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("snap")
    p.add_argument("name")

    p = sub.add_parser("find")
    p.add_argument("name")
    p.add_argument("value", type=number)
    p.add_argument("--width", type=int, choices=(1, 2, 4), default=4)
    p.add_argument("--keep", action="store_true")

    p = sub.add_parser("diff")
    p.add_argument("old")
    p.add_argument("new")
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--delta", type=number)
    mode.add_argument("--changed", action="store_true")
    mode.add_argument("--same", action="store_true")
    p.add_argument("--width", type=int, choices=(1, 2, 4), default=4)
    p.add_argument("--keep", action="store_true")

    p = sub.add_parser("read")
    p.add_argument("addr", type=number)
    p.add_argument("length", type=number, nargs="?", default=64)

    p = sub.add_parser("write")
    p.add_argument("addr", type=number)
    p.add_argument("hex")

    args = parser.parse_args()

    if args.command == "snap":
        data = Runner(args.port).read(RAM_START, RAM_END - RAM_START)
        SNAP_DIR.mkdir(parents=True, exist_ok=True)
        (SNAP_DIR / f"{args.name}.bin").write_bytes(data)
        print(f"saved {len(data):,} bytes of main RAM as {args.name!r}")

    elif args.command == "find":
        data = load_snap(args.name)
        report([o for o in offsets(args.width, args.keep)
                if value_at(data, o, args.width) == args.value], data, args.width)

    elif args.command == "diff":
        old, new = load_snap(args.old), load_snap(args.new)
        mask = (1 << (8 * args.width)) - 1
        matches = []
        for o in offsets(args.width, args.keep):
            a, b = value_at(old, o, args.width), value_at(new, o, args.width)
            if args.changed and a != b:
                matches.append(o)
            elif args.same and a == b:
                matches.append(o)
            elif args.delta is not None and a != b and (b - a) & mask == args.delta & mask:
                matches.append(o)
        report(matches, new, args.width)

    elif args.command == "read":
        data = Runner(args.port).read(args.addr, args.length)
        for row in range(0, len(data), 16):
            chunk = data[row:row + 16]
            print(f"0x{args.addr + row:08X}  {chunk.hex(' ')}")

    elif args.command == "write":
        reply = Runner(args.port).call(cmd="write_mem", cpu=9, addr=args.addr, hex=args.hex)
        print(f"wrote {reply.get('written', 0)} byte(s) at 0x{args.addr:08X}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
