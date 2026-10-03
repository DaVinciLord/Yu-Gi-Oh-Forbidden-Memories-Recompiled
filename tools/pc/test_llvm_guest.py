#!/usr/bin/env python3
"""Structured compiler regressions, independent of ROM and generated game IR."""
import unittest
from pathlib import Path
import subprocess
import tempfile
from llvm_guest import ROOT, TranslationError, inspect, normalize, translate, toolchain
from macos_deps import sdk_path


class GuestExecutionTests(unittest.TestCase):
    def test_memory_conversions_copies_and_callback_execute(self):
        # Execute the transformed IR against checked host storage. This
        # catches valid-looking IR that still dereferences a PS1 token.
        source = '''
target datalayout = "e-p:64:64-p271:32:32"
@slot = external global i32
declare void @llvm.memcpy.p271.p271.i32(ptr addrspace(271), ptr addrspace(271), i32, i1)
declare void @llvm.memmove.p271.p271.i32(ptr addrspace(271), ptr addrspace(271), i32, i1)
declare void @llvm.memset.p271.i32(ptr addrspace(271), i8, i32, i1)
define i32 @exercise(ptr %native, ptr addrspace(271) %callback) {
  %value = load i32, ptr @slot
  %encoded = ptrtoint ptr %native to i32
  %guest = inttoptr i32 %encoded to ptr addrspace(271)
  %generic = addrspacecast ptr addrspace(271) %guest to ptr
  %converted = addrspacecast ptr %generic to ptr addrspace(271)
  store i32 %value, ptr addrspace(271) %converted
  %dest = getelementptr i8, ptr addrspace(271) %guest, i32 4
  call void @llvm.memcpy.p271.p271.i32(ptr addrspace(271) %dest, ptr addrspace(271) %guest, i32 4, i1 false)
  %overlap = getelementptr i8, ptr addrspace(271) %guest, i32 5
  call void @llvm.memmove.p271.p271.i32(ptr addrspace(271) %overlap, ptr addrspace(271) %dest, i32 4, i1 false)
  %tail = getelementptr i8, ptr addrspace(271) %guest, i32 9
  call void @llvm.memset.p271.i32(ptr addrspace(271) %tail, i8 90, i32 3, i1 false)
  %counter = getelementptr i8, ptr addrspace(271) %guest, i32 12
  %old = atomicrmw add ptr addrspace(271) %counter, i32 3 seq_cst
  %changed = cmpxchg ptr addrspace(271) %counter, i32 3, i32 9 seq_cst seq_cst
  %result = call addrspace(271) i32 %callback(i32 %value)
  ret i32 %result
}
'''
        harness = r'''
#include <assert.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
static _Alignas(4) unsigned char memory[32];
static unsigned resolutions, encodings, callbacks;
void *GuestRuntime_ResolveData(void *pointer, uint64_t size) {
    uintptr_t address = (uintptr_t)pointer;
    assert(address >= 0x80010000u && address <= 0x80010020u);
    uintptr_t offset = address - 0x80010000u;
    assert(size <= sizeof(memory) - offset);
    ++resolutions;
    return memory + offset;
}
uint32_t GuestRuntime_EncodePointer(void *pointer) {
    uintptr_t address = (uintptr_t)pointer;
    ++encodings;
    if (address >= 0x80010000u && address <= 0x80010020u) return address;
    assert(address >= (uintptr_t)memory && address <= (uintptr_t)(memory + sizeof(memory)));
    return 0x80010000u + (uint32_t)(address - (uintptr_t)memory);
}
static int callback(int value) { ++callbacks; return value + 7; }
void *GuestRuntime_ResolveFunction(void *pointer) {
    assert((uintptr_t)pointer == 0x80020000u);
    return (void *)(uintptr_t)&callback;
}
extern int exercise(void *, void *);
int main(void) {
    uint32_t value = 0x12345678u;
    memcpy(memory, &value, 4);
    int result = exercise(memory + 16, (void *)(uintptr_t)0x80020000u);
    assert(result == (int)value + 7);
    const unsigned char expected[] = {0x78,0x56,0x34,0x12,0x78,0x78,0x56,0x34,0x12,0x5a,0x5a,0x5a};
    assert(!memcmp(memory + 16, expected, sizeof(expected)));
    uint32_t counter;
    memcpy(&counter, memory + 28, 4);
    assert(counter == 9);
    assert(callbacks == 1 && encodings == 2 && resolutions == 9);
    return 0;
}
'''
        translated = translate(source, {'slot': 0x80010000})
        with tempfile.TemporaryDirectory(dir=ROOT / 'tmp') as folder:
            folder = Path(folder)
            (folder / 'fixture.ll').write_text(translated)
            (folder / 'harness.c').write_text(harness)
            binary = folder / 'test'
            subprocess.run([str(toolchain() / 'bin/clang'), '-isysroot', str(sdk_path()),
                            '-O2', str(folder / 'fixture.ll'), str(folder / 'harness.c'),
                            '-o', str(binary)], check=True, capture_output=True, text=True, timeout=60)
            subprocess.run([str(binary)], check=True, timeout=20)

    def test_unsupported_address_space_rejected(self):
        with self.assertRaisesRegex(TranslationError, 'unsupported pointer address space'):
            translate('define i32 @bad(ptr addrspace(272) %p) { %v = load i32, ptr addrspace(272) %p ret i32 %v }')

    def test_machine_assembly_rejected(self):
        with self.assertRaisesRegex(TranslationError, 'machine assembly is unsupported'):
            translate('define void @bad() { call void asm sideeffect "nop", ""() ret void }')

    def test_scalable_memory_rejected(self):
        with self.assertRaisesRegex(TranslationError, 'scalable memory operation is unsupported'):
            translate('define <vscale x 4 x i32> @bad(ptr %p) { %v = load <vscale x 4 x i32>, ptr %p ret <vscale x 4 x i32> %v }')

    def test_unwind_call_rejected(self):
        with self.assertRaisesRegex(TranslationError, 'invoke/callbr are unsupported'):
            translate('''
declare void @callee()
declare i32 @personality(...)
define void @bad() personality ptr @personality {
  invoke void @callee() to label %done unwind label %cleanup
done:
  ret void
cleanup:
  %landing = landingpad { ptr, i32 } cleanup
  resume { ptr, i32 } %landing
}
''')

    def test_invalid_pinned_address_rejected(self):
        with self.assertRaisesRegex(TranslationError, 'invalid guest address'):
            translate('@value = external global i32', {'value': 0x100000000})


