#!/usr/bin/env python3
"""Exercise translated card reconstruction, including the second-side index."""
import argparse
from pathlib import Path
import subprocess
from test_sound_guest_storage import select_functions
from translate_guest_ir import translate, address_map
ROOT = Path(__file__).resolve().parents[2]
def main():
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--sanitize', action='store_true'); a = p.parse_args()
    out = ROOT/'tmp/duel-card-guest-storage'; out.mkdir(parents=True, exist_ok=True)
    raw = (ROOT/'tmp/arm64-build/raw/src_game_duel_card_record_lifecycle.c.ll').read_text()
    selected = select_functions(raw, {'func_80024D34'})
    selected += '\ndeclare ptr @Duel_SetupCardRecord(i32, i32)\ndeclare ptr @func_80024C1C(i32, i32, i32)\n'
    ir = out/'card.ll'; ir.write_text(translate(selected, address_map(ROOT/'config/pc/guest_addresses.txt')))
    flags = ['-std=c11','-DMEMORIES_PC','-fms-extensions','-I'+str(ROOT/'src'),'-w']
    if a.sanitize: flags += ['-fsanitize=address,undefined','-fno-omit-frame-pointer']
    binary = out/('test-sanitized' if a.sanitize else 'test')
    subprocess.run(['clang', *flags, str(ir), str(ROOT/'tests/pc/duel_card_guest_storage_test.c'), str(ROOT/'src/pc/memory.c'), str(ROOT/'src/pc/guest/translated_runtime.c'), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
if __name__ == '__main__': main()
