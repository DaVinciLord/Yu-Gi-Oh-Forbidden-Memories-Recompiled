"""Evidence-scoped guest-width corrections for generated native source only.

These declarations point into the retail 32-bit data image. Their current
matching-source declarations omit G32; changing those originals would affect
console codegen. Apply this adapter only to generated macOS source copies.
This is intentionally a symbol allow-list, not a general pointer rewriter.
"""
import re

TYPEDEF_TABLES = {
    'gMain_apfnModeRunner': 'MainModeRunner',
    'gAiScript_apfnCommand': 'AiScriptHandler',
    'gDuelEffect_apfnGroupHandler': 'DuelEffectHandler',
    'gDuelEffect_apfnStateHandler': 'DuelEffectHandler',
    'D_80090C50': 'ScriptCommandHandler',
    'D_80090CAC': 'SceneScriptRecordCallback',
    'D_80090E64': 'TextBoxStateCallback',
}
FUNCTION_TABLES = {
    'D_80090DF8', 'D_80090F68', 'D_80090FEC',
    'gDuel_apfnSceneStateHandler', 'D_80090EAC',
    'gDebugMenu_apfnAlternatePageSteps', 'gDebugMenu_apfnPrimaryPageSteps',
    'D_80090F9C', 'gDisplayObject_ListRenderers',
}
SCALAR_POINTERS = {'D_8009AF18': 'FileTransferDescriptor', 'D_8009AF88': 'u8',
                   'D_801695C8': 'MapObject', 'D_801695D8': 'MapObject',
                   'D_801695F8': 'u8',
                   'gFreeDuel_pThumbWidget': 'DisplayObject',
                   'gFreeDuel_apSparklePool': 'DisplayObject',
                   'gFreeDuel_pCursorWidget': 'DisplayObject'}


TABLE_CURSORS = {
    'src/game/ai_script_vm.c': ('AiScriptHandler handler;', 'AiScriptHandler G32 handler;'),
    'src/game/display_effect_process_menu_records.c': ('void (**t)(MenuRecord *) = D_80090F68;', 'void (*G32 *t)(MenuRecord *) = D_80090F68;'),
    'src/game/display_object_stream_read_next_command.c': ('s32 (**table)(DisplayObjectStreamState *, const u8 *);', 's32 (*G32 *table)(DisplayObjectStreamState *, const u8 *);'),
    'src/game/duel_magic_effect_dispatch.c': ('DuelEffectHandler *callbacks;', 'DuelEffectHandler G32 *callbacks;'),
    'src/game/func_80024200.c': ('void (**callbacks)(void);', 'void (*G32 *callbacks)(void);'),
}


