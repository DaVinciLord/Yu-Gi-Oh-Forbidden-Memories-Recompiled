#!/usr/bin/env python3
"""ROM-free native component checks; does not build the i386 game runtime."""
import argparse
import os
from pathlib import Path
import platform
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sanitize", action="store_true")
    parser.add_argument("--disc", type=Path, help="load SLUS_014.11 from a user-owned USA .bin; does not execute it")
    parser.add_argument("--fixed-address-probe", action="store_true",
                        help="probe the old runtime address contract; exits 77 when blocked")
    args = parser.parse_args()
    if Path.cwd().resolve() != ROOT:
        parser.error("run from the repository root")
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        parser.error("this bring-up runner currently requires macOS arm64")
    out = ROOT / "tmp" / "native-tests"
    out.mkdir(parents=True, exist_ok=True)
    compiler = os.environ.get("CC", "clang")
    flags = ["-std=c11", "-Wall", "-Wextra", "-Wpedantic", "-Werror",
             "-D_DARWIN_C_SOURCE", "-Isrc", "-Itests/pc"]
    if args.sanitize:
        flags += ["-fsanitize=address,undefined", "-fno-omit-frame-pointer"]
    cases = [
        ("state-native-memory", ["tests/pc/state_native_memory_test.c", "src/pc/guest/translated_state_memory.c",
                                 "src/pc/guest/translated_runtime.c", "src/pc/guest/state_io.c", "src/pc/memory.c"], [], [None]),
        ("state-io", ["tests/pc/state_io_test.c", "src/pc/guest/state_io.c"], [], [None]),
        ("core", ["tests/pc/core_test.c", "src/pc/memory.c", "src/pc/rng.c",
                  "src/game/rand_get_interval.c", "src/game/util_compare_s16.c"],
         ["-Drand=Memories_Rand", "-Dsrand=Memories_Srand"], [None]),
        ("game-files", ["tests/pc/game_files_test.c", "src/pc/platform/game_files.c"], [],
         "select cancel retry remembered moved headless override picker-failure malformed write-failure".split()),
        ("translated-image", ["tests/pc/translated_image_test.c", "src/pc/guest/translated_image.c",
                              "src/pc/memory.c"], [], [None]),
        ("state-remap", ["tests/pc/state_remap_test.c", "src/pc/guest/state_remap.c"], [], [None]),
        ("entry-layout", ["tests/pc/entry_layout_test.c", "src/pc/text/entry_layout.c"], [], [None]),
    ]
    count = 0
    for name, sources, extra, scenarios in cases:
        binary = out / name
        objects = []
        for index, source in enumerate(sources):
            obj = out / f"{name}-{index}.o"
            # RNG aliases belong only to the decompiled game unit.
            unit_flags = extra if source == "src/game/rand_get_interval.c" else []
            subprocess.run([compiler, *flags, *unit_flags, "-c", source, "-o", str(obj)], check=True)
            objects.append(str(obj))
        subprocess.run([compiler, *flags, *objects, "-o", str(binary)], check=True)
        for scenario in scenarios:
            subprocess.run([str(binary), *([] if scenario is None else [scenario])], check=True,
                           env={**os.environ, "TMPDIR": str(out)})
            count += 1
    binary = out / "native-guest-contract"
    subprocess.run([compiler, *flags, "-Wno-language-extension-token", "-DMEMORIES_PC", "-fms-extensions",
                    "tests/pc/native_guest_contract_test.c", "src/pc/memory.c",
                    "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
    count += 1
    binary = out / "arm64-state-context"
    # Context restoration deliberately switches back to the caller's frame;
    # this assembly boundary is verified without sanitizer stack bookkeeping.
    subprocess.run([compiler, "-std=c11", "-Wall", "-Wextra", "-Werror", "-O2", "-Isrc",
                    "tests/pc/state_arm64_context_test.c", "src/pc/guest/translated_state_arm64.S",
                    "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
    count += 1
    binary = out / "arm64-game-jumps"
    subprocess.run([compiler, "-std=c11", "-Wall", "-Wextra", "-Werror", "-O2", "-Isrc",
                    "tests/pc/translated_jmp_test.c", "src/pc/guest/translated_jmp.c",
                    "src/pc/guest/translated_setjmp_arm64.S", "src/pc/guest/translated_state_arm64.S",
                    "src/pc/guest/translated_runtime.c", "src/pc/guest/state_io.c", "src/pc/memory.c",
                    "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
    count += 1
    binary = out / "native-state-lifecycle"
    subprocess.run([compiler, *flags, "-Wno-language-extension-token",
                    "-Wno-gnu-folding-constant", "-Wno-pointer-to-int-cast",
                    "-DMEMORIES_PC", "-fms-extensions", "tests/pc/state_translated_test.c",
                    "src/pc/guest/state_translated.c", "src/pc/guest/state_io.c", "src/pc/guest/translated_runtime.c",
                    "src/pc/memory.c", "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
    count += 1
    subprocess.run([sys.executable, "tools/pc/test_translated_game_unit.py",
                    *(["--sanitize"] if args.sanitize else [])], check=True)
    count += 1
    print(f"{count} native component scenarios passed", flush=True)
    if args.disc:
        binary = out / "memories-native-loader"
        subprocess.run([compiler, *flags, "-Wl,-dead_strip", "tools/pc/native_loader.c",
                        "src/pc/guest/translated_image.c", "src/pc/memory.c",
                        "src/pc/platform/game_files.c", "-o", str(binary)], check=True)
        subprocess.run([str(binary), str(args.disc)], check=True)
    if not args.fixed_address_probe:
        return 0
    # ASan reserves virtual address ranges; address feasibility must be checked
    # separately in an ordinary, unsanitized Mach-O executable.
    binary = out / "darwin-address"
    subprocess.run([compiler, "-std=c11", "-Isrc", "-DMEMORIES_PC", "-fms-extensions",
                    "tests/pc/darwin_address_test.c", "-o", str(binary)], check=True)
    result = subprocess.run([str(binary)])
    if result.returncode == 77:
        print("BLOCKED: fixed-address runtime; isolated translation prototype passed", flush=True)
    elif result.returncode != 0:
        return result.returncode
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
