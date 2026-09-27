#ifndef MEMORIES_PC_TEXT_MENU_CUT_H
#define MEMORIES_PC_TEXT_MENU_CUT_H
/* A menu with choices is laid out in one go: func_80039794 steps its text
 * with no frame in between while flags_34 & 0x1000 is up, until the last
 * choice line is down (Text_TryCompleteChoiceLayout). A menu with more
 * lines than its box has rows under where it starts reaches a new line
 * whose row is past the box before that: Text_NewLine then waits for a
 * button (state 4) that nothing in that loop reads, and the game stops for
 * good, the console's too (notes/translation.md). There, and only there,
 * the port cuts the menu instead: the lines past the box are left out and
 * the choices are the ones in the box. A menu that fits never gets here.
 *
 * Kept by text channel (index_57, the four text boxes); no game headers,
 * so tests/pc/menu_cut_test.c runs it as it is. */

/* A menu starts on `channel` (the choice command). */
void TextMenu_Begin(int channel);
/* A new line of the menu on `channel` wraps past the box: `lines` lines of
 * the menu's `count` are down. 1: its rows are cut and the page wait is
 * skipped; 0: retail's path (the last line, which completes the menu). */
int TextMenu_CutsLine(int channel, int lines, int count);
/* Whether the menu on `channel` is being cut (its letters are left out). */
int TextMenu_Cutting(int channel);
/* The menu on `channel` of string `id` is laid out, with `heading` rows
 * above its choices ({choice} bits 4-5) and `count` choices: the count the
 * player picks from, cut to the choices in the box (at least one). */
int TextMenu_Finish(int id, int channel, int heading, int count);

#endif
