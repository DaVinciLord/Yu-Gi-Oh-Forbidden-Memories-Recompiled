#!/usr/bin/env python3
"""Exercise the real three-word grid writers and readers with neighboring sentinels."""
import argparse
from pathlib import Path
import subprocess
from test_sound_guest_storage import select_functions
from translate_guest_ir import translate, address_map
ROOT = Path(__file__).resolve().parents[2]
def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sanitize', action='store_true'); args = parser.parse_args()
    out = ROOT/'tmp/display-grid-guest-storage'; out.mkdir(parents=True, exist_ok=True)
    units = []
    for source, names in [
        ('display_effect_resource_setup', {'DisplayEffect_HasResourceEntry', 'DisplayEffect_BuildResourceObjects', 'func_8003A440'}),
        ('display_effect_lifecycle', {'func_80039F90'})]:
        raw = (ROOT/f'tmp/arm64-build/raw/src_game_{source}.c.ll').read_text()
        target = out/(source+'.ll')
        target.write_text(translate(select_functions(raw, names), address_map(ROOT/'config/pc/guest_addresses.txt')))
        units.append(str(target))
    flags = ['-std=c11', '-DMEMORIES_PC', '-fms-extensions', '-I'+str(ROOT/'src'), '-w']
    if args.sanitize: flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
    binary = out/('test-sanitized' if args.sanitize else 'test')
    subprocess.run(['clang', *flags, *units, str(ROOT/'tests/pc/display_grid_guest_storage_test.c'),
        str(ROOT/'src/pc/memory.c'), str(ROOT/'src/pc/guest/translated_runtime.c'), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
if __name__ == '__main__': main()
