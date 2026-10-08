/* The mods' "ui" key as read (src/pc/platform/ui_config.c): real manifests
 * through the real JSON reader. What is checked without a screen: the
 * retail defaults, each key landing where pc/cards/duel_ui.c looks for it, a
 * later mod winning key by key, what each element takes (the sliding ones
 * up and down only, and no larger than leaves the screen with the game's),
 * and the notes a mistake raises. */
#include "../../src/pc/platform/ui_config.c"
#include <stdarg.h>

#define CHECK(condition)                                                        \
    do {                                                                        \
        if (!(condition)) {                                                     \
            fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #condition);     \
            exit(1);                                                            \
        }                                                                       \
    } while (0)

static int notes;
static char note[512];
void Mods_Note(const char *id, const char *format, ...)
{
    va_list arguments;
    (void)id;
    notes++;
    va_start(arguments, format);
    vsnprintf(note, sizeof(note), format, arguments);
    va_end(arguments);
}

/* paths.c's rule, as far as these tests need it. */
int Paths_Contained(const char *relative)
{
    return relative && *relative && *relative != '/' && !strstr(relative, "..") && !strchr(relative, '\\');
}

/* UiConfig_Load's mod list: the tests read manifests themselves. */
int Mods_LoadedCount(void) { return 0; }
int Mods_Loaded(int index) { (void)index; return 0; }
int Mods_Active(int mod) { (void)mod; return 0; }
const char *Mods_Id(int mod) { (void)mod; return "test"; }
const char *Mods_Directory(int mod) { (void)mod; return "/mods/test"; }
const JsonValue *Mods_Manifest(int mod) { (void)mod; return NULL; }

static JsonDocument *documents[8];
static int document_count;

static void add_as(const char *mod, const char *text)
{
    char error[256];
    JsonDocument *document = Json_Parse(text, error, sizeof(error));
    if (!document) fprintf(stderr, "%s\n", error);
    CHECK(document != NULL);
    CHECK(document_count < 8);
    documents[document_count++] = document;
    UiConfig_Read(mod, "/mods/test", Json_Root(document));
}

static const UiConfig *one(const char *text)
{
    while (document_count) Json_Free(documents[--document_count]);
    UiConfig_Reset();
    notes = 0;
    note[0] = 0;
    add_as("test", text);
    return UiConfig_Get();
}

static void retail(void)
{
    const UiConfig *config = one("{\"id\": \"x\"}");
    int i;
    CHECK(notes == 0 && !config->any);
    for (i = 0; i < UI_ELEMENTS; i++) {
        const UiElement *e = &config->element[i];
        CHECK(!e->set && !e->x && !e->y && e->scale == 100 && e->tint == 0xFFFFFF && e->digits == 0xFFFFFF);
        CHECK(!e->hidden && !e->image.file[0] && !e->label[0]);
    }
}

static void keys(void)
{
    const UiConfig *config = one(
        "{\"ui\": {\"duel\": {"
        " \"lp_opponent\": {\"y\": 4, \"scale\": 150, \"tint\": \"#FF8080\", \"digits\": \"FFE040\","
        "                   \"label\": \"RIVAL\"},"
        " \"lp_player\": {\"image\": \"art/lp.png\", \"width\": 80, \"height\": 24, \"hide\": false},"
        " \"field\": {\"y\": 90, \"tint\": 8438015},"
        " \"card_bar\": {\"tint\": \"#C0C0FF\", \"hide\": true},"
        " \"hand_cursor\": {\"scale\": 200, \"x\": 12}, \"field_cursor\": {\"y\": -3, \"x\": -300}}}}");
    const UiElement *e = config->element;
    CHECK(notes == 0 && config->any);
    CHECK(e[UI_LP_OPPONENT].set && e[UI_LP_OPPONENT].x == 0 && e[UI_LP_OPPONENT].y == 4);
    CHECK(e[UI_LP_OPPONENT].scale == 150 && e[UI_LP_OPPONENT].tint == 0xFF8080 && e[UI_LP_OPPONENT].digits == 0xFFE040);
    CHECK(!strcmp(e[UI_LP_OPPONENT].label, "RIVAL") && !strcmp(e[UI_LP_OPPONENT].mod, "test"));
    CHECK(!strcmp(e[UI_LP_PLAYER].image.file, "/mods/test/art/lp.png") && e[UI_LP_PLAYER].image.width == 80);
    CHECK(e[UI_LP_PLAYER].image.height == 24 && !e[UI_LP_PLAYER].hidden);
    CHECK(e[UI_FIELD].y == 90 && e[UI_FIELD].tint == 0x80C0FF);
    CHECK(e[UI_CARD_BAR].tint == 0xC0C0FF && e[UI_CARD_BAR].hidden);
    CHECK(e[UI_HAND_CURSOR].scale == 200 && e[UI_HAND_CURSOR].x == 12);
    CHECK(e[UI_FIELD_CURSOR].y == -3 && e[UI_FIELD_CURSOR].x == -300);
}

