#!/usr/bin/env python3
"""Check real shared callback/pointer declarations retain PS1 word storage."""
import subprocess
from llvm_guest import ROOT, toolchain
from test_ps1_layouts import TARGETS

SOURCE = r"""
#include "game/main_modes.h"
#include "game/duel_effect_tables.h"
#include "game/display_effect_step_table.h"
#include "game/file_transfer.h"
#include "game/model_graphics_state.h"
_Static_assert(sizeof(gMain_apfnModeRunner) == MAIN_MODE_COUNT * 4, "mode slots");
_Static_assert(sizeof(gDuelEffect_apfnStateHandler) == 5 * 4, "state slots");
_Static_assert(sizeof(D_80090F68[0]) == 4, "display callback slot");
_Static_assert(sizeof(D_8009AF18) == 4, "transfer descriptor token");
_Static_assert(sizeof(D_8009AF88) == 4, "model token");
_Static_assert(sizeof(((TextStreamOwner *)0)->streams[0]) == 4, "stream token");
void *native_pointer;
_Static_assert(sizeof(native_pointer) == sizeof(void *), "native pointer preserved");
"""


def main():
    compiler = str(toolchain() / 'bin/clang')
    for target, flags in TARGETS.items():
        if target == 'macos':
            flags = [*flags, '-DMEMORIES_TRANSLATED']
        subprocess.run([compiler, *flags, '-ffreestanding', '-fms-extensions',
                        '-Isrc', '-std=c11', '-Werror', '-Wno-gnu-folding-constant',
                        '-Wno-pointer-to-int-cast',
                        '-fsyntax-only', '-x', 'c', '-'],
                       input=SOURCE, text=True, cwd=ROOT, check=True, timeout=60)
        print(f'{target}: shared callback and pointer slots are four bytes')


if __name__ == '__main__':
    main()
