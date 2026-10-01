/* View > Card passwords (passwords.h). */
#include "passwords.h"
#include "cards.h"
#include "stars.h"
#include "tables.h"
#include "pc/platform/settings.h"
#include "pc/debug/log.h"
#include "pc/sdk/disc.h"
#include "pc/text/glyphs.h"
#include "types.h"
#include "ygo_types.h"
#include "game/card_constants.h"
/* The viewer's description box links as D_8009B250 (duel_card_viewer.h). */
#define DUEL_CARD_VIEWER_ADDRESS_ALIASES
#include "game/duel_card_viewer.h"
#include "game/duel_effect.h"
#include "game/duel_effect_card_viewer_state.h"
#include "game/duel_effect_entry_control.h"
#include "game/duel_card.h"
#include "game/file_constants.h"
#include "game/library_runtime.h"
#include "game/main_modes.h"
#include "game/text_box_lifecycle.h"
#include "game/text_box_runtime.h"
#include <stdio.h>
#include <stdint.h>
#include <string.h>

extern unsigned Memories_PresentedFrames(void);

/* --- the disc's table ----------------------------------------------------- */

/* Password_LoadPackageStage reads the Password screen's package from
 * sector FILE_WA_PASSWORD_START_SECTOR of WA_MRG.MRG: 64 sectors of
 * pictures, 4 more, then 3 to 0x801A8000, the table. It has one record per
 * card id from 0, each the card's price in starchips and its password, a
 * nibble per digit, both little-endian words. */
#define TABLE_SECTOR (FILE_WA_PASSWORD_START_SECTOR + 64 + 4)
#define TABLE_SECTORS 3
#define BLUE_EYES_PASSWORD 0x89631139u  /* card 1, the check that the table is where it should be */

static unsigned table[CARD_ID_END];
static unsigned char from_mod[CARD_ID_END];   /* a mod's "passwords" set table[id] */
static int table_state;                  /* 0 unread, 1 read, -1 not there */

static int bcd(unsigned value)
{
    int i;
    for (i = 0; i < 8; i++, value >>= 4) {
        if ((value & 0xF) > 9) return 0;
    }
    return 1;
}

static void read_table(void)
{
    static unsigned char data[TABLE_SECTORS * 2048];
    int start = Memories_DiscFileStart("\\DATA\\WA_MRG.MRG;1"), id, none = 0;
    table_state = -1;
    if (start < 0 || Memories_DiscReadSectors(start + TABLE_SECTOR, TABLE_SECTORS, data) != TABLE_SECTORS) {
        fprintf(stderr, "memories-pc: card passwords: the disc's table cannot be read\n");
        return;
    }
    for (id = 1; id <= CARD_COUNT; id++) {
        const unsigned char *p = data + id * 8 + 4;
        unsigned value = (unsigned)p[0] | (unsigned)p[1] << 8 | (unsigned)p[2] << 16 | (unsigned)p[3] << 24;
        if (value != CARD_PASSWORD_NONE && !bcd(value)) {
            fprintf(stderr, "memories-pc: card passwords: card %d's is not a password (%08x); not shown\n", id, value);
            return;
        }
        none += value == CARD_PASSWORD_NONE;
        table[id] = value;
    }
    table_state = 1;
    fprintf(stderr, "memories-pc: card passwords: read, card 1's is %08X%s, %d cards have none\n", table[1],
            table[1] == BLUE_EYES_PASSWORD ? " (as it should be)" : " (not 89631139: a changed disc)", none);
    /* What the Password screen will have once the mods' "passwords" are
     * written over it (Main_RunPasswordMenu). */
    for (id = 1; id <= CARD_COUNT; id++) {
        const unsigned char *p = data + id * 8;
        unsigned price = (unsigned)p[0] | (unsigned)p[1] << 8 | (unsigned)p[2] << 16 | (unsigned)p[3] << 24;
        unsigned value = table[id];
        Tables_PasswordShop(id, &price, &table[id]);
        from_mod[id] = (unsigned char)(table[id] != value);
    }
}

