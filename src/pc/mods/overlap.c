/* What two or more mods both change (overlap.h, notes/modding.md "When mods
 * overlap").
 *
 * Every mod's manifest becomes claims: one for each thing it sets (a card, a
 * fusion pair, a pool, a limit, an image...), with a key naming the thing, a
 * mode (it sets it, adds to it, defines it, hooks it) and a hash of what it
 * sets. The claims are sorted by kind and key; a run of claims from two or
 * more mods is an overlap, and the load order decides how it comes out, the
 * way the reader of that key decides it. A kind fewer than two mods have is
 * not looked at, so one mod (or none) costs nothing.
 *
 * "all" (drops, decks, passwords) and "replace" (guardian star matchups,
 * terrain bonuses) reach things they do not name: such a claim is "wide",
 * and stands, besides its own key, beside every key of its kind another mod
 * names that it covers. */
#include "pc/compat/fs.h" /* UTF-8 paths on Windows too (notes/pc-build.md) */
#include "overlap.h"
#include "json.h"
#include "pc/platform/paths.h"
#include <ctype.h>
#include <dirent.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

enum { SET, ADD, FIXED, BASE, CHAIN, EVENT, FIRST };   /* what a claim does */
enum { VIA_WIDE = 1, AIMED = 2, RESETS = 4 };          /* claim flags */
enum { O_LATER, O_AFTER, O_AGREE, O_ADD, O_RESET, O_FIXED, O_KEYS, O_BYTES, O_CHAIN, O_EVENTS, O_FIRST, O_AIMED };
static const char *const outcome_words[] = {"later", "after", "agree", "add",   "reset",  "fixed",
                                            "keys",  "bytes", "chain", "events", "first", "aimed"};

#define TEXT_KEY (1ull << 40)      /* a card named by letters no card has: its letters' hash */
#define ALL_CARDS ((1ull << 41) - 1)
#define SUB(n) ((uint64_t)(n) << 56)
#define SUB_MASK SUB(0xFF)
#define RESET_SUB 0xFE
#define DEFAULT_EQUIP_BONUS (1ull << 62)
#define ALL_DUELISTS ((1ull << 47) - 1)

typedef struct {
    uint64_t key, mask, match; /* mask: a wide claim, beside every key k with (k & mask) == match */
    uint32_t value;            /* what it sets, hashed: equal values agree */
    int mod, seq, label;       /* label: in the strings, or -1 to make it from `src` */
    unsigned char kind, mode, flags;
    const JsonValue *src;
} Claim;

typedef struct {
    int first, count, winner, other, outcome;
    unsigned char kind, severity;
} Group;

typedef struct {
    uint64_t hash;
    int id;
} Memo;

typedef struct {
    uint64_t name;
    int id;
} StarName;

struct ModsOverlaps {
    ModsOverlapMod *mods;
    int mod_count;
    ModsOverlapSource source;
    Claim *claims;
    int claim_count, claim_room;
    Group *groups;
    int group_count;
    char *strings;
    size_t string_length, string_room;
    JsonDocument **documents;
    int document_count, document_room;
    unsigned char *declared; /* [winner * mod_count + other]: the winner loads after it on purpose */
    Memo *memo;
    int memo_room, memo_count;
    StarName *star_names;
    int star_name_count, star_name_room;
    int seq, failed;
};

/* --- small tools ---------------------------------------------------------- */

static uint64_t fnv(uint64_t hash, const char *text)
{
    while (*text) hash = (hash ^ (unsigned char)*text++) * 1099511628211ull;
    return hash;
}
static uint64_t hash_text(const char *text) { return fnv(14695981039346656037ull, text ? text : ""); }
/* Letters and digits only, lowercased, as the readers compare names
 * (tables.c same_letters): 0 for a name of neither. */
static uint64_t hash_letters(const char *text)
{
    uint64_t hash = 14695981039346656037ull;
    int any = 0;
    for (; text && *text; text++)
        if (isalnum((unsigned char)*text)) {
            hash = (hash ^ (unsigned char)tolower((unsigned char)*text)) * 1099511628211ull;
            any = 1;
        }
    return any ? hash : 0;
}
static int same_letters(const char *a, const char *b) { return hash_letters(a) == hash_letters(b); }
static uint64_t mix(uint64_t a, uint64_t b)
{
    uint64_t hash = (a ^ 0x9E3779B97F4A7C15ull) * 0xBF58476D1CE4E5B9ull;
    return (hash ^ (hash >> 31) ^ b) * 0x94D049BB133111EBull;
}
/* What a value says, its members' names included but not its own (a trap's
 * threshold is the same whether the trap is named "Bear Trap" or "600"). */
static uint32_t hash_json(uint32_t hash, const JsonValue *value, int named)
{
    const JsonValue *child;
    char number[40];
    if (!value) return hash;
    hash = (hash ^ (unsigned)Json_TypeOf(value)) * 16777619u;
    if (named && Json_Name(value)) hash = (uint32_t)fnv(hash, Json_Name(value));
    if (Json_TypeOf(value) == JSON_STRING) hash = (uint32_t)fnv(hash, Json_String(value, ""));
    if (Json_TypeOf(value) == JSON_NUMBER || Json_TypeOf(value) == JSON_BOOL) {
        snprintf(number, sizeof(number), "%ld", Json_Number(value, Json_Bool(value, 0)));
        hash = (uint32_t)fnv(hash, number);
    }
    for (child = Json_At(value, 0); child; child = Json_Next(child)) hash = hash_json(hash * 31u, child, 1);
    return hash;
}
static uint32_t value_of(const JsonValue *value) { return hash_json(2166136261u, value, 0); }
/* A value nobody else's equals: two images of two packs never "agree". */
static uint32_t own_value(int mod) { return 0x80000000u | (uint32_t)mod; }

static void *grow(void *array, int *room, int count, size_t size)
{
    void *bigger;
    int next;
    if (count < *room) return array;
    next = *room ? *room * 2 : 64;
    bigger = realloc(array, (size_t)next * size);
    if (!bigger) return NULL;
    *room = next;
    return bigger;
}

static int add_string(ModsOverlaps *x, const char *text)
{
    size_t length = strlen(text) + 1;
    int at;
    if (x->string_length + length > x->string_room) {
        size_t room = x->string_room ? x->string_room * 2 : 4096;
        char *bigger;
        while (room < x->string_length + length) room *= 2;
        if (!(bigger = realloc(x->strings, room))) {
            x->failed = 1;
            return -1;
        }
        x->strings = bigger;
        x->string_room = room;
    }
    at = (int)x->string_length;
    memcpy(x->strings + at, text, length);
    x->string_length += length;
    return at;
}

static Claim *claim(ModsOverlaps *x, int kind, int mod, uint64_t key, int mode, uint32_t value, const JsonValue *src)
{
    Claim *c;
    Claim *claims = grow(x->claims, &x->claim_room, x->claim_count, sizeof(*x->claims));
    if (!claims) {
        x->failed = 1;
        return NULL;
    }
    x->claims = claims;
    c = &claims[x->claim_count++];
    memset(c, 0, sizeof(*c));
    c->key = key;
    c->value = value;
    c->mod = mod;
    c->seq = ++x->seq;
    c->label = -1;
    c->kind = (unsigned char)kind;
    c->mode = (unsigned char)mode;
    c->src = src;
    return c;
}
static void labelled(ModsOverlaps *x, Claim *c, const char *label)
{
    if (c) c->label = add_string(x, label);
}

static const JsonValue *member(const ModsOverlaps *x, int mod, const char *key)
{
    return Json_Member(x->mods[mod].manifest, key);
}
/* How many mods have `key` in their manifest. */
static int having(const ModsOverlaps *x, const char *key)
{
    int n = 0;
    for (int i = 0; i < x->mod_count; i++) n += member(x, i, key) != NULL;
    return n;
}

/* A file of the mod's, parsed and kept for the claims that point into it. */
static const JsonValue *mod_file(ModsOverlaps *x, int mod, const char *relative)
{
    char path[1024], error[256];
    JsonDocument *document, **documents;
    if (!x->mods[mod].directory || !relative || !Paths_Contained(relative) ||
        snprintf(path, sizeof(path), "%s/%s", x->mods[mod].directory, relative) >= (int)sizeof(path))
        return NULL;
    if (!(document = Json_ParseFile(path, error, sizeof(error)))) return NULL;
    documents = grow(x->documents, &x->document_room, x->document_count, sizeof(*x->documents));
    if (!documents) {
        Json_Free(document);
        x->failed = 1;
        return NULL;
    }
    x->documents = documents;
    documents[x->document_count++] = document;
    return Json_Root(document);
}

/* The ".json" files of a folder of the mod's, sorted, as the readers list
 * them; their names without ".json", one after another, ended by "". */
