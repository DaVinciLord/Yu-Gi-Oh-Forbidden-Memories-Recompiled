/* The mods' "title" key (title_screen.h). The title is the main-menu
 * module's (src/overlays/main_menu): three sprites from its resource bank --
 * the logo, the "(c) 1996 KAZUKI TAKAHASHI" line and PUSH START BUTTON -- over a tiled picture and a shade
 * drawn by MainMenu_DrawFrontendBackground, and the eleven entries of its
 * two menus, sprites too. Nothing on it is text, and every place and colour
 * is a number in the code, so what a mod changes is applied here to the
 * objects the game made, after it made them and after each update; what
 * they show is a texture pack's (notes/modding.md). */
#include "title_screen.h"
#include "menu.h"
#include "platform.h"
#include "pc/cards/fusion_helper.h"
#include "title_config.h"
#include "title_images.h"
#include "pc/saves/save_menu.h"
#include "pc/saves/deck_menu.h"
#include "pc/guest/state.h"
#include "types.h"
#include "game/display_object.h"
#include "game/display_object_layout.h"
#include "game/display_object_config.h"
#include "game/display_object_helpers.h"
#include "game/fade.h"
#include "game/input.h"
#include "overlays/main_menu/frontend.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

enum { ENTRY_X = 0xA0 };   /* frontend.c: the entries' middle */

/* The middle of each of the game's three pictures, measured on the retail
 * title (2026-09-29): a picture of a mod's own stands there, moved by the
 * layer's x and y. */
static const struct { int x, y; } middles[TITLE_LAYERS] = {{162, 90}, {163, 207}, {160, 185}};
enum { OFF_SCREEN = -400 };

static int open;                /* between TitleScreen_Opened and _Closed */
static int prompt_level = 0x80; /* PRESS START's own pulse, under its tint */
static int idle;

int TitleScreen_Song(void)
{
    return TitleConfig_Load()->song;
}

int TitleScreen_SkipMovie(void)
{
    return TitleConfig_Load()->skip_movie;
}

/* 0xRRGGBB over the game's 128 = unchanged. */
static int scale(uint32_t tint, int shift, int level)
{
    return level * (int)(tint >> shift & 0xFF) / 0xFF;
}

static void paint(DisplayObject *object, uint32_t tint, int level)
{
    u8 *colour = (u8 *)&object->field_0C;
    colour[0] = (u8)scale(tint, 16, level);
    colour[1] = (u8)scale(tint, 8, level);
    colour[2] = (u8)scale(tint, 0, level);
}

static DisplayObject *layer(int i)
{
    return i == 0 ? D_80184558 : i == 1 ? D_8018455C : D_80184560;
}

static DisplayObject *entry(int i)
{
    return (DisplayObject *)gMain_apMenuEntries[i];
}

static int menu_base(int id) { return id < TITLE_FIRST_MENU ? 0 : TITLE_FIRST_MENU; }
static int menu_count(int id) { return id < TITLE_FIRST_MENU ? TITLE_FIRST_MENU : TITLE_ENTRIES - TITLE_FIRST_MENU; }

/* Off a hidden entry the way the pad went (down unless it went up), within
 * its menu, as the game wraps. */
static void skip_hidden(int up)
{
    int id = gMain_bMenuID, from = id, base = menu_base(id), count = menu_count(id), tries = count;
    if (id >= TITLE_ENTRIES || !TitleConfig_Get()->entries[id].hidden) return;
    while (TitleConfig_Get()->entries[id].hidden && tries-- > 0) id = (id - base + count + (up ? -1 : 1)) % count + base;
    if (entry(from)) DisplayObject_SetResourceVariant((DisplayObjectConfig *)entry(from), from << 1 | 1);
    gMain_bMenuID = (u8)id;
    if (entry(id)) DisplayObject_SetResourceVariant((DisplayObjectConfig *)entry(id), id << 1);
}

/* A slide MainMenu_StartFrontendEntryTransition has just begun (16 ticks
 * to go) runs to or from the entry's own x instead of the middle. */
static void shift_slides(void)
{
    int i;
    for (i = 0; i < TITLE_ENTRIES; i++) {
        DisplayObject *object = entry(i);
        int dx = TitleConfig_Get()->entries[i].x;
        if (!object || object->field_60 != 0x10 || !dx) continue;
        if ((s16)object->field_38.h.field_38 == ENTRY_X) object->field_38.h.field_38 += dx;
        if ((s16)object->field_34.h.field_36 == ENTRY_X) {
            object->field_34.h.field_36 += dx;
            object->field_30.h.field_30 = object->field_34.h.field_36;
        }
    }
}

static void tint_entries(void)
{
    int i;
    for (i = 0; i < TITLE_ENTRIES; i++) {
        if (entry(i) && TitleConfig_Get()->entries[i].tint != 0xFFFFFF) paint(entry(i), TitleConfig_Get()->entries[i].tint, 0x80);
    }
}

