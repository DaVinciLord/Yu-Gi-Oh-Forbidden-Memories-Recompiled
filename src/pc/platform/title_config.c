/* What the mods' "title" key asks of the title screen (title_screen.h),
 * read from every applied mod's manifest in load order, a later mod's value
 * winning field by field and the text lines adding up. Only the reading is
 * here, with none of the game's structures, so tests/pc/title_config_test.c
 * checks it at the host's own width; title_screen.c applies it. */
#include "title_config.h"
#include "pc/mods/json.h"
#include "pc/mods/mods.h"
#include "paths.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* The retail layout (frontend.c): the entries 32 apart, the first menu's
 * from y 50, the second's from 42. */
enum { SPACING = 32, FIRST_TOP = 50, SECOND_TOP = 42 };
/* About a minute at the title's 60 frames a second before the retail
 * counter, 3000 of D_8009B0D8's ticks, plays the movie again. */
enum { FRAMES_PER_SECOND = 60 };

const char *const TitleConfig_LayerNames[TITLE_LAYERS] = {"logo", "copyright", "prompt"};
const char *const TitleConfig_EntryNames[TITLE_ENTRIES] = {
    "new_game", "load", "duel", "trade", "options",
    "campaign", "free_duel", "build_deck", "library", "password", "save"};

static TitleConfig config;
static int ready;

static void defaults(void)
{
    int i;
    ready = 1;
    memset(&config, 0, sizeof(config));
    config.press_start = 1;
    config.idle_frames = -1;
    config.picture = config.shade = 1;
    config.dim = 0x80;
    config.colour = -1;
    config.tint = 0xFFFFFF;
    for (i = 0; i < TITLE_LAYERS; i++) config.layers[i].tint = 0xFFFFFF;
    for (i = 0; i < TITLE_ENTRIES; i++) config.entries[i].tint = 0xFFFFFF;
    config.spacing = SPACING;
}

/* "#RRGGBB", "RRGGBB" or a number; -1 when it is none of those. */
static long read_colour(const JsonValue *value)
{
    const char *text;
    char *end;
    long colour;
    if (!value) return -1;
    if (Json_TypeOf(value) == JSON_NUMBER) {
        colour = Json_Number(value, -1);
        return colour >= 0 && colour <= 0xFFFFFF ? colour : -1;
    }
    text = Json_String(value, NULL);
    if (!text) return -1;
    if (*text == '#') text++;
    if (strlen(text) != 6) return -1;
    colour = strtol(text, &end, 16);
    return *end ? -1 : colour;
}

static void colour_member(const char *mod, const JsonValue *object, const char *key, uint32_t *out)
{
    const JsonValue *value = Json_Member(object, key);
    long colour;
    if (!value) return;
    colour = read_colour(value);
    if (colour < 0) Mods_Note(mod, "title: \"%s\" is a colour, \"#RRGGBB\"", key);
    else *out = (uint32_t)colour;
}

static void int_member(const JsonValue *object, const char *key, int *out)
{
    const JsonValue *value = Json_Member(object, key);
    if (value) *out = (int)Json_Number(value, *out);
}

static void bool_member(const JsonValue *object, const char *key, int *out)
{
    const JsonValue *value = Json_Member(object, key);
    if (value) *out = Json_Bool(value, *out);
}

/* An entry by its name or its number, 0 to 10; -1 for neither. */
static int entry_index(const char *name)
{
    char *end;
    long number;
    int i;
    for (i = 0; i < TITLE_ENTRIES; i++) {
        if (!strcmp(name, TitleConfig_EntryNames[i])) return i;
    }
    number = strtol(name, &end, 10);
    return *name && !*end && number >= 0 && number < TITLE_ENTRIES ? (int)number : -1;
}