static char *folder_names(const ModsOverlaps *x, int mod, const char *folder)
{
    char path[1024], *names = NULL;
    size_t length = 0, room = 0;
    DIR *dir;
    struct dirent *item;
    if (!x->mods[mod].directory ||
        snprintf(path, sizeof(path), "%s/%s", x->mods[mod].directory, folder) >= (int)sizeof(path) ||
        !(dir = opendir(path)))
        return NULL;
    while ((item = readdir(dir)) != NULL) {
        size_t n = strlen(item->d_name);
        if (n < 6 || strcmp(item->d_name + n - 5, ".json")) continue;
        if (length + n + 2 > room) {
            char *bigger = realloc(names, room = (room + n + 2) * 2);
            if (!bigger) break;
            names = bigger;
        }
        memcpy(names + length, item->d_name, n - 5);
        names[length + n - 5] = 0;
        length += n - 4;
    }
    closedir(dir);
    if (names) names[length] = 0;
    return names;
}

/* --- cards and duelists by name ---------------------------------------- */

static int memo_find(ModsOverlaps *x, uint64_t hash, int *id)
{
    if (!x->memo_room) return 0;
    for (int i = (int)(hash % (uint64_t)x->memo_room);; i = (i + 1) % x->memo_room) {
        if (!x->memo[i].hash) return 0;
        if (x->memo[i].hash == hash) {
            *id = x->memo[i].id;
            return 1;
        }
    }
}
static void memo_keep(ModsOverlaps *x, uint64_t hash, int id)
{
    if ((x->memo_count + 1) * 2 > x->memo_room) {
        Memo *old = x->memo;
        int old_room = x->memo_room, room = old_room ? old_room * 2 : 1024;
        Memo *bigger = calloc((size_t)room, sizeof(*bigger));
        if (!bigger) return;
        x->memo = bigger;
        x->memo_room = room;
        x->memo_count = 0;
        for (int i = 0; i < old_room; i++)
            if (old[i].hash) memo_keep(x, old[i].hash, old[i].id);
        free(old);
    }
    for (int i = (int)(hash % (uint64_t)x->memo_room);; i = (i + 1) % x->memo_room)
        if (!x->memo[i].hash) {
            x->memo[i].hash = hash;
            x->memo[i].id = id;
            x->memo_count++;
            return;
        }
}

/* A card by what a manifest writes: its id when the game knows it, else
 * its letters' hash (two mods spelling it alike still meet). 0 for none. */
static uint64_t card_text(ModsOverlaps *x, const char *text)
{
    uint64_t hash = hash_letters(text);
    int id = 0;
    if (!hash) return 0;
    if (!memo_find(x, hash, &id)) {
        if (x->source.card) id = x->source.card(text, 0, x->source.context);
        else if (strspn(text, "0123456789") == strlen(text)) id = atoi(text);
        memo_keep(x, hash, id);
    }
    return id > 0 ? (uint64_t)id : TEXT_KEY | (hash >> 24);
}
static uint64_t card_key(ModsOverlaps *x, const JsonValue *value)
{
    if (Json_TypeOf(value) == JSON_NUMBER) {
        long number = Json_Number(value, 0);
        int id = x->source.card ? x->source.card(NULL, number, x->source.context) : (int)number;
        return id > 0 ? (uint64_t)id : number > 0 && number < (long)TEXT_KEY ? (uint64_t)number : 0;
    }
    return Json_TypeOf(value) == JSON_STRING ? card_text(x, Json_String(value, "")) : 0;
}
/* A card for a line: its name when the game has one, else as written. */
static void card_words(const ModsOverlaps *x, const JsonValue *value, char *out, size_t size)
{
    long number = Json_TypeOf(value) == JSON_NUMBER ? Json_Number(value, 0) : 0;
    const char *text = Json_String(value, NULL);
    int id = 0;
    char name[96];
    if (x->source.card) id = x->source.card(text, number, x->source.context);
    else if (number > 0) id = (int)number;
    if (id > 0 && x->source.card_name && x->source.card_name(id, name, sizeof(name), x->source.context))
        snprintf(out, size, "'%s'", name);
    else if (text)
        snprintf(out, size, "'%s'", text);
    else
        snprintf(out, size, "#%ld", number);
}

static uint64_t duelist_key(ModsOverlaps *x, const char *name)
{
    int id;
    if (same_letters(name, "all")) return ALL_DUELISTS;
    id = x->source.duelist ? x->source.duelist(name, x->source.context) : -1;
    if (id < 0 && strspn(name, "0123456789") == strlen(name) && *name) id = atoi(name);
    return id >= 0 ? (uint64_t)id : (1ull << 46) | (hash_letters(name) >> 18);
}

/* --- the kinds ------------------------------------------------------------ */

/* "data": a disc file by name (as the game asks for it, any case) or a raw
 * sector. Replacements, then patches; the later of each wins. */
static void read_data(ModsOverlaps *x, int mod)
{
    for (const JsonValue *entry = Json_At(member(x, mod, "data"), 0); entry; entry = Json_Next(entry)) {
        const char *file = Json_String(Json_Member(entry, "file"), NULL);
        long lba = Json_Number(Json_Member(entry, "lba"), -1);
        uint64_t key;
        if (file && *file) {
            char name[256];
            size_t n = 0;
            for (const char *s = file; *s && *s != ';' && n + 1 < sizeof(name); s++)
                if (n || (*s != '\\' && *s != '/')) name[n++] = *s == '/' ? '\\' : (char)toupper((unsigned char)*s);
            name[n] = 0;
            key = (1ull << 63) | (hash_text(name) >> 1);
        } else if (lba >= 0)
            key = (uint64_t)lba;
        else
            continue;
        claim(x, MODS_OVERLAP_DATA, mod, key, Json_Member(entry, "replace") ? SET : ADD, own_value(mod), entry);
    }
}

/* "audio": an id of music, xa or sfx; the mod applied later is heard. */
static long audio_id(const char *text)
{
    char *end;
    long value;
    if (!text || !*text) return -1;
    value = text[0] == '0' && (text[1] == 'x' || text[1] == 'X') ? strtol(text + 2, &end, 16) : strtol(text, &end, 10);
    return *end ? -1 : value;
}
static void read_audio(ModsOverlaps *x, int mod)
{
    static const char *const kinds[] = {"music", "xa", "sfx"};
    for (int k = 0; k < 3; k++)
        for (const JsonValue *m = Json_At(Json_Member(member(x, mod, "audio"), kinds[k]), 0); m; m = Json_Next(m)) {
            long id = audio_id(Json_Name(m));
            if (id >= 0) claim(x, MODS_OVERLAP_AUDIO, mod, ((uint64_t)k << 32) | (uint64_t)id, SET, value_of(m), m);
        }
}

/* Whether an entry naming a mod's setting ("setting", and "value" for one
 * choice of it) is used, as Mods_File, the pack loader and the rule tables
 * decide: a text file, a pack's image, a fusion, equip or ritual entry.
 * A setting the mod does not declare leaves the entry used. */
static int switched_on(const ModsOverlaps *x, int mod, const JsonValue *entry)
{
    const char *key = Json_String(Json_Member(entry, "setting"), NULL);
    const JsonValue *only = Json_Member(entry, "value");
    int value;
    if (!key || !x->source.setting || (value = x->source.setting(mod, key, x->source.context)) < 0) return 1;
    return only ? value == (int)Json_Number(only, 0) : value != 0;
}
/* "textures": the pack's manifest.json, an image per entry; the same image
 * is the same archive, offset, size, depth and palette (texture_pack.c). */
static void read_textures(ModsOverlaps *x, int mod)
{
    const char *folder = Json_String(member(x, mod, "textures"), NULL);
    char relative[512], key[512];
    const JsonValue *list;
    if (!folder || snprintf(relative, sizeof(relative), "%s/manifest.json", folder) >= (int)sizeof(relative)) return;
    list = mod_file(x, mod, relative);
    for (const JsonValue *entry = Json_At(list, 0); entry; entry = Json_Next(entry)) {
        const char *archive = Json_String(Json_Member(entry, "archive"), "");
        if (!switched_on(x, mod, entry)) continue;
        long clut = Json_Number(Json_Member(entry, "clut_entries"), 0);
        char upper[128];
        size_t n = 0;
        for (; archive[n] && n + 1 < sizeof(upper); n++) upper[n] = (char)toupper((unsigned char)archive[n]);
        upper[n] = 0;
        snprintf(key, sizeof(key), "%s|%ld|%ld|%ld|%ld|%ld|%ld", upper, Json_Number(Json_Member(entry, "offset"), -1),
                 Json_Number(Json_Member(entry, "words"), 0), Json_Number(Json_Member(entry, "rows"), 0),
                 Json_Number(Json_Member(entry, "bpp"), 0), clut ? Json_Number(Json_Member(entry, "clut_offset"), 0) : 0,
                 clut);
        claim(x, MODS_OVERLAP_TEXTURES, mod, hash_text(key), SET, own_value(mod), entry);
    }
}

