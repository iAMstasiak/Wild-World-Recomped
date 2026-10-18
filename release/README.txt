Wild World Recomped
===================

Animal Crossing: Wild World, recompiled to run natively on Windows.
Developed by Mieszko (M.Stasiak).

You need your own copy of the game: a dump of Animal Crossing: Wild World
(USA, revision 1) from your own cartridge. Nothing from Nintendo comes with
this download.


First start
-----------
1. Unzip this folder anywhere you like, except inside Program Files.
2. Run WildWorldRecomped.exe.
3. Choose your ROM and press Set Up. The launcher downloads the compiler
   (70 MB, from the w64devkit and SDL projects) and builds the game from
   your ROM on your PC. It takes about 15 minutes and only happens once.
4. Press Play.

You need Windows 10 (version 1803 or newer) or Windows 11, about 4 GB of
free space for the build, and the internet for the first start.


Your files
----------
Your save is acww.sav in this folder. The game backs it up into the backups
folder each time it starts, and the launcher's Saves page imports, exports
and restores saves. Settings are in settings.toml, controls in keybinds.ini.

If setup stops, the launcher says why. The full logs are in build\logs.


Updates
-------
When a new version is out, the launcher shows an Update button at the top.
Press it to download the new version. The launcher restarts by itself and
builds the game again. Your save, settings, controls and backups stay as
they are.


What's in here
--------------
WildWorldRecomped.exe   the launcher
WildWorldBuild.exe      builds the game (the launcher runs it)
kit                     what the game is built from: ndsrecomp's and
                        recomp-ui's source, the recompiler, and the game's
                        entry points (addresses only, none of the game)
pack, build, game       made by the first start: the compiler, the build
                        and the game


Credits and licences
--------------------
Built on ndsrecomp (static recompilation for the Nintendo DS; see the
licence files in kit\ndsrecomp), the melonDS device models, recomp-ui
(kit\recomp-ui, MIT licence), Dear ImGui (MIT), SDL 3 (zlib) and FreeBIOS.
The launcher's font is Nunito (SIL Open Font License,
assets\fonts\Nunito-OFL.txt).

Animal Crossing is a trademark of Nintendo. This project is not affiliated
with or endorsed by Nintendo.
