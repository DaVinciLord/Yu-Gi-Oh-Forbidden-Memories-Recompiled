/* A card's "stars" as cards.c reads them (notes/modding.md, "No star"):
 * Cards_Build, add_entry and replace_model_effect on a stand-in for the
 * disc's tables.
 *
 * The bug this keeps away (Discord, 30/09): a retail monster replaced with
 * "stars": [0, 0] came back with its own retail stars, because the refill
 * meant for a magic card made a monster took any monster without star bits
 * for one. Also the copy entry, a magic card made a monster with and without
 * "stars", an earlier mod's no-star card under a later replace, [none, X],
 * and what is refused with a note. */
#define _POSIX_C_SOURCE 200809L /* before any header: cards.c's strdup */
#include <stdint.h>

/* The disc's tables, here. cards.c reads them at fixed addresses. */
static unsigned test_stats[722];
static short test_sort_keys[722];
static unsigned char test_level_attr[723];
static unsigned short test_name_offsets[723];
static unsigned char test_text_bank[16] = {0xFF};
static unsigned test_glyphs[256];
#define RETAIL_STATS ((uintptr_t)test_stats)
#define RETAIL_SORT_KEYS ((uintptr_t)test_sort_keys)
#define RETAIL_LEVEL_ATTR ((uintptr_t)test_level_attr)
#define RETAIL_NAME_OFFSETS ((uintptr_t)test_name_offsets)
#define TEXT_BANK ((uintptr_t)test_text_bank)
#define GLYPH_TABLE ((uintptr_t)test_glyphs)

#include "../../src/pc/cards/cards.c"
#include <assert.h>

int gCard_nCount = CARD_COUNT, gCard_nExtraOwner;
unsigned short gCard_awBaseId[CARD_TABLE_ID_END], gDuel_awPlayerDeck[1024];
unsigned char gCard_abExtraChest[CARD_TABLE_ID_END], gCard_abExtraSeen[(CARD_TABLE_ID_END + 7) / 8];
unsigned char gCard_abPairChest[2][CARD_TABLE_ID_END], gCard_abPairPending[2][CARD_TABLE_ID_END];
int gDuel_adwCardStats[CARD_TABLE_ID_END];
short gCard_asNameSortKey[CARD_TABLE_ID_END];
unsigned char gDuel_abCardLevelAttr[CARD_TABLE_ID_END];

static int notes[5];     /* per mod, "a" to "e" */

void Mods_Note(const char *id, const char *format, ...)
{
    char note[512];
    va_list arguments;
    va_start(arguments, format);
    vsnprintf(note, sizeof(note), format, arguments);
    va_end(arguments);
    fprintf(stderr, "note: %s: %s\n", id, note);
    if (id[0] >= 'a' && id[0] <= 'e' && !id[1]) notes[id[0] - 'a']++;
}