STORAGE_VIEWS = {
    # Retail code walks o32 arguments above a4; ARM64 variadics use va_list.
    'src/game/func_80058838.c': (
        ('#include "../types.h"\n', '#include "../types.h"\n#include <stdarg.h>\n'),
        ('u8 *arguments;', 'va_list arguments;'),
        ('arguments = (u8 *)&a4 + 4;', 'va_start(arguments, a4);'),
        ('arguments += 4;\n        value = *(s32 *)(arguments - 4);',
         'value = va_arg(arguments, s32);'),
        ('a2.b3 = a1 & 127;', 'va_end(arguments);\n    a2.b3 = a1 & 127;'),
    ),
    # A retail 16-byte quad copies four callback tokens into this local.
    'src/game/model_intro_controller.c': (
        ('s32 (*handlers[4])(s32, s32);', 's32 (*G32 handlers[4])(s32, s32);'),
    ),
    # Sixteen sparkle pointers at 0x80169060 end at the cursor at 0x801690a0.
    'src/overlays/free_duel/screen_runtime.c': (
        ('DisplayObject **slot;', 'DisplayObject *G32 *slot;'),
        ('DisplayObject **FreeDuel_GetSparkleSlot', 'DisplayObject *G32 *FreeDuel_GetSparkleSlot'),
    ),
    # Card records and selection cursors live in the retail data image.
    'src/game/duel_card_record_lifecycle.c': (
        ('*(DuelCardDisplayObject **)slot', '*(DuelCardDisplayObject *G32 *)slot'),
    ),
    'src/game/duel_ritual_effect.c': (
        ('*(u8 **)&card->data', '*(u8 *G32 *)&card->data'),
    ),
    'src/game/duel_scene_battle.c': (
        ('*(void **)((u8 *)D_8009B1B4 + 4)', '*(void *G32 *)((u8 *)D_8009B1B4 + 4)'),
    ),
    'src/game/duel_scene_field_actions.c': (
        ('*(u8 **)((u8 *)SEL_REC3 + D_8009B1D5 * 0x70 - 0x18)',
         '*(u8 *G32 *)((u8 *)SEL_REC3 + D_8009B1D5 * 0x70 - 0x18)'),
    ),
    'src/game/duel_effect_command.c': (
        ('*(u8 **)text', '*(u8 *G32 *)text'),
        ('register u8**stream;', 'register u8 *G32 *stream;'),
        ('((u8**)obj)', '((u8 *G32 *)obj)'),
    ),
    'src/game/model_handler_registry.c': (
        ('*(ModelHandler *)unit->ptr', '*(ModelHandler G32 *)unit->ptr'),
    ),
    'src/game/model_packet_handlers.c': (
        ('(GsSEQ **)', '(GsSEQ *G32 *)'),
        ('*(void **)', '*(void *G32 *)'),
    ),
    'src/psyq/libhmd.h': (
        ('GsLinkAnim(GsSEQ **,u32 *)', 'GsLinkAnim(GsSEQ *G32 *,u32 *)'),
    ),
    'src/game/model_load_step.c': (
        ('*(u8 **)((u8 *)p + 0xDE8)', '*(u8 *G32 *)((u8 *)p + 0xDE8)'),
    ),
    'src/game/func_8004CB0C.c': (
        ('*(s32 **)cursor', '*(s32 *G32 *)cursor'),
    ),
    'src/game/model_scene_states.c': (
        ('next == (u32 *)-1', 'next == (u32 *)0xFFFFFFFFu'),
    ),
    # GsScanUnit writes the scratch primitive/section pointers as u32;
    # GsMapUnit rebases the HMD linked blocks and section entries as u32.
    'src/game/model_slot_row_tables.c': (
        ('*(u8 **)ctx', '*(u8 *G32 *)ctx'),
        ('*(u8 **)(ctx + 0x14)', '*(u8 *G32 *)(ctx + 0x14)'),
        ('*(u8 **)(arg1 + 0x10)', '*(u8 *G32 *)(arg1 + 0x10)'),
        ('*(u8 **)(e + 4)', '*(u8 *G32 *)(e + 4)'),
        ('*(u8 **)e', '*(u8 *G32 *)e'),
        ('*(u8 **)p3', '*(u8 *G32 *)p3'),
        # G32 loads zero-extend; the HMD terminator is the guest word -1.
        ('e != (u8 *)-1', 'e != (u8 *)0xFFFFFFFFu'),
    ),
    # MenuRecord grid rows are exactly three guest words (12 bytes).
    'src/game/func_8003A1EC.h': (
        ('DisplayObject **out', 'DisplayObject *G32 *out'),
    ),
    'src/game/func_8003A440.h': (
        ('u8 **objects', 'u8 *G32 *objects'),
    ),
    'src/game/display_effect_lifecycle.h': (
        ('void **objects', 'void *G32 *objects'),
    ),
    'src/game/display_effect_lifecycle.c': (
        ('void **objects', 'void *G32 *objects'),
        ('(void **)', '(void *G32 *)'),
    ),
    'src/game/display_effect_resource_setup.c': (
        ('DisplayObject **out', 'DisplayObject *G32 *out'),
        ('u8 **arg0', 'u8 *G32 *arg0'),
        ('(DisplayObject **)', '(DisplayObject *G32 *)'),
    ),
    'src/game/display_effect_update_callbacks.c': (
        ('(DisplayObject **)', '(DisplayObject *G32 *)'),
        ('(u8 **)', '(u8 *G32 *)'),
        ('(void **)', '(void *G32 *)'),
        ('u8 **d;', 'u8 *G32 *d;'),
    ),
    'src/game/sound_output_state.c': (
        ('u8 **table;', 'u8 *G32 *table;'),
        ('(u8 **)a->bank_0518', '(u8 *G32 *)a->bank_0518'),
        ('(u8 **)g_SDValue->bank_0518', '(u8 *G32 *)g_SDValue->bank_0518'),
        ('(u8 **)b->bank_0518', '(u8 *G32 *)b->bank_0518'),
    ),
    'src/game/func_8004ADE8.c': (
        ('(u8 **)(D_8009B458 + 0x4A8)', '(u8 *G32 *)(D_8009B458 + 0x4A8)'),
    ),
    'src/overlays/main_menu/frontend_background.c': (
        ('DisplayObject **entries = (DisplayObject **)gMain_apMenuEntries;', 'DisplayObject *G32 *entries = (DisplayObject *G32 *)gMain_apMenuEntries;'),
    ),
    'src/game/sd_arm_busy_callback.c': (
        ('#define g_SDValue (*(SDValue **)0x8009B45C)', '#define g_SDValue (*(SDValue *G32 *)0x8009B45C)'),
        ('#define D_8009B128 (*(void (**)(void))0x8009B128)', '#define D_8009B128 (*(void (*G32 *)(void))0x8009B128)'),
    ),
    'src/game/sound_init.c': (
        ('*(void **)&g_SDValue->music_track = entry;', '*(void *G32 *)&g_SDValue->music_track = entry;'),
    ),
}


def apply_guest_pointer_overrides(text, source=None):
    for old, new in STORAGE_VIEWS.get(source, ()):
        if old not in text and new not in text:
            raise ValueError('Known guest storage view changed: ' + source)
        if old in new and new in text:
            continue
        text = text.replace(old, new)
    if source in TABLE_CURSORS:
        old, new = TABLE_CURSORS[source]
        if old not in text and new not in text:
            raise ValueError('Known guest table cursor changed: ' + source)
        text = text.replace(old, new)
    for symbol, type_ in TYPEDEF_TABLES.items():
        # Includes a newline when a typedef and its table name occupy two
        # lines. Expressions never begin with the allow-listed typedef.
        pattern = r'^(\s*(?:extern\s+)?' + re.escape(type_) + r')(\s+)(' + re.escape(symbol) + r'\b)'
        text = re.sub(pattern, r'\1 G32\2\3', text, flags=re.M)
    for symbol in FUNCTION_TABLES:
        pattern = r'^(\s*(?:extern\s+)?(?:void|s32)\s*\(\*)(\s*)(' + re.escape(symbol) + r'\s*\[)'
        text = re.sub(pattern, r'\1G32 \2\3', text, flags=re.M)
    for symbol, type_ in SCALAR_POINTERS.items():
        pattern = r'^(\s*(?:extern\s+)?' + re.escape(type_) + r'\s*\*)(\s*)(' + re.escape(symbol) + r'\b)'
        text = re.sub(pattern, r'\1G32 \2\3', text, flags=re.M)
    return text
