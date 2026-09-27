#ifndef MEMORIES_PC_LANGUAGE_H
#define MEMORIES_PC_LANGUAGE_H
/* Game > Language: the game's own European translations, read at startup
 * from the player's PAL disc (notes/translation.md, "The official
 * languages"). Nothing of those discs ships with the port: a language is
 * there when a PAL disc that has it is in `game/languages` or `game/pal`
 * (any .bin or .cue; MEMORIES_LANGUAGES_DIR names another folder), found by
 * what is on it, not by its name. The setting takes effect at the next
 * launch; a mod's translation stands over it, string by string. Where the
 * text comes from is language.c's `sources` table (the discs; a pack the
 * release ships goes there too). */
#include <stddef.h>

enum { LANGUAGE_US, LANGUAGE_EN_EU, LANGUAGE_FR, LANGUAGE_DE, LANGUAGE_IT, LANGUAGE_ES, LANGUAGE_COUNT };

/* The name the menu shows (ASCII: the host menu's font). */
const char *Language_Label(int language);
/* Whether a disc with the language is there (English US always is). The
 * folders are searched once, on the first call. */
int Language_Available(int language);
/* For Text_Build, once: the chosen language's text as a listing the
 * translations' compiler reads (malloc'd; free it), or NULL for English (US)
 * or when the language's disc is not there. The language counts as in use
 * from then on. */
char *Language_Listing(size_t *length);
/* The language this launch's text is in. */
int Language_Current(void);
/* Back to English (US) for this launch: the listing did not compile. */
void Language_Drop(void);

/* TextBox_BuildStep: with a PAL language in use, the pixels to add to the
 * step past glyph `code` in a box with `flags` (0 for the small letters),
 * and in `shift` how far left the letter is drawn (pal_text.h). */
int Language_Advance(unsigned flags, int code, int *shift);

#endif