/* What cards.c and stars.c reach that these checks never get to. */
int Log_Wanted(LogChannel channel) { (void)channel; return 0; }
void Log_Printf(LogChannel channel, const char *format, ...) { (void)channel; (void)format; }
int Campaign_TestStoryFlag(int flag) { (void)flag; return 0; }
int CardArt_Crop(const char *path, int w, int h, int *x, int *y, int *cw, int *ch, int *width, int *height)
{
    (void)path; (void)w; (void)h; (void)x; (void)y; (void)cw; (void)ch; (void)width; (void)height;
    return 0;
}
int CardArt_FromImage(const char *path, unsigned char *record, char *why, size_t why_size)
{
    (void)path; (void)record; (void)why; (void)why_size;
    return 0;
}
int CardArt_ThumbnailFromImage(const char *path, unsigned char *record, char *why, size_t why_size)
{
    (void)path; (void)record; (void)why; (void)why_size;
    return 0;
}
int CardArt_FieldArtFromImage(const char *path, unsigned char *record, char *why, size_t why_size)
{
    (void)path; (void)record; (void)why; (void)why_size;
    return 0;
}
int CardArt_TitleFromImage(const char *path, unsigned char *plate, char *why, size_t why_size)
{
    (void)path; (void)plate; (void)why; (void)why_size;
    return 0;
}
int CardArt_TitleFromName(const char *name, unsigned char *plate) { (void)name; (void)plate; return 0; }
int CardNotes_Tag(const char *text, const char *key, char *out, size_t size)
{
    (void)text; (void)key; (void)out; (void)size;
    return 0;
}
void Duelists_Build(void) {}
uint32_t Glyphs_Character(int code) { return (uint32_t)code; }
int Glyphs_Code(uint32_t character) { return character < 0x80 ? (int)character : -1; }
uint32_t Glyphs_NextCharacter(const char **text) { return (unsigned char)*(*text)++; }
void Library_UpdateCardUsedFlag(int flag) { (void)flag; }
int Memories_Rand(void) { return 0; }
void Mods_SetCardNotes(const char *(*which)(int id), int (*tag)(int id, const char *key, char *out, size_t size))
{
    (void)which; (void)tag;
}
void Mods_SetCardResolver(int (*resolve)(const char *)) { (void)resolve; }
void Mods_SetCardSignature(unsigned signature) { (void)signature; }
void Mods_SetLimitSource(long (*source)(const char *name)) { (void)source; }
int Mods_Setting(const char *id, const char *key, int fallback) { (void)id; (void)key; return fallback; }
/* The mods' "cards", in load order, as Cards_Build visits them. */
static const char *const mod_cards[][2] = {
    /* The report: a retail monster replaced with no star keeps none; [none,
       X] is the one star X; 0, null and "none" are all none. A copy has its
       own stars, and a copy of a no-star card without "stars" none either. */
    {"a", "[{\"replace\": 1, \"stars\": [\"(none)\", \"(none)\"]},"
          " {\"replace\": 2, \"stars\": [0, \"Sun\"]},"
          " {\"replace\": 3, \"stars\": [null, \"none\"]},"
          " {\"copy\": 4, \"id\": \"none\", \"stars\": [0, 0]},"
          " {\"copy\": 1, \"id\": \"of-none\"}]"},
    /* A magic card made a monster: with no "stars", its model's or the Sun
       and the Moon; with [0, 0], none. */
    {"b", "[{\"replace\": 300, \"type\": \"Dragon\"},"
          " {\"replace\": 301, \"type\": \"Dragon\", \"model\": 1},"
          " {\"replace\": 302, \"type\": \"Dragon\", \"stars\": [0, 0]}]"},
    /* A later mod's entry for an earlier mod's no-star card that leaves
       "stars" out does not bring the disc's back. */
    {"c", "[{\"replace\": 1, \"attack\": 2000}]"},
    /* Refused, each with a note, the card keeping what it had; a star left
       out with none for the other is still put first. */
    {"d", "[{\"replace\": 5, \"stars\": \"Mars\"},"
          " {\"replace\": 6, \"stars\": [\"Mars\"]},"
          " {\"replace\": 7, \"stars\": [\"Nowhere\", \"Mars\"]},"
          " {\"replace\": 8, \"stars\": [0, \"Nowhere\"]}]"},
    /* Monsters made a magic, an equip and a trap card: no ATK or DEF, an
       "attack" given said to be left out, and each another kind than on the
       disc, so out of its fusion and equip tables (Cards_KindChanged). */
    {"e", "[{\"replace\": 10, \"type\": \"Magic\"},"
          " {\"replace\": 11, \"type\": \"Equip\", \"attack\": 1500},"
          " {\"replace\": 12, \"type\": \"Trap\", \"defense\": 0}]"},
};

void Mods_VisitCards(void (*visit)(const char *id, const char *directory, const struct JsonValue *cards, void *context),
                     void *context)
{
    size_t i;
    for (i = 0; i < sizeof(mod_cards) / sizeof(mod_cards[0]); i++) {
        char error[256];
        /* Kept: the cards keep their entries (definitions[]). */
        JsonDocument *document = Json_Parse(mod_cards[i][1], error, sizeof(error));
        if (!document) fprintf(stderr, "%s: %s\n", mod_cards[i][0], error);
        assert(document);
        visit(mod_cards[i][0], ".", Json_Root(document), context);
    }
}
int Mods_LoadedCount(void) { return 0; }
int Mods_Loaded(int index) { return index; }
int Mods_Active(int mod) { (void)mod; return 0; }
const char *Mods_Id(int mod) { (void)mod; return ""; }
const char *Mods_Directory(int mod) { (void)mod; return "."; }
const struct JsonValue *Mods_Manifest(int mod) { (void)mod; return NULL; }
int Paths_Contained(const char *relative) { return relative[0] != '/' && !strstr(relative, ".."); }
int Paths_MakeDirs(const char *path) { (void)path; return -1; }
int Paths_User(char *out, size_t size, const char *relative) { (void)out; (void)size; (void)relative; return -1; }
void Paths_WriteBegin(void) {}
const char *Paths_WriteError(char *out, size_t size, const char *path) { (void)size; (void)path; return out; }
int Settings_Get(SettingId id) { (void)id; return 0; }
void Starter_Build(void) {}
void Packs_Build(void) {}
unsigned Packs_Signature(void) { return 0; }
void Mods_SetPackSignature(unsigned signature) { (void)signature; }
void Tables_Build(void) {}
long Tables_Limit(const char *name) { (void)name; return -1; }
int Tables_StatCapEither(void) { return 9999; }
int Text_Overridden(int id) { (void)id; return 0; }
const unsigned char *Text_Resolve(int id, const unsigned char *retail) { (void)id; return retail; }
void TextureDump_Written(const void *destination, unsigned bytes) { (void)destination; (void)bytes; }
int TexturePack_AddMade(const void *pixels, int words, int rows, int bpp, const void *clut, int clut_entries,
                        const char *file, int x, int y, int w, int h)
{
    (void)pixels; (void)words; (void)rows; (void)bpp; (void)clut; (void)clut_entries; (void)file;
    (void)x; (void)y; (void)w; (void)h;
    return 0;
}
int Language_Current(void) { return 0; }
const char *Language_Code(int which) { (void)which; return "en-us"; }

