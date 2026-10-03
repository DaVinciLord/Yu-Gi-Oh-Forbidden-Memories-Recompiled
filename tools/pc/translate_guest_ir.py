#!/usr/bin/env python3
"""Bounded unoptimized Apple Clang IR adapter for translated guest memory.

Never transforms optimized IR. Unsupported memory operations fail closed.
This compiler bring-up tool does not certify whole-game pointer provenance.
"""
import argparse
from pathlib import Path
import re

class TranslationError(ValueError):
    pass

def split_top(text):
    parts, start, depth = [], 0, 0
    for i, c in enumerate(text):
        if c in '([{<': depth += 1
        elif c in ')]}>': depth -= 1
        elif c == ',' and depth == 0:
            parts.append(text[start:i].strip()); start = i + 1
    parts.append(text[start:].strip())
    return parts

def address_map(path):
    result = {}
    active = False
    for line in Path(path).read_text().splitlines():
        if line.startswith('['):
            active = line == '[SLUS_014.11]'
        elif active:
            pieces = line.split()
            if len(pieces) == 2:
                result[pieces[0]] = int(pieces[1], 16)
    return result

def translate(original, pinned=None):
    pinned = pinned or {}
    if 'define ' in original and 'optnone' not in original:
        raise TranslationError('requires unoptimized optnone input')
    returns_twice_groups = set(re.findall(r'^attributes #(\d+) = \{[^\n]*\breturns_twice\b', original, re.M))
    returns_twice_names = {match[1] for match in re.finditer(r'^declare .*?@([\w.$]+)\([^\n]*#(\d+)', original, re.M)
                           if match[2] in returns_twice_groups}
    # Calls with inferred attributes would describe the old raw-memory world.
    text = re.sub(r'^attributes #\d+ = \{[^\n]*\}\n', '', original, flags=re.M)
    pieces = re.split(r'("(?:[^"\\]|\\.)*")', text)
    for index in range(0, len(pieces), 2):
        pieces[index] = re.sub(r' #\d+\b', '', pieces[index])
        pieces[index] = re.sub(r'\b(?:inbounds|nuw|nsw|noundef)\b\s*', '', pieces[index])
    text = ''.join(pieces)
    text = re.sub(r', ![A-Za-z][\w.]* !\d+', '', text)
    globals_seen = set(re.findall(r'^@([\w.$]+) = ', text, re.M))
    functions = set(re.findall(r'^(?:define|declare) .*?@([\w.$]+)\(', text, re.M))
    mapped = {name: addr for name, addr in pinned.items() if name in globals_seen and name not in functions}
    text = '\n'.join(line for line in text.splitlines()
                     if not any(line.startswith('@' + name + ' = ') for name in mapped)) + '\n'
    pieces = re.split(r'("(?:[^"\\]|\\.)*")', text)
    for index in range(0, len(pieces), 2):
        for name, address in mapped.items():
            pieces[index] = re.sub(r'@' + re.escape(name) + r'(?![\w.$])',
                                   f'inttoptr (i64 {address} to ptr)', pieces[index])
    text = ''.join(pieces)
    serial = 0
    result = []
    def temp():
        nonlocal serial
        serial += 1
        return '%guest.adapter.' + str(serial)
    def native(address, prefix):
        kind, value = address.split(' ', 1)
        if kind != 'ptr': raise TranslationError('unsupported address ' + address)
        if value.startswith('addrspace('):
            match = re.fullmatch(r'addrspace\(271\) (.+)', value)
            if not match: raise TranslationError('unsupported address space ' + address)
            integer, host = temp(), temp()
            prefix.append(f'  {integer} = ptrtoint ptr addrspace(271) {match[1]} to i32')
            prefix.append(f'  {host} = inttoptr i32 {integer} to ptr')
            return host
        return value
    # Encode effective narrowing conversions, preserving full-width ptrtoint
    # used for genuine host arithmetic. ptrtoint271 already encodes guest bits.
    conversions = {}
    for line in text.splitlines():
        if line.startswith('define '): conversions = {}
        pointer_conversion = re.match(r'  (%[\w.]+) = ptrtoint ptr (.+) to i64$', line)
        if pointer_conversion: conversions[pointer_conversion[1]] = pointer_conversion[2]
        prefix = []
        twice_declaration = re.match(r'^declare .*?@([\w.$]+)\(', line)
        if twice_declaration and twice_declaration[1] in returns_twice_names:
            line += ' returns_twice'
        if re.match(r'  (?:(?:%[\w.]+) = )?(?:invoke|callbr)\b', line):
            raise TranslationError('unsupported instruction: ' + line.strip())
        intrinsic = re.search(r'call void @llvm\.(memcpy|memmove|memset)\.[^(]+\((.*)\)', line)
        if intrinsic:
            parts = split_top(intrinsic[2])
            if len(parts) != 4 or not parts[2].startswith('i64 '):
                raise TranslationError('unsupported memory intrinsic: ' + line.strip())
            count = 1 if intrinsic[1] == 'memset' else 2
            for index in range(count):
                address = re.sub(r'\balign \d+\s*', '', parts[index])
                pointer = native(address, prefix)
                resolved = temp()
                prefix.append(f'  {resolved} = call ptr @GuestRuntime_ResolveData(ptr {pointer}, {parts[2]})')
                parts[index] = 'ptr ' + resolved
            suffix = 'p0.i64' if count == 1 else 'p0.p0.i64'
            line = f'  call void @llvm.{intrinsic[1]}.{suffix}(' + ', '.join(parts) + ')'
        # Constant-expression address-space conversions within instructions
        # must be materialized; a static global initializer cannot call runtime.
        while 'addrspacecast (' in line:
            start = line.index('addrspacecast (')
            cursor = start + len('addrspacecast ')
            depth = 0
            end = None
            for index in range(cursor, len(line)):
                if line[index] == '(': depth += 1
                elif line[index] == ')':
                    depth -= 1
                    if depth == 0:
                        end = index + 1; break
            if end is None or not line.startswith('  '):
                raise TranslationError('unsupported constant address-space cast: ' + line.strip())
            expression = line[cursor + 1:end - 1]
            constant = re.fullmatch(r'ptr (.+) to ptr addrspace\(271\)', expression)
            if not constant:
                raise TranslationError('unsupported constant address-space cast: ' + line.strip())
            integer, guest = temp(), temp()
            prefix.append(f'  {integer} = call i32 @GuestRuntime_EncodePointer(ptr {constant[1]})')
            prefix.append(f'  {guest} = inttoptr i32 {integer} to ptr addrspace(271)')
            line = line[:start] + guest + line[end:]
        # Clang folds casts of known function/global addresses into constant
        # expressions inside stores/calls. Materialize narrowing before host
        # codegen can truncate the real ARM64 address.
        cursor = 0
        while True:
            start = line.find('ptrtoint (', cursor)
            if start < 0: break
            quoted = next((match for match in re.finditer(r'"(?:[^"\\]|\\.)*"', line)
                           if match.start() <= start < match.end()), None)
            if quoted:
                cursor = quoted.end(); continue
            opening = start + len('ptrtoint ')
            depth, end = 0, None
            for index in range(opening, len(line)):
                if line[index] == '(': depth += 1
                elif line[index] == ')':
                    depth -= 1
                    if depth == 0: end = index + 1; break
            if end is None: raise TranslationError('unterminated pointer constant: ' + line.strip())
            expression = line[opening + 1:end - 1]
            narrowing = re.fullmatch(r'ptr (.+) to i32', expression)
            if narrowing:
                if not line.startswith('  '):
                    raise TranslationError('narrow pointer static initializer unsupported: ' + line.strip())
                integer = temp()
                prefix.append(f'  {integer} = call i32 @GuestRuntime_EncodePointer(ptr {narrowing[1]})')
                line = line[:start] + integer + line[end:]
                cursor = start + len(integer)
            else:
                if expression.endswith(' to i32'):
                    raise TranslationError('unsupported narrow pointer constant: ' + line.strip())
                cursor = end
        # Integer constant expressions surrounding an encoded pointer now
        # contain SSA operands and must also become ordinary instructions.
        while True:
            binary = re.search(r'(add|sub|and|or|xor) \((i\d+) ([^()]+), \2 ([^()]+)\)', line)
            if not binary or '%' not in binary[0]: break
            integer = temp()
            prefix.append(f'  {integer} = {binary[1]} {binary[2]} {binary[3]}, {binary[4]}')
            line = line[:binary.start()] + integer + line[binary.end():]
        m = re.match(r'  (%[\w.]+) = addrspacecast ptr addrspace\(271\) (.+) to ptr$', line)
        if m:
            integer = temp()
            prefix.append(f'  {integer} = ptrtoint ptr addrspace(271) {m[2]} to i32')
            line = f'  {m[1]} = inttoptr i32 {integer} to ptr'
        else:
            m = re.match(r'  (%[\w.]+) = addrspacecast ptr (.+) to ptr addrspace\(271\)$', line)
            if m:
                integer = temp()
                prefix.append(f'  {integer} = call i32 @GuestRuntime_EncodePointer(ptr {m[2]})')
                line = f'  {m[1]} = inttoptr i32 {integer} to ptr addrspace(271)'
            elif 'addrspacecast' in line:
                raise TranslationError('unsupported address-space cast: ' + line.strip())
        m = re.match(r'  (%[\w.]+) = ptrtoint ptr (.+) to i32$', line)
        if m: line = f'  {m[1]} = call i32 @GuestRuntime_EncodePointer(ptr {m[2]})'
        m = re.match(r'  (%[\w.]+) = trunc i64 (%[\w.]+) to i32$', line)
        if m and m[2] in conversions:
            line = f'  {m[1]} = call i32 @GuestRuntime_EncodePointer(ptr {conversions[m[2]]})'
        atomic = re.match(r'(  (?:%[^ ]+ = )?(?:atomicrmw|cmpxchg) )(.*)', line)
        if atomic:
            parts = split_top(atomic[2])
            if len(parts) < 2: raise TranslationError('unsupported atomic operation: ' + line)
            kind = 'atomicrmw' if 'atomicrmw' in atomic[1] else 'cmpxchg'
            address_match = re.match(r'((?:volatile |weak )*(?:[a-z]+ )?)(ptr .+)$', parts[0])
            value_type = re.match(r'(i\d+|ptr) ', parts[1])
            if not address_match or not value_type: raise TranslationError('unsupported atomic operands: ' + line)
            pointer = native(address_match[2], prefix); resolved = temp()
            size = f'ptrtoint (ptr getelementptr ({value_type[1]}, ptr null, i32 1) to i64)'
            prefix.append(f'  {resolved} = call ptr @GuestRuntime_ResolveData(ptr {pointer}, i64 {size})')
            parts[0] = address_match[1] + 'ptr ' + resolved
            line = atomic[1] + ', '.join(parts)
        load = re.match(r'(  %[^ ]+ = load )(.*)', line)
        store = re.match(r'(  store )(.*)', line)
        if load or store:
            match = load or store
            parts = split_top(match[2])
            if len(parts) < 2:
                raise TranslationError('unsupported memory access: ' + line.strip())
            value_part = re.sub(r'^(?:atomic |volatile )+', '', parts[0])
            ordering = ''
            if parts[0].startswith('atomic '):
                order_match = re.search(r' (unordered|monotonic|acquire|release|acq_rel|seq_cst)$', parts[1])
                if not order_match: raise TranslationError('unsupported atomic ordering: ' + line)
                ordering = order_match[0]
                parts[1] = parts[1][:-len(ordering)]
            if load:
                type_ = value_part
            else:
                # Store type is scalar/pointer or named aggregate; reject inline
                # aggregate/vector stores rather than mis-measuring them.
                type_match = re.match(r'(ptr(?: addrspace\(271\))?|i\d+|float|double|%[\w.]+) ', value_part)
                if type_match: type_ = type_match[1]
                else:
                    aggregate = re.match(r'(\[.+\]|\{.+\}|<.+>) (?:%[\w.]+|zeroinitializer|undef|poison)', value_part)
                    if not aggregate: raise TranslationError('unsupported store type: ' + line.strip())
                    type_ = aggregate[1]
            pointer = native(parts[1], prefix)
            resolved = temp()
            size = f'ptrtoint (ptr getelementptr ({type_}, ptr null, i32 1) to i64)'
            prefix.append(f'  {resolved} = call ptr @GuestRuntime_ResolveData(ptr {pointer}, i64 {size})')
            parts[1] = 'ptr ' + resolved + ordering
            line = match[1] + ', '.join(parts)
        m = re.search(r'\bcall\b (.*?) (%[\w.]+)\(', line)
        if m:
            resolved = temp()
            target = native('ptr addrspace(271) ' + m[2], prefix) if 'addrspace(271)' in m[1] else m[2]
            prefix.append(f'  {resolved} = call ptr @GuestRuntime_ResolveFunction(ptr {target})')
            callee_prefix = m[1].replace('addrspace(271) ', '')
            line = line[:m.start(1)] + callee_prefix + ' ' + resolved + line[m.end(2):]
            line = line.replace('musttail ', '').replace('tail ', '')
        result.extend(prefix)
        result.append(line)
    declarations = ('declare ptr @GuestRuntime_ResolveData(ptr, i64)\n'
                    'declare ptr @GuestRuntime_ResolveFunction(ptr)\n'
                    'declare i32 @GuestRuntime_EncodePointer(ptr)\n')
    for name in ('memcpy', 'memmove', 'memset'):
        suffix = 'p0.i64' if name == 'memset' else 'p0.p0.i64'
        symbol = '@llvm.' + name + '.' + suffix
        if symbol + '(' in '\n'.join(result) and not any(l.startswith('declare ') and symbol + '(' in l for l in result):
            arguments = 'ptr, i8, i64, i1 immarg' if name == 'memset' else 'ptr, ptr, i64, i1 immarg'
            declarations += f'declare void {symbol}({arguments})\n'
    return '\n'.join(result) + '\n' + declarations

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--addresses', type=Path, default=Path('config/pc/guest_addresses.txt'))
    args = parser.parse_args()
    try:
        args.output.write_text(translate(args.source.read_text(), address_map(args.addresses)))
    except TranslationError as error:
        parser.error(str(error))

if __name__ == '__main__': main()
