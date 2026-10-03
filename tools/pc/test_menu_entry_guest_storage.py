#!/usr/bin/env python3
"""Run the real overlay transition with the adjacent pointers from frame506."""
import argparse
from pathlib import Path
import subprocess
from test_sound_guest_storage import select_functions
from translate_guest_ir import translate
from build_arm64 import maps

ROOT=Path(__file__).resolve().parents[2]


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--sanitize',action='store_true');args=parser.parse_args()
    raw=ROOT/'tmp/arm64-build/raw/src_overlays_main_menu_frontend_background.c.ll'
    selected=select_functions(raw.read_text(),{'MainMenu_StartFrontendEntryTransition'})
    pin_maps=maps();pins={**pin_maps['SLUS_014.11'],**pin_maps['main_menu']}
    out=ROOT/'tmp/menu-entry-guest-storage';out.mkdir(parents=True,exist_ok=True)
    ir=out/'menu-entry.ll';ir.write_text(translate(selected,pins))
    flags=['-std=c11','-DMEMORIES_PC','-fms-extensions','-I'+str(ROOT/'src'),
           '-Wno-gnu-folding-constant','-Wno-pointer-to-int-cast']
    if args.sanitize:flags+=['-fsanitize=address,undefined','-fno-omit-frame-pointer']
    binary=out/('test-sanitized' if args.sanitize else 'test')
    subprocess.run(['clang',*flags,str(ir),str(ROOT/'tests/pc/menu_entry_guest_storage_test.c'),
                    str(ROOT/'src/pc/memory.c'),str(ROOT/'src/pc/guest/translated_runtime.c'),
                    '-o',str(binary)],check=True)
    subprocess.run([str(binary)],check=True)


if __name__=='__main__':main()
