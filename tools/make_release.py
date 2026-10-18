"""Put together the release a player unzips (generated\\release).

  py -3.12 tools\\make_release.py

The folder (and a zip of it) holds the launcher and WildWorldBuild with what
they need beside them, and kit\\: what WildWorldBuild builds the game from on
the player's PC. That is ndsrecomp's source and recomp-ui's source as they are
in your checkouts (with the patches from tools\\patch_*.py in them), the
recompiler, and the seed files (entry point addresses from the coverage, no
bytes of the game). Nothing in it comes from the ROM or from BIOS dumps: the
copy refuses ROMs, saves and dumps, and leaves ndsrecomp's generated\\ out.

Build the launcher and WildWorldBuild first (cmake --build launcher\\build),
with MSYS2's bin folder on PATH: the recompiler's DLLs are found with its
objdump and copied beside it.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# What the runner's build needs from ndsrecomp, and what tells people what it
# is and under which licences (all of the recompiler, so its source is there).
NDSRECOMP_KEEP = ["runner/", "cmake/", "external/", "recompiler/", "vendor/", "third_party/freebios/",
                  "bios/freebios9.toml", "bios/freebios7.toml", "VERSION", "LICENSE", "LICENSE-GPL",
                  "LICENSE-MIT", "THIRD_PARTY_ATTRIBUTION.md", "README.md"]
RECOMPUI_KEEP = ["src/", "LICENSE", "README.md"]
# Never in a release: a game, a save, a dump.
REFUSED = {".nds", ".sav", ".dsv", ".bin", ".rom", ".srl"}
ALLOWED_BINS = {"third_party/freebios/drastic_bios_arm9.bin", "third_party/freebios/drastic_bios_arm7.bin"}


def tracked_files(root: Path) -> list[str]:
    """Every file git would keep in the checkout (tracked or new, not
    ignored), as it is now; submodules are walked."""
    out = subprocess.run(["git", "-C", str(root), "ls-files", "-z", "--cached", "--others",
                          "--exclude-standard"], check=True, capture_output=True).stdout
    files = []
    for rel in sorted(set(p for p in out.decode("utf-8").split("\0") if p)):
        path = root / rel
        if path.is_dir():   # a submodule
            for dirpath, dirnames, filenames in os.walk(path):
                dirnames[:] = [d for d in dirnames if d != ".git" and not d.lower().startswith("build")]
                for name in filenames:
                    if name != ".git":   # a submodule's pointer to its repository
                        files.append((Path(dirpath) / name).relative_to(root).as_posix())
        elif path.is_file():
            files.append(rel)
    return files


def wanted(rel: str, keep: list[str]) -> bool:
    if not any(rel == k or (k.endswith("/") and rel.startswith(k)) for k in keep):
        return False
    # A build folder left inside the source (its parts, not the file name).
    return not any(part.lower().startswith("build") for part in rel.split("/")[:-1])


def copy_tree(src: Path, dest: Path, keep: list[str], refused: list[str]) -> int:
    count = 0
    for rel in tracked_files(src):
        if not wanted(rel, keep):
            continue
        if Path(rel).suffix.lower() in REFUSED and rel not in ALLOWED_BINS:
            refused.append(f"{src.name}/{rel}")
            continue
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src / rel, target)
        count += 1
    return count


def runtime_dlls(exe: Path, dll_dir: Path) -> list[Path]:
    """The DLLs from dll_dir that exe needs, and those they need in turn."""
    objdump = shutil.which("objdump") or str(dll_dir / "objdump.exe")
    found: dict[str, Path] = {}
    todo = [exe]
    while todo:
        binary = todo.pop()
        try:
            text = subprocess.run([objdump, "-p", str(binary)], check=True, capture_output=True,
                                  text=True).stdout
        except (OSError, subprocess.CalledProcessError):
            print(f"  (can't read the DLLs {binary.name} needs: no objdump)")
            return list(found.values())
        for name in re.findall(r"DLL Name:\s*(\S+)", text):
            dll = dll_dir / name
            if name.lower() not in found and dll.is_file():
                found[name.lower()] = dll
                todo.append(dll)
    return list(found.values())


def project_version() -> str:
    text = (ROOT / "launcher" / "CMakeLists.txt").read_text(encoding="utf-8")
    m = re.search(r"project\(\s*\S+\s+VERSION\s+([0-9.]+)", text)
    return m.group(1) if m else "0.0"


def folder_size(folder: Path) -> tuple[int, int, list[tuple[int, str]]]:
    files = [p for p in folder.rglob("*") if p.is_file()]
    sizes = sorted(((p.stat().st_size, p.relative_to(folder).as_posix()) for p in files), reverse=True)
    return len(files), sum(s for s, _ in sizes), sizes[:8]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--ndsrecomp", type=Path, default=Path(r"C:\acww\ndsrecomp"))
    parser.add_argument("--recomp-ui", type=Path, default=Path(r"C:\acww\recomp-ui"))
    parser.add_argument("--recompiler", type=Path,
                        help="nds_recompile.exe (default: ndsrecomp's recompiler\\build)")
    parser.add_argument("--launcher-build", type=Path, default=ROOT / "launcher" / "build")
    parser.add_argument("--seeds", type=Path, default=ROOT / "generated" / "ingest" / "seeds")
    parser.add_argument("--dll-dir", type=Path, default=Path(r"C:\msys64\mingw64\bin"))
    parser.add_argument("--out", type=Path, default=ROOT / "generated" / "release")
    parser.add_argument("--version", default=project_version())
    parser.add_argument("--no-zip", action="store_true")
    args = parser.parse_args()
    exe = ".exe" if os.name == "nt" else ""
    recompiler = args.recompiler or args.ndsrecomp / "recompiler" / "build" / f"nds_recompile{exe}"

    name = f"Wild World Recomped {args.version}"
    release = args.out / name
    if release.exists():
        shutil.rmtree(release)
    kit = release / "kit"
    kit.mkdir(parents=True)
    refused: list[str] = []
    missing: list[str] = []

    # The launcher, its DLLs and assets, and WildWorldBuild.
    for item in sorted(args.launcher_build.iterdir()):
        if item.suffix.lower() in (".exe", ".dll") or item.name in ("WildWorldRecomped", "WildWorldBuild"):
            shutil.copy2(item, release / item.name)
    if (args.launcher_build / "assets").is_dir():
        shutil.copytree(args.launcher_build / "assets", release / "assets")
    # The game's own files from this project: no settings, save or ROM of yours.
    shutil.copy2(ROOT / "game.toml", release / "game.toml")
    (release / "mods").mkdir()
    for mod in sorted((ROOT / "mods").glob("*.toml")):
        shutil.copy2(mod, release / "mods" / mod.name)
    rooms = ROOT / "tools" / "presence_rooms.json"
    if rooms.is_file():
        (release / "tools").mkdir()
        shutil.copy2(rooms, release / "tools" / rooms.name)
    for extra in [ROOT / "release" / "README.txt", *sorted(ROOT.glob("LICENSE*"))]:
        if extra.is_file():
            shutil.copy2(extra, release / extra.name)

    # kit\: what the game is built from.
    n = copy_tree(args.ndsrecomp, kit / "ndsrecomp", NDSRECOMP_KEEP, refused)
    print(f"kit\\ndsrecomp: {n} files from {args.ndsrecomp}")
    n = copy_tree(args.recomp_ui, kit / "recomp-ui", RECOMPUI_KEEP, refused)
    print(f"kit\\recomp-ui: {n} files from {args.recomp_ui}")
    shutil.copy2(recompiler, kit / recompiler.name)
    for dll in runtime_dlls(recompiler, args.dll_dir):
        shutil.copy2(dll, kit / dll.name)
        print(f"kit\\{dll.name} (the recompiler needs it)")
    (kit / "seeds").mkdir()
    seeds = sorted(args.seeds.glob("*.toml"))
    for seed in seeds:
        shutil.copy2(seed, kit / "seeds" / seed.name)
    print(f"kit\\seeds: {len(seeds)} seed files")

    # Everything setup and the game need, by the names they look for.
    for need in [f"WildWorldRecomped{exe}", f"WildWorldBuild{exe}", "game.toml", "assets",
                 f"kit/nds_recompile{exe}", "kit/ndsrecomp/runner/CMakeLists.txt",
                 "kit/ndsrecomp/bios/freebios9.toml", "kit/ndsrecomp/bios/freebios7.toml",
                 "kit/ndsrecomp/third_party/freebios/drastic_bios_arm9.bin",
                 "kit/ndsrecomp/third_party/freebios/drastic_bios_arm7.bin",
                 "kit/ndsrecomp/external/arm-recomp-core/cmake/ArmRecompCore.cmake",
                 "kit/recomp-ui/src/recomp_runtime_ui.h", "kit/seeds"]:
        if not (release / need).exists():
            missing.append(need)

    files, size, largest = folder_size(release)
    print(f"\n{release}: {files} files, {size / 2**20:.1f} MB")
    for s, rel in largest:
        print(f"  {s / 2**20:7.1f} MB  {rel}")
    if refused:
        print("\nleft out (a game, save or dump has no place in a release):")
        for rel in refused:
            print(f"  {rel}")
    if missing:
        print("\nMISSING, so setup would fail:")
        for rel in missing:
            print(f"  {rel}")
        return 1

    if not args.no_zip:
        archive = args.out / f"{name}.zip"
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
            for path in sorted(release.rglob("*")):
                if path.is_file():
                    z.write(path, (Path(name) / path.relative_to(release)).as_posix())
        print(f"\n{archive}: {archive.stat().st_size / 2**20:.1f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
