# Wild World Recomped

Animal Crossing: Wild World for the Nintendo DS, recompiled to run natively
on Windows, with HD graphics, a launcher and mods.

Developed by Mieszko (M.Stasiak).

**[Download the latest release](https://github.com/iAMstasiak/Wild-World-Recomped/releases/latest)**

> You need your own copy of the game: a dump of Animal Crossing: Wild World
> (USA, revision 1) from your own cartridge. Nothing from Nintendo is in this
> repository or its releases, and none will be shared, so please don't ask for
> ROMs in issues.

## How it works

Wild World Recomped is a static recompilation. The game's ARM code is
translated into C ahead of time and compiled into a Windows program, instead
of being emulated one instruction at a time. It's built on ndsrecomp.

The game's code can't be shared, so the build happens on your PC from your own
ROM. A release brings the tools for that, not the game: the first time you
start it, the launcher downloads a compiler and builds the game for you.

## Features

- HD graphics: 3x resolution, anti-aliasing, smoothed 2D and sharp text
- A launcher for graphics, display, controls, mods and settings, showing your
  town, player and bells from your save
- Save backups each time the game starts, with a Saves page to restore,
  import and export saves
- Keyboard and controller bindings
- Mods: faster dialogue text, and Nookington's without the multiplayer
  requirement
- Discord presence
- Updates itself: the launcher shows an Update button when a new version is out

## Getting started

1. Download the zip from the
   [latest release](https://github.com/iAMstasiak/Wild-World-Recomped/releases/latest)
   and unzip it anywhere except Program Files.
2. Run `WildWorldRecomped.exe`.
3. Choose your ROM and press **Set Up**. The launcher downloads the compiler
   (70 MB, from the w64devkit and SDL projects) and builds the game on your
   PC. It takes about 15 minutes and only happens once.
4. Press **Play**.

You need 64-bit Windows 10 (version 1803 or newer) or Windows 11, about 4 GB
of free space, and an internet connection for the first start.

Your save (`acww.sav`), settings (`settings.toml`), controls (`keybinds.ini`)
and backups stay in the folder you unzipped. Updates leave them alone.

## What's in this repository

| Folder | What it holds |
| --- | --- |
| `launcher/` | The launcher, `WildWorldRecomped.exe`, built on recomp-ui |
| `launcher/builder/` | `WildWorldBuild.exe`, which builds the game on a player's PC and applies updates |
| `tools/` | The patches that adapt ndsrecomp and recomp-ui for Wild World, and the release script |
| `mods/` | The mods that come with the game |
| `release/` | The players' README that goes in each release |

The development setup expects checkouts of ndsrecomp and recomp-ui beside this
one and MSYS2's MinGW-w64 toolchain. `tools/make_release.py` packages a
release. A step-by-step guide for contributors is still to come.

## Licences

- The code in this repository is under the MIT licence (see `LICENSE`).
- Releases also contain ndsrecomp. Its recompiler is under the PolyForm
  Noncommercial licence, its runner code under MIT, and its parts from melonDS
  under GPL-3.0, which makes the built game a GPL program. Because of the
  recompiler's licence, releases are free and can't be sold.
- recomp-ui and Dear ImGui (MIT), SDL 3 (zlib), FreeBIOS, and the Nunito font
  (SIL Open Font License).
- The launcher's background pattern is by usrkitt.

Animal Crossing is a trademark of Nintendo. This project is not affiliated
with or endorsed by Nintendo.
