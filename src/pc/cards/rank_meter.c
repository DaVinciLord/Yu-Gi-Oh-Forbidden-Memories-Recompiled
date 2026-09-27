/* View > Duel rank: the rank the duel is heading for, drawn by the host over
 * the picture as the fusion helper is (FreeType, window pixels, any
 * internal resolution). The numbers come from rank.c. */
#define D_8009B360_AS_SIDE_ARRAY
#include "rank_meter.h"
#include "rank.h"
#include "fusion_helper.h"
#include "pc/platform/settings.h"
#include "pc/platform/platform.h"
#include "pc/text/overlay_text.h"
#include "game/duel_scene_state.h"
#include "game/duel_effect.h"
#include "game/duel_check_quit_input.h"
#include "game/duel_action_lock.h"
#include "game/duel_result_display.h"
#include "game/ai_opponent_data.h"
#include "game/duel_side_state.h"
#include "game/duel_init_scene.h"
#include "game/display_object.h"
#include <stdio.h>
#include <string.h>

extern unsigned char D_8009B26C, D_8009B26E;

/* Scene phases (gDuel_apfnSceneStateHandler) from the first draw to the turn
 * switch; 12 on are the outro and the result screens, which show the rank.
 * DuelScene_UpdateCardUse shows the card being used across the screen. */
enum { PHASE_FIRST_DRAW = 2, PHASE_CARD_USE = 6, PHASE_LAST_PLAY = 11, PHASE_RESULTS = 13 };
/* An LP win (DuelScene_UpdateFieldActions writes 2 to the winner's record);
 * until the duel ends, the rank is shown as if it ended that way. */
enum { ADJUST_LP_WIN = 2 };

static struct { int visible, level, score, tec, tier, box_x, box_y, x, y, w, h; } view;
static int checked;

static int cpu_duel(void)
{
    return (D_8009B26C & 31) == 3 && D_8009B26E == 0x81 && D_8009B360[0] < 0 && gDuel_bOpponentID >= 0;
}

/* Once a duel, as the result screen opens: the same sum over the player's
 * record with the adjustment the duel ended with against the game's own. */
static void check_result(void)
{
    const DuelResultDisplayState *result = D_8009B1E8;
    int ours, tec, tier;
    if (checked || !result) return;
    checked = 1;
    ours = Rank_Score(&D_800E9FF0[0], D_800E9FF0[0].rank.result_adjustment);
    Rank_Grade(ours, &tec, &tier);
    fprintf(stderr, "memories-pc: duel rank: ours %d, the game's %d (winner side %d, %s)\n", ours,
            (int)result->side_scores[0], gDuel_bWinnerSide,
            gDuel_bWinnerSide ? "no rank" :
            tec == result->is_tec_rank && tier == result->rank_tier ? "same rank" : "RANK DIFFERS");
}

static void update(void)
{
    int level = Settings_Get(SET_RANK_METER), phase, adjustment, score;
    view.visible = 0;
    if (!level) return;
    phase = gDuel_wSceneStateFlags & DUEL_SCENE_PHASE_MASK;
    if (!cpu_duel()) return;
    if (phase == PHASE_RESULTS && (gDuel_wSceneStateFlags & DUEL_SCENE_FLAG_INITIALIZED)) check_result();
    if (phase < PHASE_FIRST_DRAW || phase > PHASE_LAST_PLAY) return;
    checked = 0;
    if (phase == PHASE_CARD_USE) return;
    /* The card viewer, a card's effect being shown, the quit dialog. */
    if (gDuel_bEffectState || gDuel_wCardEffectFlags || gDuel_bQuitDialogState || !D_8009B214) return;
    /* The plate goes with the FIELD box (Duel_InitScene's sprite), which
     * slides off the left edge for battles, the opponent's turn and the
     * field views; while it is not all on screen the plate is not shown. */
    view.box_x = (s16)D_8009B214->field_30.h.field_30;
    view.box_y = (s16)D_8009B214->field_30.h.field_32;
    if (view.box_x < 0 || view.box_y < 0) return;
    adjustment = D_800E9FF0[0].rank.result_adjustment;
    score = Rank_Score(&D_800E9FF0[0], adjustment ? adjustment : ADJUST_LP_WIN);
    if (score == RANK_SCORE_UNKNOWN) return;
    view.visible = 1;
    view.level = level;
    view.score = score;
    Rank_Grade(score, &view.tec, &view.tier);
}

