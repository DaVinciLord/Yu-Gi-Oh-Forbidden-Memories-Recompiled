/* What the mods' "title" and "menu" keys ask of the title screen and its
 * two menus (title_screen.h, title_menu.h), read from every applied mod's
 * manifest in load order, a later mod's value winning field by field and
 * the text lines and buttons adding up. Only the reading is
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
 * from y 50 (its middle 114), the second's from 42 (122). A menu's items
 * stay between TOP and TOP + MOST, closer together when they would not fit. */
enum { SPACING = 32, FIRST_MIDDLE = 50 + 2 * SPACING, SECOND_MIDDLE = 42 + 5 * SPACING / 2, TOP = 16, MOST = 188 };
/* About a minute at the title's 60 frames a second before the retail
 * counter, 3000 of D_8009B0D8's ticks, plays the movie again. */
enum { FRAMES_PER_SECOND = 60 };

const char *const TitleConfig_LayerNames[TITLE_LAYERS] = {"logo", "copyright", "prompt"};
const char *const TitleConfig_EntryNames[TITLE_ENTRIES] = {
    "new_game", "load", "duel", "trade", "options",
    "campaign", "free_duel", "build_deck", "library", "password", "save"};

static TitleConfig config;
static int ready;

static void background_defaults(TitleBackground *background)
{
    memset(background, 0, sizeof(*background));
    background->picture = background->shade = 1;
    background->colour = -1;
    background->tint = 0xFFFFFF;
}

