/* The title's pictures of a mod's own (title_images.h). Each PNG is made
 * into the game's kind of texture -- 8 bits a texel through a 256-colour
 * palette, entry 0 clear -- at the size it is drawn, put in VRAM the title
 * leaves unused, and drawn with the game's own polygons in the place of the
 * picture it replaces, so what the game draws over it (the menu, the dimming)
 * still does. At an internal resolution above the console's the PNG itself
 * is drawn instead, at its own resolution, as a mod card's art is
 * (TexturePack_AddMade).
 *
 * The VRAM (a dump at the title, 2026-09-29): (0,256)-(479,495) is the
 * intro movie's 24-bit picture, idle while the title shows and written
 * again by the movie, which is why every opening of the title uploads the
 * pictures again; (768,256)-(1023,511) is empty. The game's own title
 * sheets are at (512,256)-(767,511) and (896,0)-(1023,255). */
#include "title_images.h"
#include "pc/cards/art.h"
#include "pc/mods/mods.h"
#include "pc/render/texture_pack.h"
#include "types.h"
#include "psyq/libgte.h"
#include "psyq/libgpu.h"
#include "psyq/libgs.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* Where each picture's texels and palette go, in 16-bit VRAM words; each
 * starts a texture page (a multiple of 64 across, row 256), and the most it
 * may measure in texels. */
static const struct { int x, y, clut_y, max_w, max_h; } slots[TITLE_IMAGES] = {
    {0, 256, 500, 320, 240},     /* background, in the movie's picture */
    {192, 256, 501, 320, 240},   /* logo, beside it */
    {768, 256, 502, 320, 120},   /* copyright */
    {768, 376, 503, 320, 120},   /* PUSH START BUTTON */
};
enum { CLUT_X = 768, STRIP = 128 };

typedef struct {
    char file[TITLE_PATH];
    int width, height, ready;
    unsigned char *texels;
    unsigned short clut[256];
} Picture;

static Picture pictures[TITLE_IMAGES];

static const TitleImage *image_of(const TitleConfig *config, int which)
{
    return which == TITLE_IMAGE_BACKGROUND ? &config->picture_image : &config->layers[which - 1].image;
}

/* The size a PNG is drawn at: the background fills the screen; a sprite is
 * "width" by "height", one of them and the PNG's shape, or the PNG's own
 * size made smaller by a whole factor until it fits (a 4x drawing of the
 * logo lands at the console's size). Even across: two texels a word. */
static void measure(int which, const TitleImage *image, int png_w, int png_h, int *w, int *h)
{
    int factor = 1;
    if (which == TITLE_IMAGE_BACKGROUND) {
        *w = 320;
        *h = 240;
        return;
    }
    if (image->width && image->height) {
        *w = image->width;
        *h = image->height;
    } else if (image->width) {
        *w = image->width;
        *h = (int)((long)png_h * image->width / png_w);
    } else if (image->height) {
        *h = image->height;
        *w = (int)((long)png_w * image->height / png_h);
    } else {
        while (png_w / factor > slots[which].max_w || png_h / factor > slots[which].max_h) factor++;
        *w = png_w / factor;
        *h = png_h / factor;
    }
    /* Whatever was asked, no bigger than the slot, keeping the shape. */
    if (*w > slots[which].max_w) { *h = (int)((long)*h * slots[which].max_w / *w); *w = slots[which].max_w; }
    if (*h > slots[which].max_h) { *w = (int)((long)*w * slots[which].max_h / *h); *h = slots[which].max_h; }
    *w = (*w + 1) & ~1;
    if (*w < 2) *w = 2;
    if (*h < 1) *h = 1;
}

