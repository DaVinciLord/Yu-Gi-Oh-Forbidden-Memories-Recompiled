#!/usr/bin/env python3
"""Verify audited generated native SoftGpu with actual raster regressions."""
import argparse
from pathlib import Path
import subprocess
SOFT_GPU = 'src/pc/render/soft_gpu.c'
from translate_guest_ir import translate
from build_arm64 import optimize_translated_ir
ROOT=Path(__file__).resolve().parents[2]
def main():
 p=argparse.ArgumentParser();p.add_argument('--sanitize',action='store_true');p.add_argument('--instrumented',action='store_true');p.add_argument('--differential',action='store_true');a=p.parse_args()
 out=ROOT/'tmp/host-renderer';out.mkdir(parents=True,exist_ok=True)
 source=out/'soft_gpu.c';source.write_text((ROOT/SOFT_GPU).read_text())
 flags=['-O2','-std=c11','-DMEMORIES_PC','-DMEMORIES_TRANSLATED','-fms-extensions','-I'+str(ROOT/'src'),'-I'+str(ROOT/'src/pc/render')]
 if a.sanitize:flags+=['-fsanitize=address,undefined','-fno-omit-frame-pointer']
 sources=[source]
 if a.instrumented or a.differential:
  frontend_flags=[flag for flag in flags if not flag.startswith('-fsanitize=')]
  frontend_flags+=['-DMEMORIES_INSTRUMENT_SOFTGPU']
  raw=out/'soft_gpu.raw.ll';subprocess.run(['clang',*frontend_flags,'-O0','-S','-emit-llvm',str(ROOT/SOFT_GPU),'-o',str(raw)],check=True)
  instrumented=out/'soft_gpu.instrumented.ll';instrumented.write_text(optimize_translated_ir(translate(raw.read_text())))
  sources=([source,instrumented] if a.differential else [instrumented])
 outputs=[]
 for source in sources:
  output=[]
  for existing in [False,True]:
   binary=out/('existing-raster' if existing else 'guest-boundaries')
   command=['clang',*flags,str(source),str(ROOT/'tests/pc/host_renderer_boundary_test.c'),str(ROOT/'src/pc/memory.c'),str(ROOT/'src/pc/guest/translated_runtime.c')]
   if existing:command+=['-DEXISTING_RASTER_TEST',str(ROOT/'tests/pc/soft_gpu_test.c')]
   subprocess.run([*command,'-o',str(binary)],check=True)
   result=subprocess.run([str(binary)],check=True,capture_output=True,text=True)
   print(result.stdout,end='');output.append(result.stdout)
  outputs.append(output)
 if a.differential:
  assert outputs[0]==outputs[1], 'Host and instrumented raster outputs differ'
  print('Native/instrumented complete VRAM hashes and raster regressions match')
if __name__=='__main__':main()
