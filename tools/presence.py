#!/usr/bin/env python3
"""Show what you're doing in Wild World Recomped on your Discord profile.

  py -3.12 tools\\presence.py                 run while the game runs
  py -3.12 tools\\presence.py room            which room you're in now
  py -3.12 tools\\presence.py label "At the museum"
                                             name the room you're in now

play.ps1 starts it with the game (-NoDiscord leaves it off). It reads the
game's memory through the debug port every few seconds, briefly each time so
the other tools can still use the port, and talks to the Discord app on this
PC. Room names live in tools\\presence_rooms.json; {shop} in a name becomes
the shop's current name. --hide-names and --hide-bells keep those private.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import struct
import time
import uuid
from pathlib import Path

from textfind import WW

CLIENT_ID = "1559911813724766218"
ROOM = 0x020E4170            # u32: 0 town, 1 house, 9 town hall, 29 shop
SAVE = 0x021D7350            # the save image in RAM
TOWN_NAME = SAVE + 0x0004    # 8 characters
PLAYER_NAME = SAVE + 0x228E  # player 1's name, 8 characters
BELLS = SAVE + 0x1B4C        # player 1's wallet (u32)
SHOP_WORD = 0x021ED15E       # bits 9-10: shop stage (tools\shop.py)
SHOPS = ["Nook's Cranny", "Nook 'n' Go", "Nookway", "Nookington's"]
ROOMS = Path(__file__).with_name("presence_rooms.json")
CREDIT = "Developed by Mieszko (M.Stasiak)"
DOT = " \u00b7 "


def read_game(port: int) -> dict | None:
    """One short visit to the debug port; None when the game isn't there."""
    try:
        sock = socket.create_connection(("127.0.0.1", port), timeout=10)
    except OSError:
        return None
    buf = b""

    def read(addr: int, length: int) -> bytes:
        nonlocal buf
        request = {"cmd": "read_mem", "cpu": 9, "addr": addr, "len": length}
        sock.sendall((json.dumps(request) + "\n").encode())
        while b"\n" not in buf:
            data = sock.recv(65536)
            if not data:
                raise OSError("the game closed the connection")
            buf += data
        line, buf = buf.split(b"\n", 1)
        return bytes.fromhex(json.loads(line)["hex"])

    def text(raw: bytes) -> str:
        return "".join(WW[b] for b in raw.split(b"\0")[0]).strip()

    try:
        return {
            "room": int.from_bytes(read(ROOM, 4), "little"),
            "town": text(read(TOWN_NAME, 8)),
            "player": text(read(PLAYER_NAME, 8)),
            "bells": int.from_bytes(read(BELLS, 4), "little"),
            "shop": SHOPS[(int.from_bytes(read(SHOP_WORD, 2), "little") >> 9) & 3],
        }
    except (OSError, ValueError, KeyError):
        return None
    finally:
        sock.close()


def load_rooms() -> dict[str, str]:
    if ROOMS.is_file():
        return json.loads(ROOMS.read_text())
    return {"0": "In town", "1": "At home", "9": "At the town hall",
            "29": "Shopping at {shop}"}


