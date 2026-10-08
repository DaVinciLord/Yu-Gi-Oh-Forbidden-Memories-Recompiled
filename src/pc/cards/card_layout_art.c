/* See card_layout_art.h. Decode-once-and-cache + store-into-bank, the same
 * shape as star_icons.c's make()/store()/Stars_IconCell() trio -- the
 * difference is colour depth: guardian star icons and glyphs are 4 bits a
 * texel (packed four to a VRAM word, tpage depth field 0), this asset is
 * CardArt_IndexedImage's own 8-bit-a-texel output (up to 255 colours plus
 * transparent 0), packed two to a word, tpage depth field 1 (getTPage's own
 * encoding, psyq/libgpu.h) -- there is no existing 8bpp bank user in this
 * codebase to copy, so that packing and tpage math are derived here from
 * the PS1's own hardware layout, not guessed. */
#include "card_layout_art.h"
#include "card_layout.h"
#include "art.h"
#include "pc/render/soft_gpu.h"
#include "pc/debug/log.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define FRAME_BANK 13   /* 1-12 the 3D Monsters mod, 14 star icons, 15 glyphs, 0 is real VRAM */
/* A layout mod's own frame PNG is stretched to this box regardless of its
 * own size (CardArt_IndexedImage's own rule, as a "title" mod's image is) --
 * not the on-screen draw size (card_layout.h's CardLayout_Get(CARD_LAYOUT_FRAME)
 * w/h, a mod's own choice), but the VRAM texture's own resolution, kept
 * under POLY_GT4's u8 UV coordinate limit (<= 255 either axis) with
 * headroom at Internal 2x/4x: 919x1319 (the feature's first frame art) at
 * the largest divisor keeping the taller axis under 255 gives 5.19, so
 * 177x254 (919/5.19=177.1, 1319/5.19=254.1) is kept as a fixed, generous
 * texel budget for any mod's own frame art, not re-derived per asset.
 *
 * At 919x1319 that is a ~27x reduction in area (the source's own pixels
 * per output texel), a plain box-filter average (CardArt_IndexedImage),
 * then a 255-colour median-cut on top. Both steps are lossless of
 * whatever contrast is actually there (checked two ways: a faithful
 * reimplementation of both steps loses nothing beyond the forced
 * downsample itself, and a bold checkerboard survives the same pipeline
 * perfectly crisp) -- but low-amplitude texture (fine marbling, soft
 * gradients a few pixels wide in the source) is exactly what a ~27x area
 * average erases first, regardless of how good the source looks at full
 * resolution. Draw new frame art bolder than looks necessary up close --
 * tools/pc/hd_recipes/anime_frame_*.png were re-contrasted for exactly
 * this (an HSV-space unsharp mask plus a small marbling layer) after the
 * first version read as a flat colour once actually in the game. */
#define FRAME_W 177
#define FRAME_H 254
#define FRAME_CLUT_Y FRAME_H   /* right after the last pixel row, same bank, no overlap */

static unsigned char made;      /* 0 not yet, 1 made, 2 failed */
static char made_path[1024];    /* the path "made" was decoded from, to notice a different mod's art */

static int make(uint16_t *bank, const char *path)
{
    unsigned char *indices = malloc((size_t)FRAME_W * FRAME_H);
    unsigned short clut[256];
    char why[128];
    int x, y;
    if (!indices) return 0;
    if (!CardArt_IndexedImage(path, FRAME_W, FRAME_H, indices, clut, why, sizeof(why))) {
        LOG(LOG_CARD_LAYOUT, "frame: %s: %s", path, why);
        free(indices);
        return 0;
    }
    for (y = 0; y < FRAME_H; y++) {
        for (x = 0; x < FRAME_W; x += 2) {
            unsigned char lo = indices[y * FRAME_W + x];
            unsigned char hi = x + 1 < FRAME_W ? indices[y * FRAME_W + x + 1] : 0;
            bank[y * SOFT_GPU_WIDTH + x / 2] = (uint16_t)(lo | (hi << 8));
        }
    }
    memcpy(&bank[FRAME_CLUT_Y * SOFT_GPU_WIDTH], clut, 256 * sizeof(uint16_t));
    free(indices);
    return 1;
}

int CardLayoutArt_FrameCell(int *tpage, int *u, int *v, int *clut, int *w, int *h)
{
    uint16_t *bank;
    const char *path = CardLayout_FramePath();
    LOG(LOG_CARD_LAYOUT, "FrameCell: path=\"%s\" made=%d made_path=\"%s\"", path ? path : "(null)", made, made_path);
    if (!path || !*path) { LOG(LOG_CARD_LAYOUT, "FrameCell: no path"); return 0; }
    if (strcmp(path, made_path)) {
        /* A different mod's frame art (or the same mod's art changed under
         * it) than whatever is cached: decode again, same as the first
         * time. Mods rarely change their own shipped art mid-session, so
         * this is a cheap strcmp on the common path (nothing changed) and
         * only actually re-decodes on the rare path (it did). */
        made = 0;
        snprintf(made_path, sizeof(made_path), "%s", path);
    }
    if (made == 2) { LOG(LOG_CARD_LAYOUT, "FrameCell: made==2 (decode failed earlier)"); return 0; }
    if (!(bank = SoftGpu_Bank(FRAME_BANK))) { LOG(LOG_CARD_LAYOUT, "FrameCell: no bank"); return 0; }
    if (!made) made = make(bank, path) ? 1 : 2;
    LOG(LOG_CARD_LAYOUT, "FrameCell: after make(), made=%d", made);
    if (made != 1) return 0;
    *tpage = 0x80 | (FRAME_BANK << 11);   /* getTPage(1, 0, 0, 0) | bank<<11: 8bpp, page (0,0) in the bank */
    *u = 0;
    *v = 0;
    *clut = (FRAME_CLUT_Y << 6) | 0;   /* getClut(0, FRAME_CLUT_Y) */
    *w = FRAME_W;
    *h = FRAME_H;
    LOG(LOG_CARD_LAYOUT, "FrameCell: ok tpage=0x%x clut=0x%x w=%d h=%d", *tpage, *clut, *w, *h);
    return 1;
}
