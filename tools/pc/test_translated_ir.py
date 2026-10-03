#!/usr/bin/env python3
"""Verify bounded IR adapter and execute original real-game command IR."""
import argparse
import os
from pathlib import Path
import subprocess
from translate_guest_ir import translate, address_map, TranslationError
from build_arm64 import replace_names, CHECKED_LIBC, HOST_LIBC, optimize_translated_ir

ROOT = Path(__file__).resolve().parents[2]

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sanitize', action='store_true')
    parser.add_argument('--optimize', action='store_true')
    parser.add_argument('--source', type=Path, default=ROOT / 'tmp/arm64-game-ir/ir/src_game_duel_effect_basic_commands.c.ll')
    args = parser.parse_args()
    string_fixture = '@.str = private constant [33 x i8] c"nuw nsw noundef #1 @pinned_record\\00"\n'
    string_input = string_fixture + 'define void @strings() {\n  ret void\n}\nattributes #0 = { optnone }\n'
    assert string_fixture in translate(string_input, {'pinned_record': 0x80018000})
    # SSA numbers are function-local. A conversion in one function must never
    # rewrite an unrelated integer truncation in the next function.
    scopes = ('define i64 @first(ptr %0) {\n  %2 = ptrtoint ptr %0 to i64\n  ret i64 %2\n}\n'
              'define i32 @second(i64 %0) {\n  %2 = add i64 %0, 1\n  %3 = trunc i64 %2 to i32\n  ret i32 %3\n}\n'
              'attributes #0 = { optnone }\n')
    assert '%3 = trunc i64 %2 to i32' in translate(scopes)
    constant_string = '@.literal = private constant [32 x i8] c"ptrtoint (ptr @callback to i32)\\00"\n'
    assert constant_string in translate(constant_string + scopes)
    try: translate('@callback_word = global i32 ptrtoint (ptr @callback to i32)\n' + scopes)
    except TranslationError: pass
    else: raise AssertionError('narrow pointer static initializer accepted')
    arithmetic = ('define void @constant_store(ptr %object) {\n'
                  '  store i32 sub (i32 ptrtoint (ptr @callback to i32), i32 16), ptr %object\n'
                  '  ret void\n}\nattributes #0 = { optnone }\n')
    rewritten = translate(arithmetic)
    assert 'call i32 @GuestRuntime_EncodePointer(ptr @callback)' in rewritten
    assert ' = sub i32 %guest.adapter.' in rewritten
    original = args.source.read_text()
    adapted = translate(original, address_map(ROOT / 'config/pc/guest_addresses.txt'))
    assert 'source_filename = "src/game/duel_effect_basic_commands.c"' in adapted
    assert '@D_8009B26C' not in adapted and '@D_8009B363' not in adapted
    for operation in ('callbr void @unexpected() to label %a [label %b]', 'invoke void @unexpected() to label %a unwind label %b'):
        try:
            translate('define void @probe() {\n  ' + operation + '\n  ret void\n}\nattributes #0 = { optnone }\n')
        except TranslationError: pass
        else: raise AssertionError('unsupported operation accepted')
    try: translate('define void @optimized() { ret void }')
    except TranslationError: pass
    else: raise AssertionError('optimized input accepted')
    out = ROOT / 'tmp/translated-game-ir'
    out.mkdir(parents=True, exist_ok=True)
    unit = out / 'duel_effect_basic_commands.ll'; unit.write_text(optimize_translated_ir(adapted) if args.optimize else adapted)
    cc = os.environ.get('CC', 'clang')
    flags = ['-std=c11', '-Wall', '-Wextra', '-Werror', '-DMEMORIES_PC', '-DTRANSLATED_GAME_IR',
             '-fms-extensions', '-Wno-pointer-to-int-cast', '-Wno-gnu-folding-constant', '-I' + str(ROOT / 'src')]
    if args.optimize: flags += ['-O2', '-fno-strict-aliasing']
    if args.sanitize: flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
    binary = out / ('proof-sanitized' if args.sanitize else 'proof')
    subprocess.run([cc, *flags, str(unit), str(ROOT / 'tests/pc/translated_game_unit_test.c'),
                    str(ROOT / 'src/pc/memory.c'), str(ROOT / 'src/pc/guest/translated_runtime.c'),
                    '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
    probe_source = ROOT / 'tests/pc/translated_ir_probe.c'
    probe_ir = out / 'probe.ll'
    subprocess.run([cc, '-std=c11', '-DMEMORIES_PC', '-fms-extensions', '-I' + str(ROOT / 'src'),
                    '-S', '-emit-llvm', str(probe_source), '-o', str(probe_ir)], check=True)
    transformed_probe = out / 'probe-translated.ll'
    boundary_ir = replace_names(probe_ir.read_text(), {name:'GuestRuntime_' + name for name in CHECKED_LIBC | HOST_LIBC})
    assert '@GuestRuntime___memcpy_chk' in boundary_ir and '@GuestRuntime___memset_chk' in boundary_ir
    probe_text = translate(boundary_ir, {'pinned_record': 0x80018000, 'callback_table': 0x80012600})
    transformed_probe.write_text(optimize_translated_ir(probe_text) if args.optimize else probe_text)
    probe_binary = out / ('contract-sanitized' if args.sanitize else 'contract')
    subprocess.run([cc, *flags, str(transformed_probe), str(ROOT / 'tests/pc/translated_ir_contract_test.c'),
                    str(ROOT / 'src/pc/memory.c'), str(ROOT / 'src/pc/guest/translated_runtime.c'), str(ROOT / 'src/pc/guest/translated_libc.c'),
                    '-o', str(probe_binary)], check=True)
    subprocess.run([str(probe_binary)], check=True)
    assert args.source.read_text() == original
    print('IR adapter rejection checks and original real-game command passed')

if __name__ == '__main__': main()
