#!/usr/bin/env python3
"""Test the real animation controller's 16-byte callback-table copy."""
import argparse,re,subprocess
from pathlib import Path
from test_sound_guest_storage import select_functions
from translate_guest_ir import translate,address_map
from build_arm64 import replace_names
ROOT=Path(__file__).resolve().parents[2]
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--sanitize',action='store_true');a=p.parse_args()
 out=ROOT/'tmp/model-effect-guest-callbacks';out.mkdir(parents=True,exist_ok=True)
 raw=replace_names((ROOT/'tmp/arm64-build/raw/src_game_model_intro_controller.c.ll').read_text(),{})
 ir=translate(select_functions(raw,{'func_8004EB00'}),address_map(ROOT/'config/pc/guest_addresses.txt'))
 (out/'controller.ll').write_text(ir)
 names=set(re.findall(r'^declare .*?@([\w.]+)\(',ir,re.M))
 unused=sorted(n for n in names if not n.startswith(('llvm.','GuestRuntime_')) and n != 'func_8005A188')
 (out/'unused.c').write_text('#include <stdlib.h>\n'+''.join(('int ' if n == 'rand' else 'void ')+n+'(void) { abort(); }\n' for n in unused))
 flags=['-std=c11','-DMEMORIES_PC','-fms-extensions','-I'+str(ROOT/'src'),'-w']
 if a.sanitize:flags+=['-fsanitize=address,undefined','-fno-omit-frame-pointer']
 binary=out/('test-sanitized' if a.sanitize else 'test')
 subprocess.run(['clang',*flags,str(out/'controller.ll'),str(out/'unused.c'),str(ROOT/'tests/pc/model_effect_guest_callbacks_test.c'),str(ROOT/'src/pc/memory.c'),str(ROOT/'src/pc/guest/translated_runtime.c'),'-o',str(binary)],check=True)
 subprocess.run([str(binary)],check=True)
if __name__=='__main__':main()