/* "cards": a "replace" changes a card in place, the later entry going over
 * the earlier key by key (cards.c); a "copy" makes new cards, whose
 * identities another mod's "replace" may name. */
static int any_identity_replace(const ModsOverlaps *x)
{
    for (int i = 0; i < x->mod_count; i++)
        for (const JsonValue *e = Json_At(member(x, i, "cards"), 0); e; e = Json_Next(e)) {
            const char *text = Json_String(Json_Member(e, "replace"), NULL);
            if (text && strchr(text, ':')) return 1;
        }
    return 0;
}
static void read_cards(ModsOverlaps *x, int mod, int identities)
{
    int index = 0;
    for (const JsonValue *e = Json_At(member(x, mod, "cards"), 0); e; e = Json_Next(e), index++) {
        const JsonValue *replaced = Json_Member(e, "replace");
        if (replaced) {
            uint64_t key = card_key(x, replaced);
            Claim *c = key ? claim(x, MODS_OVERLAP_CARDS, mod, key, SET, value_of(e), e) : NULL;
            const char *text = Json_String(replaced, NULL);
            if (c && text && strchr(text, ':') && strncmp(text, x->mods[mod].id, strlen(x->mods[mod].id)))
                c->flags |= AIMED;
        } else if (identities && Json_Member(e, "copy")) {
            long count = Json_Number(Json_Member(e, "count"), 1);
            const char *id = Json_String(Json_Member(e, "id"), NULL);
            char entry[64], identity[256];
            if (!id) {
                snprintf(entry, sizeof(entry), "entry-%d", index);
                id = entry;
            }
            for (long n = 1; n <= count && n <= 4096; n++) {
                Claim *c;
                snprintf(identity, sizeof(identity), "%s:%s:%ld", x->mods[mod].id, id, n);
                c = claim(x, MODS_OVERLAP_CARDS, mod, card_text(x, identity), BASE, 0, e);
                snprintf(entry, sizeof(entry), "Card '%.40s'", identity);
                labelled(x, c, entry);
            }
        }
    }
}

/* "fusions": a pair in either order, the later mod's rule winning;
 * "remove"s add up (a mod's own recipes still make the card). */
static void read_fusions(ModsOverlaps *x, int mod)
{
    for (const JsonValue *rule = Json_At(member(x, mod, "fusions"), 0); rule; rule = Json_Next(rule)) {
        const JsonValue *with = Json_Member(rule, "with"), *removed = Json_Member(rule, "remove");
        if (!switched_on(x, mod, rule)) continue;
        if (removed) {
            uint64_t key = card_key(x, removed);
            if (key) claim(x, MODS_OVERLAP_FUSIONS, mod, (1ull << 63) | key, ADD, 0, rule);
        } else if (Json_Count(with) == 2) {
            uint64_t a = card_key(x, Json_At(with, 0)), b = card_key(x, Json_Next(Json_At(with, 0)));
            const JsonValue *result = Json_Member(rule, "result");
            if (!a || !b || !result) continue;
            claim(x, MODS_OVERLAP_FUSIONS, mod, (mix(a < b ? a : b, a < b ? b : a) >> 1), SET,
                  (uint32_t)card_key(x, result) ^ (uint32_t)(card_key(x, result) >> 32), rule);
        }
    }
}

/* "equips": an entry per equip card; the latest entry that says anything
 * about a monster decides (tables.c Tables_Equip), so entries naming other
 * monsters add up. "equip_bonus_default": the latest mod's. */
static void read_equips(ModsOverlaps *x, int mod)
{
    const JsonValue *bonus = member(x, mod, "equip_bonus_default");
    for (const JsonValue *e = Json_At(member(x, mod, "equips"), 0); e; e = Json_Next(e)) {
        uint64_t key = card_key(x, Json_Member(e, "card"));
        if (key && switched_on(x, mod, e)) claim(x, MODS_OVERLAP_EQUIPS, mod, key, SET, value_of(e), e);
    }
    if (bonus) claim(x, MODS_OVERLAP_EQUIPS, mod, DEFAULT_EQUIP_BONUS, SET, value_of(bonus), bonus);
}

/* "rituals": the latest recipe of a ritual card is the one used. */
static void read_rituals(ModsOverlaps *x, int mod)
{
    for (const JsonValue *e = Json_At(member(x, mod, "rituals"), 0); e; e = Json_Next(e)) {
        uint64_t key = card_key(x, Json_Member(e, "card"));
        if (key && switched_on(x, mod, e))
            claim(x, MODS_OVERLAP_RITUALS, mod, key, SET,
                  hash_json(value_of(Json_Member(e, "tributes")), Json_Member(e, "result"), 0), e);
    }
}

/* "drops" and "decks": an opponent's pools. Plain edits add up, each on the
 * pool as the mods before left it; "replace": true empties it first; a fixed
 * deck wins over every weighted edit (tables.c). "all" reaches every
 * opponent. The pools may be in a file, or a file per opponent in the mod's
 * drops/ and decks/ folders. */
static int pool_named(const char *name)
{
    static const char *const names[][2] = {{"pow", "sa-pow"}, {"bcd", "b-c-d"}, {"tec", "sa-tec"}};
    for (int i = 0; i < 3; i++)
        if (same_letters(name, names[i][0]) || same_letters(name, names[i][1])) return i + 1;
    return -1;
}
static const char *const pool_words[] = {"deck", "POW drops", "B/C/D drops", "TEC drops"};
static void pool_claim(ModsOverlaps *x, int mod, const char *duelist, int pool, const JsonValue *entry)
{
    uint64_t who = duelist_key(x, duelist);
    int fixed = !pool && Json_Bool(Json_Member(entry, "fixed"), 0);
    Claim *c = claim(x, MODS_OVERLAP_POOLS, mod, (who << 8) | (uint64_t)pool,
                     fixed                                          ? FIXED
                     : Json_Bool(Json_Member(entry, "replace"), 0) ? SET
                                                                    : ADD,
                     value_of(entry), entry);
    char label[160];
    if (!c) return;
    if (c->mode == SET) c->flags |= RESETS;
    if (who == ALL_DUELISTS) {
        c->mask = 0xFF;
        c->match = (uint64_t)pool;
        snprintf(label, sizeof(label), "Every opponent's %s", pool_words[pool]);
    } else
        snprintf(label, sizeof(label), "%.80s's %s", duelist, pool_words[pool]);
    labelled(x, c, label);
}
static void pool_table(ModsOverlaps *x, int mod, const JsonValue *table, int decks)
{
    for (const JsonValue *entry = Json_At(table, 0); entry; entry = Json_Next(entry)) {
        if (decks) {
            pool_claim(x, mod, Json_Name(entry), 0, entry);
            continue;
        }
        for (const JsonValue *pool = Json_At(entry, 0); pool; pool = Json_Next(pool)) {
            int which = pool_named(Json_Name(pool));
            if (which > 0) pool_claim(x, mod, Json_Name(entry), which, pool);
        }
    }
}
static void read_pools(ModsOverlaps *x, int mod)
{
    for (int decks = 0; decks < 2; decks++) {
        const JsonValue *table = member(x, mod, decks ? "decks" : "drops");
        char *names, relative[160];
        if (Json_TypeOf(table) == JSON_STRING) table = mod_file(x, mod, Json_String(table, NULL));
        pool_table(x, mod, table, decks);
        names = folder_names(x, mod, decks ? "decks" : "drops");
        for (const char *name = names; name && *name; name += strlen(name) + 1) {
            const JsonValue *root;
            snprintf(relative, sizeof(relative), "%s/%.100s.json", decks ? "decks" : "drops", name);
            if (!(root = mod_file(x, mod, relative))) continue;
            if (decks)
                pool_claim(x, mod, name, 0, root);
            else
                for (const JsonValue *pool = Json_At(root, 0); pool; pool = Json_Next(pool))
                    if (pool_named(Json_Name(pool)) > 0) pool_claim(x, mod, name, pool_named(Json_Name(pool)), pool);
        }
        free(names);
    }
}

/* "passwords": a card's password and its price; "all" every card, before
 * the cards named beside it. The latest mod that sets one wins. */
