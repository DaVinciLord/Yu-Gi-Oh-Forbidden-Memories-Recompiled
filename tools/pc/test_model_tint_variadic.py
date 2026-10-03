#!/usr/bin/env python3
"""Execute the translated tint-mask builder using native variadic arguments."""
import argparse, subprocess
from pathlib import Path
from test_sound_guest_storage import select_functions
from build_arm64 import replace_names
from translate_guest_ir import translate
ROOT=Path(__file__).resolve().parents[2]
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--sanitize',action='store_true');a=p.parse_args()
    out=ROOT/'tmp/model-tint-variadic';out.mkdir(parents=True,exist_ok=True)
    raw=replace_names((ROOT/'tmp/arm64-build/raw/src_game_func_80058838.c.ll').read_text(),{})
    ir=translate(select_functions(raw,{'Model_QueueTintRequestForParts'}),{})
    (out/'tint.ll').write_text(ir)
    flags=['-std=c11','-DMEMORIES_PC','-fms-extensions','-I'+str(ROOT/'src'),'-w']
    if a.sanitize: flags+=['-fsanitize=address,undefined','-fno-omit-frame-pointer']
    binary=out/('test-sanitized' if a.sanitize else 'test')
    subprocess.run(['clang',*flags,str(out/'tint.ll'),str(ROOT/'tests/pc/model_tint_variadic_test.c'),str(ROOT/'src/pc/memory.c'),str(ROOT/'src/pc/guest/translated_runtime.c'),'-o',str(binary)],check=True)
    subprocess.run([str(binary)],check=True)
if __name__=='__main__':main()