static void read_entries(const char *mod, const JsonValue *entries)
{
    const JsonValue *member;
    if (!entries) return;
    if (Json_TypeOf(entries) != JSON_OBJECT) {
        Mods_Note(mod, "title: \"entries\" is an object of entries by name (\"load\": {\"hide\": true})");
        return;
    }
    for (member = Json_At(entries, 0); member; member = Json_Next(member)) {
        int i = entry_index(Json_Name(member));
        if (i < 0) {
            Mods_Note(mod, "title: no entry \"%s\" (new_game, load, duel, trade, options, campaign, free_duel, "
                           "build_deck, library, password, save)", Json_Name(member));
            continue;
        }
        bool_member(member, "hide", &config.entries[i].hidden);
        int_member(member, "x", &config.entries[i].x);
        if (Json_Member(member, "y")) {
            int_member(member, "y", &config.entries[i].y);
            config.entries[i].set_y = 1;
        }
        colour_member(mod, member, "tint", &config.entries[i].tint);
    }
}

static void read_lines(const char *mod, const JsonValue *list)
{
    const JsonValue *item;
    if (!list) return;
    if (Json_TypeOf(list) != JSON_ARRAY) {
        Mods_Note(mod, "title: \"text\" is a list of lines ({\"text\": \"...\", \"x\": 160, \"y\": 220})");
        return;
    }
    for (item = Json_At(list, 0); item; item = Json_Next(item)) {
        TitleLine *line;
        const char *text = Json_String(Json_Member(item, "text"), NULL), *align, *show;
        if (!text) {
            Mods_Note(mod, "title: a \"text\" line without \"text\"");
            continue;
        }
        if (config.lines >= TITLE_MAX_LINES) {
            Mods_Note(mod, "title: more than %d lines of text; the rest are left out", TITLE_MAX_LINES);
            return;
        }
        line = &config.line[config.lines++];
        snprintf(line->text, sizeof(line->text), "%s", text);
        line->x = 160;
        line->y = 220;
        line->size = 1;
        line->colour = 0xFFFFFF;
        int_member(item, "x", &line->x);
        int_member(item, "y", &line->y);
        int_member(item, "size", &line->size);
        if (line->size < 1) line->size = 1;
        if (line->size > 8) line->size = 8;
        colour_member(mod, item, "color", &line->colour);
        align = Json_String(Json_Member(item, "align"), "center");
        line->align = !strcmp(align, "left") ? TITLE_ALIGN_LEFT : !strcmp(align, "right") ? TITLE_ALIGN_RIGHT : TITLE_ALIGN_CENTRE;
        show = Json_String(Json_Member(item, "show"), "always");
        line->show = !strcmp(show, "press_start") ? TITLE_SHOW_PROMPT : !strcmp(show, "menu") ? TITLE_SHOW_MENU : TITLE_SHOW_ALWAYS;
    }
}

/* "image", "width", "height": a PNG in the mod and, for a sprite, the size
 * to draw it at. */
static void read_image(const char *mod, const char *directory, const char *where, const JsonValue *part,
                       TitleImage *image)
{
    const JsonValue *value = Json_Member(part, "image");
    const char *file;
    if (value) {
        file = Json_String(value, NULL);
        snprintf(image->mod, sizeof(image->mod), "%s", mod);
        if (!file || !*file) {
            image->file[0] = 0;   /* "" or null: the game's own again */
        } else if (!Paths_Contained(file) ||
                   snprintf(image->file, sizeof(image->file), "%s/%s", directory, file) >= (int)sizeof(image->file)) {
            Mods_Note(mod, "title: %s \"image\": %s is outside the mod", where, file);
            image->file[0] = 0;
        }
    }
    int_member(part, "width", &image->width);
    int_member(part, "height", &image->height);
    if (image->width < 0 || image->width > 320) image->width = 0;
    if (image->height < 0 || image->height > 240) image->height = 0;
}