static void defaults(void)
{
    int i;
    ready = 1;
    memset(&config, 0, sizeof(config));
    config.press_start = 1;
    config.idle_frames = -1;
    config.dim = 0x80;
    background_defaults(&config.background[0]);
    background_defaults(&config.background[1]);
    for (i = 0; i < TITLE_LAYERS; i++) config.layers[i].tint = 0xFFFFFF;
    for (i = 0; i < TITLE_ITEMS; i++) {
        TitleItem *item = &config.items[i];
        item->tint = 0xFFFFFF;
        item->action = TITLE_ACTION_OWN;
        if (i >= TITLE_ENTRIES) continue;
        snprintf(item->name, sizeof(item->name), "%s", TitleConfig_EntryNames[i]);
        item->used = 1;
        item->menu = i >= TITLE_FIRST_MENU;
    }
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

/* The key being read, "title" or "menu", for the notes. */
static const char *reading = "title";

static void colour_member(const char *mod, const JsonValue *object, const char *key, uint32_t *out)
{
    const JsonValue *value = Json_Member(object, key);
    long colour;
    if (!value) return;
    colour = read_colour(value);
    if (colour < 0) Mods_Note(mod, "%s: \"%s\" is a colour, \"#RRGGBB\"", reading, key);
    else *out = (uint32_t)colour;
}

static void int_member(const JsonValue *object, const char *key, int *out)
{
    const JsonValue *value = Json_Member(object, key);
    if (value) *out = (int)Json_Number(value, *out);
}

/* "wide_x", "wide_y": a place for widescreen. */
static void read_wide(const JsonValue *object, TitleWide *wide)
{
    if (Json_Member(object, "wide_x")) {
        int_member(object, "wide_x", &wide->x);
        wide->set_x = 1;
    }
    if (Json_Member(object, "wide_y")) {
        int_member(object, "wide_y", &wide->y);
        wide->set_y = 1;
    }
}

static void bool_member(const JsonValue *object, const char *key, int *out)
{
    const JsonValue *value = Json_Member(object, key);
    if (value) *out = Json_Bool(value, *out);
}

/* Every key of `object` is one of `known`, or noted. */
static void only(const char *mod, const char *where, const JsonValue *object, const char *const *known, size_t count)
{
    const JsonValue *member;
    for (member = Json_At(object, 0); member; member = Json_Next(member)) {
        size_t k;
        for (k = 0; k < count; k++) {
            if (!strcmp(Json_Name(member), known[k])) break;
        }
        if (k == count) Mods_Note(mod, "%s: unknown key \"%s\"%s%s", reading, Json_Name(member), *where ? " in " : "", where);
    }
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

/* An item by name: an entry's name or number, a button's "mod:id", or,
 * for `mod` itself, the button's bare id. -1 for none. */
static int item_index(const char *mod, const char *name)
{
    char qualified[TITLE_NAME];
    int i = entry_index(name);
    if (i >= 0) return i;
    if (!strchr(name, ':')) {
        snprintf(qualified, sizeof(qualified), "%s:%s", mod, name);
        name = qualified;
    }
    for (i = TITLE_ENTRIES; i < TITLE_ITEMS; i++) {
        if (config.items[i].used && !strcmp(config.items[i].name, name)) return i;
    }
    return -1;
}

/* "image", "width", "height": a PNG in the mod and, for a sprite, the size
 * to draw it at. `key` names the picture's file ("image" or
 * "selected_image"). */
static void read_image(const char *mod, const char *directory, const char *where, const JsonValue *part,
                       const char *key, TitleImage *image)
{
    const JsonValue *value = Json_Member(part, key);
    const char *file;
    if (value) {
        file = Json_String(value, NULL);
        snprintf(image->mod, sizeof(image->mod), "%s", mod);
        if (!file || !*file) {
            image->file[0] = 0;   /* "" or null: the game's own again */
        } else if (!Paths_Contained(file) ||
                   snprintf(image->file, sizeof(image->file), "%s/%s", directory, file) >= (int)sizeof(image->file)) {
            Mods_Note(mod, "%s: %s \"%s\": %s is outside the mod", reading, where, key, file);
            image->file[0] = 0;
        }
    }
    int_member(part, "width", &image->width);
    int_member(part, "height", &image->height);
    if (image->width < 0 || image->width > 320) image->width = 0;
    if (image->height < 0 || image->height > 240) image->height = 0;
}

static const char *const action_names[] = {"back", "notice", "quit", "debug_menu", "event", "none"};

const char *TitleConfig_ActionName(int action)
{
    if (action >= 0 && action < TITLE_ENTRIES) return TitleConfig_EntryNames[action];
    if (action >= TITLE_ACTION_BACK && action <= TITLE_ACTION_NONE) return action_names[action - TITLE_ACTION_BACK];
    return "its own";
}

/* An action by name: an entry's (what that entry does), or one of
 * action_names. -2 for none. */
static int action_index(const char *name)
{
    size_t i;
    for (i = 0; i < TITLE_ENTRIES; i++) {
        if (!strcmp(name, TitleConfig_EntryNames[i])) return (int)i;
    }
    for (i = 0; i < sizeof(action_names) / sizeof(action_names[0]); i++) {
        if (!strcmp(name, action_names[i])) return TITLE_ACTION_BACK + (int)i;
    }
    return -2;
}

/* The keys an entry and a button share. */
static const char *const item_keys[] = {"hide", "x", "y", "tint", "image", "selected_image", "width", "height",
                                        "label", "action", "value", "notice", "wide_x", "wide_y"};

static void read_item(const char *mod, const char *directory, const JsonValue *part, TitleItem *item)
{
    const JsonValue *value;
    snprintf(item->mod, sizeof(item->mod), "%s", mod);
    bool_member(part, "hide", &item->hidden);
    int_member(part, "x", &item->x);
    if (Json_Member(part, "y")) {
        int_member(part, "y", &item->y);
        item->set_y = 1;
    }
    read_wide(part, &item->wide);
    colour_member(mod, part, "tint", &item->tint);
    read_image(mod, directory, item->name, part, "image", &item->image);
    read_image(mod, directory, item->name, part, "selected_image", &item->selected);
    if ((value = Json_Member(part, "label"))) {
        const char *label = Json_String(value, NULL);
        if (!label) Mods_Note(mod, "%s: %s \"label\" is text", reading, item->name);
        else if (strlen(label) >= sizeof(item->label))
            Mods_Note(mod, "%s: %s \"label\" is longer than %d letters", reading, item->name, TITLE_LABEL - 1);
        snprintf(item->label, sizeof(item->label), "%s", label ? label : "");
    }
    if ((value = Json_Member(part, "action"))) {
        const char *name = Json_String(value, "");
        int action = action_index(name);
        if (action == -2)
            Mods_Note(mod, "%s: %s: no action \"%s\" (an entry's name, back, notice, quit, debug_menu, event or none)",
                      reading, item->name, name);
        else item->action = action;
    }
    int_member(part, "value", &item->value);
    if ((value = Json_Member(part, "notice"))) {
        const char *text = Json_String(value, NULL), *title = "";
        if (!text && Json_TypeOf(value) == JSON_OBJECT) {
            text = Json_String(Json_Member(value, "text"), NULL);
            title = Json_String(Json_Member(value, "title"), "");
        }
        if (!text) {
            Mods_Note(mod, "%s: %s \"notice\" is text, or {\"title\": ..., \"text\": ...}", reading, item->name);
        } else {
            snprintf(item->notice, sizeof(item->notice), "%s", text);
            snprintf(item->notice_title, sizeof(item->notice_title), "%s", title);
            if (item->action == TITLE_ACTION_OWN && item - config.items >= TITLE_ENTRIES) item->action = TITLE_ACTION_NOTICE;
        }
    }
}

static void read_entries(const char *mod, const char *directory, const JsonValue *entries)
{
    const JsonValue *member;
    if (!entries) return;
    if (Json_TypeOf(entries) != JSON_OBJECT) {
        Mods_Note(mod, "%s: \"entries\" is an object of entries by name (\"load\": {\"hide\": true})", reading);
        return;
    }
    for (member = Json_At(entries, 0); member; member = Json_Next(member)) {
        int i = entry_index(Json_Name(member));
        if (i < 0) {
            Mods_Note(mod, "%s: no entry \"%s\" (new_game, load, duel, trade, options, campaign, free_duel, "
                           "build_deck, library, password, save)", reading, Json_Name(member));
            continue;
        }
        read_item(mod, directory, member, &config.items[i]);
        only(mod, Json_Name(member), member, item_keys, sizeof(item_keys) / sizeof(item_keys[0]));
    }
}

/* A button's id: letters, digits, '_' and '-'. */
static int valid_id(const char *id)
{
    if (!*id || strlen(id) > 31) return 0;
    for (; *id; id++) {
        if (!((*id >= 'a' && *id <= 'z') || (*id >= 'A' && *id <= 'Z') || (*id >= '0' && *id <= '9') || *id == '_' ||
              *id == '-'))
            return 0;
    }
    return 1;
}

/* "buttons": a list of buttons, each made the first time its id is seen
 * and changed after; "other-mod:id" changes another mod's. */
static void read_buttons(const char *mod, const char *directory, const JsonValue *list)
{
    const JsonValue *part;
    if (!list) return;
    if (Json_TypeOf(list) != JSON_ARRAY) {
        Mods_Note(mod, "menu: \"buttons\" is a list ({\"id\": \"credits\", \"label\": \"CREDITS\", ...})");
        return;
    }
    for (part = Json_At(list, 0); part; part = Json_Next(part)) {
        static const char *const button_keys[] = {"id", "menu", "hide", "x", "y", "tint", "image", "selected_image",
                                                  "width", "height", "label", "action", "value", "notice", "wide_x",
                                                  "wide_y"};
        const char *id = Json_String(Json_Member(part, "id"), ""), *menu = Json_String(Json_Member(part, "menu"), NULL);
        const char *colon = strchr(id, ':');
        int i = item_index(mod, id);
        TitleItem *item;
        if (i >= 0 && i < TITLE_ENTRIES) {
            Mods_Note(mod, "menu: button \"%s\" has an entry's name; change an entry under \"entries\"", id);
            continue;
        }
        if (i < 0) {
            if (colon || !valid_id(id)) {
                Mods_Note(mod, colon ? "menu: no button \"%s\" to change" :
                                       "menu: a button's \"id\" is letters, digits, '_' and '-' (\"%s\")", id);
                continue;
            }
            for (i = TITLE_ENTRIES; i < TITLE_ITEMS && config.items[i].used; i++) {}
            if (i == TITLE_ITEMS) {
                Mods_Note(mod, "menu: more than %d buttons; \"%s\" is left out", TITLE_MAX_BUTTONS, id);
                continue;
            }
            item = &config.items[i];
            item->used = 1;
            snprintf(item->name, sizeof(item->name), "%s:%s", mod, id);
        }
        item = &config.items[i];
        if (menu) {
            if (!strcmp(menu, "first")) item->menu = 0;
            else if (!strcmp(menu, "second")) item->menu = 1;
            else Mods_Note(mod, "menu: button \"%s\" \"menu\" is \"first\" or \"second\"", id);
        }
        read_item(mod, directory, part, item);
        only(mod, id, part, button_keys, sizeof(button_keys) / sizeof(button_keys[0]));
    }
}

/* "order": the names of one menu's items, top to bottom; {"first": [...],
 * "second": [...]} or, for the first menu, the list alone. Worked out at
 * TitleConfig_Finish, once every mod's buttons are there. */
static void read_order_list(const char *mod, int menu, const JsonValue *list)
{
    const JsonValue *name;
    if (Json_TypeOf(list) != JSON_ARRAY) {
        Mods_Note(mod, "menu: an \"order\" is a list of names ([\"new_game\", \"credits\", ...])");
        return;
    }
    config.order_count[menu] = 0;
    snprintf(config.order_mod[menu], sizeof(config.order_mod[menu]), "%s", mod);
    for (name = Json_At(list, 0); name && config.order_count[menu] < TITLE_ITEMS; name = Json_Next(name)) {
        snprintf(config.order_names[menu][config.order_count[menu]++], TITLE_NAME, "%s", Json_String(name, ""));
    }
}

static void read_order(const char *mod, const JsonValue *order)
{
    if (!order) return;
    if (Json_TypeOf(order) == JSON_OBJECT) {
        static const char *const menus[] = {"first", "second"};
        if (Json_Member(order, "first")) read_order_list(mod, 0, Json_Member(order, "first"));
        if (Json_Member(order, "second")) read_order_list(mod, 1, Json_Member(order, "second"));
        only(mod, "order", order, menus, 2);
        return;
    }
    read_order_list(mod, 0, order);
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
        read_wide(item, &line->wide);
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

/* A "background" object into `background`; `set` gets the parts it gave. */
static void read_background(const char *mod, const char *directory, const JsonValue *part, TitleBackground *background,
                            unsigned *set)
{
    static const char *const known[] = {"picture", "shade", "tint", "color", "dim", "image", "wide", "wide_image"};
    if (Json_TypeOf(part) != JSON_OBJECT) {
        Mods_Note(mod, "%s: \"background\" is an object ({\"image\": \"art/bg.png\"})", reading);
        return;
    }
    if (Json_Member(part, "picture")) *set |= TITLE_BACKGROUND_PICTURE;
    if (Json_Member(part, "shade")) *set |= TITLE_BACKGROUND_SHADE;
    if (Json_Member(part, "tint")) *set |= TITLE_BACKGROUND_TINT;
    if (Json_Member(part, "image")) *set |= TITLE_BACKGROUND_IMAGE;
    if (Json_Member(part, "wide")) *set |= TITLE_BACKGROUND_WIDE;
    if (Json_Member(part, "wide_image")) *set |= TITLE_BACKGROUND_WIDE_IMAGE;
    bool_member(part, "wide", &background->wide);
    read_image(mod, directory, "background", part, "wide_image", &background->wide_image);
    /* A picture for widescreen fills it. */
    if (Json_Member(part, "wide_image") && background->wide_image.file[0] && !Json_Member(part, "wide")) {
        background->wide = 1;
        *set |= TITLE_BACKGROUND_WIDE;
    }
    bool_member(part, "picture", &background->picture);
    bool_member(part, "shade", &background->shade);
    colour_member(mod, part, "tint", &background->tint);
    if (Json_Member(part, "color")) {
        long colour = read_colour(Json_Member(part, "color"));
        if (colour < 0) {
            Mods_Note(mod, "%s: \"color\" is a colour, \"#RRGGBB\"", reading);
        } else {
            background->colour = colour;
            *set |= TITLE_BACKGROUND_COLOUR;
        }
    }
    int_member(part, "dim", &config.dim);
    read_image(mod, directory, "background", part, "image", &background->image);
    if (config.dim < 0) config.dim = 0;
    if (config.dim > 0x80) config.dim = 0x80;
    only(mod, "background", part, known, sizeof(known) / sizeof(known[0]));
}

static void read_title(const char *mod, const char *directory, const JsonValue *title)
{
    static const char *const known[] = {"music", "skip_intro", "press_start", "idle_seconds", "background",
                                        "logo", "copyright", "prompt", "spacing", "entries", "text"};
    static const char *const layer_keys[] = {"hide", "x", "y", "tint", "image", "width", "height", "show", "wide_x",
                                             "wide_y"};
    const JsonValue *part;
    unsigned set = 0;
    int i;
    reading = "title";
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
    if ((part = Json_Member(title, "background"))) read_background(mod, directory, part, &config.background[0], &set);
    for (i = 0; i < TITLE_LAYERS; i++) {
        const char *show;
        if (!(part = Json_Member(title, TitleConfig_LayerNames[i]))) continue;
        bool_member(part, "hide", &config.layers[i].hidden);
        int_member(part, "x", &config.layers[i].x);
        int_member(part, "y", &config.layers[i].y);
        read_wide(part, &config.layers[i].wide);
        colour_member(mod, part, "tint", &config.layers[i].tint);
        read_image(mod, directory, TitleConfig_LayerNames[i], part, "image", &config.layers[i].image);
        if ((show = Json_String(Json_Member(part, "show"), NULL))) {
            if (!strcmp(show, "always")) config.layers[i].show = TITLE_SHOW_ALWAYS;
            else if (!strcmp(show, "press_start")) config.layers[i].show = TITLE_SHOW_PROMPT;
            else if (!strcmp(show, "menu") && i != 2) config.layers[i].show = TITLE_SHOW_MENU;
            else Mods_Note(mod, "title: %s \"show\" is always, press_start%s", TitleConfig_LayerNames[i],
                           i != 2 ? " or menu" : "");
        }
        only(mod, TitleConfig_LayerNames[i], part, layer_keys, sizeof(layer_keys) / sizeof(layer_keys[0]));
    }
    int_member(title, "spacing", &config.spacing);
    read_entries(mod, directory, Json_Member(title, "entries"));
    read_lines(mod, Json_Member(title, "text"));
    only(mod, "", title, known, sizeof(known) / sizeof(known[0]));
}

static void read_menu(const char *mod, const char *directory, const JsonValue *menu)
{
    static const char *const known[] = {"background", "spacing", "entries", "buttons", "order"};
    const JsonValue *part;
    reading = "menu";
    if ((part = Json_Member(menu, "background"))) read_background(mod, directory, part, &config.background[1], &config.menu_set);
    int_member(menu, "spacing", &config.spacing);
    read_entries(mod, directory, Json_Member(menu, "entries"));
    read_buttons(mod, directory, Json_Member(menu, "buttons"));
    read_order(mod, Json_Member(menu, "order"));
    only(mod, "", menu, known, sizeof(known) / sizeof(known[0]));
}

void TitleConfig_Read(const char *mod, const char *directory, const JsonValue *manifest)
{
    const JsonValue *title = Json_Member(manifest, "title"), *menu = Json_Member(manifest, "menu");
    if (title && Json_TypeOf(title) != JSON_OBJECT)
        Mods_Note(mod, "\"title\" is an object (notes/modding.md, \"The title screen\")");
    else if (title)
        read_title(mod, directory, title);
    if (menu && Json_TypeOf(menu) != JSON_OBJECT)
        Mods_Note(mod, "\"menu\" is an object (notes/modding.md, \"The title's menus\")");
    else if (menu)
        read_menu(mod, directory, menu);
    reading = "title";
}

int TitleConfig_Drawn(const TitleItem *item)
{
    return item->image.file[0] || item->label[0];
}

/* Whether `action` can be chosen from `menu`: the choices that open a
 * dialog in the menu itself (load, 2P duel and trade in the first, save in
 * the second) stay in their own, and those that need a game loaded
 * (campaign to password) are the second's. */
static int allowed(int action, int menu)
{
    if (action == TITLE_ACTION_OWN || action >= TITLE_ACTION_BACK) return 1;
    if (action == 0 || action == 4) return 1;
    return menu == 0 ? action < TITLE_FIRST_MENU : action >= TITLE_FIRST_MENU;
}

/* A menu's items in order: the "order" list's first, then the rest as the
 * game has its entries and the mods made their buttons. */
static void arrange(int menu)
{
    int list[TITLE_ITEMS], count = 0, placed[TITLE_ITEMS] = {0}, i, n;
    const char *mod = config.order_mod[menu];
    for (n = 0; n < config.order_count[menu]; n++) {
        const char *name = config.order_names[menu][n];
        i = item_index(mod, name);
        if (i < 0 || !config.items[i].used) {
            Mods_Note(mod, "menu: \"order\" names \"%s\", which is not an entry or a button", name);
            continue;
        }
        if (config.items[i].menu != menu) {
            Mods_Note(mod, "menu: \"order\" puts \"%s\" in the %s menu; it is in the %s", name,
                      menu ? "second" : "first", menu ? "first" : "second");
            continue;
        }
        if (!placed[i]) list[count++] = i;
        placed[i] = 1;
    }
    for (i = 0; i < TITLE_ITEMS; i++) {
        if (config.items[i].used && config.items[i].menu == menu && !placed[i]) list[count++] = i;
    }
    config.shown[menu] = 0;
    for (n = 0; n < count; n++) {
        if (!config.items[list[n]].hidden) config.order[menu][config.shown[menu]++] = list[n];
    }
    /* Nothing left to choose: the game's own entries back. */
    if (!config.shown[menu]) {
        for (n = 0; n < count; n++) {
            if (list[n] < TITLE_ENTRIES) {
                config.items[list[n]].hidden = 0;
                config.order[menu][config.shown[menu]++] = list[n];
            }
        }
    }
}

/* The shown items one under another, `spacing` apart (closer when they
 * would not fit), around the middle of the retail menu; a "y" of the mod's
 * own stands. */
static void stack(int menu, int middle)
{
    int shown = config.shown[menu], spacing = config.spacing, first, row, i;
    if (shown > 1 && (shown - 1) * spacing > MOST) spacing = MOST / (shown - 1);
    first = middle - (shown - 1) * spacing / 2;
    if (first < TOP) first = TOP;
    if (first + (shown - 1) * spacing > TOP + MOST) first = TOP + MOST - (shown - 1) * spacing;
    for (i = 0; i < TITLE_ITEMS; i++) {
        if (config.items[i].used && config.items[i].menu == menu && config.items[i].hidden) config.items[i].y = TITLE_PARKED_Y;
    }
    for (row = 0; row < shown; row++) {
        TitleItem *item = &config.items[config.order[menu][row]];
        if (!item->set_y) item->y = first + row * spacing;
    }
}

void TitleConfig_Reset(void)
{
    defaults();
}

void TitleConfig_Finish(void)
{
    TitleBackground menu = config.background[0], *given = &config.background[1];
    int i;
    for (i = 0; i < TITLE_ITEMS; i++) {
        TitleItem *item = &config.items[i];
        if (!item->used) continue;
        if (!allowed(item->action, item->menu)) {
            Mods_Note(item->mod, "menu: %s cannot %s from the %s menu", item->name, TitleConfig_ActionName(item->action),
                      item->menu ? "second" : "first");
            item->action = TITLE_ACTION_NONE;
        }
        if (i >= TITLE_ENTRIES && !TitleConfig_Drawn(item)) {
            Mods_Note(item->mod, "menu: button %s has no \"image\" or \"label\"; it shows its id", item->name);
            snprintf(item->label, sizeof(item->label), "%s", strchr(item->name, ':') + 1);
        }
        if (i >= TITLE_ENTRIES && item->action == TITLE_ACTION_OWN) item->action = TITLE_ACTION_NONE;
    }
    arrange(0);
    arrange(1);
    stack(0, FIRST_MIDDLE);
    stack(1, SECOND_MIDDLE);
    /* The menus' background: the title's, but for what "menu" set. */
    if (config.menu_set & TITLE_BACKGROUND_PICTURE) menu.picture = given->picture;
    if (config.menu_set & TITLE_BACKGROUND_SHADE) menu.shade = given->shade;
    if (config.menu_set & TITLE_BACKGROUND_COLOUR) menu.colour = given->colour;
    if (config.menu_set & TITLE_BACKGROUND_TINT) menu.tint = given->tint;
    if (config.menu_set & TITLE_BACKGROUND_IMAGE) menu.image = given->image;
    if (config.menu_set & TITLE_BACKGROUND_WIDE) menu.wide = given->wide;
    if (config.menu_set & TITLE_BACKGROUND_WIDE_IMAGE) menu.wide_image = given->wide_image;
    /* A menu picture of its own without a wide one: not the title's wide one. */
    else if (config.menu_set & TITLE_BACKGROUND_IMAGE) menu.wide_image.file[0] = 0;
    config.background[1] = menu;
    config.menu_set = 0;
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
