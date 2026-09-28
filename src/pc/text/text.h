#ifndef MEMORIES_PC_TEXT_H
#define MEMORIES_PC_TEXT_H
#include <stddef.h>
/* Translations: the game's text as mods rewrite it (notes/translation.md).
 *
 * A mod's "text" names listings (tools/pc/text_listing.py writes the
 * retail one) whose strings stand in for the game's, by string id: the
 * dialogue and menus, the card descriptions, and the card, type and
 * duelist names. "font" names font files for letters the game has none of.
 * The game's own code asks Text_Resolve wherever it turns a string id into
 * text, and Text_Retarget wherever a text jumps. */

/* Read and compile every applied mod's text and fonts; once, at startup,
 * before the cards, whose names may use the fonts' letters. */
void Text_Build(void);

/* Once the cards are built: if a translation renames cards, the
 * alphabetical order the Library and Build Deck sort by is the new names'. */
void Text_SortCards(void);

/* The text for string `id`: a mod's, else `retail`. */
const unsigned char *Text_Resolve(int id, const unsigned char *retail);

/* A menu with choices is laid out in one go: func_80039794 steps its text
 * with no frame in between until the last choice line is down. A line
 * wider than the box wraps by itself, and if that row pushes the menu past
 * the box's height first, the text waits for a button that nothing in that
 * loop reads, and the game stops (the console's too; notes/translation.md).
 * Whether the glyph at `x`, `y` of string `id`'s menu, with `lines_left`
 * choice lines still to come, is dropped instead: only where the wrap would
 * stop the game, so a line cut at the box's edge is all that changes. */
int Text_CutsMenuGlyph(int id, int x, int width, int y, int line_height, int height, int lines_left);

/* Whether an applied mod's text rewrites string `id`. */
int Text_Overridden(int id);
/* The port's own strings, which it draws in the game's letters inside the
 * game's picture: ids no retail string has, in the dialogue bank, which a
 * translation may define as it does the game's (notes/translation.md lists
 * them). `%d` stands for a number the port puts in. */
#define TEXT_OWN_FIRST 0xFE00
#define TEXT_OWN_LAST 0xFEFF
enum {
    TEXT_OWN_NEW = 0xFE00,          /* card drops: a card the player had none of */
    TEXT_OWN_MORE_CARD = 0xFE01,    /* card drops: the heading, one card past the first */
    TEXT_OWN_MORE_CARDS = 0xFE02,   /* card drops: the heading, more */
    TEXT_OWN_PAGE_OF = 0xFE03,      /* card drops: which page of how many */
    TEXT_OWN_DECK_SLOTS = 0xFE10,   /* the card shop's added menu entry */
    TEXT_OWN_FREE_DUEL_PAGE = 0xFE11, /* the Free Duel grid's page line */
    TEXT_OWN_OPPONENT = 0xFE40      /* + duelist id (1-39, FE41-FE67): the name in place of COM */
};
/* Ids above the block, which the port composes rather than a translation
 * writing them: FF00-FF57 the name of a duelist a mod added, one each
 * (free_duel/duelists.h), and FFFD-FFFF one line apiece for the Free Duel
 * grid's page, the Password screen's label and the results screen's added
 * pages (free_duel/page_box.h, cards/passwords.h, cards/drops.h). */
/* The compiled text an applied mod gives string `id` (glyph codes and
 * codes, ending in {end}), or NULL: for the port's own strings, and for a
 * retail string the port adds to. */
const unsigned char *Text_Own(int id);
/* The name in place of COM (View > Opponent's name for COM) for a duelist
 * (1-39), in Latin-1: a translation's TEXT_OWN_OPPONENT + id; else its name
 * for the duelist in the names bank (0x8328 + id) when it differs from the
 * English, shortened as Tables_ShortenName does; else the English
 * (Tables_DuelistShortName). NULL for no opponent. */
const char *Text_OpponentName(int duelist);

/* String `id` of a listing the port writes itself (a menu it adds an entry
 * to), compiled as a mod's text is, so that its jumps land (Text_Retarget);
 * it stands in for nothing by itself. NULL if it does not compile. */
const unsigned char *Text_CompileOwn(const char *listing, int id, size_t *size);

/* Where a jump from the stream at `cursor` to `target` lands: into the
 * translation `cursor` is in, by the translation's own targets, or, for the
 * game's own text, `target` in the cursor's 64 KB bank. */
unsigned char *Text_Retarget(unsigned char *cursor, unsigned target);

#endif
