#!/usr/bin/env python3
"""Verify typed imported call through the actual duel-effect gate."""
import argparse
from pathlib import Path
import subprocess
from direct_overlay_bridges import emit_bridge, validate_declaration
ROOT=Path(__file__).resolve().parents[2]
def main():
 p=argparse.ArgumentParser();p.add_argument('--sanitize',action='store_true');a=p.parse_args()
 validate_declaration('func_801462B0','declare void @func_801462B0(i16 noundef signext, i16 noundef signext, i32 noundef, ptr noundef) #1')
 out=ROOT/'tmp/duel-effect-bridge';out.mkdir(parents=True,exist_ok=True)
 bridge=out/'bridge.c';bridge.write_text(emit_bridge('func_801462B0'))
 flags=['-O2','-w','-DMEMORIES_PC','-fms-extensions','-I'+str(ROOT/'tmp/arm64-build/generated/src'),'-I'+str(ROOT/'src')]
 if a.sanitize:flags+=['-fsanitize=address,undefined','-fno-omit-frame-pointer']
 binary=out/'test'
 subprocess.run(['xcrun','clang',*flags,str(bridge),str(ROOT/'src/pc/overlays/duel_effects.c'),str(ROOT/'tests/pc/duel_effect_bridge_test.c'),'-o',str(binary)],check=True)
 subprocess.run([str(binary)],check=True)
if __name__=='__main__':main()