class Discord:
    """The Discord app's local pipe: 8-byte header (op, length), then JSON."""

    def __init__(self) -> None:
        self.pipe = None

    def connect(self) -> bool:
        for i in range(10):
            try:
                self.pipe = open(rf"\\.\pipe\discord-ipc-{i}", "r+b", buffering=0)
                break
            except OSError:
                continue
        else:
            return False
        try:
            self.send(0, {"v": 1, "client_id": CLIENT_ID})
            op, reply = self.recv()
            if reply.get("evt") == "READY":
                return True
            print(f"[presence] Discord said no: {reply}")
        except OSError:
            pass
        self.close()
        return False

    def send(self, op: int, message: dict) -> None:
        payload = json.dumps(message).encode()
        self.pipe.write(struct.pack("<II", op, len(payload)) + payload)

    def recv(self) -> tuple[int, dict]:
        op, length = struct.unpack("<II", self.read_exactly(8))
        return op, json.loads(self.read_exactly(length))

    def read_exactly(self, n: int) -> bytes:
        data = b""
        while len(data) < n:
            chunk = self.pipe.read(n - len(data))
            if not chunk:
                raise OSError("Discord closed the pipe")
            data += chunk
        return data

    def set_activity(self, activity: dict | None) -> None:
        self.send(1, {"cmd": "SET_ACTIVITY", "nonce": str(uuid.uuid4()),
                      "args": {"pid": os.getpid(), "activity": activity}})
        _, reply = self.recv()
        if reply.get("evt") == "ERROR":
            print(f"[presence] Discord didn't take it: {reply.get('data')}")

    def close(self) -> None:
        if self.pipe:
            try:
                self.pipe.close()
            except OSError:
                pass
        self.pipe = None


def activity_for(game: dict, rooms: dict[str, str], started: int,
                 hide_names: bool, hide_bells: bool) -> dict:
    where = rooms.get(str(game["room"]), "Playing").format(shop=game["shop"])
    parts = []
    if not hide_names and game["player"] and game["town"]:
        parts.append(f"{game['player']} of {game['town']}")
    if not hide_bells:
        parts.append(f"{game['bells']:,} bells")
    activity = {"details": where, "timestamps": {"start": started},
                "assets": {"large_image": "icon", "large_text": CREDIT}}
    if parts:
        activity["state"] = DOT.join(parts)
    return activity


def run(args: argparse.Namespace) -> int:
    rooms = load_rooms()
    discord = Discord()
    started = int(time.time())
    seen_game = False
    last = None
    unknown: set[int] = set()
    next_discord_try = 0.0
    waited = 0.0
    while True:
        game = read_game(args.port)
        if game is None:
            if seen_game or waited > 180:
                discord.close()
                print("[presence] the game has closed; stopping")
                return 0
            time.sleep(3)
            waited += 3
            continue
        if not seen_game:
            print("[presence] found the game")
            seen_game = True
        if game["room"] not in unknown and str(game["room"]) not in rooms:
            unknown.add(game["room"])
            print(f"[presence] room {game['room']} has no name yet; while you're "
                  f"there run: py -3.12 tools\\presence.py label \"At the ...\"")
        if discord.pipe is None and time.time() >= next_discord_try:
            if discord.connect():
                print("[presence] connected to Discord")
                last = None
            else:
                next_discord_try = time.time() + 30
        if discord.pipe is not None:
            activity = activity_for(game, rooms, started,
                                    args.hide_names, args.hide_bells)
            if activity != last:
                try:
                    discord.set_activity(activity)
                    last = activity
                except OSError:
                    discord.close()
        time.sleep(5)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("what", nargs="?", choices=["room", "label"])
    parser.add_argument("name", nargs="?", help="for label: e.g. \"At the museum\"")
    parser.add_argument("--port", type=int, default=19842)
    parser.add_argument("--hide-names", action="store_true")
    parser.add_argument("--hide-bells", action="store_true")
    args = parser.parse_args()
    if args.what is None:
        return run(args)

    game = read_game(args.port)
    if game is None:
        raise SystemExit("can't reach the game: is it running?")
    rooms = load_rooms()
    if args.what == "room":
        name = rooms.get(str(game["room"]), "(no name yet)")
        print(f"room {game['room']}: {name}")
        print(f"{game['player']} of {game['town']}, {game['bells']:,} bells, "
              f"shop: {game['shop']}")
        return 0
    if not args.name:
        raise SystemExit('give the room a name, e.g. label "At the museum"')
    rooms[str(game["room"])] = args.name
    ROOMS.write_text(json.dumps(dict(sorted(rooms.items(), key=lambda kv: int(kv[0]))),
                                indent=1) + "\n")
    print(f"room {game['room']} is now \"{args.name}\" (saved in {ROOMS.name})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
