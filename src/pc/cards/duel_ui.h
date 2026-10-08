#ifndef MEMORIES_PC_CARDS_DUEL_UI_H
#define MEMORIES_PC_CARDS_DUEL_UI_H
/* The mods' "ui" key in the duel (notes/modding.md, "The duel's pictures";
 * read by pc/platform/ui_config.h): the life-point panel's two halves with
 * their digits, the FIELD box, the card bar and the two cursors, each moved,
 * sized about its middle, coloured, hidden or drawn from a PNG of the mod's
 * own. All of it is done as they are drawn: the game's objects keep their
 * places, so its own slides and turns go on as they do, and without such a
 * mod nothing here draws. */
#include "game/display_object.h"
#include "ygo_types.h"

/* While set, the sprites DisplayObject_SubmitPacket would sort (its cases 1
 * to 3) are kept here instead, each with its mode, for the port to draw
 * itself; past DISPLAY_OBJECT_CAPTURE_MAX they are sorted as usual. */
#define DISPLAY_OBJECT_CAPTURE_MAX 16
typedef struct {
    SpritePrim sprite[DISPLAY_OBJECT_CAPTURE_MAX];
    s32 mode[DISPLAY_OBJECT_CAPTURE_MAX];
    s32 count;
} DisplayObjectCapture;
extern DisplayObjectCapture *DisplayObject_Capture;

/* Duel_InitScene: the mods' "ui" read again for this duel. */
void DuelUi_Prepare(void);
/* DisplayObject_RenderSpriteSheetList: 1 when it drew the object (or hid
 * it) itself, 0 for the game to draw it. */
int DuelUi_RenderObject(DisplayObject *object, s32 ot, s32 depth);
/* Duel_DrawLifePointsAndDeckCounts, before its digits: whether the panel is
 * the mod's to draw (then the game's own widening for a fifth digit is not
 * done: the panel's halves widen themselves), and the digits' count. */
int DuelUi_PanelDrawn(int digits);
/* One row of the panel's digits for side 0 (the player's, the bottom half)
 * or 1 (the opponent's, the top), as func_80016D2C draws them from `digit`
 * (a GsSPRITE at their first place): 1 when it drew them, moved, sized and
 * coloured with their half. */
int DuelUi_DrawDigits(int side, DisplayObject *panel, void *digit, int value, int count);
/* Whether a mod's "ui" draws the panel itself this duel (the renderers
 * then put the names over its pieces, hd_text.h). */
int DuelUi_PanelCut(void);
/* The words in place of COM (which 0) or YOU (1), or NULL (hd_text.c). */
const char *DuelUi_Label(int which);
/* How far an element is moved this duel (rank_meter.c follows the FIELD
 * box); 0, 0 for one left alone. */
void DuelUi_Offset(int element, int *x, int *y);
#endif
