#!/usr/bin/env python3
"""Execute the original game command through the structured LLVM compiler."""
import argparse
import os
import subprocess
from llvm_guest import ROOT, toolchain, translate, process
from macos_deps import sdk_path
from translate_guest_ir import address_map


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sanitize', action='store_true')
    args = parser.parse_args()
    out = ROOT / 'tmp/translated-game-unit'
    out.mkdir(parents=True, exist_ok=True)
    source = ROOT / 'src/game/duel_effect_basic_commands.c'
    original = source.read_bytes()
    compiler = str(toolchain() / 'bin/clang')
    flags = ['-std=c11', '-DMEMORIES_PC', '-DMEMORIES_TRANSLATED',
             '-DTRANSLATED_GAME_IR', '-fms-extensions', '-Isrc',
             '-isysroot', str(sdk_path()), '-Wno-pointer-to-int-cast',
             '-Wno-gnu-folding-constant']
    raw = out / 'command.raw.ll'
    subprocess.run([compiler, *flags, '-O0', '-S', '-emit-llvm', str(source),
                    '-o', str(raw)], cwd=ROOT, check=True, timeout=60)
    unit = out / 'command.ll'
    unit.write_text(process('optimize', translate(raw.read_text(),
        address_map(ROOT / 'config/pc/guest_addresses.txt'))))
    if args.sanitize:
        flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
    binary = out / ('proof-sanitized' if args.sanitize else 'proof')
    subprocess.run([os.environ.get('CC', compiler), *flags, '-O2', str(unit),
                    'tests/pc/translated_game_unit_test.c', 'src/pc/memory.c',
                    'src/pc/guest/translated_runtime.c', 'src/pc/guest/state_io.c',
                    '-Wl,-dead_strip', '-o', str(binary)], cwd=ROOT, check=True, timeout=60)
    subprocess.run([str(binary)], cwd=ROOT, check=True, timeout=30)
    assert source.read_bytes() == original, 'source must remain unchanged'


if __name__ == '__main__':
    main()
