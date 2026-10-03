#!/usr/bin/env python3
"""Run real HMD row/channel readers with adjacent guest-pointer sentinels."""
import argparse
from pathlib import Path
import subprocess
from test_sound_guest_storage import select_functions
from translate_guest_ir import translate, address_map
ROOT = Path(__file__).resolve().parents[2]
def main():
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--sanitize', action='store_true'); a = p.parse_args()
    out = ROOT/'tmp/model-rows-guest-storage'; out.mkdir(parents=True, exist_ok=True)
    raw = (ROOT/'tmp/arm64-build/raw/src_game_model_slot_row_tables.c.ll').read_text()
    ir = out/'rows.ll'; ir.write_text(translate(select_functions(raw, {'func_8004D58C', 'func_8004D134'}), address_map(ROOT/'config/pc/guest_addresses.txt')))
    units = [str(ir)]
    for source, names in [('src_game_model_handler_registry.c.ll', {'Model_ProcessType2Unit'}),
                          ('src_pc_sdk_libgs_unit.c.ll', {'GsLinkAnim'})]:
        unit = out/source
        unit.write_text(translate(select_functions((ROOT/'tmp/arm64-build/raw'/source).read_text(), names), address_map(ROOT/'config/pc/guest_addresses.txt')))
        units.append(str(unit))
    flags = ['-std=c11','-DMEMORIES_PC','-fms-extensions','-I'+str(ROOT/'src'),'-w']
    if a.sanitize: flags += ['-fsanitize=address,undefined','-fno-omit-frame-pointer']
    binary = out/('test-sanitized' if a.sanitize else 'test')
    subprocess.run(['clang', *flags, *units, str(ROOT/'tests/pc/model_rows_guest_storage_test.c'), str(ROOT/'src/pc/memory.c'), str(ROOT/'src/pc/guest/translated_runtime.c'), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
if __name__ == '__main__': main()
