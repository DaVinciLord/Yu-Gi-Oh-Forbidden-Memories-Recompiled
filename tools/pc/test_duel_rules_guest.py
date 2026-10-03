#!/usr/bin/env python3
"""Run real translated ritual matching and attack-trap selection."""
import argparse
from pathlib import Path
import subprocess
from test_sound_guest_storage import select_functions
from translate_guest_ir import translate, address_map
ROOT = Path(__file__).resolve().parents[2]
def main():
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--sanitize', action='store_true'); a = p.parse_args()
    out = ROOT/'tmp/duel-rules-guest'; out.mkdir(parents=True, exist_ok=True)
    units = []
    for source, names in [('duel_check_ritual', {'Duel_CheckRitual','disc_recipe'}),
                          ('duel_trap_resolution', {'Duel_SelectAttackTrap'}),
                          ('duel_calc_card_stats', {'Duel_CalcCardStats'})]:
        raw = (ROOT/f'tmp/arm64-build/raw/src_game_{source}.c.ll').read_text()
        ir = out/(source+'.ll')
        ir.write_text(translate(select_functions(raw, names), address_map(ROOT/'config/pc/guest_addresses.txt')))
        units.append(str(ir))
    flags = ['-std=c11','-DMEMORIES_PC','-fms-extensions','-I'+str(ROOT/'src'),'-w']
    if a.sanitize: flags += ['-fsanitize=address,undefined','-fno-omit-frame-pointer']
    binary = out/('test-sanitized' if a.sanitize else 'test')
    subprocess.run(['clang', *flags, *units, str(ROOT/'tests/pc/duel_rules_guest_test.c'), str(ROOT/'src/pc/memory.c'), str(ROOT/'src/pc/guest/translated_runtime.c'), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
if __name__ == '__main__': main()