static void mods_win_key_by_key(void)
{
    const UiConfig *config = one("{\"ui\": {\"duel\": {\"lp_player\": {\"y\": 10, \"tint\": \"#808080\", \"label\": \"ME\"}}}}");
    add_as("later", "{\"ui\": {\"duel\": {\"lp_player\": {\"y\": 20, \"image\": \"a.png\"}}}}");
    CHECK(notes == 0);
    CHECK(config->element[UI_LP_PLAYER].y == 20 && config->element[UI_LP_PLAYER].tint == 0x808080);
    CHECK(!strcmp(config->element[UI_LP_PLAYER].label, "ME") && !strcmp(config->element[UI_LP_PLAYER].mod, "later"));
    /* A later "" puts the game's picture back. */
    add_as("last", "{\"ui\": {\"duel\": {\"lp_player\": {\"image\": \"\"}}}}");
    CHECK(!config->element[UI_LP_PLAYER].image.file[0]);
}

/* What the game slides off the screen sideways keeps its place across. */
static void sliding_ones_move_up_and_down(void)
{
    const UiConfig *config = one("{\"ui\": {\"duel\": {\"lp_opponent\": {\"x\": -236, \"y\": -2},"
                                 " \"lp_player\": {\"x\": -236}, \"field\": {\"x\": 170, \"y\": 40}}}}");
    const UiElement *e = config->element;
    CHECK(notes == 3 && strstr(note, "\"x\" is left out"));
    CHECK(e[UI_LP_OPPONENT].set && e[UI_LP_OPPONENT].x == 0 && e[UI_LP_OPPONENT].y == -2);
    CHECK(e[UI_LP_PLAYER].set && e[UI_LP_PLAYER].x == 0 && e[UI_FIELD].x == 0 && e[UI_FIELD].y == 40);
}

/* No larger than leaves the screen at the nearest place the game slides it
 * to (the panel's middle at 384, the box's at -36): the panel's half with a
 * fifth digit reaches 40 from its middle, a picture of the element's size
 * 32; the box 28. */
