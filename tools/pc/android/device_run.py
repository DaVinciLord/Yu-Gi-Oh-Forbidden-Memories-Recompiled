#!/usr/bin/env python3
"""Run the Android build as a plain process on a phone over adb, headless,
as if it were a desktop executable: tools/pc/replay.py and smoke-style
callers start it with their MEMORIES_* environment, and this forwards it.

    python tools/pc/android/device_run.py setup BUILD      push runner, libraries, disc
    python tools/pc/android/device_run.py run BUILD        (what BUILD/device.cmd runs)

setup builds tools/pc/android/runner.c with the NDK, pushes it with
libgame.so, libSDL3.so and the disc (MEMORIES_DISC, or game/*.bin) to
/data/local/tmp/yfm64, and writes BUILD/device.cmd (Windows) and
BUILD/device.sh, which replay.py takes as --executable:

    python tools/pc/replay.py play tests/pc/replays/first-duel --check \\
        --executable tmp/pc/android-arm64-v8a/device.cmd

run pushes the files the environment names (MEMORIES_SETTINGS,
MEMORIES_PLAY, MEMORIES_LOAD_STATE), runs the game there with the same
variables pointed at the copies, and pulls MEMORIES_RECORD's file back. The
serial is $ANDROID_SERIAL, else the only device. The disc stays on the
phone, in the shell user's private folder; nothing of it is committed."""
import glob, os, shlex, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import build_android_deps  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
REMOTE = "/data/local/tmp/yfm64"
FILES = ("MEMORIES_SETTINGS", "MEMORIES_PLAY", "MEMORIES_LOAD_STATE", "MEMORIES_INPUT_FILE")


def adb():
    sdk = os.environ.get("ANDROID_SDK_ROOT") or os.environ.get("ANDROID_HOME") or "D:/Android/sdk"
    path = os.path.join(sdk, "platform-tools", "adb.exe" if os.name == "nt" else "adb")
    return [path] + (["-s", os.environ["ANDROID_SERIAL"]] if os.environ.get("ANDROID_SERIAL") else [])


def call(*args, quiet=False):
    result = subprocess.run(adb() + list(args), capture_output=True, text=True)
    if result.returncode and not quiet:
        sys.exit(f"adb {' '.join(args)}: {result.stderr.strip() or result.stdout.strip()}")
    return result.stdout


def setup(build):
    clang = os.path.join(build_android_deps.llvm_bin(), "clang")
    runner = os.path.join(build, "runner")
    subprocess.run([clang, "--target=aarch64-linux-android24", "-fPIE", "-pie", "-O2", "-Wall",
                    "-DGAME_BASE=0x40000000", "-DGAME_SPAN=0x04000000",
                    os.path.join(ROOT, "tools", "pc", "android", "runner.c"), "-ldl", "-o", runner], check=True)
    disc = os.environ.get("MEMORIES_DISC") or next(iter(sorted(glob.glob(os.path.join(ROOT, "game", "*.bin")))), None)
    if not disc:
        sys.exit("device_run: no disc (set MEMORIES_DISC)")
    call("shell", f"mkdir -p {REMOTE}/game {REMOTE}/run")
    sdl = os.path.join(build_android_deps.OUT, "arm64-v8a", "lib", "libSDL3.so")
    for local in (runner, os.path.join(build, "libgame.so"), sdl):
        call("push", local, f"{REMOTE}/")
    if call("shell", f"ls {REMOTE}/game/disc.bin", quiet=True).strip() != f"{REMOTE}/game/disc.bin":
        call("push", disc, f"{REMOTE}/game/disc.bin")
    call("shell", f"chmod 755 {REMOTE}/runner")
    with open(os.path.join(build, "device.cmd"), "w") as handle:
        handle.write(f'@"{sys.executable}" "{os.path.abspath(__file__)}" run "{os.path.abspath(build)}" %*\n')
    with open(os.path.join(build, "device.sh"), "w", newline="\n") as handle:
        handle.write(f'#!/bin/sh\nexec python3 "{os.path.abspath(__file__)}" run "{os.path.abspath(build)}" "$@"\n')
    print(f"device_run: ready in {REMOTE}; executable for replay.py: {os.path.join(build, 'device.cmd')}")


def run(build, argv):
    env = {key: value for key, value in os.environ.items() if key.startswith("MEMORIES_")}
    call("shell", f"rm -rf {REMOTE}/run; mkdir -p {REMOTE}/run/user")
    for key in FILES:
        if env.get(key) and os.path.isfile(env[key]):
            remote = f"{REMOTE}/run/{key.lower()}_{os.path.basename(env[key])}"
            call("push", env[key], remote)
            env[key] = remote
    record = env.get("MEMORIES_RECORD")
    if record:
        env["MEMORIES_RECORD"] = f"{REMOTE}/run/record.txt"
    env["MEMORIES_USER_DIR"] = f"{REMOTE}/run/user"
    env["MEMORIES_DISC"] = f"{REMOTE}/game/disc.bin"
    env["MEMORIES_PROGRAM_DIR"] = REMOTE
    env["MEMORIES_RUNNER_LIBS"] = REMOTE
    exports = " ".join(f"{key}={shlex.quote(value)}" for key, value in sorted(env.items()))
    command = f"cd {REMOTE} && LD_LIBRARY_PATH={REMOTE} {exports} ./runner {' '.join(shlex.quote(a) for a in argv)}; echo EXIT=$?"
    result = subprocess.run(adb() + ["shell", command], capture_output=True, text=True, errors="replace")
    output = result.stdout + result.stderr
    code = 1
    for line in output.splitlines():
        if line.startswith("EXIT="):
            code = int(line[5:].strip() or 1)
        else:
            print(line)
    if record:
        call("pull", f"{REMOTE}/run/record.txt", record, quiet=True)
    return code


if __name__ == "__main__":
    if len(sys.argv) < 3 or sys.argv[1] not in ("setup", "run"):
        sys.exit(__doc__)
    sys.exit(setup(sys.argv[2]) if sys.argv[1] == "setup" else run(sys.argv[2], sys.argv[3:]))
