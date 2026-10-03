#!/usr/bin/env python3
"""Exact, scoped adapter for func_80038898; never modifies matching sources.

This is an executable feasibility proof, not a general source translator.
Only this known command's pointer load and two pinned globals are adapted.
"""
import argparse
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
BODY = """    u8 *G32 *stream = &((TextStreamOwner *)object)->streams[object->stream_58];
    u8 value = *(*stream)++;
    D_8009B26C[0] = 5;
    D_8009B363[0] = value;"""
ADAPTED = """    u8 *G32 *stream = &((TextStreamOwner *)object)->streams[object->stream_58];
    u32 address = (u32)(uintptr_t)*stream;
    u8 value = *TranslatedUnit_Resolve(address, 1);
    *stream = (u8 *G32)(uintptr_t)(address + 1u);
    TranslatedUnit_Resolve(0x8009B26Cu, 1)[0] = 5;
    TranslatedUnit_Resolve(0x8009B363u, 1)[0] = value;"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sanitize", action="store_true")
    args = parser.parse_args()
    if Path.cwd().resolve() != ROOT:
        parser.error("run from the repository root")
    source = ROOT / "src/game/duel_effect_basic_commands.c"
    original = source.read_text()
    if original.count(BODY) != 1:
        parser.error("known command body changed: inspect adapter before regenerating")
    # Broad unmatched declarations contain ELF section spellings. This unit
    # needs only the actual retail struct definitions; no generated stand-ins.
    prefix, functions = original.split("void func_80038888(void)", 1)
    expected = ('#define MAIN_MODE_STATE_NEXT_AS_SCALAR\n'
                '#define MAIN_MODE_STATE_ACTIVE_AS_ARRAY\n'
                '#include "../types.h"\n#include "../unmatched.h"\n'
                '#include "duel_effect_basic_commands.h"\n'
                '#include "main_mode_state.h"\n\n')
    if prefix != expected:
        parser.error("known include block changed: inspect adapter before regenerating")
    generated = ('/* Generated isolated proof; do not use as runtime unit. */\n'
                 '#include "ygo_types.h"\n#include <stdint.h>\n'
                 'extern u8 *TranslatedUnit_Resolve(u32, unsigned);\n'
                 'void func_80038888(void)' + functions.replace(BODY, ADAPTED))
    out = ROOT / "tmp/translated-game-unit"
    out.mkdir(parents=True, exist_ok=True)
    unit = out / "duel_effect_basic_commands.c"
    unit.write_text(generated)
    binary = out / ("proof-sanitized" if args.sanitize else "proof")
    flags = ["-std=c11", "-Wall", "-Wextra", "-Werror", "-DMEMORIES_PC",
             "-fms-extensions", "-Wno-pointer-to-int-cast",
             "-Wno-gnu-folding-constant", "-I" + str(ROOT / "src")]
    if args.sanitize:
        flags += ["-fsanitize=address,undefined", "-fno-omit-frame-pointer"]
    subprocess.run([os.environ.get("CC", "clang"), *flags, str(unit),
                    str(ROOT / "tests/pc/translated_game_unit_test.c"),
                    str(ROOT / "src/pc/memory.c"), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
    assert source.read_text() == original, "matching source must remain unchanged"


if __name__ == "__main__":
    main()
