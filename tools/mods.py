#!/usr/bin/env python3
"""Apply the code patches in mods/*.toml to the running game.

Each mod file has a [mod] table (name, enabled) and [[patch]] entries with
addr, original and patched bytes. A patch is only written when the live
bytes still match `original`, so a wrong ROM or a clashing mod is reported
instead of corrupting code. Writes go through the runner's debug port and
its normal bus path, which drops the recompiled copy of the patched code.

  list      show the mods and whether each is enabled
  apply     wait for the game, then apply every enabled mod (play.ps1 runs this)
  status    show which patches are live in the running game
  revert    put the original bytes back for every patch
"""

from __future__ import annotations

import argparse
import time
import tomllib
from pathlib import Path

from memscan import Runner

MODS_DIR = Path("mods")


def load_mods() -> list[dict]:
    mods = []
    for path in sorted(MODS_DIR.glob("*.toml")):
        with path.open("rb") as handle:
            data = tomllib.load(handle)
        info = data.get("mod", {})
        patches = [{"addr": int(p["addr"]),
                    "original": bytes.fromhex(p["original"]),
                    "patched": bytes.fromhex(p["patched"])}
                   for p in data.get("patch", [])]
        for p in patches:
            if len(p["original"]) != len(p["patched"]):
                raise SystemExit(f"{path}: patch at 0x{p['addr']:08X} changes the length")
        mods.append({"file": path.name, "name": info.get("name", path.stem),
                     "enabled": bool(info.get("enabled", False)), "patches": patches})
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


def live_state(runner: Runner, patch: dict) -> str:
    live = runner.read(patch["addr"], len(patch["original"]))
    if live == patch["patched"]:
        return "patched"
    if live == patch["original"]:
        return "original"
    return "other"


def wait_for_code(runner: Runner, mods: list[dict], timeout: float) -> None:
    """The port opens before the game's code is in RAM; wait until it is."""
    deadline = time.monotonic() + timeout
    patches = [p for m in mods for p in m["patches"]]
    while time.monotonic() < deadline:
        if all(live_state(runner, p) != "other" for p in patches):
            return
        time.sleep(0.25)


def cmd_apply(runner: Runner, mods: list[dict]) -> None:
    enabled = [m for m in mods if m["enabled"]]
    if not enabled:
        print("mods: none enabled")
        return
    wait_for_code(runner, enabled, timeout=30)
    for mod in enabled:
        states = [live_state(runner, p) for p in mod["patches"]]
        if "other" in states:
            print(f"mods: SKIPPED {mod['name']}: the code there is not what this "
                  f"mod expects (different ROM, or another mod changed it)")
            continue
        for patch, state in zip(mod["patches"], states):
            if state == "original":
                runner.call(cmd="write_mem", cpu=9, addr=patch["addr"],
                            hex=patch["patched"].hex())
        ok = all(live_state(runner, p) == "patched" for p in mod["patches"])
        print(f"mods: {'applied' if ok else 'FAILED'} {mod['name']}")


def cmd_status(runner: Runner, mods: list[dict]) -> None:
    for mod in mods:
        states = {live_state(runner, p) for p in mod["patches"]}
        live = states.pop() if len(states) == 1 else "mixed"
        print(f"  {mod['name']}: {live}  ({'enabled' if mod['enabled'] else 'disabled'}"
              f" in {mod['file']})")


def cmd_revert(runner: Runner, mods: list[dict]) -> None:
    for mod in mods:
        for patch in mod["patches"]:
            if live_state(runner, patch) == "patched":
                runner.call(cmd="write_mem", cpu=9, addr=patch["addr"],
                            hex=patch["original"].hex())
        print(f"  {mod['name']}: reverted")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=19842)
    parser.add_argument("command", choices=("list", "apply", "status", "revert"))
    args = parser.parse_args()

    mods = load_mods()
    if args.command == "list":
        for mod in mods:
            print(f"  [{'x' if mod['enabled'] else ' '}] {mod['name']}  ({mod['file']}, "
                  f"{len(mod['patches'])} patch(es))")
        return 0
    runner = connect(args.port, timeout=60 if args.command == "apply" else 2)
    {"apply": cmd_apply, "status": cmd_status, "revert": cmd_revert}[args.command](runner, mods)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
