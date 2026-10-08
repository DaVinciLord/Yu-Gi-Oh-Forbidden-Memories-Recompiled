/* The mods' "ui" key as read (src/pc/platform/ui_config.c): real manifests
 * through the real JSON reader. What is checked without a screen: the
 * retail defaults, each key landing where pc/cards/duel_ui.c looks for it, a
 * later mod winning key by key, what each element takes, and the notes a
 * mistake raises. */
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
        " \"lp_opponent\": {\"x\": -232, \"y\": 4, \"scale\": 150, \"tint\": \"#FF8080\", \"digits\": \"FFE040\","
        "                   \"label\": \"RIVAL\"},"
        " \"lp_player\": {\"image\": \"art/lp.png\", \"width\": 80, \"height\": 24, \"hide\": false},"
        " \"field\": {\"x\": 240, \"tint\": 8438015},"
        " \"card_bar\": {\"tint\": \"#C0C0FF\", \"hide\": true},"
        " \"hand_cursor\": {\"scale\": 200}, \"field_cursor\": {\"y\": -3}}}}");
    const UiElement *e = config->element;
    CHECK(notes == 0 && config->any);
    CHECK(e[UI_LP_OPPONENT].set && e[UI_LP_OPPONENT].x == -232 && e[UI_LP_OPPONENT].y == 4);
    CHECK(e[UI_LP_OPPONENT].scale == 150 && e[UI_LP_OPPONENT].tint == 0xFF8080 && e[UI_LP_OPPONENT].digits == 0xFFE040);
    CHECK(!strcmp(e[UI_LP_OPPONENT].label, "RIVAL") && !strcmp(e[UI_LP_OPPONENT].mod, "test"));
    CHECK(!strcmp(e[UI_LP_PLAYER].image.file, "/mods/test/art/lp.png") && e[UI_LP_PLAYER].image.width == 80);
    CHECK(e[UI_LP_PLAYER].image.height == 24 && !e[UI_LP_PLAYER].hidden);
    CHECK(e[UI_FIELD].x == 240 && e[UI_FIELD].tint == 0x80C0FF);
    CHECK(e[UI_CARD_BAR].tint == 0xC0C0FF && e[UI_CARD_BAR].hidden);
    CHECK(e[UI_HAND_CURSOR].scale == 200 && e[UI_FIELD_CURSOR].y == -3);
}

static void mods_win_key_by_key(void)
{
    const UiConfig *config = one("{\"ui\": {\"duel\": {\"lp_player\": {\"x\": 10, \"tint\": \"#808080\", \"label\": \"ME\"}}}}");
    add_as("later", "{\"ui\": {\"duel\": {\"lp_player\": {\"x\": 20, \"image\": \"a.png\"}}}}");
    CHECK(notes == 0);
    CHECK(config->element[UI_LP_PLAYER].x == 20 && config->element[UI_LP_PLAYER].tint == 0x808080);
    CHECK(!strcmp(config->element[UI_LP_PLAYER].label, "ME") && !strcmp(config->element[UI_LP_PLAYER].mod, "later"));
    /* A later "" puts the game's picture back. */
    add_as("last", "{\"ui\": {\"duel\": {\"lp_player\": {\"image\": \"\"}}}}");
    CHECK(!config->element[UI_LP_PLAYER].image.file[0]);
}

static void mistakes(void)
{
    const UiConfig *config;
    one("{\"ui\": 3}");
    CHECK(notes == 1);
    one("{\"ui\": {\"duel\": {\"lp\": {}}, \"title\": {}}}");
    CHECK(notes == 2);
    config = one("{\"ui\": {\"duel\": {\"field\": {\"scale\": 900, \"x\": 9999, \"tint\": \"red\", \"spin\": 1}}}}");
    CHECK(notes == 4 && config->element[UI_FIELD].scale == 100 && config->element[UI_FIELD].x == 0);
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
    mistakes();
    while (document_count) Json_Free(documents[--document_count]);
    printf("ui config: ok\n");
    return 0;
}