unsigned Cards_Password(int id)
{
    unsigned own;
    /* A "passwords" entry is what the Password screen takes, so it wins
     * over a replaced card's "password", which is only shown. */
    if (id >= 1 && id <= CARD_COUNT && !table_state) read_table();
    if (id >= 1 && id <= CARD_COUNT && table_state > 0 && from_mod[id]) return table[id];
    if (Cards_OwnPassword(id, &own)) return own;
    if (id < 1 || id > CARD_COUNT) return CARD_PASSWORD_NONE;
    return table_state > 0 ? table[id] : CARD_PASSWORD_NONE;
}

/* --- the line --------------------------------------------------------- */

/* The viewer's text box is laid out by string 3 (a monster) or 4 (the
 * rest): the card's kind, then for a monster GUARDIAN STAR 24 pixels down
 * and the two stars 16 and 32 below that, and in both the card's text from
 * 80 down ({f8 00 40}). The password goes on the second star's row, 24
 * above the card's text, flush right: the box is as wide as the panel
 * (0xA8) and the longest star name (Mercury) ends at about 80. In the
 * other layout that row is the bottom of the empty middle panel. */
#define ROW_ABOVE_TEXT 24
#define DIGITS_X 96
#define LAYOUT_MONSTER 3
#define LAYOUT_OTHER 4

u32 Text_LookupString(s32 bank, s32 id);   /* src/game/text_lookup_string.c */

static unsigned char text[256];
static int text_card = -1;

static int layout_of(int card)
{
    /* As the viewer chose it: a monster a mod gave no star has the other
     * layout, with no GUARDIAN STAR heading (stars.h). */
    return ((gDuel_adwCardStats[card - 1] >> CARD_STAT_TYPE_SHIFT) & CARD_STAT_TYPE_MASK) >= CARD_TYPE_MAGIC ||
                   Stars_NoStarCard(card)
               ? LAYOUT_OTHER
               : LAYOUT_MONSTER;
}

/* The card's layout (a translation's, if it has one) with the password
 * before the card's text. 0 when the card has no password, or the layout
 * has no card text or anything this does not copy (a jump, a choice). */
static int compose(int card)
{
    unsigned password = Cards_Password(card);
    const unsigned char *layout = (const unsigned char *)(uintptr_t)Text_LookupString(0, layout_of(card));
    unsigned char *out = text, *end = text + sizeof(text) - 24;
    int i, placed = 0;
    text_card = -1;
    if (password == CARD_PASSWORD_NONE || !layout) return 0;
    for (; *layout != 0xFF; layout++) {
        if (out >= end) return 0;
        /* A port glyph (glyphs.h: F1-F5 and a low byte, any value) or a
         * command's index is copied with its prefix, so a translation's
         * accented letter is not read as a code or the end of the text. */
        if ((*layout >= 0xF1 && *layout <= 0xF5) || (*layout == 0xF8 && layout[1] != 0x00)) {
            if (layout[1] == 0xFF) break;   /* cut short: end there */
            *out++ = *layout++;
            *out++ = *layout;
            continue;
        }
        if (*layout >= 0xF9 && *layout <= 0xFD) return 0;   /* {if}, {choice}, {call}, {jump} */
        if (!placed && layout[0] == 0xF8 && layout[1] == 0x00 && layout[2] == 0x40) {
            *out++ = 0xF8, *out++ = 0x01, *out++ = (unsigned char)-ROW_ABOVE_TEXT;   /* up to the row */
            *out++ = 0xF8, *out++ = 0x06, *out++ = DIGITS_X & 0xFF, *out++ = DIGITS_X >> 8;
            for (i = 7; i >= 0; i--) {
                int code = Glyphs_Code((uint32_t)('0' + ((password >> (i * 4)) & 0xF)));
                if (code < 0 || code >= 0xF0) return 0;             /* the retail digits are single bytes */
                *out++ = (unsigned char)code;
            }
            *out++ = 0xF8, *out++ = 0x01, *out++ = ROW_ABOVE_TEXT;  /* and back */
            placed = 1;
        }
        *out++ = *layout;
    }
    *out = 0xFF;
    if (!placed) return 0;
    text_card = card;
    return 1;
}

const unsigned char *CardPassword_Text(int id)
{
    return id == CARD_PASSWORD_TEXT_ID && text_card >= 0 ? text : NULL;
}

/* --- the box ------------------------------------------------------------ */

/* The viewer's description box, as the game made it (3 or 4) or as this
 * made it again. */