static void read_passwords(ModsOverlaps *x, int mod)
{
    static const char *const fields[][2] = {{"password", NULL}, {"starchips", "starchips_percent"}};
    for (const JsonValue *m = Json_At(member(x, mod, "passwords"), 0); m; m = Json_Next(m)) {
        int all = same_letters(Json_Name(m), "all");
        uint64_t card = all ? ALL_CARDS : card_text(x, Json_Name(m));
        if (!card) continue;
        for (int f = 0; f < 2; f++) {
            const JsonValue *v = Json_Member(m, fields[f][0]);
            char label[160];
            Claim *c;
            if (!v && fields[f][1]) v = Json_Member(m, fields[f][1]);
            if (!v) continue;
            c = claim(x, MODS_OVERLAP_PASSWORDS, mod, (card << 4) | (uint64_t)(f + 1), SET, value_of(v), m);
            if (!c) return;
            if (all) {
                c->mask = 0xF;
                c->match = (uint64_t)(f + 1);
                snprintf(label, sizeof(label), "Every card's %s", f ? "price" : "password");
            } else {
                char card_name[120];
                snprintf(label, sizeof(label), "%s of '%.80s'", f ? "Price" : "Password", Json_Name(m));
                if (x->source.card_name && card < TEXT_KEY &&
                    x->source.card_name((int)card, card_name, sizeof(card_name), x->source.context))
                    snprintf(label, sizeof(label), "%s of '%.100s'", f ? "Price" : "Password", card_name);
            }
            labelled(x, c, label);
        }
    }
}

/* "guardian_stars": an ordered pair of stars, a star's name, icon and
 * palette, the way a summon chooses; the later mod's, and "replace" sets
 * every pair to 0 first (stars.c). */
static const char *const star_retail[] = {"",        "Mars",    "Jupiter", "Saturn", "Uranus", "Pluto",
                                          "Neptune", "Mercury", "Sun",     "Moon",   "Venus"};
static void star_learn(ModsOverlaps *x, uint64_t name, int id)
{
    StarName *names;
    if (!name) return;
    names = grow(x->star_names, &x->star_name_room, x->star_name_count, sizeof(*x->star_names));
    if (!names) return;
    x->star_names = names;
    names[x->star_name_count].name = name;
    names[x->star_name_count++].id = id;
}
static void star_names(ModsOverlaps *x)
{
    for (int i = 1; i <= 10; i++) star_learn(x, hash_letters(star_retail[i]), i);
    for (int mod = 0; mod < x->mod_count; mod++)
        for (const JsonValue *s = Json_At(Json_Member(member(x, mod, "guardian_stars"), "stars"), 0); s;
             s = Json_Next(s)) {
            const JsonValue *name = Json_Member(s, "name");
            int id = (int)Json_Number(Json_Member(s, "id"), -1);
            if (Json_TypeOf(name) == JSON_STRING) star_learn(x, hash_letters(Json_String(name, "")), id);
            for (const JsonValue *n = Json_TypeOf(name) == JSON_OBJECT ? Json_At(name, 0) : NULL; n; n = Json_Next(n))
                star_learn(x, hash_letters(Json_String(n, "")), id);
        }
}
static int star_of(const ModsOverlaps *x, const JsonValue *value)
{
    const char *text = Json_String(value, NULL);
    uint64_t name;
    if (Json_TypeOf(value) == JSON_NUMBER) return (int)Json_Number(value, -1);
    if (!text) return -1;
    if (*text && strspn(text, "0123456789") == strlen(text)) return atoi(text);
    name = hash_letters(text);
    for (int i = 0; i < x->star_name_count; i++)
        if (x->star_names[i].name == name) return x->star_names[i].id;
    return -1;
}
static void star_pair(ModsOverlaps *x, int mod, int a, int d, long bonus, const JsonValue *src)
{
    if (a >= 0 && a <= 15 && d >= 0 && d <= 15)
        claim(x, MODS_OVERLAP_STARS, mod, SUB(1) | ((uint64_t)a << 8) | (uint64_t)d, SET, (uint32_t)bonus, src);
}
static void read_stars(ModsOverlaps *x, int mod)
{
    const JsonValue *section = member(x, mod, "guardian_stars"), *v;
    long bonus = 500;
    int reset = Json_Bool(Json_Member(section, "replace"), 0);
    if (Json_TypeOf(section) != JSON_OBJECT) return;
    if (reset) {
        Claim *c = claim(x, MODS_OVERLAP_STARS, mod, SUB(RESET_SUB), SET, 0, Json_Member(section, "replace"));
        if (c) {
            c->mask = SUB_MASK;
            c->match = SUB(1);
            c->flags |= RESETS;
        }
    }
    if ((v = Json_Member(section, "default_bonus")) != NULL && Json_TypeOf(v) == JSON_NUMBER) {
        bonus = Json_Number(v, 500);
        claim(x, MODS_OVERLAP_STARS, mod, SUB(3) | 1, SET, (uint32_t)bonus, v);
        /* It is what the disc's two cycles give, unless "replace" took them. */
        for (int a = 1; a <= 10 && !reset; a++) {
            int d = a <= 6 ? a % 6 + 1 : (a - 7 + 1) % 4 + 7;
            star_pair(x, mod, a, d, bonus, v);
            star_pair(x, mod, d, a, -bonus, v);
        }
    }
    if ((v = Json_Member(section, "choice")) != NULL)
        claim(x, MODS_OVERLAP_STARS, mod, SUB(3) | 2, SET, (uint32_t)hash_letters(Json_String(v, "")), v);
    for (const JsonValue *s = Json_At(Json_Member(section, "stars"), 0); s; s = Json_Next(s)) {
        static const char *const fields[] = {"name", "icon", "palette"};
        int id = (int)Json_Number(Json_Member(s, "id"), -1);
        if (id < 1 || id > 15) continue;
        for (int f = 0; f < 3; f++)
            if ((v = Json_Member(s, fields[f])) != NULL)
                claim(x, MODS_OVERLAP_STARS, mod, SUB(2) | ((uint64_t)id << 8) | (uint64_t)(f + 1), SET,
                      f == 1 ? own_value(mod) : value_of(v), v);
        for (const JsonValue *t = Json_At(Json_Member(s, "beats"), 0); t; t = Json_Next(t)) {
            int other = star_of(x, t);
            star_pair(x, mod, id, other, bonus, t);
            star_pair(x, mod, other, id, -bonus, t);
        }
    }
    for (const JsonValue *m = Json_At(Json_Member(section, "matchups"), 0); m; m = Json_Next(m)) {
        int a = star_of(x, Json_Member(m, "attacker")), d = star_of(x, Json_Member(m, "defender"));
        long points = Json_Member(m, "bonus") ? Json_Number(Json_Member(m, "bonus"), bonus) : bonus;
        star_pair(x, mod, a, d, points, m);
        if (Json_Bool(Json_Member(m, "mirror"), 0)) star_pair(x, mod, d, a, -points, m);
    }
}

/* "limits" (and "chest_overflow"): each key the latest mod's; two mods'
 * entries for different duelists add up. */
static void limit_claim(ModsOverlaps *x, int mod, const char *path, const JsonValue *v)
{
    char label[200];
    snprintf(label, sizeof(label), "Limit %s", path);
    labelled(x, claim(x, MODS_OVERLAP_LIMITS, mod, hash_text(path), SET, value_of(v), v), label);
}
static void limit_tree(ModsOverlaps *x, int mod, const char *path, const JsonValue *v)
{
    char inner[200];
    if (Json_TypeOf(v) != JSON_OBJECT) {
        limit_claim(x, mod, path, v);
        return;
    }
    for (const JsonValue *m = Json_At(v, 0); m; m = Json_Next(m)) {
        snprintf(inner, sizeof(inner), "%s.%.60s", path, Json_Name(m));
        if (!strcmp(path, "life_points.duelists")) {
            /* By opponent, however it is named: a number or an object, one setting. */
            uint64_t who = duelist_key(x, Json_Name(m));
            char key[200], label[220];
            snprintf(key, sizeof(key), "life_points.duelists.#%llx", (unsigned long long)who);
            snprintf(label, sizeof(label), "Limit %s", inner);
            labelled(x, claim(x, MODS_OVERLAP_LIMITS, mod, hash_text(key), SET, value_of(m), m), label);
        } else
            limit_tree(x, mod, inner, m);
    }
}
static void read_limits(ModsOverlaps *x, int mod)
{
    const JsonValue *limits = member(x, mod, "limits"), *overflow = member(x, mod, "chest_overflow");
    for (const JsonValue *m = Json_At(limits, 0); m; m = Json_Next(m)) {
        if (!strcmp(Json_Name(m), "life_points") && Json_TypeOf(m) == JSON_NUMBER)
            limit_claim(x, mod, "life_points.start", m);
        else
            limit_tree(x, mod, Json_Name(m), m);
    }
    /* chest_overflow's "limit" is "limits": {"chest"} by another name. */
    if (Json_Member(overflow, "limit")) limit_claim(x, mod, "chest", Json_Member(overflow, "limit"));
    if (Json_Member(overflow, "starchips"))
        limit_claim(x, mod, "chest_overflow.starchips", Json_Member(overflow, "starchips"));
}

/* "terrain_bonus": a terrain and a monster type; "replace" clears every
 * pair the earlier mods set. */