/* Remade only when the file or its size changes. */
static int make(int which, const TitleImage *image)
{
    Picture *picture = &pictures[which];
    int png_w, png_h, w, h;
    char why[1300];
    if (!CardArt_ImageSize(image->file, &png_w, &png_h)) {
        Mods_Note(image->mod, "title: %s is not a PNG it could read", image->file);
        return 0;
    }
    measure(which, image, png_w, png_h, &w, &h);
    if (picture->texels && picture->width == w && picture->height == h && !strcmp(picture->file, image->file))
        return 1;
    free(picture->texels);
    memset(picture, 0, sizeof(*picture));
    picture->texels = malloc((size_t)w * h);
    if (!picture->texels) return 0;
    if (!CardArt_IndexedImage(image->file, w, h, picture->texels, picture->clut, why, sizeof(why))) {
        Mods_Note(image->mod, "title: %s", why);
        free(picture->texels);
        picture->texels = NULL;
        return 0;
    }
    snprintf(picture->file, sizeof(picture->file), "%s", image->file);
    picture->width = w;
    picture->height = h;
    picture->ready = 1;
    /* Above the console's resolution, the PNG itself: known by these bytes
     * when they are uploaded below. */
    if ((png_w > w || png_h > h) &&
        !TexturePack_AddMadeSeeThrough(picture->texels, w / 2, h, 8, picture->clut, 256, image->file, 0, 0, png_w,
                                       png_h))
        fprintf(stderr, "memories-pc: title: %s is drawn at the console's size only\n", image->file);
    return 1;
}

void TitleImages_Prepare(const TitleConfig *config)
{
    int which;
    for (which = 0; which < TITLE_IMAGES; which++) {
        const TitleImage *image = image_of(config, which);
        pictures[which].ready = image->file[0] && make(which, image);
    }
    /* A picture made just now is known by its bytes only once the packs
     * have sorted it in, which they do between frames: now, before the
     * upload, or the first opening of the title would draw it at the
     * console's size. */
    TexturePack_Service();
    for (which = 0; which < TITLE_IMAGES; which++) {
        Picture *picture = &pictures[which];
        RECT rect;
        if (!picture->ready) continue;
        rect.x = (short)slots[which].x;
        rect.y = (short)slots[which].y;
        rect.w = (short)(picture->width / 2);
        rect.h = (short)picture->height;
        LoadImage(&rect, (u32 *)picture->texels);
        rect.x = CLUT_X;
        rect.y = (short)slots[which].clut_y;
        rect.w = 256;
        rect.h = 1;
        LoadImage(&rect, (u32 *)picture->clut);
    }
}

int TitleImages_Ready(int which, int *width, int *height)
{
    if (which < 0 || which >= TITLE_IMAGES || !pictures[which].ready) return 0;
    if (width) *width = pictures[which].width;
    if (height) *height = pictures[which].height;
    return 1;
}

/* In strips of STRIP texels, each inside one texture page, as the game
 * draws its own background (MainMenu_DrawFrontendBackground). */
void TitleImages_Draw(int which, void *ot, int depth, int x, int y, int r, int g, int b)
{
    const Picture *picture;
    POLY_FT4 strip;
    int left;
    if (!TitleImages_Ready(which, NULL, NULL)) return;
    picture = &pictures[which];
    setPolyFT4(&strip);
    strip.r0 = (u8)r;
    strip.g0 = (u8)g;
    strip.b0 = (u8)b;
    strip.clut = getClut(CLUT_X, slots[which].clut_y);
    for (left = 0; left < picture->width; left += STRIP) {
        int width = picture->width - left < STRIP ? picture->width - left : STRIP;
        int word = slots[which].x + left / 2, page = word & ~63, u = (word - page) * 2;
        int v = slots[which].y - 256;
        strip.tpage = getTPage(1, 0, page, 256);
        strip.x0 = strip.x2 = (short)(x + left);
        strip.x1 = strip.x3 = (short)(x + left + width);
        strip.y0 = strip.y1 = (short)y;
        strip.y2 = strip.y3 = (short)(y + picture->height);
        strip.u0 = strip.u2 = (u8)u;
        /* The far edge is the texel after the last, as a polygon's is not
         * drawn: one to one, no texel twice. A strip starts at most 126
         * texels into its page, so it ends by 254. */
        strip.u1 = strip.u3 = (u8)(u + width);
        strip.v0 = strip.v1 = (u8)v;
        strip.v2 = strip.v3 = (u8)(v + picture->height);
        GsSortPoly(&strip, (GsOT *)ot, (unsigned short)depth);
    }
}