static int description(const DuelEffectChannel *box)
{
    return box && (box->flags_34 & DUEL_EFFECT_CHANNEL_FLAG_ACTIVE) &&
           (box->field_36 == LAYOUT_MONSTER || box->field_36 == LAYOUT_OTHER || box->field_36 == CARD_PASSWORD_TEXT_ID);
}

/* The box made again in place, on its channel, where it is and as it was
 * set up, from string `id`, built at once as the viewer builds it. Its
 * fields read the card from gDuel_wSelectedCardID. Returns 0 if the text
 * filled the channel's slice of the entries (DuelEffect_AppendEntry leaves
 * the rest out), which would cut the end of the card's text. */
static int remake(DuelEffectChannel *box, int id, int card)
{
    s16 x = box->field_3C, y = box->field_40, w = box->field_3E, h = box->field_42, selected = gDuel_wSelectedCardID;
    u8 delay = box->field_53, step = box->field_54, depth = box->field_59, index = box->index_57;
    DuelEffectChannel *made;
    int used;
    TextBox_Destroy(box);
    gDuel_wSelectedCardID = (s16)card;
    made = TextBox_Create(index, id, x, y, w, h);
    made->field_53 = delay;
    made->field_54 = step;
    made->field_59 = depth;
    func_80039A14(made);
    gDuel_wSelectedCardID = selected;
    used = (int)(made->entry_end_20 - &D_800EB288[made->range_start_5C]);
    LOG(LOG_DUEL_EFFECTS, "card password: card %d's box made from string %04x on channel %d (%d of %d entries) at frame %u",
        card, id, index, used, made->range_count_5E, Memories_PresentedFrames());
    return used < made->range_count_5E - 1;
}

/* Once a frame on either screen, for the description box of the card on
 * view: with the password while `show`, else as the game has it. Nothing
 * is kept here that a loaded state could contradict: which it is, is the
 * box's string id, and the retail layout comes from the card. */
static void sync(DuelEffectChannel *box, int card, int show)
{
    static int unfit = -1;   /* the card whose text and password did not fit together */
    if (!description(box) || !Cards_Valid(card)) return;
    if (box->field_36 == CARD_PASSWORD_TEXT_ID && show && card == text_card) return;
    /* The game's box once all its text is in and still: the Library's
     * types it in, each letter settling over a few frames. */
    if (show &&
        (box->field_36 == CARD_PASSWORD_TEXT_ID ||
         ((box->flags_34 & TEXT_BOX_FLAG_DONE) && !DuelEffect_HasActiveEntry(box))) &&
        card != unfit && compose(card)) {
        if (remake(box, CARD_PASSWORD_TEXT_ID, card)) return;
        unfit = card;
        remake(box, layout_of(card), card);
    } else if (box->field_36 == CARD_PASSWORD_TEXT_ID) {
        remake(box, layout_of(card), card);
    }
}

void CardPassword_UpdateViewer(void)
{
    u8 flags;
    DuelEffect_UpdateCardViewerState();
    flags = gDuel_bEffectHandlerFlags;
    /* Past the opening (the description box is there, D_8009B250), with
     * 0x20 once the face has turned up; 0x40 the slides, 0x10 the closing
     * (DuelEffect_UpdateCardViewerState). */
    if (D_8009B250 && (Settings_Get(SET_CARD_PASSWORDS) || D_8009B250->field_36 == CARD_PASSWORD_TEXT_ID)) {
        sync(D_8009B250, (s16)gDuel_wViewerCardID,
             Settings_Get(SET_CARD_PASSWORDS) && (flags & 0x20) && !(flags & 0x50));
    }
}

void CardPassword_RunLibraryMenu(void)
{
    const u8 *state = D_800EA1E8;
    DuelEffectChannel *box = &D_800EB0F8[0];
    Main_RunLibraryMenu();
    /* The card page (func_8002ACA4), with its description box on channel
     * 0, at rest at step 5: after the card has turned and the grid has
     * gone, until Circle (6, the way back) or the 3D model (4). */
    if ((state[0] & 0xF) == 2 && (Settings_Get(SET_CARD_PASSWORDS) || box->field_36 == CARD_PASSWORD_TEXT_ID)) {
        sync(box, *(const u16 *)(state + 6), Settings_Get(SET_CARD_PASSWORDS) && (state[1] & 0x1F) == 5);
    }
}
