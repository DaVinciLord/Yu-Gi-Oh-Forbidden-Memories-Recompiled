#!/usr/bin/env python3
"""Replay actual sound bank table reads with the campaign failure sentinels."""
import argparse,subprocess
from pathlib import Path
from test_sound_guest_storage import select_functions
from translate_guest_ir import translate,address_map
ROOT=Path(__file__).resolve().parents[2]
def main():
 p=argparse.ArgumentParser();p.add_argument('--sanitize',action='store_true');a=p.parse_args()
 out=ROOT/'tmp/sound-bank-pointers';out.mkdir(parents=True,exist_ok=True)
 raw=(ROOT/'tmp/arm64-build/raw/src_game_sound_output_state.c.ll').read_text()
 ir=out/'commands.ll';ir.write_text(translate(select_functions(raw,{'func_80045208','func_80045334'}),address_map(ROOT/'config/pc/guest_addresses.txt')))
 flags=['-std=c11','-DMEMORIES_PC','-fms-extensions','-I'+str(ROOT/'src')]
 if a.sanitize:flags+=['-fsanitize=address,undefined','-fno-omit-frame-pointer']
 binary=out/'test';subprocess.run(['clang',*flags,str(ir),str(ROOT/'tests/pc/sound_bank_pointer_test.c'),str(ROOT/'src/pc/memory.c'),str(ROOT/'src/pc/guest/translated_runtime.c'),'-o',str(binary)],check=True);subprocess.run([str(binary)],check=True)
if __name__=='__main__':main()