static int terrain_named(const char *name)
{
    static const char *const names[][2] = {{"Forest", NULL},     {"Wasteland", NULL}, {"Mountain", NULL},
                                           {"Sogen", "Meadow"}, {"Umi", "Sea"},       {"Yami", "Dark"}};
    for (int i = 0; i < 6; i++)
        if (same_letters(name, names[i][0]) || (names[i][1] && same_letters(name, names[i][1]))) return i + 1;
    if (*name && strspn(name, "0123456789") == strlen(name)) return atoi(name);
    return -1;
}
static const char *const terrain_names[] = {"", "Forest", "Wasteland", "Mountain", "Sogen", "Umi", "Yami"};
static void read_terrain(ModsOverlaps *x, int mod)
{
    const JsonValue *table = member(x, mod, "terrain_bonus");
    if (Json_Bool(Json_Member(table, "replace"), 0)) {
        Claim *c = claim(x, MODS_OVERLAP_TERRAIN, mod, SUB(RESET_SUB), SET, 0, Json_Member(table, "replace"));
        if (c) {
            c->mask = SUB_MASK;
            c->match = SUB(1);
            c->flags |= RESETS;
        }
        labelled(x, c, "Every terrain bonus (\"replace\")");
    }
    for (const JsonValue *t = Json_At(table, 0); t; t = Json_Next(t)) {
        int terrain = terrain_named(Json_Name(t));
        if (terrain < 1 || terrain > 6 || Json_TypeOf(t) != JSON_OBJECT) continue;
        for (const JsonValue *type = Json_At(t, 0); type; type = Json_Next(type)) {
            char label[160];
            snprintf(label, sizeof(label), "%s bonus of %.60s", terrain_names[terrain], Json_Name(type));
            labelled(x,
                     claim(x, MODS_OVERLAP_TERRAIN, mod,
                           SUB(1) | ((uint64_t)terrain << 48) | (hash_letters(Json_Name(type)) >> 16), SET,
                           value_of(type), type),
                     label);
        }
    }
}

/* "trap_thresholds": a trap's threshold, the latest mod's. */
static void read_traps(ModsOverlaps *x, int mod)
{
    for (const JsonValue *t = Json_At(member(x, mod, "trap_thresholds"), 0); t; t = Json_Next(t)) {
        uint64_t key = card_text(x, Json_Name(t));
        if (key) claim(x, MODS_OVERLAP_TRAPS, mod, key, SET, value_of(t), t);
    }
}

/* The duelists/ folder (notes/more-duelists.md): the later of two mods
 * replacing one duelist has him; of two asking for one slot, the earlier
 * keeps it. */
static void read_duelists(ModsOverlaps *x, int mod)
{
    char *names = folder_names(x, mod, "duelists"), relative[160], label[200];
    for (const char *name = names; name && *name; name += strlen(name) + 1) {
        const JsonValue *root, *replaced, *slot;
        snprintf(relative, sizeof(relative), "duelists/%.100s.json", name);
        if (!(root = mod_file(x, mod, relative))) continue;
        if ((replaced = Json_Member(root, "replace")) != NULL) {
            const char *who = Json_String(replaced, "");
            char number[24];
            if (Json_TypeOf(replaced) == JSON_NUMBER) {
                snprintf(number, sizeof(number), "%ld", Json_Number(replaced, 0));
                who = number;
            }
            snprintf(label, sizeof(label), "Duelist '%.80s' replaced", who);
            labelled(x, claim(x, MODS_OVERLAP_DUELISTS, mod, (1ull << 62) | duelist_key(x, who), SET, own_value(mod), root),
                     label);
        }
        if ((slot = Json_Member(root, "slot")) != NULL && Json_TypeOf(slot) == JSON_NUMBER) {
            snprintf(label, sizeof(label), "Free Duel slot %ld", Json_Number(slot, 0));
            labelled(x,
                     claim(x, MODS_OVERLAP_DUELISTS, mod, (2ull << 62) | (uint64_t)Json_Number(slot, 0), FIRST,
                           own_value(mod), root),
                     label);
        }
    }
    free(names);
}

/* "text": the listings' strings by id (translation.c: a later string with
 * the same id replaces an earlier one). The value is the string's text, so
 * two mods with the same words agree. */
static void text_file(ModsOverlaps *x, int mod, const char *path)
{
    FILE *file = fopen(path, "rb");
    char line[4096];
    long id = -1;
    uint32_t value = 2166136261u;
    Claim *open = NULL;
    if (!file) return;
    while (fgets(line, sizeof(line), file)) {
        size_t n = strlen(line);
        while (n && (line[n - 1] == '\n' || line[n - 1] == '\r')) line[--n] = 0;
        if (line[0] == '[' || line[0] == '@') {
            char *end;
            if (open) open->value = value;
            open = NULL;
            if (line[0] == '@') continue;
            id = strtol(line + 1, &end, 16);
            if (*end != ']' || id < 0) continue;
            value = 2166136261u;
            open = claim(x, MODS_OVERLAP_TEXT, mod, (uint64_t)id, SET, 0, NULL);
        } else if (open && line[0] && line[0] != '#')
            value = (uint32_t)fnv(value * 31u, line);
    }
    if (open) open->value = value;
    fclose(file);
}
static void read_text(ModsOverlaps *x, int mod)
{
    const JsonValue *text = member(x, mod, "text");
    const JsonValue *one = Json_TypeOf(text) == JSON_ARRAY ? Json_At(text, 0) : text;
    char path[1024];
    for (; one; one = Json_TypeOf(text) == JSON_ARRAY ? Json_Next(one) : NULL) {
        const char *name = Json_String(one, Json_String(Json_Member(one, "file"), NULL));
        if (name && x->mods[mod].directory && Paths_Contained(name) && switched_on(x, mod, one) &&
            snprintf(path, sizeof(path), "%s/%s", x->mods[mod].directory, name) < (int)sizeof(path))
            text_file(x, mod, path);
    }
}

/* "title" and "menu": each key the latest mod's; the title's "text" lines
 * add up; a button belongs to the mod that makes it, and another changes it
 * by naming it "<mod id>:<id>" (title_config.c). */
static void title_tree(ModsOverlaps *x, int mod, const char *path, const JsonValue *v, int mode, int flags)
{
    char inner[256];
    if (Json_TypeOf(v) != JSON_OBJECT) {
        Claim *c = claim(x, MODS_OVERLAP_TITLE, mod, hash_text(path), mode, value_of(v), v);
        if (c) c->flags |= (unsigned char)flags;
        labelled(x, c, path);
        return;
    }
    for (const JsonValue *m = Json_At(v, 0); m; m = Json_Next(m)) {
        snprintf(inner, sizeof(inner), "%s.%.60s", path, Json_Name(m));
        title_tree(x, mod, inner, m, mode, flags);
    }
}
static void read_title(ModsOverlaps *x, int mod)
{
    const JsonValue *title = member(x, mod, "title"), *menu = member(x, mod, "menu");
    for (const JsonValue *m = Json_At(title, 0); m; m = Json_Next(m)) {
        char path[128];
        snprintf(path, sizeof(path), "title.%.60s", Json_Name(m));
        if (!strcmp(Json_Name(m), "text"))
            labelled(x, claim(x, MODS_OVERLAP_TITLE, mod, hash_text(path), ADD, 0, m), "title.text (lines)");
        else
            title_tree(x, mod, path, m, SET, 0);
    }
    for (const JsonValue *m = Json_At(menu, 0); m; m = Json_Next(m)) {
        char path[160];
        if (!strcmp(Json_Name(m), "buttons")) {
            for (const JsonValue *b = Json_At(m, 0); b; b = Json_Next(b)) {
                const char *id = Json_String(Json_Member(b, "id"), "");
                size_t own = strlen(x->mods[mod].id);
                int theirs = strchr(id, ':') && !(strncmp(id, x->mods[mod].id, own) == 0 && id[own] == ':');
                if (strchr(id, ':'))
                    snprintf(path, sizeof(path), "menu.buttons.%.100s", id);
                else
                    snprintf(path, sizeof(path), "menu.buttons.%.60s:%.60s", x->mods[mod].id, id);
                for (const JsonValue *k = Json_At(b, 0); k; k = Json_Next(k)) {
                    char leaf[256];
                    if (!strcmp(Json_Name(k), "id")) continue;
                    snprintf(leaf, sizeof(leaf), "%s.%.60s", path, Json_Name(k));
                    title_tree(x, mod, leaf, k, theirs ? SET : BASE, theirs ? AIMED : 0);
                }
            }
        } else if (!strcmp(Json_Name(m), "order") && Json_TypeOf(m) == JSON_ARRAY)
            title_tree(x, mod, "menu.order.first", m, SET, 0);
        else {
            snprintf(path, sizeof(path), "menu.%.60s", Json_Name(m));
            title_tree(x, mod, path, m, SET, 0);
        }
    }
}

