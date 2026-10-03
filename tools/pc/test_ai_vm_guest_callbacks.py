#!/usr/bin/env python3
"""Verify real AI VM terminators compare guest callback tokens correctly."""
import argparse
from pathlib import Path
import subprocess
from test_sound_guest_storage import select_functions
from translate_guest_ir import translate, address_map
ROOT = Path(__file__).resolve().parents[2]
def main():
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--sanitize', action='store_true'); a = p.parse_args()
    out = ROOT/'tmp/ai-vm-guest-callbacks'; out.mkdir(parents=True, exist_ok=True)
    units = []
    for source, names in [('ai_script_vm', {'AiScript_Init', 'AiScript_Run', 'AiScript_ReadByte'}),
                          ('ai_script_end', {'AiScript_EndHand', 'AiScript_EndField', 'AiScript_PlayFieldCard'})]:
        raw = (ROOT/f'tmp/arm64-build/raw/src_game_{source}.c.ll').read_text()
        raw = raw.replace('@bzero(', '@test_guest_bzero(')
        ir = out/(source+'.ll'); ir.write_text(translate(select_functions(raw, names), address_map(ROOT/'config/pc/guest_addresses.txt')))
        units.append(str(ir))
    flags = ['-std=c11','-DMEMORIES_PC','-fms-extensions','-I'+str(ROOT/'src'),'-w']
    if a.sanitize: flags += ['-fsanitize=address,undefined','-fno-omit-frame-pointer']
    binary = out/('test-sanitized' if a.sanitize else 'test')
    subprocess.run(['clang', *flags, *units, str(ROOT/'tests/pc/ai_vm_guest_callbacks_test.c'), str(ROOT/'src/pc/memory.c'), str(ROOT/'src/pc/guest/translated_runtime.c'), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
if __name__ == '__main__': main()
