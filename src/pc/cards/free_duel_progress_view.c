/* View > Free Duel progress: "owned/obtainable" right of the FREE DUEL title
 * for the opponent under the grid cursor, drawn by the host over the picture
 * as the fusion helper is (FreeType, window pixels, any internal
 * resolution). The numbers come from free_duel_progress.c. */
#include "free_duel_progress.h"
#include "fusion_helper.h"
#include "pc/platform/settings.h"
#include "pc/platform/platform.h"
#include "pc/text/overlay_text.h"
#include "game/card_constants.h"
#include "game/main_modes.h"
#include "game/fade.h"
#include "game/file_transfer.h"
#include "overlays/free_duel/free_duel.h"
#include "overlays/free_duel/module_state.h"
#include <stdio.h>

extern unsigned char D_8009B26C; /* main_mode_state.h: the running mode */

/* Main_RunFreeDuelMenu sets 0x40 once it has opened the screen. The screen's
 * own flags: 0x20 while a text box is up (SELECT OPPONENT!, the deck
 * refusal), 0x40 once it is leaving. */
enum { MODE_MASK = 0x1F, MODE_ENTERED = 0x40, SCREEN_DIALOG = 0x20, SCREEN_LEAVING = 0x40 };

static struct { int visible, duelist, owned, obtainable, x, y, w, h; } view;

static void update(void)
{
    int column, row, cell;
    view.visible = 0;
    if (!Settings_Get(SET_FREE_DUEL_PROGRESS)) return;
    if ((D_8009B26C & MODE_MASK) != MAIN_MODE_FREE_DUEL || !(D_8009B26C & MODE_ENTERED)) return;
    /* Main_InitFreeDuelMenu waits for the module to load before FreeDuel_Init
     * builds the grid, and frames are shown meanwhile: until then the
     * module's state is the last screen's. Then the fade in. */
    if ((D_8009B0F4 & FILE_TRANSFER_REQUEST_BLOCKED_MASK) | D_8009B134) return;
    if (gFade_State.flags & FADE_FLAG_ACTIVE) return;
    if (gFreeDuel_bScreenFlags & (SCREEN_DIALOG | SCREEN_LEAVING)) return;
    /* The pending cell the pad moves at once; the cursor glides after it.
     * Its index is the opponent's id (func_80024DC8); 0 is Build Deck. */
    column = gFreeDuel_bTargetColumn;
    row = gFreeDuel_bTargetRow;
    if (column < 0 || column >= FREE_DUEL_GRID_COLUMN_COUNT || row < 0 || row >= FREE_DUEL_GRID_ROW_COUNT) return;
    cell = row * FREE_DUEL_GRID_COLUMN_COUNT + column;
    if (cell < FREE_DUEL_STORY_OPPONENT_FIRST_INDEX || !gFreeDuel_abGridAvailable[cell]) return;
    if (!FreeDuelProgress_Count(cell, &view.owned, &view.obtainable)) return;
    view.duelist = cell;
    view.visible = 1;
}

unsigned FreeDuelProgress_Signature(void)
{
    int x, y, w, h;
    update();
    if (!view.visible) return 0;
    FusionHelper_GetViewport(&x, &y, &w, &h);
    return ((((unsigned)view.duelist * 1031u + (unsigned)view.owned) * 1031u + (unsigned)view.obtainable) * 331u +
            (unsigned)x * 17u + (unsigned)y) * 31u + (unsigned)w * 7u + (unsigned)h + 1u;
}

/* Game picture coordinates (320x240; 2D stays centred when widened) to
 * window pixels, as the fusion helper maps them. */
static int screen_x(int x)
{ return view.x + view.w / 2 + (x - 160) * view.w / (Platform_Widescreen() ? 426 : 320); }
static int screen_y(int y) { return view.y + y * view.h / 240; }

/* The title banner's middle row and the right edge of the text, in picture
 * pixels: over the eye right of the banner, clear of the grid's frame. */
enum { TITLE_MIDDLE = 23, TEXT_RIGHT = 304, TEXT_HEIGHT = 11 };

/* A see-through plate with "12/157" on it, gold once every card is owned. */
void FreeDuelProgress_Draw(MenuCanvas *canvas, int *x, int *y, int *w, int *h)
{
    char text[24];
    int font, pad, width, height, left, top, row, col;
    *x = *y = *w = *h = 0;
    update();
    FusionHelper_GetViewport(&view.x, &view.y, &view.w, &view.h);
    if (!view.visible || view.w <= 0 || view.h <= 0) return;
    snprintf(text, sizeof(text), "%d/%d", view.owned, view.obtainable);
    font = screen_y(TEXT_HEIGHT) - screen_y(0);
    if (font < 8) font = 8;
    pad = font / 3 > 1 ? font / 3 : 1;
    height = font + 2 * pad;
    width = pad * 2 + OverlayText_Width(text, font);
    left = screen_x(TEXT_RIGHT) - width;
    top = screen_y(TITLE_MIDDLE) - height / 2;
    if (left < 0) left = 0;
    if (width > canvas->width - left) width = canvas->width - left;
    if (width <= 0 || height <= 0 || top < 0 || top + height > canvas->height) return;
    for (row = top; row < top + height; row++)
        for (col = left; col < left + width; col++) OverlayText_Blend(canvas, col, row, 0x0b0f18u, 150);
    OverlayText_Draw(canvas, left + pad, top + height / 2, left + width, text, font,
                     view.obtainable && view.owned == view.obtainable ? 0xf2c85au : 0xe4ecdcu);
    *x = left; *y = top; *w = width; *h = height;
}