/* Code: function hooks chain, the mod applied last called first; event
 * subscribers are all called, by priority. */
static void read_code(ModsOverlaps *x)
{
    char label[200], text[160];
    int mod;
    uint64_t what;
    for (int kind = 0; kind < 2; kind++) {
        int (*next)(int, int *, uint64_t *, char *, size_t, void *) = kind ? x->source.event : x->source.hook;
        for (int i = 0; next && next(i, &mod, &what, text, sizeof(text), x->source.context); i++) {
            if (mod < 0 || mod >= x->mod_count) continue;
            snprintf(label, sizeof(label), kind ? "%s event" : "Function %s", text);
            labelled(x, claim(x, kind ? MODS_OVERLAP_EVENTS : MODS_OVERLAP_HOOKS, mod, what, kind ? EVENT : CHAIN, 0, NULL),
                     label);
        }
    }
}

/* --- wide claims and grouping ------------------------------------------- */

static int by_key(const void *left, const void *right)
{
    const Claim *a = left, *b = right;
    if (a->kind != b->kind) return a->kind < b->kind ? -1 : 1;
    if (a->key != b->key) return a->key < b->key ? -1 : 1;
    if (a->mod != b->mod) return a->mod < b->mod ? -1 : 1;
    return (a->seq > b->seq) - (a->seq < b->seq);
}

/* A wide claim stands beside each key of its kind another mod names that
 * it covers, as a copy marked VIA_WIDE. */
static void widen(ModsOverlaps *x)
{
    int count = x->claim_count, wide = 0;
    for (int i = 0; i < count; i++) wide += x->claims[i].mask != 0;
    if (!wide) return;
    qsort(x->claims, (size_t)count, sizeof(*x->claims), by_key);
    for (int w = 0; w < count; w++) {
        Claim spread = x->claims[w];
        int emitted = 0;
        uint64_t last = 0;
        if (!spread.mask) continue;
        for (int i = 0; i < count; i++) {
            Claim c = x->claims[i], *copy;
            if (c.kind != spread.kind || c.mask || c.mod == spread.mod || (c.key & spread.mask) != spread.match ||
                (emitted && c.key == last))
                continue;
            if (!(copy = claim(x, spread.kind, spread.mod, c.key, spread.mode, spread.value, spread.src))) return;
            copy->seq = spread.seq;
            copy->label = spread.label;
            copy->flags = (unsigned char)(spread.flags | VIA_WIDE);
            emitted = 1;
            last = c.key;
        }
    }
}

static int declared(const ModsOverlaps *x, int winner, int other)
{
    return x->declared[winner * x->mod_count + other];
}

/* Where a mod's entry for one card sets a key another mod's sets
 * differently: those keys of the winner's, and whether any key met at all. */
static int card_keys(const ModsOverlaps *x, const Group *g, char *out, size_t size, int *met)
{
    const Claim *c = &x->claims[g->first];
    int conflicts = 0;
    size_t length = 0;
    if (out && size) *out = 0;
    *met = 0;
    for (int i = 0; i < g->count; i++) {
        if (c[i].mode != SET) continue;
        for (const JsonValue *k = Json_At(c[i].src, 0); k; k = Json_Next(k)) {
            const char *name = Json_Name(k);
            int differs = 0, later = 0;
            if (!strcmp(name, "replace") || !strcmp(name, "notes") || !strcmp(name, "id")) continue;
            for (int j = 0; j < g->count; j++) {
                const JsonValue *other;
                if (c[j].mode != SET || c[j].mod == c[i].mod || !(other = Json_Member(c[j].src, name))) continue;
                if (j > i) later = 1;
                else {
                    *met = 1;
                    differs |= value_of(other) != value_of(k);
                }
            }
            if (differs && !later) {
                conflicts++;
                if (out && length + strlen(name) + 3 < size)
                    length += (size_t)snprintf(out + length, size - length, "%s%s", length ? ", " : "", name);
            }
        }
    }
    return conflicts;
}

/* The equip entries meeting on one equip card: whether the later says
 * something different about a monster, a type or a bonus the earlier
 * named; whether they said the same about one. */
static void equip_targets(const JsonValue *entry, int pass, const JsonValue **list)
{
    *list = Json_Member(entry, pass == 0 ? "add" : pass == 1 ? "remove" : "bonus_if");
}
static int equips_meet(ModsOverlaps *x, const Group *g, int *agree)
{
    const Claim *c = &x->claims[g->first];
    *agree = 0;
    for (int i = 0; i < g->count; i++)
        for (int j = i + 1; j < g->count; j++) {
            if (c[i].mod == c[j].mod) continue;
            if (Json_Member(c[i].src, "bonus") && Json_Member(c[j].src, "bonus")) {
                if (value_of(Json_Member(c[i].src, "bonus")) != value_of(Json_Member(c[j].src, "bonus"))) return 1;
                *agree = 1;
            }
            for (int p = 0; p < 3; p++)
                for (int q = 0; q < 3; q++) {
                    const JsonValue *a, *b;
                    if ((p == 2) != (q == 2)) continue;
                    equip_targets(c[i].src, p, &a);
                    equip_targets(c[j].src, q, &b);
                    for (const JsonValue *s = Json_At(a, 0); s; s = Json_Next(s))
                        for (const JsonValue *t = Json_At(b, 0); t; t = Json_Next(t)) {
                            int same = p == 2 ? same_letters(Json_Name(s), Json_Name(t)) : card_key(x, s) == card_key(x, t);
                            if (!same) continue;
                            if (p == 2 ? value_of(s) != value_of(t) : p != q) return 1;
                            *agree = 1;
                        }
                }
        }
    return 0;
}

/* Two patches from different mods over the same bytes. */
static long patch_length(const JsonValue *patch)
{
    long digits = 0;
    for (const char *s = Json_String(Json_Member(patch, "bytes"), ""); *s; s++) digits += isxdigit((unsigned char)*s) != 0;
    return digits / 2;
}
static int patches_meet(const Claim *a, const Claim *b)
{
    for (const JsonValue *p = Json_At(Json_Member(a->src, "patch"), 0); p; p = Json_Next(p))
        for (const JsonValue *q = Json_At(Json_Member(b->src, "patch"), 0); q; q = Json_Next(q)) {
            long pa = Json_Number(Json_Member(p, "at"), 0), qa = Json_Number(Json_Member(q, "at"), 0);
            if (pa < qa + patch_length(q) && qa < pa + patch_length(p)) return 1;
        }
    return 0;
}

static void decide(ModsOverlaps *x, Group *g)
{
    const Claim *c = &x->claims[g->first];
    int last = -1, fixed = -1, i, losers = 0, agree = 1, all_declared = 1;
    g->winner = g->other = -1;
    g->severity = MODS_OVERLAP_WARNING;
    switch (g->kind) {
    case MODS_OVERLAP_HOOKS:
        g->winner = c[g->count - 1].mod;
        g->outcome = O_CHAIN;
        return;
    case MODS_OVERLAP_EVENTS:
        g->outcome = O_EVENTS;
        g->severity = MODS_OVERLAP_INFO;
        return;
    case MODS_OVERLAP_DATA: {
        int replaced = -1, other = -1;
        for (i = 0; i < g->count; i++)
            if (c[i].mode == SET) {
                if (replaced >= 0 && c[replaced].mod != c[i].mod) other = c[replaced].mod;
                replaced = i;
            }
        if (other >= 0) {
            g->winner = c[replaced].mod;
            g->other = other;
            g->outcome = declared(x, g->winner, other) ? O_AFTER : O_LATER;
            g->severity = g->outcome == O_AFTER ? MODS_OVERLAP_INFO : MODS_OVERLAP_WARNING;
            return;
        }
        for (i = g->count - 1; i >= 0; i--)
            for (int j = 0; j < i; j++)
                if (c[i].mode == ADD && c[j].mode == ADD && c[i].mod != c[j].mod && patches_meet(&c[i], &c[j])) {
                    g->winner = c[i].mod;
                    g->other = c[j].mod;
                    g->outcome = O_BYTES;
                    return;
                }
        g->outcome = O_ADD;
        g->severity = MODS_OVERLAP_INFO;
        return;
    }
    default:
        break;
    }
    for (i = 0; i < g->count; i++) {
        if (c[i].mode == FIXED) fixed = i;
        if (c[i].mode == SET || c[i].mode == FIXED) last = i;
    }
    if (g->kind == MODS_OVERLAP_DUELISTS && c[0].mode == FIRST) {
        g->winner = c[0].mod;
        g->outcome = O_FIRST;
        return;
    }
    if (fixed >= 0) {
        g->winner = c[fixed].mod;
        for (i = 0; i < g->count; i++)
            if (c[i].mod != g->winner && (c[i].mode != FIXED || c[i].value != c[fixed].value)) agree = 0;
        g->outcome = agree ? O_AGREE : O_FIXED;
        g->severity = agree ? MODS_OVERLAP_INFO : MODS_OVERLAP_WARNING;
        return;
    }
    if (last < 0) {
        /* Only additions, and maybe the owner's own definition. */
        g->outcome = O_ADD;
        g->severity = MODS_OVERLAP_INFO;
        return;
    }
    g->winner = c[last].mod;
    for (i = 0; i < last; i++) {
        if (c[i].mod == g->winner) continue;
        if (c[i].mode == BASE) {
            g->other = c[i].mod;
            continue;
        }
        losers++;
        g->other = c[i].mod;
        if (c[i].mode != SET || c[i].value != c[last].value) agree = 0;
        if (!declared(x, g->winner, c[i].mod)) all_declared = 0;
    }
    if (!losers) {
        /* The one change is the only one, on top of what the others add, or
         * of a card or button another mod made (its BASE). */
        for (i = 0; i < g->count; i++)
            if (c[i].mode == BASE && c[i].mod != g->winner) g->other = c[i].mod;
        g->outcome = g->other >= 0 ? O_AIMED : O_ADD;
        g->severity = MODS_OVERLAP_INFO;
        return;
    }
    if (g->kind == MODS_OVERLAP_CARDS) {
        int met, conflicts = card_keys(x, g, NULL, 0, &met);
        if (!conflicts) {
            g->outcome = met ? O_AGREE : O_ADD;
            g->severity = MODS_OVERLAP_INFO;
            return;
        }
        g->outcome = O_KEYS;
    } else if (g->kind == MODS_OVERLAP_EQUIPS && c[last].key != DEFAULT_EQUIP_BONUS) {
        int same;
        if (Json_Bool(Json_Member(c[last].src, "replace"), 0))
            g->outcome = O_RESET;
        else if (equips_meet(x, g, &same))
            g->outcome = O_LATER;
        else {
            g->outcome = same ? O_AGREE : O_ADD;
            g->severity = MODS_OVERLAP_INFO;
            return;
        }
    } else if (agree) {
        g->outcome = O_AGREE;
        g->severity = MODS_OVERLAP_INFO;
        return;
    } else
        g->outcome = c[last].flags & RESETS ? O_RESET : O_LATER;
    if (all_declared) {
        g->outcome = O_AFTER;
        g->severity = MODS_OVERLAP_INFO;
    }
}

