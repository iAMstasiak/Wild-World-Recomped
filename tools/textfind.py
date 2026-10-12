#!/usr/bin/env python3
"""Find where a piece of on-screen text sits in RAM, and what points at it.

Type a few words exactly as the game shows them (same capitals and
punctuation; stay within one line of the text box, and leave out names):

  py -3.12 tools\\textfind.py "a few words"

It searches main RAM in Wild World's own character set (the one save
editors use for names), plain ASCII and UTF-16, then lists 4-byte values
elsewhere in RAM that point into each hit: those are the structures that
use the text, such as the message window and its cursor.
"""

from __future__ import annotations

import argparse

from memscan import RAM_START, Runner

# Wild World USA/EUR character set (LeafEdit-Core wwCharacterDictionary).
WW = (
    "\0ABCDEFGHIJKLMNO"
    "PQRSTUVWXYZabcde"
    "fghijklmnopqrstu"
    "vwxyz0123456789\u2a0d"
    "\u24e2\u0152\u017d\u0161\u0153\u017e\u0178\u00c0\u00c1\u00c2\u00c3\u00c4\u00c5\u00c6\u00c7\u00c8"
    "\u00c9\u00ca\u00cb\u00cc\u00cd\u00ce\u00cf\u0110\u00d1\u00d2\u00d3\u00d4\u00d5\u00d6\u00d8\u00d9"
    "\u00da\u00db\u00dc\u00dd\u00de\u03b2\u00e0\u00e1\u00e2\u00e3\u00e4\u00e5\u00e6\u00e7\u00e8\u00e9"
    "\u00ea\u00eb\u00ec\u00ed\u00ee\u00ef\u00f0\u00f1\u00f2\u00f3\u00f4\u00f5\u00f6\u00f8\u00f9\u00fa"
    "\u00fb\u00fc\u00fd\u00fe\u00ff \n!\"#$%&\u00b4()"
    "*+,-./:;<=>?@[\\]"
    "^_\u00b4{|}~\u20ac\u201a\u201e\u2026\u2020\u2021\uff3e\u2030\u27e8"
    "\u2018\u2019\u201c\u201d\u2022\u2013\u2014\u02dc\u2122\u27e9\u2001\u00a1\u00a2\u00a3\u00a4\u00a5"
    "\u254e\u00a7\u00a8\u00a9\u00aa\u00ab\u00ac-\u00ae\u203e\u00b0\u00b1\u00b2\u00b3\u2044\u00b5"
    "\u00b6\u2022\u00b8\u00b9\u00ba\u00bb\u00bc\u00bd\u00be\u00bf\u00d7\u00f7\u2614\u2605\u2764\u266a"
)
TO_WW = {}
for code, ch in enumerate(WW):
    TO_WW.setdefault(ch, code)
TO_WW["'"] = TO_WW["\u2019"]          # the game's apostrophe is a curly one


def encode_ww(text: str) -> bytes | None:
    try:
        return bytes(TO_WW[c] for c in text)
    except KeyError:
        return None


def decode_ww(data: bytes) -> str:
    """Printable ASCII view: other characters show as '.' so any console copes."""
    out = []
    for b in data:
        ch = WW[b] if b < len(WW) else "\0"
        ch = "'" if ch in "\u2018\u2019" else ch
        out.append(ch if " " <= ch <= "~" else ".")
    return "".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("text")
    parser.add_argument("--port", type=int, default=19842)
    args = parser.parse_args()

    runner = Runner(args.port)
    ram = bytes.fromhex(runner.call(cmd="read_region", region="mainram")["hex"])
    words = memoryview(ram).cast("I")

    encodings = {"Wild World": encode_ww(args.text),
                 "ASCII": args.text.encode("ascii", "replace"),
                 "UTF-16": args.text.encode("utf-16-le")}
    for name, needle in encodings.items():
        if not needle:
            print(f"{name}: can't encode that text")
            continue
        hits = []
        pos = ram.find(needle)
        while pos != -1 and len(hits) < 12:
            hits.append(pos)
            pos = ram.find(needle, pos + 1)
        print(f"\n{name}: {len(hits)} hit(s)")
        for pos in hits:
            start = max(0, pos - 32)
            context = decode_ww(ram[start:pos + len(needle) + 48]) if name == "Wild World" else ""
            print(f"  0x{RAM_START + pos:08X}  {context}")
            lo, hi = RAM_START + pos - 0x800, RAM_START + pos + 0x800
            pointers = [(i, v) for i, v in enumerate(words) if lo <= v < hi]
            for i, v in pointers[:16]:
                print(f"      pointed at by 0x{RAM_START + 4 * i:08X} -> 0x{v:08X} "
                      f"(hit {v - RAM_START - pos:+#x})")
            if len(pointers) > 16:
                print(f"      ... {len(pointers) - 16} more pointers")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