void TitleScreen_Opened(void)
{
    int i;
    DisplayObject *prompt = D_80184560;
    open = 1;
    idle = 0;
    prompt_level = 0x80;
    TitleImages_Prepare(TitleConfig_Get());
    for (i = 0; i < TITLE_LAYERS; i++) {
        DisplayObject *object = layer(i);
        if (!object) continue;
        /* A picture of the mod's own stands in: the game's goes off the
         * screen but keeps running, PUSH START BUTTON's pulse and all. */
        if (TitleImages_Ready(TITLE_IMAGE_LOGO + i, NULL, NULL)) object->field_30.h.field_32 = OFF_SCREEN;
        object->field_30.h.field_30 += TitleConfig_Get()->layers[i].x;
        object->field_30.h.field_32 += TitleConfig_Get()->layers[i].y;
        if (TitleConfig_Get()->layers[i].hidden && i != 2) object->flags &= ~DISPLAY_OBJECT_FLAG_RENDERABLE;
        if (TitleConfig_Get()->layers[i].tint != 0xFFFFFF) paint(object, TitleConfig_Get()->layers[i].tint, 0x80);
    }
    for (i = 0; i < TITLE_ENTRIES; i++) {
        if (entry(i)) entry(i)->field_30.h.field_32 = TitleConfig_Get()->entries[i].y;
    }
    /* PRESS START hidden or skipped: straight to the menu, as the game opens
     * it on any entry but the first (frontend.c). The entries' slide in is
     * already under way. */
    if (prompt && (!TitleConfig_Get()->press_start || TitleConfig_Get()->layers[2].hidden) && (prompt->flags & DISPLAY_OBJECT_FLAG_RENDERABLE)) {
        prompt->flags &= ~DISPLAY_OBJECT_FLAG_RENDERABLE;
        D_80184597 = 0x80;
    }
    skip_hidden(0);
    shift_slides();
    tint_entries();
}

void TitleScreen_Closed(void)
{
    open = 0;
}

void TitleScreen_State(MemoriesState *state)
{
    MemoriesStateField fields[] = {{&open, sizeof(open)}, {&idle, sizeof(idle)}, {&prompt_level, sizeof(prompt_level)}};
    if (!Memories_StateLoading(state)) {
        Memories_StateChunk(state, "title-screen", fields, 3);
        return;
    }
    /* A state from before the chunk: the title is taken as closed. */
    open = 0;
    idle = 0;
    prompt_level = 0x80;
    if (Memories_StateChunk(state, "title-screen", fields, 3) && open) TitleImages_Prepare(TitleConfig_Load());
}

static int prompt_showing(void)
{
    return open && D_80184560 && (D_80184560->flags & DISPLAY_OBJECT_FLAG_RENDERABLE);
}

int TitleScreen_Update(void)
{
    DisplayObject *prompt = D_80184560;
    int tinted = TitleConfig_Get()->layers[2].tint != 0xFFFFFF, prompting = prompt_showing(), result;
    u8 *colour;
    unsigned short repeat = gInput_wPad1Repeat;

    /* The pulse runs on the game's grey; the tint goes on after. */
    if (prompting && tinted) {
        colour = (u8 *)&prompt->field_0C;
        colour[0] = colour[1] = colour[2] = (u8)prompt_level;
    }
    if (prompting && TitleConfig_Get()->idle_frames >= 0) prompt->field_34.h.field_36 = 0;

    result = MainMenu_UpdateFrontendMenu();
    if (!open || result != -1) return result;

    if (prompt_showing() && tinted) {
        colour = (u8 *)&prompt->field_0C;
        prompt_level = colour[2];
        paint(prompt, TitleConfig_Get()->layers[2].tint, prompt_level);
    }
    if (prompting && prompt_showing() && TitleConfig_Get()->idle_frames > 0 && ++idle >= TitleConfig_Get()->idle_frames) {
        idle = 0;
        return -2;
    }
    if (!prompt_showing()) idle = 0;
    skip_hidden((repeat & PAD_DIRECTION_UP) != 0);
    shift_slides();
    tint_entries();
    return result;
}

void TitleScreen_BackgroundTint(unsigned char *r, unsigned char *g, unsigned char *b)
{
    *r = (unsigned char)scale(TitleConfig_Get()->tint, 16, 128);
    *g = (unsigned char)scale(TitleConfig_Get()->tint, 8, 128);
    *b = (unsigned char)scale(TitleConfig_Get()->tint, 0, 128);
}

int TitleScreen_ShowPicture(void)
{
    return TitleConfig_Get()->picture && !TitleImages_Ready(TITLE_IMAGE_BACKGROUND, NULL, NULL);
}

