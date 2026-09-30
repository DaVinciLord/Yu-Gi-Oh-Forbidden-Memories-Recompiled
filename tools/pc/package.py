#!/usr/bin/env python3
"""Build the game for sharing: one archive for Windows, one for Linux.

    python3 tools/pc/package.py            # both, into dist/

Each archive is a folder a player unpacks and runs: the executable, the mods
the release ships (the same object files for both systems), the mod SDK,
the official European languages' text (languages/, Game > Language), the
symbol table save states and crash reports use, an empty "game" folder for
the player's own disc image, and README.txt (tools/pc/release). Nothing else
from the game's discs is included.

The Linux executable is built against Debian 11's libraries
(tools/pc/build_linux_sysroot.py), as every Linux build is, so it runs on
other people's Linux. Both builds are smoke tested before they are packed."""
import argparse, datetime, os, re, shutil, struct, subprocess, sys, tarfile, zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DIST = os.path.join(ROOT, "dist")
NAME = "yfm-redecomp"
# memories-pc.pdb: the Windows build's symbols, for a debugger or profiler.
BUILDS = {"windows": ("tmp/pc/win32", "memories-pc.exe", ["SDL3.dll", "memories-pc.pdb"]),
          "linux": ("tmp/pc/game32", "memories-pc", [])}
GAME_README = """Start memories-pc and choose your own ROM in the welcome screen.
Alternatively, put your raw image of Forbidden Memories (USA, SLUS-01411)
here: the .bin file of a .bin/.cue pair. Any file name ending in .bin will do.
"""


def version():
    commit = subprocess.run(["git", "describe", "--always", "--dirty"], cwd=ROOT, capture_output=True,
                            text=True).stdout.strip() or "unknown"
    return f"{datetime.date.today():%Y%m%d}-{commit}"


def build(system, label, skip_smoke=False):
    command = [sys.executable, "tools/pc/build_game32.py", "--target", system,
               "--backend", "sdl", "--release", "--build", BUILDS[system][0]]
    # The label is the version the update check compares (notes/updates.md);
    # one that is not vX.Y.Z[-PRE] makes a build that never checks.
    subprocess.run(command, cwd=ROOT, check=True, env=dict(os.environ, MEMORIES_VERSION=label))
    if skip_smoke:
        print("package: gameplay smoke tests skipped (no disc required)")
        return
    smoke = [sys.executable, "tools/pc/smoke.py"]
    smoke += ["--windows"] if system == "windows" else ["--executable", os.path.join(BUILDS[system][0], BUILDS[system][1])]
    if subprocess.run(smoke, cwd=ROOT).returncode:
        sys.exit(f"package: the {system} build failed its smoke test; nothing was packed")


def strip(executable):
    """Drop the COFF symbol table and DWARF from the shipped .exe. The build
    keeps the table only to write symbols/<id>.txt, which save states and
    crash reports read; memories-pc.pdb serves debuggers. Left in, it is
    some 350 KB after the last section, where scanners' heuristics expect a
    dropper's payload (Bitdefender flagged v0.1.2 as Gen:Variant.Yogi)."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import build_win32_deps
    build_win32_deps.use_toolchain()
    subprocess.run(["llvm-strip", "--strip-all", executable], check=True)
    set_pe_checksum(executable)


def set_pe_checksum(executable):
    """Fill in the PE header's CheckSum, which the linker leaves 0 (Windows
    checks it only for drivers). Virus scanners' models read a zero or wrong
    one as a sign of a hand-made or patched file; the Microsoft toolchain's
    /RELEASE writes it. The algorithm is ImageHlp's CheckSumMappedFile."""
    with open(executable, "rb") as handle:
        data = bytearray(handle.read())
    field = int.from_bytes(data[0x3C:0x40], "little") + 24 + 64   # e_lfanew, PE signature + COFF header, CheckSum
    data[field:field + 4] = bytes(4)
    padded = data + bytes(len(data) % 2)
    total = 0
    for (word,) in struct.iter_unpack("<H", padded):
        total += word
        total = (total & 0xFFFF) + (total >> 16)
    total = (total & 0xFFFF) + (total >> 16)
    data[field:field + 4] = (total + len(data)).to_bytes(4, "little")
    with open(executable, "wb") as handle:
        handle.write(data)


