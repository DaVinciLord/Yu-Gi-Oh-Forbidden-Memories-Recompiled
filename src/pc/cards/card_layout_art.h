#ifndef MEMORIES_PC_CARDS_CARD_LAYOUT_ART_H
#define MEMORIES_PC_CARDS_CARD_LAYOUT_ART_H
/* The unified card frame (card_layout.h's CardLayout_Get(CARD_LAYOUT_FRAME)
 * w/h) -- a layout mod's own PNG, no disc counterpart and no counterpart
 * compiled into the port either (card_layout.h's CardLayout_FramePath),
 * decoded once into a SoftGpu_Bank the same way src/pc/cards/star_icons.c
 * and src/pc/text/glyphs.c already do for theirs, then read back as an
 * ordinary tpage/u/v/clut cell. */

/* The frame is drawn as COLS x ROWS abutting tiles, each one quad on its own
 * texture page (card_layout_art.c explains why: a quad reads at most 255
 * texels an axis). This is the one place the grid is set: func_80028B08.c's
 * CardLayout_DrawFrame loops over it, card_layout_art.c's tile layout and
 * its FRAME_W/FRAME_H follow it, and tools/pc/card_frame_window.py's
 * FRAME_TEXELS is the same grid of 177x254 texel tiles (3x3 = 531x762).
 * A row or column left out of the loop is a part of the frame never drawn:
 * with ROWS 2 the bottom third, the stat band, went missing. Changing
 * either number means changing all of those; the tile pages also have room
 * for at most 9 (the digit strip sits on the page after them). */
#define CARD_LAYOUT_FRAME_COLS 3
#define CARD_LAYOUT_FRAME_ROWS 3

/* 1 on success (`*tpage`/`*clut` filled, the tile's own texel w/h in
 * `*w`/`*h`; its texels start at u = v = 0 of that page), 0 when no mod
 * gives a frame path, or it could not be decoded or the bank could not be
 * allocated -- the caller (func_80028B08.c) simply doesn't draw it then,
 * purely decorative. */
int CardLayoutArt_FrameTile(int col, int row, int *tpage, int *clut, int *w, int *h);

/* The layout's ATK/DFD digits (card_layout.h's CardLayout_Digits): one PNG,
 * DIGIT_COLS x DIGIT_ROWS cells of DIGIT_CELL_W x DIGIT_CELL_H texels, digit
 * d in column d % 5, row d / 5, and the same ten greyed (`dim`: the stat
 * the attack screen dims) two rows further down -- 200x192 (4 texels a card
 * unit, one a screen pixel at Internal 4x), which tools/pc/card_digits.py
 * draws from a font. 1 on success (the cell's page, u, v, clut and texel
 * size filled), 0 when the layout gives none or it could not be built: the
 * caller draws the retail digits then. */
#define CARD_LAYOUT_DIGIT_COLS 5
#define CARD_LAYOUT_DIGIT_ROWS 4
#define CARD_LAYOUT_DIGIT_CELL_W 40
#define CARD_LAYOUT_DIGIT_CELL_H 48
int CardLayoutArt_DigitCell(int digit, int dim, int *tpage, int *u, int *v, int *clut, int *w, int *h);

/* Once a frame (cards.c's Cards_Frame): builds, one a call and only now and
 * then, any frame image of the active layout not built yet, so the cost of
 * building one (decoding a 919x1319 PNG and a 255-colour median cut of it,
 * tens to hundreds of milliseconds) is paid off screen, not on the frame a
 * card first draws. */
void CardLayoutArt_Prewarm(void);

#endif
