#!/usr/bin/env python3
"""Build the game for sharing: archives for Windows (32-bit and 64-bit) and Linux.

    python3 tools/pc/package.py                # all three, into dist/
    python3 tools/pc/package.py windows-x64    # the 64-bit Windows one only

Packing all three where the 64-bit Windows game cannot be built (no
x86_64-w64-mingw32-clang 21 or later) skips that one with a message and
packs the other two; asking for windows-x64 by name stops there instead.

Each archive is a folder a player unpacks and runs: the executable, the mods
the release ships (the same object files for both systems), the mod SDK,
the official European languages' text (languages/, Game > Language), the
symbol table save states and crash reports use, an empty "game" folder for
the player's own disc image, and README.txt (tools/pc/release). Nothing else
from the game's discs is included.

The Linux executable is built against Debian 11's libraries
(tools/pc/build_linux_sysroot.py), as every Linux build is, so it runs on
other people's Linux. Every build is smoke tested before it is packed.

The 64-bit Windows archive (-windows-x64.zip, notes/pc-build.md "64-bit
Windows") unpacks to a folder of its own (yfm-redecomp-<version>-x64) and
carries only the data mods, no mod SDK, and a README whose Mods section
says so: that game refuses code mods, which are 32-bit objects. Its smoke
test skips the cases that turn one on.

    python3 tools/pc/package.py android-arm64  # the Android app, signed

android-arm64 is not among the default ones (it needs the Android SDK, the
NDK and a JDK; notes/pc-build.md, "Android"). Its package is the APK itself,
dist/yfm-redecomp-<version>-android-arm64.apk, and it is made only with the
release key: MEMORIES_ANDROID_KEYSTORE and its password must be set
(tools/pc/package_android.py, notes/pc-release.md "Android signing"), and an
APK signed with the debug key is never put in dist/. A build_game32.py
--target android-arm64-v8a build without them is the debug-signed APK for
testing, in its build folder."""
import argparse, datetime, os, re, shutil, struct, subprocess, sys, tarfile, zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DIST = os.path.join(ROOT, "dist")
NAME = "yfm-redecomp"
# memories-pc.pdb: the Windows build's symbols, for a debugger or profiler.
BUILDS = {"windows": ("tmp/pc/win32", "memories-pc.exe", ["SDL3.dll", "memories-pc.pdb"]),
          "windows-x64": ("tmp/pc/win64", "memories-pc.exe", ["SDL3.dll", "memories-pc.pdb"]),
          "linux": ("tmp/pc/game32", "memories-pc", []),
          "android-arm64": ("tmp/pc/android-arm64-v8a", "memories-arm64-v8a.apk", [])}
SUFFIX = {"windows": "-windows.zip", "windows-x64": "-windows-x64.zip", "linux": "-linux.tar.gz",
          "android-arm64": "-android-arm64.apk"}
# build_game32.py's --target for a system, where it is not the same name.
TARGETS = {"android-arm64": "android-arm64-v8a"}
# The archive's top folder: the two Windows archives unpacked side by side
# must not mix (the 32-bit sdk/ beside the 64-bit executable).
FOLDER = {"windows-x64": "-x64"}
# The README's Mods section for the 64-bit Windows game, which ships and
# loads data mods only (tools/pc/release/README.txt has the 32-bit one).
X64_MODS = """Game > Mods lists the mods the game found and lets you turn them on and
off. This is the 64-bit Windows game: it loads mods made of data (cards,
rules, texture packs, sounds, translations), not mods that contain code,
which are built for the 32-bit game. 3D Monsters, Hand Camera, AI Hard
Mode and Yamyi Mods are code mods, so they come with the 32-bit Windows
and Linux archives only; a code mod you install here stays off, with the
reason beside it in Game > Mods.

To install someone else's mod, put its folder in the "mods" folder of your
user folder. Mod authors: the mod SDK comes with the 32-bit archives.
"""
GAME_README = """Start memories-pc and choose your own ROM in the welcome screen.
Alternatively, put your raw image of Forbidden Memories (USA, SLUS-01411)
here: the .bin file of a .bin/.cue pair. Any file name ending in .bin will do.
"""


