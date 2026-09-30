#ifndef MEMORIES_PC_PLATFORM_TITLE_CONFIG_H
#define MEMORIES_PC_PLATFORM_TITLE_CONFIG_H
/* The mods' "title" key as read (title_config.c); title_screen.h puts it on
 * the screen. Places are in the game's 320 x 240, colours 0xRRGGBB. */
#include <stdint.h>

struct JsonValue;

/* The three sprites, in "title" order: the logo, the copyright line and
 * PUSH START BUTTON (D_80184558, D_8018455C, D_80184560); the eleven
 * entries in the game's order, the first menu's five then the second's six
 * (main_menu_selection.h). */
enum { TITLE_LAYERS = 3, TITLE_ENTRIES = 11, TITLE_FIRST_MENU = 5, TITLE_MAX_LINES = 16, TITLE_LINE_TEXT = 96,
       TITLE_PATH = 1024 };
enum { TITLE_SHOW_ALWAYS, TITLE_SHOW_PROMPT, TITLE_SHOW_MENU };
enum { TITLE_ALIGN_LEFT, TITLE_ALIGN_CENTRE, TITLE_ALIGN_RIGHT };
/* A hidden entry's y: off the screen, afterimages and all. */
enum { TITLE_PARKED_Y = -400 };
extern const char *const TitleConfig_LayerNames[TITLE_LAYERS];
extern const char *const TitleConfig_EntryNames[TITLE_ENTRIES];

typedef struct {
    char text[TITLE_LINE_TEXT];
    int x, y, align, show, size;
    uint32_t colour;
} TitleLine;

/* A picture of the mod's own in place of the game's: its PNG ("" for none),
 * the mod that named it, and the size it is drawn at in the game's pixels
 * (0: worked out from the PNG). */
typedef struct {
    char file[TITLE_PATH];
    char mod[64];
    int width, height;
} TitleImage;

typedef struct {
    int song;                  /* 0x000 retail */
    int skip_movie, press_start;
    int idle_frames;           /* -1 retail, 0 never */
    int picture, shade, dim;   /* dim 0-0x80, retail 0x80 */
    long colour;               /* under the picture, or -1 */
    uint32_t tint;             /* 0xFFFFFF unchanged */
    TitleImage picture_image;  /* the whole background */
    struct { int x, y, hidden; uint32_t tint; TitleImage image; } layers[TITLE_LAYERS]; /* x, y added to the game's */
    struct { int x, y, set_y, hidden; uint32_t tint; } entries[TITLE_ENTRIES]; /* x added; y the place */
    int spacing, lines;
    TitleLine line[TITLE_MAX_LINES];
} TitleConfig;

/* The retail title, then each applied mod's "title" over it, then the
 * entries laid out (TitleConfig_Finish). */
const TitleConfig *TitleConfig_Load(void);
/* The last one loaded (the retail one before any). */
const TitleConfig *TitleConfig_Get(void);
/* The pieces of TitleConfig_Load, for tests: back to retail; one manifest's
 * "title" over what there is; the entries' places worked out -- a menu
 * with every entry hidden shows them all, and the shown ones stand
 * `spacing` apart around the retail menu's middle unless given a "y".
 * `directory` is the mod's, which its "image" files are named from. */
void TitleConfig_Reset(void);
void TitleConfig_Read(const char *mod, const char *directory, const struct JsonValue *manifest);
void TitleConfig_Finish(void);
#endif
