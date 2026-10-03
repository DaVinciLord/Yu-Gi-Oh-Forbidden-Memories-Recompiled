#!/usr/bin/env python3
"""ROM-free test of the generated ARM64 native-call argument bridge."""
import argparse
from pathlib import Path
import subprocess
from native_call_marshalling import emit_native_calls
ROOT = Path(__file__).resolve().parents[2]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sanitize',action='store_true');args=parser.parse_args()
    out=ROOT/'tmp/native-call-marshalling';out.mkdir(parents=True,exist_ok=True)
    ir='define i32 @TenPointers('+', '.join('ptr %'+str(i) for i in range(10))+') {\n'
    ir+='define i32 @Mixed(i32 %0, ptr %1, i8 %2, i16 %3, ptr %4, i32 %5, ptr %6, i32 %7, i32 %8, ptr %9, i16 %10, ptr %11) {\n'
    ir+='define ptr @PointerResult() {\n'
    ir+='define void @Model_QueueTintRequest(i32 %0, i32 %1, i64 %2, i64 %3, i32 %4, ptr %5) {\n'
    ir+='define void @GsSetAmbient(i64 %0, i64 %1, i64 %2) {\n'
    ir+='define i64 @StartRCnt(i64 %0) {\n'
    ir+='define signext i16 @SignedSmall(i8 signext %0, i16 signext %1) {\n'
    mapped=[(1,'TenPointers',0,0),(2,'Mixed',0,0),(3,'PointerResult',0,0)]
    mapped += [(4,'Model_QueueTintRequest',0,0),(5,'GsSetAmbient',0,0),(6,'StartRCnt',0,0)]
    mapped += [(7,'SignedSmall',0,0)]
    (out/'calls.inc').write_text(emit_native_calls(mapped,[ir]))
    for bad in ['define void @Unknown(i64 %0) {\n','define void @Unknown(i32 %0, ...) {\n']:
        try: emit_native_calls([(1,'Unknown',0,0)],[bad])
        except ValueError: pass
        else: raise AssertionError('Unaudited ABI was accepted')
    flags=['-std=c11','-Wall','-Wextra','-Wno-unused-parameter','-I'+str(ROOT/'src'),'-I'+str(out)]
    if args.sanitize:flags+=['-fsanitize=address,undefined','-fno-omit-frame-pointer']
    binary=out/('test-sanitized' if args.sanitize else 'test')
    subprocess.run(['clang',*flags,str(ROOT/'tests/pc/native_call_marshalling_test.c'),'-o',str(binary)],check=True)
    subprocess.run([str(binary)],check=True)
if __name__=='__main__':main()