def stage(system, label):
    build_dir, executable, extras = BUILDS[system]
    build_dir = os.path.join(ROOT, build_dir)
    folder = os.path.join(DIST, "stage", system, f"{NAME}-{label}")
    shutil.rmtree(os.path.dirname(folder), ignore_errors=True)
    os.makedirs(os.path.join(folder, "game"))
    for name in [executable, "buildid", "commit"] + extras:
        shutil.copy2(os.path.join(build_dir, name), folder)
    if system == "windows":
        strip(os.path.join(folder, executable))
    for name in ("mods", "sdk", "languages"):
        shutil.copytree(os.path.join(build_dir, name), os.path.join(folder, name))
    # This build's symbol table, under its build id and under the game
    # fingerprint (the same table): not the ones earlier builds left there.
    with open(os.path.join(build_dir, "buildid")) as handle:
        current = os.path.join(build_dir, "symbols", handle.read().strip() + ".txt")
    os.makedirs(os.path.join(folder, "symbols"))
    for name in os.listdir(os.path.join(build_dir, "symbols")):
        path = os.path.join(build_dir, "symbols", name)
        with open(path, "rb") as a, open(current, "rb") as b:
            if a.read() == b.read():
                shutil.copy2(path, os.path.join(folder, "symbols", name))
    shutil.copy2(os.path.join(ROOT, "tools/pc/release/README.txt"), folder)
    shutil.copy2(os.path.join(ROOT, "LICENSE"), folder)
    with open(os.path.join(folder, "game", "README.txt"), "w", newline="\r\n" if system == "windows" else "\n") as handle:
        handle.write(GAME_README)
    if system == "windows":   # Notepad and friends
        with open(os.path.join(folder, "README.txt"), encoding="utf-8") as handle:
            text = handle.read()
        with open(os.path.join(folder, "README.txt"), "w", encoding="utf-8", newline="\r\n") as handle:
            handle.write(text)
    return folder


def pack(system, folder):
    base = os.path.join(DIST, os.path.basename(folder) + ("-windows.zip" if system == "windows" else "-linux.tar.gz"))
    parent = os.path.dirname(folder)
    if system == "windows":
        with zipfile.ZipFile(base, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for directory, _, files in os.walk(folder):
                for name in sorted(files):
                    path = os.path.join(directory, name)
                    archive.write(path, os.path.relpath(path, parent))
    else:
        def executable(info):   # the program runs; everything else is plain data
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            if info.isfile():
                info.mode = 0o755 if info.name.endswith("/memories-pc") else 0o644
            return info
        with tarfile.open(base, "w:gz") as archive:
            archive.add(folder, os.path.basename(folder), filter=executable)
    return base


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("systems", nargs="*", help="windows, linux (default: both)")
    parser.add_argument("--no-build", action="store_true", help="pack what is already built")
    parser.add_argument("--skip-smoke", action="store_true", help="build without ROM-dependent gameplay tests (CI)")
    parser.add_argument("--version", help="archive version, e.g. v0.1.0 or dev-abcdef0")
    options = parser.parse_args()
    systems = options.systems or ["windows", "linux"]
    if set(systems) - set(BUILDS):
        parser.error("systems are windows and linux")
    label = options.version or version()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}", label):
        parser.error("version must be 1-100 letters, numbers, dots, underscores or hyphens, starting with a letter or number")
    made = []
    for system in systems:
        if not options.no_build:
            build(system, label, options.skip_smoke)
        made.append(pack(system, stage(system, label)))
    shutil.rmtree(os.path.join(DIST, "stage"), ignore_errors=True)
    for path in made:
        print(f"{os.path.relpath(path, ROOT)}: {os.path.getsize(path) / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
