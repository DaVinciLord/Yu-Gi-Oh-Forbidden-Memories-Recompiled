#!/usr/bin/env python3
"""Emit resident game LLVM IR on macOS arm64 without changing console sources.

This is a translation experiment, not a playable build. The resident source
selection matches build_game32.py. ELF section attributes are removed only
from generated copies because Mach-O does not accept their spelling.
"""
import concurrent.futures
import json
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / "tmp/arm64-game-ir"
SECTION = re.compile(r'__attribute__\s*\(\(\s*section\s*\(\s*"[^"\n]+"\s*\)\s*\)\)')


def main():
    generated = BUILD / "generated"
    generated.mkdir(parents=True, exist_ok=True)
    shutil.copytree(ROOT / "src", generated / "src", dirs_exist_ok=True)
    removed = 0
    for path in (generated / "src").rglob("*"):
        if path.suffix not in (".c", ".h"):
            continue
        original = path.read_text(encoding="latin-1")
        updated, count = SECTION.subn("", original)
        removed += count
        if count:
            path.write_text(updated, encoding="latin-1")
    # Retail table at 0x8009078c stores eight four-byte pointers. These
    # declarations predate guest-width annotations; fix only generated copies.
    for name in ("file_names.h", "file_names.c"):
        path = generated / "src/game" / name
        path.write_text(path.read_text().replace("u8 *gFile_apszName[8]", "u8 *G32 gFile_apszName[8]"))
    path = generated / "src/game/file_set_position_table.c"
    path.write_text(path.read_text().replace("u8 **name;", "u8 *G32 *name;"))
    sources = sorted((ROOT / "src/game").glob("*.c")) + sorted((ROOT / "src/pc/game").glob("*.c"))
    flags = ["-std=gnu11", "-fms-extensions", "-O0", "-S", "-emit-llvm", "-fno-strict-aliasing", "-fwrapv", "-fcommon", "-fno-stack-protector", "-DMEMORIES_PC", "-D_LANGUAGE_C", "-DLANGUAGE_C", "-Isrc", "-include", "src/pc/compat/pgxp_game.h", "-Wno-incompatible-pointer-types", "-Wno-int-conversion", "-Wno-implicit-function-declaration", "-w"]
    def compile_unit(source):
        relative = source.relative_to(ROOT)
        output = BUILD / "ir" / (str(relative).replace("/", "_") + ".ll")
        output.parent.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(["xcrun", "clang", *flags, str(relative), "-o", str(output)], cwd=generated, text=True, capture_output=True)
        log = BUILD / "logs" / (output.stem + ".log")
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(result.stderr)
        errors = [line.strip() for line in result.stderr.splitlines() if "error:" in line]
        return {"source": str(relative), "ir": str(output.relative_to(ROOT)), "status": result.returncode, "errors": errors}
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(compile_unit, sources))
    summary = {"units": len(results), "passed": sum(r["status"] == 0 for r in results), "section_attributes_removed": removed, "flags": flags, "results": results}
    (BUILD / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(f"Resident LLVM IR: {summary['passed']}/{summary['units']} units; {removed} section attributes removed in generated copies")
    for result in results:
        if result["status"]:
            print(result["source"], *result["errors"][:3], sep="\n  ")
    return int(summary["passed"] != summary["units"])


if __name__ == "__main__":
    raise SystemExit(main())
