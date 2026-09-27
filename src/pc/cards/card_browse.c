/* Browsing cards in the card viewer (card_browse.h).
 *
 * The viewer (DuelEffect_UpdateCardViewerState) opens by loading the card
 * into resource slot 3 (func_80029164 starts the disc read, whose callback
 * puts its art in VRAM), making the card's picture (func_800291E0) and a
 * text box of its description, then sliding them in; while they slide it
 * waits for the read, then fades the card in, then shows it until Circle.
 * Closing lets the card go with func_80029528(3) and destroys the text box.
 *
 * Another card is shown the same way without the slides: the card and its
 * text box are let go as closing does, the opening's steps are taken again
 * with the pieces where they slide to, and the viewer is handed back to its
 * own wait for the read and fade. The background panel stays. So the card
 * is loaded and drawn exactly as when triangle opens it.
 *
 * Build Deck (mode 7): the viewer was opened from the active pane's list
 * (build_deck_pane_input.c), which does not read the pad while the viewer
 * is up (func_800339D0 only runs a pane when DuelEffect_UpdateState is
 * idle). The next row holding a card is found round the list, and the
 * cursor put on it, the page moved and rebuilt at once as R2 does when it
 * has to scroll. The page is rebuilt before the text box is made:
 * CardList_CreateSlotTextBox leaves gDuel_wSelectedCardID on its last row,
 * and the description is set from gDuel_wSelectedCardID. */
#include "card_browse.h"
#include "pc/platform/settings.h"
#include "types.h"
#include "game/input.h"
#include "game/sound.h"
#include "game/main_modes.h"
#include "game/display_object.h"
#include "game/display_object_core.h"
#include "game/display_object_helpers.h"
#include "game/display_object_interpolation.h"
#include "game/duel_effect.h"
#include "game/duel_card.h"
#define DUEL_CARD_VIEWER_ADDRESS_ALIASES /* the viewer's card, background and text box */
#include "game/duel_card_viewer.h"
#include "game/duel_effect_resource_record.h"
#include "game/duel_effect_resource_setup.h"
#include "game/func_800291E0.h"
#include "game/func_80029574.h"
#include "game/card_constants.h"
#include "game/text_box_lifecycle.h"
#include "game/text_box_runtime.h"
#include "game/card_list_text_boxes.h"
#include "game/build_deck_transition_state.h"

extern u8 D_8009B26C; /* main_mode_state.h: the active mode */

#define VIEWER_SLOT 3
#define LIST_PAGE_ROWS 8
/* The viewer's state byte (D_8009B248): 0x40 while its pieces slide and it
 * waits for the card's read, 0x20 once the card has faded in, 0x10 while
 * closing. */
#define VIEWER_WAITING 0x40
#define VIEWER_SHOWN 0x20
#define VIEWER_CLOSING 0x10

/* The next card `step` (1 or -1) along the Build Deck list the viewer came
 * from, the list's cursor moved onto it; 0 at either end of the list. */
static u16 build_deck_next(int step)
{
    BuildDeckTransitionState *state = gBuildDeck_pState;
    CardList *list;
    int rows, row;
    if (!state) return 0;
    list = &state->lists[state->pane_index];
    rows = list->row_count;
    for (row = list->first + list->cursor + step; row >= 0 && row < rows; row += step) {
        int first;
        if (list->entries[row].flags == 0) continue;
        /* The cursor keeps its place on the page where it can. */
        first = row - list->cursor;
        if (first > rows - LIST_PAGE_ROWS) first = rows - LIST_PAGE_ROWS;
        if (first < 0) first = 0;
        list->cursor = (s8)(row - first);
        list->cursor_box->field_30.h.field_32 = list->cursor * 22 + 0x2A;
        if (first != list->first) {
            list->first = list->first_target = (s16)first;
            func_80031E04(list, LIST_PAGE_ROWS);
        }
        return list->entries[row].id;
    }
    return 0;
}

/* The viewer's opening for `id`, its pieces already where they slide to. */
static void show(u16 id)
{
    DuelEffectResourceRecord *record = &D_800EA0E8[VIEWER_SLOT];
    DisplayObject *background = D_8009B240, *card;
    DuelEffectChannel *channel = D_800EB0F8;
    int i;

    func_80029528(VIEWER_SLOT);
    if (D_8009B250) TextBox_Destroy(D_8009B250);
    D_8009B250 = 0;

    DuelEffect_ClearResourceObjectPointers(VIEWER_SLOT);
    record->src_y = 0x100;
    record->src_x = 0;
    record->field_2C = 0;
    record->field_2E = 0xFF;
    gDuel_wViewerCardID = id;
    func_80029164(VIEWER_SLOT, (s16)id);
    card = (DisplayObject *)func_800291E0(VIEWER_SLOT, -1, -1);
    *(s16 *)&card->field_30.h.field_30 = 2;
    card->field_20.b.field_21 = 0x80;
    card->field_30.h.field_32 += gDuel_bCardViewerYOffset;
    card->flags |= DISPLAY_OBJECT_FLAG_CLIP_TEST;
    DisplayObject_SavePosition((DisplayObjectSnapshot *)card);
    card->field_60 = 0;
    DisplayObject_SelectOrderingTable1(card);
    DisplayObject_SetDepthOffset(card, 0x14);
    D_8009B24C = card;

    for (i = 0; i < 3; i++, channel++) {
        DuelEffectChannel *box;
        int kind = 3;
        if (channel->flags_34 & DUEL_EFFECT_CHANNEL_FLAG_ACTIVE) continue;
        gDuel_wSelectedCardID = id;
        if (((gDuel_adwCardStats[(s16)id - 1] >> CARD_STAT_TYPE_SHIFT) & CARD_STAT_TYPE_MASK) >= CARD_TYPE_MAGIC) {
            kind = 4;
        }
        box = TextBox_Create(i, kind, 0x148, 0xE, 0xA8, 0xC0);
        box->field_53 = 1;
        box->field_54 = 0;
        box->field_59 = 0x15;
        D_8009B250 = box;
        func_80039A14((struct DuelEffectChannel *)box);
        TextBox_SetPos(box, *(s16 *)&background->field_30.h.field_30, *(s16 *)&background->field_30.h.field_32);
        break;
    }
    D_8009B248 = (u8)((D_8009B248 | VIEWER_WAITING) & ~(VIEWER_SHOWN | VIEWER_CLOSING));
}

int CardBrowse_Poll(void)
{
    int step = 0;
    u16 id = 0;
    if (!Settings_Get(SET_CARD_BROWSE)) return 0;
    if (gInput_wPad1Repeat & PAD_DIRECTION_DOWN) step = 1;
    else if (gInput_wPad1Repeat & PAD_DIRECTION_UP) step = -1;
    if (!step) return 0;
    if ((D_8009B26C & 0x1F) == MAIN_MODE_BUILD_DECK) id = build_deck_next(step);
    if (!id) return 0;
    SD_SEPlayFull(6);
    show(id);
    return 1;
}
