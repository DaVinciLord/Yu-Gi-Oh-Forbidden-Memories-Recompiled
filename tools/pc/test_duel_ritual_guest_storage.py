#!/usr/bin/env python3
"""Exercise the ritual's actual card/data publication branch."""
import argparse
from pathlib import Path
import re
import subprocess
from test_sound_guest_storage import select_functions
from translate_guest_ir import translate, address_map
from build_arm64 import replace_names
ROOT = Path(__file__).resolve().parents[2]
def main():
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--sanitize', action='store_true'); a = p.parse_args()
    out = ROOT/'tmp/duel-ritual-guest-storage'; out.mkdir(parents=True, exist_ok=True)
    raw = replace_names((ROOT/'tmp/arm64-build/raw/src_game_duel_ritual_effect.c.ll').read_text(), {})
    selected = select_functions(raw, {'DuelEffect_ApplyRitual'})
    ir = out/'ritual.ll'; ir.write_text(translate(selected, address_map(ROOT/'config/pc/guest_addresses.txt')))
    # Every dependency outside the publication branch must stay unexecuted.
    names = set(re.findall(r'^declare .*?@([\w.]+)\(', selected, re.M))
    stubs = out/'unused.c'
    stubs.write_text('#include <stdlib.h>\nint rand(void) { abort(); }\n' + '\n'.join(
        f'void {name}(void) {{ abort(); }}' for name in sorted(names)
        if name not in {'DuelEffect_MarkInitialized', 'StoreImage', 'rand'} and not name.startswith('llvm.')))
    flags = ['-std=c11','-DMEMORIES_PC','-fms-extensions','-I'+str(ROOT/'src'),'-w']
    if a.sanitize: flags += ['-fsanitize=address,undefined','-fno-omit-frame-pointer']
    binary = out/('test-sanitized' if a.sanitize else 'test')
    subprocess.run(['clang', *flags, str(ir), str(stubs), str(ROOT/'tests/pc/duel_ritual_guest_storage_test.c'), str(ROOT/'src/pc/memory.c'), str(ROOT/'src/pc/guest/translated_runtime.c'), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
if __name__ == '__main__': main()