static void sliding_ones_leave_the_screen(void)
{
    const UiConfig *config;
    CHECK(UiConfig_ScaleMax(UI_LP_OPPONENT, 0, 0, 0) == 161 && UiConfig_ScaleMax(UI_LP_PLAYER, 1, 0, 0) == 201);
    CHECK(UiConfig_ScaleMax(UI_FIELD, 0, 0, 0) == 130 && UiConfig_ScaleMax(UI_FIELD, 1, 0, 0) == 130);
    CHECK(UiConfig_ScaleMax(UI_HAND_CURSOR, 0, 0, 0) == UI_SCALE_MAX && UiConfig_ScaleMax(UI_CARD_BAR, 0, 0, 0) == 100);
    CHECK(UiConfig_Reach(UI_LP_PLAYER, 161, 0, 0, 0) == 64 && UiConfig_Reach(UI_LP_PLAYER, 162, 0, 0, 0) == 65);
    CHECK(UiConfig_Reach(UI_FIELD, 100, 1, 72, 0) == 36 && UiConfig_Reach(UI_FIELD, 100, 1, 0, 48) == 56);
    config = one("{\"ui\": {\"duel\": {\"lp_player\": {\"scale\": 161}, \"field\": {\"scale\": 130},"
                 " \"hand_cursor\": {\"scale\": 400}}}}");
    CHECK(notes == 0 && config->element[UI_LP_PLAYER].scale == 161 && config->element[UI_FIELD].scale == 130);
    config = one("{\"ui\": {\"duel\": {\"lp_player\": {\"scale\": 300}, \"field\": {\"scale\": 131}}}}");
    CHECK(notes == 2 && strstr(note, "drawn at 130%"));
    CHECK(config->element[UI_LP_PLAYER].scale == 161 && config->element[UI_FIELD].scale == 130);
    /* A picture: its own width; one too wide even at the least size is made
     * narrower, as tall for its width. */
    config = one("{\"ui\": {\"duel\": {\"lp_player\": {\"image\": \"a.png\", \"scale\": 201},"
                 " \"field\": {\"image\": \"b.png\", \"width\": 144, \"height\": 48}}}}");
    CHECK(notes == 1 && config->element[UI_LP_PLAYER].scale == 201);
    CHECK(config->element[UI_FIELD].scale == 50 && config->element[UI_FIELD].image.width == 144);
    config = one("{\"ui\": {\"duel\": {\"field\": {\"image\": \"b.png\", \"width\": 320, \"height\": 80,"
                 " \"scale\": 25}}}}");
    CHECK(notes == 1 && strstr(note, "drawn 290 wide"));
    CHECK(config->element[UI_FIELD].image.width == 290 && config->element[UI_FIELD].image.height == 72);
    /* A later mod's picture is fitted too. */
    one("{\"ui\": {\"duel\": {\"field\": {\"scale\": 130}}}}");
    add_as("later", "{\"ui\": {\"duel\": {\"field\": {\"image\": \"b.png\", \"width\": 72}}}}");
    CHECK(notes == 1 && config->element[UI_FIELD].scale == 101);
}

static void mistakes(void)
{
    const UiConfig *config;
    one("{\"ui\": 3}");
    CHECK(notes == 1);
    one("{\"ui\": {\"duel\": {\"lp\": {}}, \"title\": {}}}");
    CHECK(notes == 2);
    config = one("{\"ui\": {\"duel\": {\"field\": {\"scale\": 900, \"y\": 9999, \"tint\": \"red\", \"spin\": 1}}}}");
    CHECK(notes == 4 && config->element[UI_FIELD].scale == 100 && config->element[UI_FIELD].y == 0);
    CHECK(config->element[UI_FIELD].tint == 0xFFFFFF);
    /* The card bar stays put; only the LP halves have words and digits. */
    config = one("{\"ui\": {\"duel\": {\"card_bar\": {\"x\": 5, \"scale\": 120}, \"field\": {\"label\": \"F\"}}}}");
    CHECK(notes == 3 && config->element[UI_CARD_BAR].x == 0 && config->element[UI_CARD_BAR].scale == 100);
    CHECK(!config->element[UI_FIELD].label[0]);
    config = one("{\"ui\": {\"duel\": {\"lp_player\": {\"label\": \"A NAME FAR TOO LONG\", \"image\": \"../out.png\"}}}}");
    CHECK(notes == 2 && strlen(config->element[UI_LP_PLAYER].label) == UI_LABEL - 1);
    CHECK(!config->element[UI_LP_PLAYER].image.file[0]);
    one("{\"ui\": {\"duel\": {\"lp_player\": 7}}}");
    CHECK(notes == 1);
}

int main(void)
{
    retail();
    keys();
    mods_win_key_by_key();
    sliding_ones_move_up_and_down();
    sliding_ones_leave_the_screen();
    mistakes();
    while (document_count) Json_Free(documents[--document_count]);
    printf("ui config: ok\n");
    return 0;
}
