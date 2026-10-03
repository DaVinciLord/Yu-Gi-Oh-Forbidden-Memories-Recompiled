#!/usr/bin/env python3
"""Execute the real SDK descriptor reader reproducing the frame-38 pointer."""
import argparse
from pathlib import Path
import subprocess
from test_sound_guest_storage import select_functions
from translate_guest_ir import translate, address_map

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sanitize',action='store_true');args=parser.parse_args()
    raw=ROOT/'tmp/arm64-build/raw/src_pc_sdk_libgpu.c.ll'
    selected=select_functions(raw.read_text(),{'GsDrawOt'})+'\ndeclare void @DrawOTag(ptr)\n'
    out=ROOT/'tmp/gsdrawot-guest-storage';out.mkdir(parents=True,exist_ok=True)
    ir=out/'GsDrawOt.ll';ir.write_text(translate(selected,address_map(ROOT/'config/pc/guest_addresses.txt')))
    flags=['-std=c11','-DMEMORIES_PC','-fms-extensions','-I'+str(ROOT/'src')]
    if args.sanitize:flags+=['-fsanitize=address,undefined','-fno-omit-frame-pointer']
    binary=out/('test-sanitized' if args.sanitize else 'test')
    subprocess.run(['clang',*flags,str(ir),str(ROOT/'tests/pc/gsdrawot_guest_storage_test.c'),
                    str(ROOT/'src/pc/memory.c'),str(ROOT/'src/pc/guest/translated_runtime.c'),
                    '-o',str(binary)],check=True)
    subprocess.run([str(binary)],check=True)


if __name__=='__main__':main()
