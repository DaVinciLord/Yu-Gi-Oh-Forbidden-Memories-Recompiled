/* The mods' "title" key as read (src/pc/platform/title_config.c): real
 * manifests through the real JSON reader. What is checked without a screen:
 * the retail defaults, each key landing where title_screen.c looks for it,
 * a later mod winning field by field while text lines add up, the entries'
 * layout around hidden ones, the pictures' files and sizes, and the notes a
 * mistake raises. */
#include "../../src/pc/platform/title_config.c"
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

/* TitleConfig_Load's mod list: the tests read manifests themselves. */
int Mods_LoadedCount(void) { return 0; }
int Mods_Loaded(int index) { (void)index; return 0; }
int Mods_Active(int mod) { (void)mod; return 0; }
const char *Mods_Id(int mod) { (void)mod; return "test"; }
const char *Mods_Directory(int mod) { (void)mod; return "/mods/test"; }
const JsonValue *Mods_Manifest(int mod) { (void)mod; return NULL; }

static JsonDocument *documents[8];
static int document_count;

static void add(const char *text)
{
    char error[256];
    JsonDocument *document = Json_Parse(text, error, sizeof(error));
    if (!document) fprintf(stderr, "%s\n", error);
    CHECK(document != NULL);
    CHECK(document_count < 8);
    documents[document_count++] = document;
    TitleConfig_Read("test", "/mods/test", Json_Root(document));
}

static const TitleConfig *one(const char *text)
{
    while (document_count) Json_Free(documents[--document_count]);
    TitleConfig_Reset();
    notes = 0;
    note[0] = 0;
    add(text);
    TitleConfig_Finish();
    return TitleConfig_Get();
}

static void retail(void)
{
    const TitleConfig *config = one("{\"id\": \"x\"}");
    int i;
    CHECK(notes == 0);
    CHECK(config->song == 0 && !config->skip_movie && config->press_start && config->idle_frames == -1);
    CHECK(config->picture && config->shade && config->dim == 0x80 && config->colour == -1);
    CHECK(config->tint == 0xFFFFFF && config->lines == 0);
    for (i = 0; i < TITLE_LAYERS; i++) CHECK(!config->layers[i].hidden && config->layers[i].tint == 0xFFFFFF);
    /* frontend.c's own places: 50 + 32i, then 42 + 32(i - 5). */
    for (i = 0; i < TITLE_ENTRIES; i++) {
        CHECK(!config->entries[i].hidden && config->entries[i].x == 0);
        CHECK(config->entries[i].y == (i < 5 ? 50 + i * 32 : 42 + (i - 5) * 32));
    }
}

static void keys(void)
{
    const TitleConfig *config = one(
        "{\"title\": {\"music\": \"0x010\", \"skip_intro\": true, \"press_start\": false, \"idle_seconds\": 3,"
        " \"background\": {\"picture\": false, \"shade\": false, \"tint\": \"#9070FF\", \"color\": \"102040\","
        "                  \"dim\": 64},"
        " \"logo\": {\"x\": -10, \"y\": 4}, \"copyright\": {\"hide\": true}, \"prompt\": {\"tint\": 16769088},"
        " \"entries\": {\"options\": {\"x\": 80, \"tint\": \"#FF8080\"}, \"9\": {\"y\": 7}},"
        " \"text\": [{\"text\": \"v1\", \"x\": 316, \"y\": 232, \"align\": \"right\", \"color\": \"#FFD000\","
        "            \"size\": 2, \"show\": \"menu\"}, {\"text\": \"hi\"}]}}");
    CHECK(notes == 0);
    CHECK(config->song == 0x10 && config->skip_movie && !config->press_start && config->idle_frames == 180);
    CHECK(!config->picture && !config->shade && config->tint == 0x9070FF && config->colour == 0x102040);
    CHECK(config->dim == 64);
    CHECK(config->layers[0].x == -10 && config->layers[0].y == 4 && config->layers[1].hidden);
    CHECK(config->layers[2].tint == 0xFFE040);
    CHECK(config->entries[4].x == 80 && config->entries[4].tint == 0xFF8080);
    CHECK(config->entries[9].set_y && config->entries[9].y == 7);
    CHECK(config->lines == 2);
    CHECK(!strcmp(config->line[0].text, "v1") && config->line[0].x == 316 && config->line[0].y == 232);
    CHECK(config->line[0].align == TITLE_ALIGN_RIGHT && config->line[0].colour == 0xFFD000);
    CHECK(config->line[0].size == 2 && config->line[0].show == TITLE_SHOW_MENU);
    /* A line's defaults: centred at the bottom, white, size 1, always. */
    CHECK(config->line[1].x == 160 && config->line[1].y == 220 && config->line[1].align == TITLE_ALIGN_CENTRE);
    CHECK(config->line[1].colour == 0xFFFFFF && config->line[1].size == 1 && config->line[1].show == TITLE_SHOW_ALWAYS);
}

