#!/usr/bin/env python3
"""Census existing native runtime compatibility with macOS arm64, without linking.

No dependency downloads or source modifications. Requires the generated source
copies from build_arm64_game_ir.py. Excludes the replaced fixed-address image,
x86 assembly, and fixed-address branch thunks. This is not a playable build.
"""
import concurrent.futures
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / "tmp/arm64-native-ir"
GENERATED = ROOT / "tmp/arm64-game-ir/generated"
BACKENDS = {"src/pc/platform/sdl.c", "src/pc/platform/x11.c", "src/pc/platform/audio_alsa.c", "src/pc/platform/gamepad_evdev.c"}
EXCLUDE = {"src/pc/guest/image.c", "src/pc/guest/branch_thunks.c"}


def main():
    if not GENERATED.exists():
        raise SystemExit("Run build_arm64_game_ir.py first")
    patterns = ["guest/*.c", "sdk/*.c", "platform/*.c", "overlays/*.c", "overrides/*.c", "audio/*.c", "mods/*.c", "debug/*.c", "cards/*.c", "free_duel/*.c", "saves/*.c", "text/*.c"]
    sources = {p.relative_to(ROOT) for pattern in patterns for p in (ROOT / "src/pc").glob(pattern)}
    sources |= {Path("src/pc/") / p for p in ["render/soft_gpu.c", "render/texture_dump.c", "render/texture_pack.c", "rng.c", "compat/fs.c", "compat/gte.c", "compat/pgxp.c", "compat/libgs_ot.c", "render/packets.c"]}
    sources = sorted(s for s in sources if str(s) not in BACKENDS | EXCLUDE)
    flags = ["-std=gnu11", "-fms-extensions", "-O0", "-S", "-emit-llvm", "-fno-strict-aliasing", "-DMEMORIES_PC", "-D_LANGUAGE_C", "-DLANGUAGE_C", "-Isrc", "-I/opt/homebrew/include", "-I/opt/homebrew/include/freetype2", "-Wno-incompatible-pointer-types", "-Wno-int-conversion", "-Wno-implicit-function-declaration", "-w"]
    def compile_unit(source):
        output = BUILD / "ir" / (str(source).replace("/", "_") + ".ll")
        output.parent.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(["xcrun", "clang", *flags, str(source), "-o", str(output)], cwd=GENERATED, text=True, capture_output=True)
        log = BUILD / "logs" / (output.stem + ".log")
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(result.stderr)
        return {"source": str(source), "status": result.returncode, "errors": [line.strip() for line in result.stderr.splitlines() if "error:" in line]}
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(compile_unit, sources))
    summary = {"units": len(results), "passed": sum(r["status"] == 0 for r in results), "flags": flags, "excluded": sorted(EXCLUDE | BACKENDS), "results": results}
    (BUILD / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(f"Native runtime LLVM IR: {summary['passed']}/{summary['units']} units")
    for result in results:
        if result["status"]:
            print(result["source"], *result["errors"][:5], sep="\n  ")
    return int(summary["passed"] != summary["units"])


if __name__ == "__main__":
    raise SystemExit(main())
