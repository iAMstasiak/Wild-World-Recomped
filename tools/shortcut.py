#!/usr/bin/env python3
"""Make a "Wild World Recomped" shortcut that starts the game.

  py -3.12 tools\\shortcut.py                 desktop shortcut
  py -3.12 tools\\shortcut.py --start-menu    ... and one in the Start menu

The shortcut's icon is the game's own DS menu icon, read from your ROM and
saved in %LOCALAPPDATA%\\Wild World Recomped, outside the project folder, so
none of Nintendo's art ends up in git. The shortcut runs play.ps1 (add switches
with --play-args) with its console window minimised.
"""

from __future__ import annotations

import argparse
import base64
import os
import struct
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SIZES = (16, 24, 32, 48, 64, 128, 256)


def read_banner_icon(rom: Path) -> list[int]:
    """The 32x32 DS menu icon as ARGB pixels (alpha 0 = see-through)."""
    with rom.open("rb") as f:
        header = f.read(0x6C)
        if len(header) < 0x6C:
            raise SystemExit(f"{rom} is too short to be a DS game")
        banner = struct.unpack_from("<I", header, 0x68)[0]
        if banner == 0:
            raise SystemExit(f"{rom} has no banner, so no icon to use")
        f.seek(banner + 0x20)
        icon = f.read(0x220)   # tiles, then the 16-colour palette
    if len(icon) < 0x220:
        raise SystemExit(f"{rom}: the banner is cut short")

    def expand(v: int) -> int:
        return (v << 3) | (v >> 2)

    palette = []
    for i in range(16):
        c = struct.unpack_from("<H", icon, 0x200 + i * 2)[0]
        palette.append(0xFF000000 | expand(c & 31) << 16 |
                       expand((c >> 5) & 31) << 8 | expand((c >> 10) & 31))
    palette[0] = 0
    pixels = []
    for y in range(32):
        for x in range(32):
            pair = icon[((y // 8) * 4 + x // 8) * 32 + (y % 8) * 4 + (x % 8) // 2]
            pixels.append(palette[(pair >> 4) if x & 1 else (pair & 15)])
    return pixels


def scaled(pixels: list[int], size: int) -> list[int]:
    """Hard pixel edges going up; 16x16 averages each 2x2 block instead."""
    if size == 16:
        out = []
        for y in range(16):
            for x in range(16):
                block = [pixels[(y * 2 + dy) * 32 + x * 2 + dx]
                         for dy in (0, 1) for dx in (0, 1)]
                solid = [p for p in block if p >> 24]
                if len(solid) < 2:
                    out.append(0)
                    continue
                avg = [sum((p >> s) & 255 for p in solid) // len(solid)
                       for s in (16, 8, 0)]
                out.append(0xFF000000 | avg[0] << 16 | avg[1] << 8 | avg[2])
        return out
    return [pixels[(y * 32 // size) * 32 + x * 32 // size]
            for y in range(size) for x in range(size)]


def write_ico(path: Path, pixels: list[int]) -> None:
    images = []
    for size in SIZES:
        px = scaled(pixels, size)
        mask_row = ((size + 31) // 32) * 4
        colour = bytearray()
        mask = bytearray()
        for y in reversed(range(size)):   # icons are stored bottom row first
            row_mask = bytearray(mask_row)
            for x in range(size):
                p = px[y * size + x]
                colour += struct.pack("<I", p)   # B, G, R, A in memory
                if p >> 24 == 0:
                    row_mask[x // 8] |= 0x80 >> (x % 8)
            mask += row_mask
        header = struct.pack("<IiiHHIIiiII", 40, size, size * 2, 1, 32, 0,
                             len(colour) + len(mask), 0, 0, 0, 0)
        images.append((size, header + colour + mask))
    out = bytearray(struct.pack("<HHH", 0, 1, len(images)))
    offset = 6 + 16 * len(images)
    for size, data in images:
        side = 0 if size >= 256 else size
        out += struct.pack("<BBBBHHII", side, side, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    for _, data in images:
        out += data
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes(out))


MAKE_SHORTCUT = r"""
$folder = [Environment]::GetFolderPath($env:ACWW_FOLDER)
$path = Join-Path $folder 'Wild World Recomped.lnk'
$link = (New-Object -ComObject WScript.Shell).CreateShortcut($path)
$link.TargetPath = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$link.Arguments = '-NoProfile -ExecutionPolicy Bypass -File ' + [char]34 + $env:ACWW_PLAY + [char]34 + ' ' + $env:ACWW_PLAY_ARGS
$link.WorkingDirectory = $env:ACWW_ROOT
$link.IconLocation = $env:ACWW_ICON + ',0'
$link.WindowStyle = 7
$link.Description = 'Wild World Recomped'
$link.Save()
Write-Output $path
"""


def make_shortcut(folder: str, icon: Path, play_args: str) -> None:
    env = dict(os.environ, ACWW_FOLDER=folder, ACWW_ICON=str(icon),
               ACWW_ROOT=str(ROOT), ACWW_PLAY=str(ROOT / "play.ps1"),
               ACWW_PLAY_ARGS=play_args)
    encoded = base64.b64encode(MAKE_SHORTCUT.encode("utf-16-le")).decode()
    result = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
        env=env, capture_output=True, text=True)
    if result.returncode != 0 or not result.stdout.strip():
        raise SystemExit("could not make the shortcut:\n" + result.stderr.strip())
    print(f"made the shortcut: {result.stdout.strip()}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--rom", type=Path, default=ROOT / "acww.nds")
    parser.add_argument("--start-menu", action="store_true",
                        help="also add the shortcut to the Start menu")
    parser.add_argument("--play-args", default="",
                        help="what to pass to play.ps1 (default: none)")
    args = parser.parse_args()

    base = Path(os.environ.get("LOCALAPPDATA", ROOT / "generated"))
    icon = base / "Wild World Recomped" / "icon.ico"
    write_ico(icon, read_banner_icon(args.rom))
    print(f"saved the icon: {icon}")
    make_shortcut("Desktop", icon, args.play_args)
    if args.start_menu:
        make_shortcut("Programs", icon, args.play_args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
