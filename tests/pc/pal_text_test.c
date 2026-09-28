/* PalText_Listing on a made-up language pack (nothing of the game's): the
 * ids, the PAL codes the US text spells another way, the menus the US text
 * keeps and the placeholder letters. */
#include "pc/text/pal_text.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static unsigned char a[PAL_FILE_A_SIZE], b[PAL_FILE_B_SIZE], c[PAL_FILE_C_SIZE], glyphs[PAL_GLYPH_TABLE_SIZE];
static int failures;

static void put16(unsigned char *at, unsigned value)
{
    at[0] = (unsigned char)value;
    at[1] = (unsigned char)(value >> 8);
}

static void expect(const char *listing, const char *text, int present)
{
    if ((strstr(listing, text) != NULL) != present) {
        fprintf(stderr, "listing %s \"%s\"\n", present ? "lacks" : "has", text);
        failures++;
    }
}

int main(void)
{
    static const unsigned char hi[] = {1, 2, 0xFE, 3, 0xFF};
    static const unsigned char codes[] = {0xF8, 0x1B, 0xFC, 0x48, 0xF8, 0xF8, 0x03, 0x8C, 0xF8, 0x1B, 0x80, 0x00,
                                          0xF8, 0x1C, 0x00, 0xFF};
    static const unsigned char jump[] = {0xFD, 0x00, 0x02};
    static const unsigned char e[] = {3, 0xFF}, i[] = {2, 0xFF}, accent[] = {0x3F, 0xFF}, name[] = {3, 2, 0xFF};
    PalTextPack pack = {a, b, c, glyphs};
    size_t length = 0;
    int problems = -1, shift;
    char *listing;

    /* The glyphs: H, i, E in full-width Shift-JIS; 0x3F a placeholder kanji
     * the Spanish font draws as á. */
    put16(glyphs + 1 * 4, 0x8267);
    put16(glyphs + 2 * 4, 0x8289);
    put16(glyphs + 3 * 4, 0x8264);
    put16(glyphs + 0x3F * 4, 0x89E7);

    put16(a, 0x0F + 3 * PAL_SPANISH);
    put16(a + 4 + 0x01 * 2, 0x1000);
    memcpy(a + 0x1000, hi, sizeof(hi));
    put16(a + 4 + 0x02 * 2, 0x1010);
    memcpy(a + 0x1010, codes, sizeof(codes));
    put16(a + 4 + 0x03 * 2, 0x1030);
    memcpy(a + 0x1030, jump, sizeof(jump));
    memcpy(a + 0x0200, e, sizeof(e));
    put16(a + 4 + 0x10 * 2, 0x1040);   /* the debug menu: the US one stays */
    memcpy(a + 0x1040, e, sizeof(e));
    put16(a + 4 + 0x40 * 2, 0x1050);   /* the result pages: the US ones stay */
    memcpy(a + 0x1050, i, sizeof(i));
    put16(a + 4 + 0x44 * 2, 0x1060);
    memcpy(a + 0x1060, e, sizeof(e));
    put16(a + 4 + 0x100 * 2, 0x1070);  /* card text 1: US D101 is 0x100 + 1 */
    memcpy(a + 0x1070, e, sizeof(e));
    put16(a + 4 + 0x400 * 2, 0x0010);  /* the story's first line, in file B */
    put16(b, 0x10 + 3 * PAL_SPANISH);
    memcpy(b + 0x10, accent, sizeof(accent));
    put16(c, 0x11 + 3 * PAL_SPANISH);
    put16(c + 4 + 1 * 2, 0x5800 + 0x700); /* card 1's name */
    memcpy(c + 0x700, name, sizeof(name));

    listing = PalText_Listing(&pack, PAL_SPANISH, &length, &problems);
    if (!listing) {
        fprintf(stderr, "no listing\n");
        return 1;
    }
    expect(listing, "[0001]\nHi\nE{end}", 1);
    expect(listing, "[0002]\n{call L125A}{call L125A}{f8 03 08 56 1D 80 00}{end}", 1);
    expect(listing, "f8 1C", 0);
    expect(listing, "[0003]\n{jump LF000}", 1);
    expect(listing, "{:LF000}\nE{end}", 1);
    expect(listing, "[0010]", 0);
    expect(listing, "[0040]", 0);
    expect(listing, "[0044]", 0);
    expect(listing, "[D100]\nE{end}", 1);
    expect(listing, "@bank descriptions", 1);
    expect(listing, "[0500]\n\xC3\xA1{end}", 1);
    expect(listing, "[8001]\nEi{end}", 1);
    if (problems) {
        fprintf(stderr, "%d problems\n", problems);
        failures++;
    }
    if (strlen(listing) != length) failures++;
    free(listing);

    /* The PAL font's spacing. */
    if (PalText_Advance(' ', &shift) != -1 || shift) failures++;
    if (PalText_Advance('i', &shift) != -2 || shift != -1) failures++;
    if (PalText_Advance('\'', &shift) != -6 || shift != -3) failures++;
    if (PalText_Advance('m', &shift) != 0 || shift) failures++;
    if (failures) fprintf(stderr, "%d failures\n", failures);
    return failures != 0;
}
