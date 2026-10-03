#!/usr/bin/env python3
"""Check allow-listed generated guest declarations keep four-byte slots."""
from pathlib import Path
import subprocess
from guest_pointer_overrides import apply_guest_pointer_overrides, STORAGE_VIEWS, TABLE_CURSORS

ROOT = Path(__file__).resolve().parents[2]


def main():
    declarations = ('typedef void (*MainModeRunner)(void);\n'
                    'typedef void (*DuelEffectHandler)(void);\n'
                    'typedef struct FileTransferDescriptor FileTransferDescriptor;\n'
                    'extern MainModeRunner gMain_apfnModeRunner[17];\n'
                    'extern DuelEffectHandler\n    gDuelEffect_apfnStateHandler[5];\n'
                    'extern void (*D_80090F68[8])(void);\n'
                    'extern FileTransferDescriptor *D_8009AF18;\n'
                    'extern u8 *D_8009AF88;\n'
                    'extern u8 *unrelated_native_pointer;\n')
    adapted = apply_guest_pointer_overrides(declarations)
    assert adapted == apply_guest_pointer_overrides(adapted)
    assert 'extern u8 *unrelated_native_pointer;' in adapted
    assert apply_guest_pointer_overrides('gMain_apfnModeRunner[index]();\n') == 'gMain_apfnModeRunner[index]();\n'
    code = '#include "types.h"\n' + adapted + '''
_Static_assert(sizeof(gMain_apfnModeRunner) == 17 * 4, "mode callback slots");
_Static_assert(sizeof(gDuelEffect_apfnStateHandler) == 5 * 4, "multiline typedef slots");
_Static_assert(sizeof(D_80090F68) == 8 * 4, "callback declarator slots");
_Static_assert(sizeof(D_8009AF18) == 4, "transfer descriptor pointer");
_Static_assert(sizeof(D_8009AF88) == 4, "model pointer");
_Static_assert(sizeof(unrelated_native_pointer) == sizeof(void *), "native pointer preserved");
int main(void) { return 0; }
'''
    out = ROOT / 'tmp/guest-pointer-overrides';out.mkdir(parents=True, exist_ok=True)
    source = out / 'layout.c';source.write_text(code)
    subprocess.run(['clang', '-std=c11', '-DMEMORIES_PC', '-fms-extensions',
                    '-I' + str(ROOT / 'src'), str(source), '-o', str(out / 'layout')], check=True)
    subprocess.run([str(out / 'layout')], check=True)
    # Check every patch against current real sources, preserving originals.
    changed = []
    for path in (ROOT / 'src/game').iterdir():
        if path.suffix not in {'.h','.c'}:continue
        original = path.read_text(encoding='latin-1')
        if apply_guest_pointer_overrides(original) != original:changed.append(path.name)
    for source in set(STORAGE_VIEWS) | set(TABLE_CURSORS):
        original = (ROOT/source).read_text(encoding='latin-1')
        adapted = apply_guest_pointer_overrides(original, source)
        assert adapted != original, source
        assert adapted == apply_guest_pointer_overrides(adapted, source), source
    print(f'Guest pointer overrides: four-byte layout checks passed; {len(changed)} real source copies affected')


if __name__ == '__main__': main()