def version():
    commit = subprocess.run(["git", "describe", "--always", "--dirty"], cwd=ROOT, capture_output=True,
                            text=True).stdout.strip() or "unknown"
    return f"{datetime.date.today():%Y%m%d}-{commit}"


def x64_toolchain_missing():
    """Why the 64-bit Windows game cannot be built here, or None: it needs
    x86_64-w64-mingw32-clang, clang 21 or later (build_game32.py's compiler
    gate refuses older ones), looked for where the build looks too."""
    if sys.platform != "win32":     # the llvm-mingw fetched into tmp/pc (on Windows it would fetch one)
        import build_win32_deps
        build_win32_deps.use_toolchain()
    compiler = shutil.which("x86_64-w64-mingw32-clang")
    if not compiler:
        return "x86_64-w64-mingw32-clang is not on PATH"
    first = (subprocess.run([compiler, "--version"], capture_output=True, text=True).stdout.splitlines() or ["?"])[0]
    match = re.search(r"clang version (\d+)", first)
    if not match or int(match.group(1)) < 21:
        return f"{compiler} is {first}, and the 64-bit game needs clang 21 or later"
    return None


def build(system, label, skip_smoke=False):
    command = [sys.executable, "tools/pc/build_game32.py", "--target", TARGETS.get(system, system),
               "--backend", "sdl", "--release", "--build", BUILDS[system][0]]
    # The label is the version the update check compares (notes/updates.md);
    # one that is not vX.Y.Z[-PRE] makes a build that never checks.
    subprocess.run(command, cwd=ROOT, check=True, env=dict(os.environ, MEMORIES_VERSION=label))
    if skip_smoke or system == "android-arm64":
        print("package: gameplay smoke tests skipped " +
              ("(no disc required)" if skip_smoke else "(the smoke test runs desktop games only)"))
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
    if sys.platform != "win32":     # the llvm-mingw fetched into tmp/pc (on Windows it would fetch one)
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
    folder = os.path.join(DIST, "stage", system, f"{NAME}-{label}{FOLDER.get(system, '')}")
    shutil.rmtree(os.path.dirname(folder), ignore_errors=True)
    os.makedirs(os.path.join(folder, "game"))
    for name in [executable, "buildid", "commit"] + extras:
        shutil.copy2(os.path.join(build_dir, name), folder)
    if system.startswith("windows"):
        strip(os.path.join(folder, executable))
    for name in ("mods", "sdk", "languages"):
        if name == "sdk" and system == "windows-x64":
            continue   # the SDK builds 32-bit code mods, which this game refuses
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
    if system == "windows-x64":
        with open(os.path.join(folder, "README.txt"), encoding="utf-8") as handle:
            text = handle.read()
        start = text.index("Game > Mods lists")
        end = text.index("Languages" + chr(10) + "---------")
        with open(os.path.join(folder, "README.txt"), "w", encoding="utf-8") as handle:
            handle.write(text[:start] + X64_MODS + chr(10) + chr(10) + text[end:])
    shutil.copy2(os.path.join(ROOT, "LICENSE"), folder)
    with open(os.path.join(folder, "game", "README.txt"), "w", newline="\r\n" if system.startswith("windows") else "\n") as handle:
        handle.write(GAME_README)
    if system.startswith("windows"):   # Notepad and friends
        with open(os.path.join(folder, "README.txt"), encoding="utf-8") as handle:
            text = handle.read()
        with open(os.path.join(folder, "README.txt"), "w", encoding="utf-8", newline="\r\n") as handle:
            handle.write(text)
    return folder


def release_key_missing():
    """Why the Android APK cannot be packed, or None: only the release key
    signs what goes in dist/ (package_android.signing_key)."""
    if not os.environ.get("MEMORIES_ANDROID_KEYSTORE"):
        return ("MEMORIES_ANDROID_KEYSTORE is not set, and the APK in dist/ is signed with the release key only "
                "(notes/pc-release.md, \"Android signing\"); build_game32.py --target android-arm64-v8a makes "
                "a debug-signed one for testing")
    return None


