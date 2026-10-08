#ifndef MEMORIES_PC_PLATFORM_UI_CONFIG_H
#define MEMORIES_PC_PLATFORM_UI_CONFIG_H
/* The mods' "ui" key as read (ui_config.c): the duel's pictures -- the two
 * halves of the life-point panel, the FIELD box, the card bar and the
 * cursors -- moved, sized, coloured, hidden or drawn from a PNG of the
 * mod's own; pc/cards/duel_ui.h draws them so. Places are in the game's
 * 320 x 240, colours 0xRRGGBB. Only the reading is here, so
 * tests/pc/ui_config_test.c checks it at the host's own width. */
#include <stdint.h>

struct JsonValue;

/* The elements, in "ui"."duel" order (UiConfig_ElementNames). */
enum {
    UI_LP_OPPONENT,   /* the panel's top half: the opponent's LP, COM, their deck count */
    UI_LP_PLAYER,     /* its bottom half: YOU, the player's LP and deck count */
    UI_FIELD,         /* the FIELD box, the terrain's name */
    UI_CARD_BAR,      /* the strip under the hand: the card's name, ATK/DEF, stars */
    UI_HAND_CURSOR,   /* the red arrow under the hand */
    UI_FIELD_CURSOR,  /* the hand pointing at a zone */
    UI_ELEMENTS
};
enum { UI_PATH = 1024, UI_LABEL = 16, UI_SCALE_MIN = 25, UI_SCALE_MAX = 400 };
extern const char *const UiConfig_ElementNames[UI_ELEMENTS];

typedef struct {
    char file[UI_PATH];         /* the PNG, "" for the game's own picture */
    char mod[64];
    int width, height;          /* its size in the game's pixels, 0 the element's */
} UiImage;

typedef struct {
    int set;                    /* a mod changed it: drawn by duel_ui.c */
    char mod[64];               /* the last mod that did */
    int x, y;                   /* moved by, in the game's pixels */
    int scale;                  /* percent of its size, about its middle (100 as it is) */
    uint32_t tint;              /* its colours multiplied, 0xFFFFFF as they are */
    uint32_t digits;            /* the LP and deck digits' colours (the LP halves) */
    int hidden;
    UiImage image;
    char label[UI_LABEL];       /* the LP halves: words in place of COM or YOU */
} UiElement;

typedef struct {
    UiElement element[UI_ELEMENTS];
    int any;                    /* some element is set */
} UiConfig;

/* Elements the game slides off the screen sideways (the LP halves, the
 * FIELD box) are moved up or down only and sized no more than leaves the
 * screen with the game's (ui_config.c). How far an element drawn at
 * `scale` (its own pieces, or a picture of the mod's own with its "width"
 * and "height", 0 for the element's) reaches from its middle; the most
 * size at which it still leaves the screen (UI_SCALE_MAX for one that does
 * not slide, 100 for one that cannot be sized). */
int UiConfig_Reach(int which, int scale, int picture, int width, int height);
int UiConfig_ScaleMax(int which, int picture, int width, int height);
/* The retail duel, then each applied mod's "ui" over it, a later mod's
 * value winning key by key. */
const UiConfig *UiConfig_Load(void);
const UiConfig *UiConfig_Get(void);
/* The pieces of UiConfig_Load, for tests: back to retail, and one
 * manifest's "ui" over what there is (`directory` names its "image"s). */
void UiConfig_Reset(void);
void UiConfig_Read(const char *mod, const char *directory, const struct JsonValue *manifest);
#endif