#define STATS(type, star1, star2) (((unsigned)(type) << 26) | ((unsigned)(star1) << 22) | ((unsigned)(star2) << 18) | 100u)
#define MARS 1
#define SUN 8
#define MOON 9

static void stars_of(int id, int *first, int *second)
{
    unsigned stats = (unsigned)gDuel_adwCardStats[id - 1];
    *first = (int)((stats >> 22) & 0xF);
    *second = (int)((stats >> 18) & 0xF);
}

static void expect(int id, int first, int second)
{
    int a, b;
    stars_of(id, &a, &b);
    if (a != first || b != second) {
        fprintf(stderr, "card %d: stars %d, %d; expected %d, %d\n", id, a, b, first, second);
        assert(0);
    }
}

int main(void)
{
    int id;
    /* The disc, as far as these checks go: 1-3 monsters with two stars,
       300-302 magic cards (no stars), the rest plain Dragons. */
    for (id = 1; id <= CARD_COUNT; id++) test_stats[id - 1] = STATS(0, SUN, MOON);
    test_stats[0] = STATS(0, SUN, MARS);       /* Blue-eyes White Dragon */
    test_stats[1] = STATS(6, SUN, 2);          /* Mystical Elf */
    test_stats[2] = STATS(1, MOON, MARS);      /* Hitotsu-me Giant */
    for (id = 300; id <= 302; id++) test_stats[id - 1] = STATS(CARD_TYPE_MAGIC, 0, 0);
    Stars_Clear();
    assert(!Stars_NoStarUsed());

    Cards_Build();
    assert(Stars_NoStarUsed());

    expect(1, 0, 0);
    expect(2, SUN, 0);
    expect(3, 0, 0);
    assert(gCard_nCount == CARD_COUNT + 2);
    expect(CARD_COUNT + 1, 0, 0);
    expect(CARD_COUNT + 2, 0, 0);
    expect(4, SUN, MOON);                      /* a copy's base is left alone */
    assert(notes[0] == 0);

    expect(300, SUN, MOON);
    expect(301, SUN, MARS);
    expect(302, 0, 0);
    assert(notes[1] == 0);

    /* "c" set the attack of 1, and only that. */
    assert(((unsigned)gDuel_adwCardStats[0] & 0x1FF) == 200);

    assert(notes[3] == 4);
    expect(5, SUN, MOON);
    expect(6, SUN, MOON);
    expect(7, SUN, MARS);                      /* the star it names, the other kept */
    expect(8, MOON, 0);

    for (id = 10; id <= 12; id++) assert(!((unsigned)gDuel_adwCardStats[id - 1] & 0x3FFFF));
    assert(notes[4] == 1);
    assert(Cards_KindChanged(10) && Cards_KindChanged(11) && Cards_KindChanged(12));
    assert(Cards_KindChanged(300) && Cards_KindChanged(301));   /* magic cards made Dragons */
    assert(!Cards_KindChanged(1) && !Cards_KindChanged(4) && !Cards_KindChanged(CARD_COUNT + 1));
    assert(((unsigned)gDuel_adwCardStats[3] & 0x1FF) == 100);   /* a monster keeps its own */

    puts("cards stars: ok");
    return 0;
}