unsigned RankMeter_Signature(void)
{
    int x, y, w, h;
    update();
    if (!view.visible) return 0;
    FusionHelper_GetViewport(&x, &y, &w, &h);
    return (((((unsigned)view.score * 3u + (unsigned)view.level) * 331u + (unsigned)view.box_x) * 241u +
             (unsigned)view.box_y) * 31u + (unsigned)x * 17u + (unsigned)y) * 31u + (unsigned)w * 7u + (unsigned)h + 1u;
}

/* Game picture coordinates (320x240; 2D stays centred when widened) to
 * window pixels, as the fusion helper maps them. */
static int screen_x(int x)
{ return view.x + view.w / 2 + (x - 160) * view.w / (Platform_Widescreen() ? 426 : 320); }
static int screen_y(int y) { return view.y + y * view.h / 240; }

/* The FIELD box sprite from its position: its right edge, and its height
 * (12,24 at rest; the frame spans 13-67 and 24-48). */
enum { FIELD_BOX_RIGHT = 55, FIELD_BOX_HEIGHT = 24, GAP = 5 };

/* A see-through plate right of the FIELD box, as tall as it: "S-POW",
 * orange for POW and blue for TEC when the rank picks that pool (S and A),
 * grey for B, C and D; the score after it in grey at level 2. */
void RankMeter_Draw(MenuCanvas *canvas, int *x, int *y, int *w, int *h)
{
    static const char letters[] = "DCBAS";
    char rank[8], score[8] = "";
    int font, small, pad, width, height, row, col, left, top;
    uint32_t colour;
    *x = *y = *w = *h = 0;
    update();
    FusionHelper_GetViewport(&view.x, &view.y, &view.w, &view.h);
    if (!view.visible || view.w <= 0 || view.h <= 0) return;
    snprintf(rank, sizeof(rank), "%c-%s", letters[view.tier], view.tec ? "TEC" : "POW");
    if (view.level == 2) snprintf(score, sizeof(score), "%d", view.score < 0 ? 0 : view.score > 99 ? 99 : view.score);
    height = screen_y(view.box_y + FIELD_BOX_HEIGHT) - screen_y(view.box_y);
    font = height * 3 / 5 < 8 ? 8 : height * 3 / 5;
    small = font * 3 / 4 < 8 ? 8 : font * 3 / 4;
    pad = font / 2;
    width = pad + OverlayText_Width(rank, font) + pad;
    if (score[0]) width += OverlayText_Width(score, small) + pad;
    left = screen_x(view.box_x + FIELD_BOX_RIGHT + GAP);
    top = screen_y(view.box_y);
    if (width > view.x + view.w - left) width = view.x + view.w - left;
    if (width <= 0 || height <= 0) return;
    for (row = top; row < top + height; row++)
        for (col = left; col < left + width; col++) OverlayText_Blend(canvas, col, row, 0x0b0f18u, 150);
    colour = view.tier < 3 ? 0xc4ccd2u : view.tec ? 0x74c6f2u : 0xf2a65au;
    OverlayText_Draw(canvas, left + pad, top + height / 2, left + width, rank, font, colour);
    if (score[0])
        OverlayText_Draw(canvas, left + width - pad - OverlayText_Width(score, small), top + height / 2,
                         left + width, score, small, 0xc4ccd2u);
    *x = left; *y = top; *w = width; *h = height;
    if (*x < 0) { *w += *x; *x = 0; }
    if (*y < 0) { *h += *y; *y = 0; }
    if (*w > canvas->width - *x) *w = canvas->width - *x;
    if (*h > canvas->height - *y) *h = canvas->height - *y;
}