void TitleConfig_Read(const char *mod, const char *directory, const JsonValue *manifest)
{
    const JsonValue *title = Json_Member(manifest, "title"), *part, *member;
    int i;
    if (!title) return;
    if (Json_TypeOf(title) != JSON_OBJECT) {
        Mods_Note(mod, "\"title\" is an object (notes/modding.md, \"The title screen\")");
        return;
    }
    if ((part = Json_Member(title, "music"))) {
        long song = Json_Number(part, -1);
        if (song < 0 || song > 0xFFF) Mods_Note(mod, "title: \"music\" is a song id, 0x000 to 0xFFF");
        else config.song = (int)song;
    }
    bool_member(title, "skip_intro", &config.skip_movie);
    bool_member(title, "press_start", &config.press_start);
    if ((part = Json_Member(title, "idle_seconds"))) {
        long seconds = Json_Number(part, -1);
        if (seconds < 0) Mods_Note(mod, "title: \"idle_seconds\" is 0 (never) or more");
        else config.idle_frames = (int)seconds * FRAMES_PER_SECOND;
    }
    if ((part = Json_Member(title, "background"))) {
        bool_member(part, "picture", &config.picture);
        bool_member(part, "shade", &config.shade);
        colour_member(mod, part, "tint", &config.tint);
        if (Json_Member(part, "color")) {
            long colour = read_colour(Json_Member(part, "color"));
            if (colour < 0) Mods_Note(mod, "title: \"color\" is a colour, \"#RRGGBB\"");
            else config.colour = colour;
        }
        int_member(part, "dim", &config.dim);
        read_image(mod, directory, "background", part, &config.picture_image);
        if (config.dim < 0) config.dim = 0;
        if (config.dim > 0x80) config.dim = 0x80;
    }
    for (i = 0; i < TITLE_LAYERS; i++) {
        if (!(part = Json_Member(title, TitleConfig_LayerNames[i]))) continue;
        bool_member(part, "hide", &config.layers[i].hidden);
        int_member(part, "x", &config.layers[i].x);
        int_member(part, "y", &config.layers[i].y);
        colour_member(mod, part, "tint", &config.layers[i].tint);
        read_image(mod, directory, TitleConfig_LayerNames[i], part, &config.layers[i].image);
    }
    int_member(title, "spacing", &config.spacing);
    read_entries(mod, Json_Member(title, "entries"));
    read_lines(mod, Json_Member(title, "text"));
    for (member = Json_At(title, 0); member; member = Json_Next(member)) {
        static const char *const known[] = {"music", "skip_intro", "press_start", "idle_seconds", "background",
                                            "logo", "copyright", "prompt", "spacing", "entries", "text"};
        size_t k;
        for (k = 0; k < sizeof(known) / sizeof(known[0]); k++) {
            if (!strcmp(Json_Name(member), known[k])) break;
        }
        if (k == sizeof(known) / sizeof(known[0])) Mods_Note(mod, "title: unknown key \"%s\"", Json_Name(member));
    }
}

/* A menu with every entry hidden keeps them all. */
static void keep_one(int base, int count)
{
    int i;
    for (i = base; i < base + count; i++) {
        if (!config.entries[i].hidden) return;
    }
    for (i = base; i < base + count; i++) config.entries[i].hidden = 0;
}

/* The shown entries of a menu one under another, `spacing` apart, around
 * the middle of the retail menu; a "y" of the mod's own stands. */
static void stack(int base, int count, int top)
{
    int shown = 0, i, row = 0, middle = top + (count - 1) * SPACING / 2, first;
    for (i = base; i < base + count; i++) shown += !config.entries[i].hidden;
    first = middle - (shown - 1) * config.spacing / 2;
    for (i = base; i < base + count; i++) {
        if (config.entries[i].hidden) {
            config.entries[i].y = TITLE_PARKED_Y;
            continue;
        }
        if (!config.entries[i].set_y) config.entries[i].y = first + row * config.spacing;
        row++;
    }
}

void TitleConfig_Reset(void)
{
    defaults();
}

void TitleConfig_Finish(void)
{
    keep_one(0, TITLE_FIRST_MENU);
    keep_one(TITLE_FIRST_MENU, TITLE_ENTRIES - TITLE_FIRST_MENU);
    stack(0, TITLE_FIRST_MENU, FIRST_TOP);
    stack(TITLE_FIRST_MENU, TITLE_ENTRIES - TITLE_FIRST_MENU, SECOND_TOP);
}

const TitleConfig *TitleConfig_Load(void)
{
    int i;
    defaults();
    for (i = 0; i < Mods_LoadedCount(); i++) {
        int mod = Mods_Loaded(i);
        if (Mods_Active(mod)) TitleConfig_Read(Mods_Id(mod), Mods_Directory(mod), Mods_Manifest(mod));
    }
    TitleConfig_Finish();
    return &config;
}

const TitleConfig *TitleConfig_Get(void)
{
    if (!ready) defaults();
    return &config;
}

