#!/usr/bin/env python3
"""Check actual Free Duel cursor and sparkle functions against guest storage."""
import argparse
from pathlib import Path
import subprocess
from test_sound_guest_storage import select_functions
from translate_guest_ir import translate, address_map
from build_arm64 import replace_names, maps
ROOT = Path(__file__).resolve().parents[2]
def main():
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--sanitize', action='store_true'); a = p.parse_args()
    out = ROOT/'tmp/free-duel-guest-storage'; out.mkdir(parents=True, exist_ok=True)
    raw = replace_names((ROOT/'tmp/arm64-build/raw/src_overlays_free_duel_screen_runtime.c.ll').read_text(), {})
    pins = maps()
    ir = out/'cursor.ll'; ir.write_text(translate(select_functions(raw, {'FreeDuel_GetSparkleSlot','FreeDuel_UpdateSparkle','FreeDuel_UpdateScrollbar'}), {**pins['SLUS_014.11'], **pins['free_duel']}))
    flags = ['-std=c11','-DMEMORIES_PC','-fms-extensions','-I'+str(ROOT/'src'),'-w']
    if a.sanitize: flags += ['-fsanitize=address,undefined','-fno-omit-frame-pointer']
    binary = out/('test-sanitized' if a.sanitize else 'test')
    subprocess.run(['clang', *flags, str(ir), str(ROOT/'tests/pc/free_duel_guest_storage_test.c'), str(ROOT/'src/pc/memory.c'), str(ROOT/'src/pc/guest/translated_runtime.c'), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
if __name__ == '__main__': main()
