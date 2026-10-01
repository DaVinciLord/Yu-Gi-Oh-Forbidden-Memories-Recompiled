/* Test save remapping independently of the retail data/image renderer. */
#include "pc/compat/fs.h"
#include "../../src/pc/cards/cards.c"
#include "scratch.h"
#include <assert.h>
#include <unistd.h>
int gCard_nCount = 724, gCard_nExtraOwner;
unsigned short gCard_awBaseId[CARD_TABLE_ID_END], gDuel_awPlayerDeck[1024];
unsigned char gCard_abExtraChest[CARD_TABLE_ID_END], gCard_abExtraSeen[(CARD_TABLE_ID_END + 7) / 8];
unsigned char gCard_abPairChest[2][CARD_TABLE_ID_END], gCard_abPairPending[2][CARD_TABLE_ID_END];
int Log_Wanted(LogChannel channel)
{
    (void)channel;
    return 0;
}
void Log_Printf(LogChannel channel, const char *format, ...)
{
    (void)channel;
    (void)format;
}
/* Card text: letters stand for themselves here, so the codes show. */
uint32_t Glyphs_NextCharacter(const char **text) { return (unsigned char)*(*text)++; }
int Glyphs_Code(uint32_t character) { return character >= 'A' && character <= 'z' ? (int)character : -1; }
void Mods_Note(const char *id, const char *format, ...)
{
    (void)id;
    (void)format;
}
static void card_text_codes(void)
{
    /* As the FM Editor shows a ROM hack's text: an icon is one letter of
     * the line, a colour none, and both are the game's own bytes. */
    static const unsigned char icon[] = {'a', 0, 0xF8, 0x0B, 0x04, 0, 'm', 0xFF};
    static const unsigned char colour[] = {0xF8, 0x0A, 0x02, 'R', 'e', 'd', 0xFE, 'G', 0xF1, 0x23, 0xFF};
    unsigned char *text = encode_description("t", "a {f8 0B 04} m", 1);
    assert(!memcmp(text, icon, sizeof(icon)));
    free(text);
    text = encode_description("t", "{f8 0A 02}Red\nG{g 123}", 1);
    assert(!memcmp(text, colour, sizeof(colour)));
    free(text);
    /* Twenty letters with the icon, so "c" still fits; an unknown code is
     * its letters (and the braces, which this stub has no glyph for). */
    text = encode_description("t", "aaaaaaaaaaaaaaaa {f8 0B 04} c", 1);
    assert(text[16] == 0 && text[17] == 0xF8 && text[20] == 0 && text[21] == 'c' && text[22] == 0xFF);
    free(text);
    text = encode_description("t", "{f8 99 04}", 1);
    assert(text[0] == 'f' && text[1] == 0);   /* "f", a space, and the rest has no glyph */
    free(text);
}
int main(void)
{
    card_text_codes();
    char directory[SCRATCH_MAX];
    unsigned char state[2048] = {0};
    int code = 123;
    unsigned sequence = 1;
    assert(scratch_dir(directory, sizeof(directory), "memories-card-identities"));
    setenv("MEMORIES_USER_DIR", directory, 1);
    memcpy(state + SAVE_DUELIST_CODE, &code, 4);
    memcpy(state + SAVE_SEQUENCE, &sequence, 4);
    identities[723] = "alpha:dragon:1";
    identities[724] = "beta:mage:1";
    gCard_awBaseId[723] = 1;
    gCard_awBaseId[724] = 2;
    gCard_abExtraChest[723] = 3;
    gCard_abExtraChest[724] = 5;
    gCard_abExtraSeen[723 >> 3] |= 1u << (723 & 7);
    ((unsigned short *)state)[0] = 723;
    Cards_SaveWritten(state, 1);
    identities[723] = "beta:mage:1";
    identities[724] = "alpha:dragon:1";
    gCard_awBaseId[723] = 2;
    gCard_awBaseId[724] = 1;
    Cards_SaveLoaded(state);
    assert(gCard_abExtraChest[724] == 3 && gCard_abExtraChest[723] == 5);
    assert(((unsigned short *)state)[0] == 724);
    assert((gCard_abExtraSeen[724 >> 3] >> (724 & 7)) & 1);
    /* Temporarily remove alpha, save beta, then restore alpha: ownership survives. */
    gCard_nCount = 723;
    identities[724] = NULL;
    ((unsigned short *)state)[0] = 723;
    Cards_SaveLoaded(state);
    assert(((unsigned short *)state)[0] == 1);
    Cards_SaveWritten(state, 2);
    gCard_nCount = 724;
    identities[724] = "alpha:dragon:1";
    sequence = 2;
    memcpy(state + SAVE_SEQUENCE, &sequence, 4);
    Cards_SaveLoaded(state);
    assert(gCard_abExtraChest[724] == 3 && gCard_abExtraChest[723] == 5);
    /* Ambiguous legacy IDs are preserved, never assigned to a new card. */
    char path[1024], backup[1040];
    assert(!sidecar_path(path, sizeof(path), code));
    FILE *file = fopen(path, "w");
    assert(file);
    fputs("save 2\nchest 723 9\ndeck 0 723 1\nend\n", file);
    fclose(file);
    ((unsigned short *)state)[0] = 723;
    Cards_SaveLoaded(state);
    assert(!gCard_abExtraChest[723] && ((unsigned short *)state)[0] == 1);
    /* New progress is still saved beside the unmigrated legacy lines. */
    gCard_abExtraChest[724] = 4;
    Cards_SaveWritten(state, 3);
    file = fopen(path, "r");
    char text[1024] = {0};
    assert(file);
    fread(text, 1, sizeof(text) - 1, file);
    fclose(file);
    assert(strstr(text, "chest 723 9"));
    assert(strstr(text, "chest2 alpha:dragon:1 4"));
    gCard_abExtraChest[724] = 0;
    setenv("MEMORIES_MIGRATE_CARD_IDS", "1", 1);
    Cards_SaveLoaded(state);
    assert(gCard_abExtraChest[723] == 9);
    Cards_SaveWritten(state, 3);
    snprintf(backup, sizeof(backup), "%s.legacy", path);
    file = fopen(backup, "r");
    assert(file);
    fclose(file);
    unsetenv("MEMORIES_MIGRATE_CARD_IDS");
    sequence = 3;
    memcpy(state + SAVE_SEQUENCE, &sequence, 4);
    Cards_SaveLoaded(state);
    assert(gCard_abExtraChest[723] == 9);

    /* Two slots of one duelist at the same sequence (saved twice, then played
     * on from the older): each reads back its own cards, and a section a
     * slot still holds outlives any number of later saves. */
    {
        unsigned live[2] = {0xA1, 0xB2};
        code = 456;
        memcpy(state + SAVE_DUELIST_CODE, &code, 4);
        sequence = 10;
        memcpy(state + SAVE_SEQUENCE, &sequence, 4);
        memset(gCard_abExtraChest, 0, sizeof(gCard_abExtraChest));
        gCard_abExtraChest[724] = 1;
        Cards_SetSlotTokens(0xA1, live, 2);
        Cards_SaveWritten(state, 10);
        gCard_abExtraChest[724] = 2;
        Cards_SetSlotTokens(0xB2, live, 2);
        Cards_SaveWritten(state, 10);
        for (unsigned later = 11; later < 30; later++) {
            unsigned token = 0x100 + later;
            gCard_abExtraChest[724] = 7;
            Cards_SetSlotTokens(token, live, 2);
            Cards_SaveWritten(state, later);
        }
        Cards_SetSlotTokens(0xA1, live, 2);
        Cards_SaveLoaded(state);
        assert(gCard_abExtraChest[724] == 1);
        Cards_SetSlotTokens(0xB2, live, 2);
        Cards_SaveLoaded(state);
        assert(gCard_abExtraChest[724] == 2);
    }
    return 0;
}