def pack_apk(label):
    """dist/yfm-redecomp-<version>-android-arm64.apk: the APK the build
    signed, checked again here. The key named by MEMORIES_ANDROID_KEYSTORE
    signed it, which this checks as far as it can without the key: one
    signer, not the debug key, and MEMORIES_ANDROID_CERT_SHA256 if set."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import package_android
    build_dir, apk, _ = BUILDS["android-arm64"]
    source = os.path.join(ROOT, build_dir, apk)
    certificate = package_android.signer(source)
    if certificate["dn"] == package_android.DEBUG_DN:
        sys.exit(f"package: {os.path.relpath(source, ROOT)} is signed with the debug key; nothing was packed")
    expected = os.environ.get("MEMORIES_ANDROID_CERT_SHA256")
    mismatch = expected and package_android.check_fingerprint(certificate["sha256"], expected)
    if mismatch:
        sys.exit(f"package: {os.path.relpath(source, ROOT)}: {mismatch}; nothing was packed")
    # The version the APK was built with must be this package's (--version):
    # --no-build packs what is there, which may be an earlier build's.
    os.environ["MEMORIES_VERSION"] = label
    wanted, found = package_android.app_version(), package_android.manifest_version(source)
    if found != wanted:
        sys.exit(f"package: {os.path.relpath(source, ROOT)} is version {found[1]} (versionCode {found[0]}), "
                 f"not {wanted[1]} ({wanted[0]}) as --version {label} makes it: build it again; nothing was packed")
    os.makedirs(DIST, exist_ok=True)
    target = os.path.join(DIST, f"{NAME}-{label}{SUFFIX['android-arm64']}")
    shutil.copyfile(source, target)
    print(f"package: {os.path.relpath(target, ROOT)}: {found[1]} (versionCode {found[0]}), "
          f"signed by {certificate['dn']}, SHA-256 {package_android.colons(certificate['sha256'])}")
    return target


def pack(system, folder):
    name = os.path.basename(folder)
    name = name[:len(name) - len(FOLDER.get(system, ""))]
    base = os.path.join(DIST, name + SUFFIX[system])
    parent = os.path.dirname(folder)
    if system.startswith("windows"):
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
    parser.add_argument("systems", nargs="*", help="windows, windows-x64, linux (default: those three), "
                                                    "android-arm64 (the APK, release key only)")
    parser.add_argument("--no-build", action="store_true", help="pack what is already built")
    parser.add_argument("--skip-smoke", action="store_true", help="build without ROM-dependent gameplay tests (CI)")
    parser.add_argument("--version", help="archive version, e.g. v0.1.0 or dev-abcdef0")
    options = parser.parse_args()
    systems = options.systems or ["windows", "windows-x64", "linux"]
    if set(systems) - set(BUILDS):
        parser.error("systems are windows, windows-x64, linux and android-arm64")
    if "android-arm64" in systems and release_key_missing():
        sys.exit(f"package: cannot pack android-arm64: {release_key_missing()}")
    label = options.version or version()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}", label):
        parser.error("version must be 1-100 letters, numbers, dots, underscores or hyphens, starting with a letter or number")
    if "windows-x64" not in systems:
        missing = None
    elif options.no_build:
        executable = os.path.join(ROOT, BUILDS["windows-x64"][0], BUILDS["windows-x64"][1])
        missing = None if os.path.isfile(executable) else f"{os.path.relpath(executable, ROOT)} is not built"
    else:
        missing = x64_toolchain_missing()
    if missing and options.systems:
        sys.exit(f"package: cannot pack windows-x64: {missing}")
    if missing:
        # Packing everything: the other archives do not wait on it.
        print(f"package: windows-x64 skipped: {missing}; the other archives are packed", file=sys.stderr)
        systems = [system for system in systems if system != "windows-x64"]
    made = []
    for system in systems:
        if not options.no_build:
            build(system, label, options.skip_smoke)
        made.append(pack_apk(label) if system == "android-arm64" else pack(system, stage(system, label)))
    shutil.rmtree(os.path.join(DIST, "stage"), ignore_errors=True)
    for path in made:
        print(f"{os.path.relpath(path, ROOT)}: {os.path.getsize(path) / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
