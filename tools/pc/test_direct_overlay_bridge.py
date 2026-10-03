#!/usr/bin/env python3
"""Run generated direct entry against real backend and module-bank filter."""
import argparse,re,subprocess
from pathlib import Path
from test_sound_guest_storage import select_functions
from translate_guest_ir import translate
from direct_overlay_bridges import ENTRIES, emit_bridge, validate_declaration
ROOT=Path(__file__).resolve().parents[2]
def main():
 p=argparse.ArgumentParser();p.add_argument('--sanitize',action='store_true');a=p.parse_args()
 out=ROOT/'tmp/direct-overlay-bridge';out.mkdir(parents=True,exist_ok=True)
 flags=['-O0','-DMEMORIES_PC','-DMEMORIES_TRANSLATED','-fms-extensions','-I'+str(ROOT/'src')]
 raw=out/'backend.raw.ll';subprocess.run(['clang',*flags,'-S','-emit-llvm',str(ROOT/'src/pc/guest/translated_image_backend.c'),'-o',str(raw)],check=True)
 backend=out/'backend.ll';backend.write_text(select_functions(raw.read_text(),{'resolve_function'}).replace('define internal ptr @resolve_function','define ptr @resolve_function'))
 modules=out/'modules.ll';modules.write_text(translate(select_functions((ROOT/'tmp/arm64-build/raw/src_pc_guest_modules.c.ll').read_text(),{'Memories_ModuleIsResident'})))
 for name in ENTRIES:
  if name == 'func_801462B0': continue
  validate_declaration(name, 'declare void @'+name+('('+'i32 noundef'+')' if ENTRIES[name][1] else '()')+' #1')
  try: validate_declaration(name, 'declare void @'+name+'(i64)')
  except ValueError: pass
  else: raise AssertionError('wrong ABI accepted')
 bridge=out/'bridge.c';bridge.write_text('#include "pc/guest/translated_runtime.h"\n#include <stdint.h>\n'+''.join(emit_bridge(name) for name in ENTRIES if name != 'func_801462B0'))
 if a.sanitize:flags+=['-fsanitize=address,undefined','-fno-omit-frame-pointer']
 binary=out/'test';subprocess.run(['clang',*flags,str(backend),str(modules),str(bridge),str(ROOT/'tests/pc/direct_overlay_bridge_test.c'),str(ROOT/'src/pc/memory.c'),str(ROOT/'src/pc/guest/translated_runtime.c'),'-o',str(binary)],check=True);subprocess.run([str(binary)],check=True)
if __name__=='__main__':main()
