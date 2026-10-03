"""Optional diagnostics in generated name-entry copies; retail sources unchanged."""
PREFIX = '#include <stdio.h>\n#include <stdlib.h>\nextern unsigned Memories_PresentedFrames(void);\n#define NAME_TRACE(...) do { if (getenv("MEMORIES_TRACE_NAME")) printf(__VA_ARGS__); } while (0)\n'
EDITS = {
 'src/overlays/password/name_entry_keyboard_update.c': [
  ('    w = D_8016D404;', '    w = D_8016D404;\n    if (gInput_wPad1Pressed || gInput_wPad1Repeat) NAME_TRACE("name keyboard frame=%u held=%x pressed=%x repeat=%x row=%d col=%d flags=%x caret=%d\\n", Memories_PresentedFrames(), gInput_wPad1Held, gInput_wPad1Pressed, gInput_wPad1Repeat, (s8)D_8016D402, (s8)D_8016D401, D_8016D400, D_8016D42C);'),
  ('    node = TextBox_GetGlyphAt(kind, gx, gy);', '    node = TextBox_GetGlyphAt(kind, gx, gy);\n    NAME_TRACE("name select frame=%u kind=%d gx=%d gy=%d cell=%d node=%x code=%x\\n", Memories_PresentedFrames(), kind, gx, gy, glyphCode, (u32)(uintptr_t)node, node ? node->code_00 : 0);'),
  ('        obj = NameEntry_SpawnGlyphSprite(1, node);', '        NAME_TRACE("name store frame=%u buffer=%x caret=%d slot=%x code=%x\\n", Memories_PresentedFrames(), (u32)(uintptr_t)D_8016D418, D_8016D42C, (u32)(uintptr_t)slot, *slot);\n        obj = NameEntry_SpawnGlyphSprite(1, node);')],
 'src/overlays/password/name_entry_dialog.c': [
  ('    if (D_8016D4D2 != 0) {', '    if (gInput_wPad1Pressed || gInput_wPad1Repeat) NAME_TRACE("name dialog frame=%u flags=%x dialog=%x pressed=%x repeat=%x\\n", Memories_PresentedFrames(), D_8016D400, D_8016D4D2, gInput_wPad1Pressed, gInput_wPad1Repeat);\n    if (D_8016D4D2 != 0) {'),
  ('            func_80039794();\n            if ((*(u32 *)&box->flags_34', '            func_80039794();\n            if (gInput_wPad1Pressed || Memories_PresentedFrames() % 120 == 0) NAME_TRACE("name wait frame=%u textflags=%x choice=%x pressed=%x completion=%x\\n", Memories_PresentedFrames(), box->flags_34, (u32)(uintptr_t)box->field_30, gInput_wPad1Pressed, *(u32 *)&box->flags_34 & TEXT_BOX_COMPLETION_MASK);\n            if ((*(u32 *)&box->flags_34'),
  ('        Text_SjisToGlyphCodes(D_801B125A, D_8016D418, 6);', '        NAME_TRACE("name transfer frame=%u buffer=%x first=%x caret=%d\\n", Memories_PresentedFrames(), (u32)(uintptr_t)D_8016D418, *(u16 *)D_8016D418, D_8016D42C);\n        Text_SjisToGlyphCodes(D_801B125A, D_8016D418, 6);')]
}
def adapt_name_entry_trace(text, source):
 if source not in EDITS:return text
 for before, after in EDITS[source]:
  if text.count(before)!=1:raise ValueError('Name trace source shape changed: '+source+' '+before)
  text=text.replace(before,after)
 return PREFIX+text