static void layout(void)
{
    /* Two of the first menu's five hidden: the other three close up around
     * the retail middle (y 114), 32 apart; the hidden ones go off screen. */
    const TitleConfig *config = one("{\"title\": {\"entries\": {\"duel\": {\"hide\": true}, \"trade\": {\"hide\": true}}}}");
    CHECK(config->entries[0].y == 82 && config->entries[1].y == 114 && config->entries[4].y == 146);
    CHECK(config->entries[2].y == TITLE_PARKED_Y && config->entries[3].y == TITLE_PARKED_Y);
    CHECK(config->entries[5].y == 42);
    /* Wider apart, one "y" of the mod's own left alone. */
    config = one("{\"title\": {\"spacing\": 40, \"entries\": {\"options\": {\"y\": 200}}}}");
    CHECK(config->entries[0].y == 34 && config->entries[1].y == 74 && config->entries[4].y == 200);
    /* Every entry of a menu hidden: none is. */
    config = one("{\"title\": {\"entries\": {\"new_game\": {\"hide\": true}, \"load\": {\"hide\": true},"
                 " \"duel\": {\"hide\": true}, \"trade\": {\"hide\": true}, \"options\": {\"hide\": true},"
                 " \"save\": {\"hide\": true}}}}");
    CHECK(!config->entries[0].hidden && !config->entries[4].hidden && config->entries[0].y == 50);
    CHECK(config->entries[10].hidden && config->entries[10].y == TITLE_PARKED_Y);
}

static void pictures(void)
{
    const TitleConfig *config = one("{\"title\": {\"background\": {\"image\": \"art/bg.png\"},"
                                    " \"logo\": {\"image\": \"logo.png\", \"width\": 300},"
                                    " \"prompt\": {\"image\": \"press.png\", \"width\": 400, \"height\": -2}}}");
    CHECK(notes == 0);
    CHECK(!strcmp(config->picture_image.file, "/mods/test/art/bg.png") && !strcmp(config->picture_image.mod, "test"));
    CHECK(!strcmp(config->layers[0].image.file, "/mods/test/logo.png") && config->layers[0].image.width == 300);
    CHECK(config->layers[0].image.height == 0 && !config->layers[1].image.file[0]);
    /* Out of range: worked out from the PNG instead. */
    CHECK(config->layers[2].image.width == 0 && config->layers[2].image.height == 0);
    config = one("{\"title\": {\"logo\": {\"image\": \"../other/logo.png\"}}}");
    CHECK(notes == 1 && strstr(note, "outside the mod") && !config->layers[0].image.file[0]);
    /* A later mod's "" puts the game's own picture back. */
    one("{\"title\": {\"logo\": {\"image\": \"logo.png\"}}}");
    add("{\"title\": {\"logo\": {\"image\": \"\"}}}");
    CHECK(!TitleConfig_Get()->layers[0].image.file[0]);
}

static void mods_add_up(void)
{
    const TitleConfig *config;
    one("{\"title\": {\"music\": 5, \"background\": {\"tint\": \"#FF0000\"}, \"text\": [{\"text\": \"a\"}]}}");
    add("{\"title\": {\"background\": {\"dim\": 0}, \"text\": [{\"text\": \"b\"}]}}");
    TitleConfig_Finish();
    config = TitleConfig_Get();
    CHECK(config->song == 5 && config->tint == 0xFF0000 && config->dim == 0);
    CHECK(config->lines == 2 && !strcmp(config->line[1].text, "b"));
}

static void mistakes(void)
{
    const TitleConfig *config = one("{\"title\": 3}");
    CHECK(notes == 1 && strstr(note, "is an object"));
    config = one("{\"title\": {\"musik\": 1}}");
    CHECK(notes == 1 && strstr(note, "unknown key \"musik\""));
    config = one("{\"title\": {\"music\": 4096}}");
    CHECK(notes == 1 && config->song == 0);
    config = one("{\"title\": {\"background\": {\"tint\": \"#12345\"}}}");
    CHECK(notes == 1 && strstr(note, "colour") && config->tint == 0xFFFFFF);
    config = one("{\"title\": {\"entries\": {\"quit\": {\"hide\": true}}}}");
    CHECK(notes == 1 && strstr(note, "no entry \"quit\""));
    config = one("{\"title\": {\"entries\": {\"11\": {\"hide\": true}}}}");
    CHECK(notes == 1);
    config = one("{\"title\": {\"text\": [{\"x\": 3}]}}");
    CHECK(notes == 1 && config->lines == 0);
    config = one("{\"title\": {\"idle_seconds\": -1}}");
    CHECK(notes == 1 && config->idle_frames == -1);
    config = one("{\"title\": {\"background\": {\"dim\": 500}}}");
    CHECK(notes == 0 && config->dim == 0x80);
}

int main(void)
{
    retail();
    keys();
    layout();
    pictures();
    mods_add_up();
    mistakes();
    while (document_count) Json_Free(documents[--document_count]);
    printf("title config: ok\n");
    return 0;
}