/* Within a kind, the warnings first, then as the earliest mod's manifest
 * has them (its claims come first in a group). */
static const Claim *sorting;
static int by_severity(const void *left, const void *right)
{
    const Group *a = left, *b = right;
    int sa = sorting[a->first].seq, sb = sorting[b->first].seq;
    if (a->kind != b->kind) return a->kind < b->kind ? -1 : 1;
    if (a->severity != b->severity) return a->severity > b->severity ? -1 : 1;
    if (sa != sb) return sa < sb ? -1 : 1;
    return (a->first > b->first) - (a->first < b->first);
}

static void group(ModsOverlaps *x)
{
    int start = 0;
    if (!x->claim_count) return;
    qsort(x->claims, (size_t)x->claim_count, sizeof(*x->claims), by_key);
    x->groups = NULL;
    for (int i = 1; i <= x->claim_count; i++) {
        const Claim *a = &x->claims[start];
        int mods = 0, room;
        if (i < x->claim_count && x->claims[i].kind == a->kind && x->claims[i].key == a->key) continue;
        for (int j = start + 1; j < i; j++) mods += x->claims[j].mod != x->claims[j - 1].mod;
        if (mods) {
            Group *g, *groups;
            room = x->group_count;
            groups = realloc(x->groups, (size_t)(room + 1) * sizeof(*groups));
            if (!groups) {
                x->failed = 1;
                return;
            }
            x->groups = groups;
            g = &groups[x->group_count++];
            g->first = start;
            g->count = i - start;
            g->kind = a->kind;
            decide(x, g);
        }
        start = i;
    }
    sorting = x->claims;
    if (x->group_count) qsort(x->groups, (size_t)x->group_count, sizeof(*x->groups), by_severity);
}

ModsOverlaps *Mods_OverlapCompute(const ModsOverlapMod *mods, int count, const ModsOverlapSource *source)
{
    ModsOverlaps *x = calloc(1, sizeof(*x));
    int identities;
    if (!x) return NULL;
    if (source) x->source = *source;
    x->mod_count = count;
    x->mods = calloc((size_t)(count ? count : 1), sizeof(*x->mods));
    x->declared = calloc((size_t)(count ? count * count : 1), 1);
    if (!x->mods || !x->declared) {
        Mods_OverlapFree(x);
        return NULL;
    }
    memcpy(x->mods, mods, (size_t)count * sizeof(*mods));
    for (int w = 0; w < count; w++)
        for (int k = 0; k < 2; k++)
            for (const JsonValue *v = Json_At(member(x, w, k ? "requires" : "after"), 0); v; v = Json_Next(v)) {
                const char *id = Json_String(v, Json_String(Json_Member(v, "id"), ""));
                for (int o = 0; o < count; o++)
                    if (!strcmp(id, mods[o].id)) x->declared[w * count + o] = 1;
            }
    if (count < 2) return x;
    identities = any_identity_replace(x);
    if (having(x, "guardian_stars") >= 2) star_names(x);
    for (int mod = 0; mod < count; mod++) {
        if (having(x, "data") >= 2) read_data(x, mod);
        if (having(x, "audio") >= 2) read_audio(x, mod);
        if (having(x, "textures") >= 2) read_textures(x, mod);
        if (having(x, "cards") >= 2) read_cards(x, mod, identities);
        if (having(x, "fusions") >= 2) read_fusions(x, mod);
        if (having(x, "equips") + having(x, "equip_bonus_default") >= 2) read_equips(x, mod);
        if (having(x, "rituals") >= 2) read_rituals(x, mod);
        read_pools(x, mod);
        if (having(x, "starter") >= 2 && member(x, mod, "starter"))
            claim(x, MODS_OVERLAP_STARTER, mod, 0, ADD, 0, member(x, mod, "starter"));
        if (having(x, "passwords") >= 2) read_passwords(x, mod);
        if (having(x, "guardian_stars") >= 2) read_stars(x, mod);
        if (having(x, "limits") + having(x, "chest_overflow") >= 2) read_limits(x, mod);
        if (having(x, "terrain_bonus") >= 2) read_terrain(x, mod);
        if (having(x, "trap_thresholds") >= 2) read_traps(x, mod);
        read_duelists(x, mod);
        if (having(x, "text") >= 2) read_text(x, mod);
        if (having(x, "font") >= 2 && member(x, mod, "font"))
            claim(x, MODS_OVERLAP_FONT, mod, 0, ADD, 0, member(x, mod, "font"));
        if (having(x, "title") + having(x, "menu") >= 2) read_title(x, mod);
    }
    read_code(x);
    widen(x);
    group(x);
    if (x->failed) {
        Mods_OverlapFree(x);
        return NULL;
    }
    return x;
}

void Mods_OverlapFree(ModsOverlaps *x)
{
    if (!x) return;
    for (int i = 0; i < x->document_count; i++) Json_Free(x->documents[i]);
    free(x->documents);
    free(x->claims);
    free(x->groups);
    free(x->strings);
    free(x->memo);
    free(x->star_names);
    free(x->declared);
    free(x->mods);
    free(x);
}

/* --- lines ---------------------------------------------------------------- */

int Mods_OverlapCount(const ModsOverlaps *x) { return x ? x->group_count : 0; }
int Mods_OverlapKind(const ModsOverlaps *x, int index) { return x->groups[index].kind; }
int Mods_OverlapSeverity(const ModsOverlaps *x, int index) { return x->groups[index].severity; }
const char *Mods_OverlapOutcome(const ModsOverlaps *x, int index) { return outcome_words[x->groups[index].outcome]; }
int Mods_OverlapInvolves(const ModsOverlaps *x, int index, int mod)
{
    const Group *g = &x->groups[index];
    for (int i = 0; i < g->count; i++)
        if (x->claims[g->first + i].mod == mod) return 1;
    return 0;
}

const char *Mods_OverlapKindName(int kind)
{
    static const char *const names[MODS_OVERLAP_KINDS] = {
        "Disc data", "Sounds",   "Texture images", "Cards",        "Fusions",  "Equips",          "Rituals",
        "Drops and decks", "Starter decks", "Passwords", "Guardian Stars", "Limits", "Terrain bonuses",
        "Attack traps", "Duelists", "Text", "Fonts", "Title screen and menus", "Code hooks", "Game events"};
    return kind >= 0 && kind < MODS_OVERLAP_KINDS ? names[kind] : "";
}