class SymbolNormalizationTests(unittest.TestCase):
    def test_assembler_global_aliases_share_guest_address(self):
        source = r'''
@record = external global [1 x i8]
@"\01record" = external global i8
define ptr @address() {
  ret ptr @"\01record"
}
'''
        normalized = normalize(source)
        self.assertNotIn('record.1', normalized)
        self.assertNotIn('\\01record', normalized)
        self.assertIn('ret ptr @record', normalized)
        adapted = translate(normalized, {'record': 0x80018000})
        self.assertNotIn('@record', adapted)
        self.assertIn('2147581952', adapted)

    def test_function_alias_keeps_definition_and_call_type(self):
        source = r'''
declare void @"\01_transform"(i32)
define i32 @transform(i16 %value) {
  %result = zext i16 %value to i32
  ret i32 %result
}
define void @caller() {
  call void @"\01_transform"(i32 65535)
  ret void
}
'''
        normalized = normalize(source)
        self.assertEqual(inspect(normalized)['definitions'], ['transform', 'caller'])
        self.assertIn('call void @transform(i32 65535)', normalized)
        self.assertNotIn('transform.1', normalized)

    def test_definition_wins_over_existing_declaration(self):
        normalized = normalize(r'''
@value = external global i32
@"\01value" = global i32 7
define ptr @address() { ret ptr @value }
''')
        self.assertEqual(inspect(normalized)['globals'], ['value'])
        self.assertIn('@value = global i32 7', normalized)

    def test_explicit_renames_merge_global_declarations(self):
        normalized = normalize('''
@old = external global i8
@new = global i8 9
define ptr @address() { ret ptr @old }
''', {'old': 'new'})
        self.assertIn('ret ptr @new', normalized)
        self.assertNotIn('@old', normalized)

    def test_duplicate_definitions_fail(self):
        with self.assertRaisesRegex(TranslationError, 'duplicate renamed definition: value'):
            normalize(r'@value = global i32 1' + '\n' + r'@"\01value" = global i32 2')

    def test_incompatible_symbol_kinds_fail(self):
        with self.assertRaisesRegex(TranslationError, 'incompatible renamed symbols: value'):
            normalize('''
@value = external global i32
declare void @old()
''', {'old': 'value'})


if __name__ == '__main__':
    unittest.main()
