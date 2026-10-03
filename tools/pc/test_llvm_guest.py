#!/usr/bin/env python3
"""Structured compiler regressions, independent of ROM and generated game IR."""
import unittest
from llvm_guest import TranslationError, inspect, normalize, translate


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
