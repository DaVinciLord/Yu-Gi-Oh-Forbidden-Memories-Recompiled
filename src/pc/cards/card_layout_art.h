#ifndef MEMORIES_PC_CARDS_CARD_LAYOUT_ART_H
#define MEMORIES_PC_CARDS_CARD_LAYOUT_ART_H
/* The unified card frame (card_layout.h's CardLayout_Get(CARD_LAYOUT_FRAME)
 * w/h) -- a layout mod's own PNG, no disc counterpart and no counterpart
 * compiled into the port either (card_layout.h's CardLayout_FramePath),
 * decoded once into a SoftGpu_Bank the same way src/pc/cards/star_icons.c
 * and src/pc/text/glyphs.c already do for theirs, then read back as an
 * ordinary tpage/u/v/clut cell. */

/* 1 on success (`*tpage`/`*u`/`*v`/`*clut` filled, its own stored w/h in
 * `*w`/`*h`), 0 when no mod gives a frame path, or it could not be decoded
 * or the bank could not be allocated -- the caller (func_80028B08.c) simply
 * doesn't draw it then, purely decorative. */
int CardLayoutArt_FrameCell(int *tpage, int *u, int *v, int *clut, int *w, int *h);

#endif