/* The mod's own pictures, in the background's ordering table: its
 * background where the game's wall goes (4095), the others over the shade
 * (4094) and under the menu's dimming (0), where the game's own are seen. */
void TitleScreen_DrawImages(void *ot)
{
    const TitleConfig *config = TitleConfig_Get();
    unsigned char r, g, b;
    int i, w, h;
    if (config->picture) {
        TitleScreen_BackgroundTint(&r, &g, &b);
        TitleImages_Draw(TITLE_IMAGE_BACKGROUND, ot, 4095, 0, 0, r, g, b);
    }
    for (i = 0; i < TITLE_LAYERS; i++) {
        DisplayObject *object = layer(i);
        const u8 *colour;
        if (!object || !TitleImages_Ready(TITLE_IMAGE_LOGO + i, &w, &h) || config->layers[i].hidden) continue;
        if (!(object->flags & DISPLAY_OBJECT_FLAG_RENDERABLE)) continue;
        /* The game's colour for it: the tint, and PUSH START BUTTON's pulse. */
        colour = (const u8 *)&object->field_0C;
        TitleImages_Draw(TITLE_IMAGE_LOGO + i, ot, 4093, middles[i].x + config->layers[i].x - w / 2,
                         middles[i].y + config->layers[i].y - h / 2, colour[0], colour[1], colour[2]);
    }
}
int TitleScreen_ShowShade(void) { return TitleConfig_Get()->shade; }
long TitleScreen_BackgroundColour(void) { return TitleConfig_Get()->colour; }
int TitleScreen_Dim(int level) { return level * TitleConfig_Get()->dim / 0x80; }

/* --- the text lines ------------------------------------------------------ */

static int line_shown(const TitleLine *line)
{
    if (line->show == TITLE_SHOW_PROMPT) return prompt_showing();
    if (line->show == TITLE_SHOW_MENU) return !prompt_showing();
    return 1;
}

static int visible(void)
{
    return open && TitleConfig_Get()->lines && !(gFade_State.flags & FADE_FLAG_ACTIVE) && !SaveMenu_Active() &&
           !DeckMenu_Active();
}

unsigned TitleScreen_Signature(void)
{
    unsigned signature = 0;
    int x, y, w, h, i;
    if (!visible()) return 0;
    FusionHelper_GetViewport(&x, &y, &w, &h);
    for (i = 0; i < TitleConfig_Get()->lines; i++) signature = signature * 3u + (unsigned)line_shown(&TitleConfig_Get()->line[i]);
    return ((signature * 31u + (unsigned)x) * 31u + (unsigned)y) * 31u + (unsigned)w * 7u + (unsigned)h + 1u;
}

/* Each line at its place in the game's 320 x 240, which grows with the
 * window and stays centred in widescreen, in the port's menu font with a
 * shadow; size 1 is about the game's own 12-pixel letters. */
void TitleScreen_Draw(MenuCanvas *canvas, int *x, int *y, int *w, int *h)
{
    int vx, vy, vw, vh, width_2d, i, x0 = 0, y0 = 0, x1 = 0, y1 = 0;
    *x = *y = *w = *h = 0;
    if (!visible()) return;
    FusionHelper_GetViewport(&vx, &vy, &vw, &vh);
    if (vw <= 0 || vh <= 0) return;
    width_2d = Platform_Widescreen() ? 426 : 320;
    for (i = 0; i < TitleConfig_Get()->lines; i++) {
        const TitleLine *line = &TitleConfig_Get()->line[i];
        int size = vh / 240 * line->size, left, middle, width;
        if (size < line->size) size = line->size;
        if (!line_shown(line)) continue;
        width = Menu_TextWidthScaled(line->text, size);
        left = vx + vw / 2 + (line->x - 160) * vw / width_2d;
        if (line->align == TITLE_ALIGN_CENTRE) left -= width / 2;
        else if (line->align == TITLE_ALIGN_RIGHT) left -= width;
        middle = vy + line->y * vh / 240;
        Menu_DrawTextScaled(canvas, left + size, middle + size, line->text, 0x000000, size);
        Menu_DrawTextScaled(canvas, left, middle, line->text, line->colour, size);
        if (x0 >= x1) { x0 = left; y0 = middle - 10 * size; x1 = left + width + size; y1 = middle + 11 * size; }
        if (left < x0) x0 = left;
        if (middle - 10 * size < y0) y0 = middle - 10 * size;
        if (left + width + size > x1) x1 = left + width + size;
        if (middle + 11 * size > y1) y1 = middle + 11 * size;
    }
    if (x0 < 0) x0 = 0;
    if (y0 < 0) y0 = 0;
    if (x1 > canvas->width) x1 = canvas->width;
    if (y1 > canvas->height) y1 = canvas->height;
    if (x1 <= x0 || y1 <= y0) return;
    *x = x0; *y = y0; *w = x1 - x0; *h = y1 - y0;
}
