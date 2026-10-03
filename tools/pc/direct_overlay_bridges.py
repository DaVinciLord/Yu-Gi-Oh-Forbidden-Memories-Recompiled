"""Typed direct imports whose actual target depends on the loaded PS1 bank."""
import re
ENTRIES = {'func_8016AA6C': (0x8016AA6C, False),
           'func_8016866C': (0x8016866C, True),
           'func_80168FB4': (0x80168FB4, False),
           'func_801462B0': (0x801462B0, 'effect')}

def validate_declaration(name, declaration):
    argument = r'i32(?: noundef)?' if ENTRIES[name][1] else ''
    if name == 'func_801462B0':
        argument = r'i16(?: noundef)?(?: signext)?, i16(?: noundef)?(?: signext)?, i32(?: noundef)?, ptr(?: noundef)?'
    if not re.fullmatch(r'declare void @' + name + r'\(' + argument + r'\)(?: #[0-9]+)?', declaration):
        raise ValueError('Unsupported direct overlay entry signature: ' + declaration)

def emit_bridge(name):
    if name == 'func_801462B0':
        return ('#include "game/duel_effect_request.h"\n'
                'extern void Memories_DuelEffectControl(short, short, int, DuelEffectRequest *);\n'
                'void func_801462B0(short id, short state, int buffer, DuelEffectRequest *request) '
                '{ Memories_DuelEffectControl(id, state, buffer, request); }\n')
    address, takes_index = ENTRIES[name]
    argument = 'int32_t index' if takes_index else 'void'
    pointer_argument = 'int32_t' if takes_index else 'void'
    call = 'index' if takes_index else ''
    return f'void {name}({argument}) {{ ((void (*)({pointer_argument}))GuestRuntime_ResolveFunction((void *)(uintptr_t)0x{address:08x}u))({call}); }}\n'
