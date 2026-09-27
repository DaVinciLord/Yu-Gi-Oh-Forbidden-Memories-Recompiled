/* The Free Duel grid's page indicator (page_box.h).
 *
 * Composed in the game's text codes, as cards/drops.c composes its added
 * result pages: 0xF8 begins a command, 0x0A sets the colour, 0x04 the cell
 * size, 0x02 steps along the line and 0x06 moves to a column. The letters are
 * the game's own, through Glyphs_Code.
 *
 * The size command matters as much as the colour: 0x04 with 1 is the 8x8 the
 * card counts are drawn in, which is a sheet of its own and not the font --
 * its entries never take the glyph path, so HD text cannot set them
 * (func_80035E20, hd_text.h). 2 is the letters every other box uses.
 *
 * It sits along the top of the picture, above the FREE DUEL artwork: the
 * button to go back at the left, the page in the middle, the button to go on
 * at the right. All three are one string in one box, since a colour and a
 * column are both runs within a string; the box is on channel 2, and channel
 * 3 is left to Build Deck and the Library, whose stale entries would
 * otherwise be what the screen finds there. The arrow beside each button is
 * the game's own sprite, placed by the screen -- the pair the hand's card
 * cycling puts either side of a card.
 */
#include "page_box.h"
#include "pc/text/glyphs.h"
#include <stdio.h>

/* Columns from the box's own left edge, which is 4 across the picture. A
 * glyph and a space are both eight wide, and the box begins at 4. The arrows
 * are 16 in from each edge, and each button sits right against its own: "L1"
 * at 14 starts 18 across the picture and "R1" at 282 ends 18 from its right
 * edge. "PAGE n/m" is the 64 from 128, which is the middle. */
#define PAGE_COLUMN 124
#define RIGHT_COLUMN 265

/* The hints sit a little in from the edges, leaving room for the red arrow
 * sprite the screen places outside each. */
#define LEFT_COLUMN 31

/* The page reads centred a little left of the arithmetic centre: the six the
 * eye wants, measured against the picture. */
#define PAGE_NUDGE 6

enum { WHITE = 0x00, GOLD = 0x01 };

/* 0xF8 commands: the colour, and the cell size (1 is the counts' 8x8 sheet,
 * 2 the font's letters). duel_effect_command.c: func_800382A8 sets the box's
 * step from the size and marks it, which is why it cannot be guessed at. */
#define COMMAND_COLOUR 0x0A
#define COMMAND_SIZE 0x04
#define SIZE_LETTERS 2

typedef struct {
    u8 *at, *end;
} Out;

static u8 line[FREE_DUEL_PAGE_TEXT_SIZE];
static int showing;

static void put(Out *out, int byte)
{
    if (out->at < out->end) *out->at++ = (u8)byte;
}

static void command(Out *out, int op, int operand)
{
    put(out, 0xF8);
    put(out, op);
    put(out, operand);
}

static void at_x(Out *out, int x)
{
    put(out, 0xF8);
    put(out, 0x06);
    put(out, x & 0xFF);
    put(out, (x >> 8) & 0xFF);
}

/* ASCII in the game's letters; a space is a step, not a glyph. */
static void words(Out *out, const char *text)
{
    for (; *text; text++) {
        if (*text == ' ') command(out, 0x02, 8);
        else {
            const int code = Glyphs_Code((unsigned char)*text);
            if (code < 0) continue;
            if (code >= 0xF0) put(out, 0xF0 + (code >> 8));
            put(out, code & 0xFF);
        }
    }
}

/* How wide a string comes out: a glyph steps the channel's cell width and a
 * space is the eight `words` puts in its place. */
static int text_width(const char *text)
{
    int width = 0;
    for (; *text; text++) width += *text == ' ' ? 8 : FREE_DUEL_PAGE_ADVANCE;
    return width;
}

void FreeDuelPage_Compose(int page, int pages)
{
    Out out = {line, line + sizeof line - 1};
    char text[32];

    /* One page is the screen the disc has; it says nothing. */
    if (pages <= 1) {
        FreeDuelPage_Clear();
        return;
    }
    snprintf(text, sizeof text, "PAGE %d/%d", page + 1, pages);

    /* The font's letters, not the counts' 8x8 sheet: the size is what decides
     * whether the box is drawn from the font at all, and so whether HD text
     * can set it. */
    command(&out, COMMAND_SIZE, SIZE_LETTERS);

    /* Each run begins at a column of its own, so the three are placed without
     * regard to one another's width: the button to go back at the left, the
     * page on the picture's centre, the button to go on at the right. */
    at_x(&out, LEFT_COLUMN);
    command(&out, COMMAND_COLOUR, WHITE);
    words(&out, "L1");

    at_x(&out, (FREE_DUEL_PAGE_BOX_WIDTH - text_width(text)) / 2 - PAGE_NUDGE);
    command(&out, COMMAND_COLOUR, GOLD);
    words(&out, text);

    at_x(&out, RIGHT_COLUMN);
    command(&out, COMMAND_COLOUR, WHITE);
    words(&out, "R1");
    put(&out, 0xFF);
    showing = 1;
}

void FreeDuelPage_Clear(void)
{
    showing = 0;
}

const unsigned char *FreeDuelPage_Text(int id)
{
    return id == FREE_DUEL_PAGE_TEXT_ID && showing ? line : NULL;
}
