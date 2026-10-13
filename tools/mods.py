#!/usr/bin/env python3
"""Apply the code patches in mods/*.toml to the running game.

A mod file has a [mod] table (name, enabled, and `setting` when it has
options), [[patch]] entries that always apply, and optionally [[option]]
tables, each with a name and its own [[option.patch]] entries; `setting`
picks one. A patch has addr, original and patched bytes and is only written
when the live bytes still match `original` (or another option's bytes it
replaces), so a wrong ROM or a clashing mod is reported, not written over.
Writes go through the runner's debug port and its normal bus path, which
drops the recompiled copy of the patched code.

  list                 show the mods, their settings and options
  apply                apply every enabled mod (play.ps1 runs this at launch)
  set MOD VALUE        pick an option, or on / off; applied at once if the
                       game is running (MOD = file name without .toml)
  status               show what is live in the running game
  revert               put the original bytes back everywhere
"""

from __future__ import annotations

import argparse
import re
import time
import tomllib
from pathlib import Path

from memscan import Runner

MODS_DIR = Path("mods")


def read_patches(entries: list[dict], where: str) -> list[dict]:
    patches = [{"addr": int(p["addr"]), "original": bytes.fromhex(p["original"]),
                "patched": bytes.fromhex(p["patched"])} for p in entries]
    for p in patches:
        if len(p["original"]) != len(p["patched"]):
            raise SystemExit(f"{where}: patch at 0x{p['addr']:08X} changes the length")
    return patches


def load_mods() -> list[dict]:
    mods = []
    for path in sorted(MODS_DIR.glob("*.toml")):
        with path.open("rb") as handle:
            data = tomllib.load(handle)
        info = data.get("mod", {})
        base = read_patches(data.get("patch", []), path.name)
        options = {o["name"]: read_patches(o.get("patch", []), path.name)
                   for o in data.get("option", [])}
        setting = info.get("setting")
        if options and setting not in options:
            raise SystemExit(f"{path.name}: setting {setting!r} is not one of "
                             f"{', '.join(options)}")
        enabled = bool(info.get("enabled", False))
        active = (base + options.get(setting, [])) if enabled else []
        known = base + [p for patches in options.values() for p in patches]
        mods.append({"file": path.name, "id": path.stem, "path": path,
                     "name": info.get("name", path.stem), "enabled": enabled,
                     "setting": setting, "options": options, "base": base,
                     "active": active, "known": known})
    return mods


def connect(port: int, timeout: float) -> Runner:
    deadline = time.monotonic() + timeout
    while True:
        try:
            return Runner(port)
        except SystemExit:
            if time.monotonic() > deadline:
                raise SystemExit(f"mods: can't reach the game on port {port} "
                                 f"(waited {timeout:.0f}s); is it running?")
            time.sleep(0.5)


def live(runner: Runner, patch: dict) -> bytes:
    return runner.read(patch["addr"], len(patch["original"]))


def write(runner: Runner, addr: int, data: bytes) -> None:
    runner.call(cmd="write_mem", cpu=9, addr=addr, hex=data.hex())


def recognised(runner: Runner, mod: dict, patch: dict) -> bool:
    """Live bytes are the original or something one of this mod's patches writes."""
    now = live(runner, patch)
    return now == patch["original"] or any(
        k["addr"] == patch["addr"] and now == k["patched"] for k in mod["known"])


