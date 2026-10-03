#!/usr/bin/env python3
"""Replay the actual duel card-text stream commands with adjacent pointers."""
import argparse
from pathlib import Path
import subprocess
from test_sound_guest_storage import select_functions
from translate_guest_ir import translate, address_map
ROOT = Path(__file__).resolve().parents[2]
def main():
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--sanitize', action='store_true'); a = p.parse_args()
    out = ROOT/'tmp/duel-text-guest-storage'; out.mkdir(parents=True, exist_ok=True)
    raw = (ROOT/'tmp/arm64-build/raw/src_game_duel_effect_command.c.ll').read_text()
    ir = out/'text.ll'; ir.write_text(translate(select_functions(raw, {'func_80037DA4', 'func_800384E4'}), address_map(ROOT/'config/pc/guest_addresses.txt')))
    flags = ['-std=c11','-DMEMORIES_PC','-fms-extensions','-I'+str(ROOT/'src'),'-w']
    if a.sanitize: flags += ['-fsanitize=address,undefined','-fno-omit-frame-pointer']
    binary = out/('test-sanitized' if a.sanitize else 'test')
    subprocess.run(['clang', *flags, str(ir), str(ROOT/'tests/pc/duel_text_guest_storage_test.c'), str(ROOT/'src/pc/memory.c'), str(ROOT/'src/pc/guest/translated_runtime.c'), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
if __name__ == '__main__': main()