static void star_words(const ModsOverlaps *x, int star, char *out, size_t size)
{
    if (star >= 1 && star <= 10) {
        snprintf(out, size, "%s", star_retail[star]);
        return;
    }
    for (int mod = 0; mod < x->mod_count; mod++)
        for (const JsonValue *s = Json_At(Json_Member(member(x, mod, "guardian_stars"), "stars"), 0); s;
             s = Json_Next(s)) {
            const JsonValue *name = Json_Member(s, "name");
            if (Json_Number(Json_Member(s, "id"), -1) != star) continue;
            if (Json_TypeOf(name) == JSON_OBJECT) name = Json_At(name, 0);
            if (Json_String(name, NULL)) {
                snprintf(out, size, "%s", Json_String(name, ""));
                return;
            }
        }
    snprintf(out, size, "Star %d", star);
}

void Mods_OverlapLabel(const ModsOverlaps *x, int index, char *out, size_t size)
{
    const Group *g = &x->groups[index];
    const Claim *c = &x->claims[g->first];
    char a[120], b[120];
    for (int i = 0; i < g->count; i++)
        if (!(x->claims[g->first + i].flags & VIA_WIDE)) {
            c = &x->claims[g->first + i];
            break;
        }
    if (c->label >= 0) {
        snprintf(out, size, "%s", x->strings + c->label);
        return;
    }
    switch (g->kind) {
    case MODS_OVERLAP_DATA: {
        const char *file = Json_String(Json_Member(c->src, "file"), NULL);
        if (file) snprintf(out, size, "File %s", file);
        else snprintf(out, size, "Sector %ld", Json_Number(Json_Member(c->src, "lba"), 0));
        return;
    }
    case MODS_OVERLAP_AUDIO: {
        static const char *const kinds[] = {"Song", "XA clip", "Sound effect"};
        snprintf(out, size, "%s 0x%llX", kinds[(c->key >> 32) % 3], (unsigned long long)(c->key & 0xFFFFFFFFu));
        return;
    }
    case MODS_OVERLAP_TEXTURES:
        snprintf(out, size, "Image %s, %s at 0x%lX",
                 Json_String(Json_Member(c->src, "alias"), Json_String(Json_Member(c->src, "file"), "?")),
                 Json_String(Json_Member(c->src, "archive"), "?"), Json_Number(Json_Member(c->src, "offset"), 0));
        return;
    case MODS_OVERLAP_CARDS:
        card_words(x, Json_Member(c->src, "replace"), a, sizeof(a));
        snprintf(out, size, "Card %s", a);
        return;
    case MODS_OVERLAP_FUSIONS:
        if (Json_Member(c->src, "remove")) {
            card_words(x, Json_Member(c->src, "remove"), a, sizeof(a));
            snprintf(out, size, "Disc recipes for %s removed", a);
        } else {
            const JsonValue *with = Json_Member(c->src, "with");
            card_words(x, Json_At(with, 0), a, sizeof(a));
            card_words(x, Json_Next(Json_At(with, 0)), b, sizeof(b));
            snprintf(out, size, "Fusion %s + %s", a, b);
        }
        return;
    case MODS_OVERLAP_EQUIPS:
        if (c->key == DEFAULT_EQUIP_BONUS) {
            snprintf(out, size, "The default equip bonus");
            return;
        }
        card_words(x, Json_Member(c->src, "card"), a, sizeof(a));
        snprintf(out, size, "Equip %s", a);
        return;
    case MODS_OVERLAP_RITUALS:
        card_words(x, Json_Member(c->src, "card"), a, sizeof(a));
        snprintf(out, size, "Ritual %s", a);
        return;
    case MODS_OVERLAP_STARTER: snprintf(out, size, "Starter decks"); return;
    case MODS_OVERLAP_STARS: {
        int sub = (int)(c->key >> 56), one = (int)((c->key >> 8) & 0xFF), two = (int)(c->key & 0xFF);
        static const char *const fields[] = {"", "name", "icon", "palette"};
        if (sub == 1) {
            star_words(x, one, a, sizeof(a));
            star_words(x, two, b, sizeof(b));
            snprintf(out, size, "Matchup %s attacking %s", a, b);
        } else if (sub == 2) {
            star_words(x, one, a, sizeof(a));
            snprintf(out, size, "The %s of star %d, %s", fields[two & 3], one, a);
        } else if (sub == 3)
            snprintf(out, size, two == 1 ? "The default star bonus" : "How a summon chooses its star");
        else
            snprintf(out, size, "Every matchup (\"replace\")");
        return;
    }
    case MODS_OVERLAP_TRAPS:
        snprintf(out, size, "Attack trap '%s'", Json_Name(c->src) ? Json_Name(c->src) : "?");
        return;
    case MODS_OVERLAP_TEXT: snprintf(out, size, "Text [%04llX]", (unsigned long long)c->key); return;
    case MODS_OVERLAP_FONT: snprintf(out, size, "Fonts"); return;
    default: snprintf(out, size, "?"); return;
    }
}

void Mods_OverlapMods(const ModsOverlaps *x, int index, char *out, size_t size)
{
    const Group *g = &x->groups[index];
    size_t length = 0;
    if (size) *out = 0;
    for (int i = 0; i < g->count; i++) {
        int mod = x->claims[g->first + i].mod;
        if (i && x->claims[g->first + i - 1].mod == mod) continue;
        if (length < size)
            length += (size_t)snprintf(out + length, size - length, "%s%s", length ? ", " : "", x->mods[mod].id);
    }
}

void Mods_OverlapText(const ModsOverlaps *x, int index, char *out, size_t size)
{
    const Group *g = &x->groups[index];
    char label[256], names[512], keys[200];
    const char *winner = g->winner >= 0 ? x->mods[g->winner].name : "",
               *other = g->other >= 0 ? x->mods[g->other].name : "";
    size_t length = 0;
    int distinct = 0, via = 0;
    Mods_OverlapLabel(x, index, label, sizeof(label));
    names[0] = 0;
    for (int i = 0; i < g->count; i++) {
        const Claim *c = &x->claims[g->first + i];
        if (c->mod == g->winner && c->flags & VIA_WIDE) via = 1;
        if (i && x->claims[g->first + i - 1].mod == c->mod) continue;
        distinct++;
        if (length < sizeof(names))
            length += (size_t)snprintf(names + length, sizeof(names) - length, "%s%s", length ? ", " : "",
                                       x->mods[c->mod].name);
    }
    switch (g->outcome) {
    case O_LATER:
        snprintf(out, size, "%s (%s): %s wins (later in load order%s)", label, names, winner,
                 via ? ", through its \"all\"" : "");
        break;
    case O_AFTER:
        snprintf(out, size, "%s (%s): %s wins (it loads after %s on purpose: after/requires)", label, names,
                 winner, other);
        break;
    case O_AGREE:
        snprintf(out, size, "%s (%s): %s", label, names,
                 g->kind == MODS_OVERLAP_CARDS ? "where they set the same key they agree; the rest combines"
                                               : "the same in each, so no difference");
        break;
    case O_ADD:
        snprintf(out, size, "%s (%s): %s apply and add up%s", label, names, distinct > 2 ? "all" : "both",
                 g->kind == MODS_OVERLAP_DATA      ? " (replacements first, then patches of different bytes)"
                 : g->kind == MODS_OVERLAP_CARDS   ? " (they set different keys)"
                 : g->kind == MODS_OVERLAP_POOLS   ? " (each edits the pool as the mods before left it)"
                 : g->kind == MODS_OVERLAP_FONT    ? " (a letter comes from the first font that has it)"
                                                   : "");
        break;
    case O_RESET:
        snprintf(out, size, "%s (%s): %s's \"replace\" clears what the earlier mods set", label, names, winner);
        break;
    case O_FIXED:
        snprintf(out, size, "%s (%s): %s's fixed deck is dealt; the other edits of it are left out", label, names,
                 winner);
        break;
    case O_KEYS: {
        int met;
        card_keys(x, g, keys, sizeof(keys), &met);
        snprintf(out, size, "%s (%s): the later mod's %s %s used; the rest combines", label, names, keys,
                 strchr(keys, ',') ? "are" : "is");
        break;
    }
    case O_BYTES:
        snprintf(out, size, "%s (%s): %s's bytes are read where they patch the same ones", label, names, winner);
        break;
    case O_CHAIN:
        snprintf(out, size, "%s (%s): %s's hook runs first (applied last); the others run only if it calls its original",
                 label, names, winner);
        break;
    case O_EVENTS:
        snprintf(out, size, "%s (%s): each is called, higher priority first; one that handles it stops the rest", label,
                 names);
        break;
    case O_FIRST:
        snprintf(out, size, "%s (%s): %s keeps it, earlier in load order; the others take the next free slot", label,
                 names, winner);
        break;
    case O_AIMED:
        snprintf(out, size, "%s (%s): %s changes %s's own on purpose", label, names, winner, other);
        break;
    }
}