def wait_for_code(runner: Runner, mods: list[dict], timeout: float) -> None:
    """The port opens before the game's code is in RAM; wait until it is."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if all(recognised(runner, m, p) for m in mods for p in m["active"]):
            return
        time.sleep(0.25)


def label(mod: dict) -> str:
    return mod["name"] + (f" ({mod['setting']})" if mod["options"] else "")


def apply_mod(runner: Runner, mod: dict) -> str:
    # First undo whatever this mod wrote that the current choice doesn't want.
    wanted = {(p["addr"], p["patched"]) for p in mod["active"]}
    for patch in mod["known"]:
        if (patch["addr"], patch["patched"]) not in wanted and live(runner, patch) == patch["patched"]:
            write(runner, patch["addr"], patch["original"])
    if not mod["active"]:
        return f"mods: {mod['name']} is off" if not mod["enabled"] else f"mods: {label(mod)}"
    if not all(live(runner, p) in (p["original"], p["patched"]) for p in mod["active"]):
        return (f"mods: SKIPPED {label(mod)}: the code there is not what this mod "
                f"expects (different ROM, or another mod changed it)")
    for patch in mod["active"]:
        if live(runner, patch) == patch["original"]:
            write(runner, patch["addr"], patch["patched"])
    ok = all(live(runner, p) == p["patched"] for p in mod["active"])
    return f"mods: {'applied' if ok else 'FAILED'} {label(mod)}"


def cmd_apply(runner: Runner, mods: list[dict]) -> None:
    wait_for_code(runner, mods, timeout=30)
    for mod in mods:
        if mod["enabled"] or any(live(runner, p) == p["patched"] for p in mod["known"]):
            print(apply_mod(runner, mod))


def cmd_status(runner: Runner, mods: list[dict]) -> None:
    for mod in mods:
        if mod["options"]:
            on = [name for name, patches in mod["options"].items()
                  if patches and all(live(runner, p) == p["patched"] for p in patches)]
            now = on[0] if on else "normal (nothing patched)"
        else:
            states = {"patched" if live(runner, p) == p["patched"] else "original"
                      for p in mod["base"]}
            now = states.pop() if len(states) == 1 else "mixed"
        print(f"  {mod['name']}: live {now}  ({'enabled' if mod['enabled'] else 'disabled'}"
              + (f", setting {mod['setting']}" if mod["options"] else "") + f", {mod['file']})")


def cmd_revert(runner: Runner, mods: list[dict]) -> None:
    for mod in mods:
        for patch in mod["known"]:
            if live(runner, patch) == patch["patched"]:
                write(runner, patch["addr"], patch["original"])
        print(f"  {mod['name']}: reverted")


def cmd_set(mods: list[dict], which: str, value: str, port: int) -> None:
    mod = next((m for m in mods if which in (m["id"], m["name"])), None)
    if mod is None:
        raise SystemExit(f"no mod called {which!r}: try one of {', '.join(m['id'] for m in mods)}")
    text = mod["path"].read_text(encoding="utf-8")
    if value in ("on", "off"):
        text, n = re.subn(r"(?m)^(\s*enabled\s*=\s*)(true|false)",
                          rf"\g<1>{'true' if value == 'on' else 'false'}", text, count=1)
    elif value in mod["options"]:
        text, n = re.subn(r'(?m)^(\s*setting\s*=\s*)"[^"]*"', rf'\g<1>"{value}"', text, count=1)
    else:
        choices = ", ".join(list(mod["options"]) + ["on", "off"])
        raise SystemExit(f"{mod['id']}: {value!r} is not one of {choices}")
    if not n:
        raise SystemExit(f"{mod['file']}: couldn't find the line to change")
    mod["path"].write_text(text, encoding="utf-8")
    print(f"{mod['id']}: set to {value}")
    try:
        runner = connect(port, timeout=1)
    except SystemExit:
        print("(the game isn't running; it takes effect at the next launch)")
        return
    print(apply_mod(runner, next(m for m in load_mods() if m["id"] == mod["id"])))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=19842)
    parser.add_argument("command", choices=("list", "apply", "set", "status", "revert"))
    parser.add_argument("mod", nargs="?")
    parser.add_argument("value", nargs="?")
    args = parser.parse_args()

    mods = load_mods()
    if args.command == "list":
        for mod in mods:
            extra = (f" setting {mod['setting']} (options: {', '.join(mod['options'])})"
                     if mod["options"] else "")
            print(f"  [{'x' if mod['enabled'] else ' '}] {mod['id']}: {mod['name']}{extra}")
        return 0
    if args.command == "set":
        if not (args.mod and args.value):
            raise SystemExit("usage: mods.py set MOD VALUE   (e.g. set faster_text instant)")
        cmd_set(mods, args.mod, args.value, args.port)
        return 0
    runner = connect(args.port, timeout=60 if args.command == "apply" else 2)
    {"apply": cmd_apply, "status": cmd_status, "revert": cmd_revert}[args.command](runner, mods)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
