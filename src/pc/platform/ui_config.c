/* What the mods' "ui" key asks of the duel's pictures (ui_config.h), read
 * from every applied mod's manifest in load order, a later mod's value
 * winning key by key. Only the reading is here, with none of the game's
 * structures, so tests/pc/ui_config_test.c checks it at the host's own
 * width; pc/cards/duel_ui.c draws what it says. */
#include "ui_config.h"
#include "pc/mods/json.h"
#include "pc/mods/mods.h"
#include "paths.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

const char *const UiConfig_ElementNames[UI_ELEMENTS] = {"lp_opponent", "lp_player",   "field",
                                                         "card_bar",    "hand_cursor", "field_cursor"};

/* What each element takes. The LP halves and the FIELD box are slid off
 * the screen sideways by the game (to x 408 and -116 for a battle and the
 * duel's end, 384 and -64 for Exodia: duel_scene_battle.c,
 * duel_result_runtime.c, func_80018FEC.c), so they are moved up or down
 * only, where they slide with the game's and leave the screen when it
 * does; the card bar, whose words, cards and stars are drawn by others
 * that follow it, takes only its colours, a picture of its own or none;
 * only the LP halves have digits and words. */
enum { TAKES_X = 1, TAKES_Y = 2, TAKES_SCALE = 4, TAKES_LABEL = 8 };
static const unsigned takes[UI_ELEMENTS] = {TAKES_Y | TAKES_SCALE | TAKES_LABEL, TAKES_Y | TAKES_SCALE | TAKES_LABEL,
                                            TAKES_Y | TAKES_SCALE, 0, TAKES_X | TAKES_Y | TAKES_SCALE,
                                            TAKES_X | TAKES_Y | TAKES_SCALE};

/* How far a sliding element may reach from its middle towards the side it
 * leaves by and still be off the screen at the nearest place the game
 * slides it to: the panel's middle (280) to 384 leaves 64 of the screen
 * on its left; the FIELD box's (40, its parts 12 to 68) to -36 leaves 36
 * on its right. The game's own pieces reach 32 (and 8 more for a fifth
 * LP digit) and 28. 0: it does not slide. */
static const int slide_reach[UI_ELEMENTS] = {64, 64, 36, 0, 0, 0};
static const int own_reach[UI_ELEMENTS] = {32 + 8, 32 + 8, 28, 0, 0, 0};
static const int own_size[UI_ELEMENTS][2] = {{64, 20}, {64, 20}, {56, 24}, {320, 72}, {16, 16}, {64, 64}};

static UiConfig config;
static int ready;

static void defaults(void)
{
    int i;
    ready = 1;
    memset(&config, 0, sizeof(config));
    for (i = 0; i < UI_ELEMENTS; i++) {
        config.element[i].scale = 100;
        config.element[i].tint = 0xFFFFFF;
        config.element[i].digits = 0xFFFFFF;
    }
}

/* "#RRGGBB", "RRGGBB" or a number; -1 when it is none of those. */
static long read_colour(const JsonValue *value)
{
    const char *text;
    char *end;
    long colour;
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

static void colour_member(const char *mod, const char *name, const JsonValue *object, const char *key, uint32_t *out)
{
    const JsonValue *value = Json_Member(object, key);
    long colour;
    if (!value) return;
    colour = read_colour(value);
    if (colour < 0) Mods_Note(mod, "ui: duel %s \"%s\" is a colour, \"#RRGGBB\"", name, key);
    else *out = (uint32_t)colour;
}

/* A whole number from `low` to `high`, or noted and left as it was. */
static void int_member(const char *mod, const char *name, const JsonValue *object, const char *key, int low, int high,
                       int *out)
{
    const JsonValue *value = Json_Member(object, key);
    long number;
    if (!value) return;
    number = Json_Number(value, (long)low - 1);
    if (Json_TypeOf(value) != JSON_NUMBER || number < low || number > high) {
        Mods_Note(mod, "ui: duel %s \"%s\" is a whole number from %d to %d", name, key, low, high);
        return;
    }
    *out = (int)number;
}

/* d * scale / 100 rounded half away from 0, as duel_ui.c places a point
 * about an element's middle. */
static int scaled(int d, int scale)
{
    int t = d * scale;
    return t >= 0 ? (t + 50) / 100 : -((-t + 50) / 100);
}

/* How wide a picture of the mod's own is drawn before its size: its
 * "width", or its "height" at the element's shape, or the element's. */
static int picture_width(int which, int width, int height)
{
    if (width) return width;
    if (height) return own_size[which][0] * height / own_size[which][1];
    return own_size[which][0];
}

int UiConfig_Reach(int which, int scale, int picture, int width, int height)
{
    if (which < 0 || which >= UI_ELEMENTS) return 0;
    if (picture) {
        /* About the element's middle (duel_ui.c draw_picture): its far
         * side from there is width - width / 2. */
        width = picture_width(which, width, height);
        return scaled(width - width / 2, scale);
    }
    return scaled(own_reach[which], scale);
}

int UiConfig_ScaleMax(int which, int picture, int width, int height)
{
    int scale = UI_SCALE_MAX;
    if (which < 0 || which >= UI_ELEMENTS || !(takes[which] & TAKES_SCALE)) return 100;
    if (!slide_reach[which]) return UI_SCALE_MAX;
    while (scale > UI_SCALE_MIN && UiConfig_Reach(which, scale, picture, width, height) > slide_reach[which]) scale--;
    return scale;
}

/* A sliding element sized past what leaves the screen with the game's: at
 * the most size that does, its picture made narrower if even the least is
 * too wide; noted. */
static void fit(const char *mod, int which)
{
    UiElement *element = &config.element[which];
    UiImage *image = &element->image;
    int picture = image->file[0] != 0, most, width, fitted;
    if (!slide_reach[which]) return;
    most = UiConfig_ScaleMax(which, picture, image->width, image->height);
    if (element->scale > most) {
        Mods_Note(mod, "ui: duel %s at %d%% would not leave the screen with the game's; drawn at %d%%",
                  UiConfig_ElementNames[which], element->scale, most);
        element->scale = most;
    }
    if (UiConfig_Reach(which, element->scale, picture, image->width, image->height) <= slide_reach[which]) return;
    width = picture_width(which, image->width, image->height);
    for (fitted = width - 1; fitted > 1; fitted--) {
        if (UiConfig_Reach(which, element->scale, 1, fitted, 0) <= slide_reach[which]) break;
    }
    /* As tall as before for its new width. */
    if (image->height && !(image->height = image->height * fitted / width)) image->height = 1;
    image->width = fitted;
    Mods_Note(mod, "ui: duel %s \"image\" is too wide to leave the screen with the game's; drawn %d wide",
              UiConfig_ElementNames[which], image->width);
}

static void read_element(const char *mod, const char *directory, int which, const JsonValue *part)
{
    static const char *const known[] = {"x", "y", "scale", "tint", "hide", "image", "width", "height", "label",
                                        "digits"};
    UiElement *element = &config.element[which];
    const char *name = UiConfig_ElementNames[which];
    const JsonValue *value, *member;
    if (Json_TypeOf(part) != JSON_OBJECT) {
        Mods_Note(mod, "ui: duel \"%s\" is an object ({\"x\": -40, \"tint\": \"#80C0FF\"})", name);
        return;
    }
    element->set = 1;
    config.any = 1;
    snprintf(element->mod, sizeof(element->mod), "%s", mod);
    for (member = Json_At(part, 0); member; member = Json_Next(member)) {
        const char *key = Json_Name(member);
        size_t k;
        for (k = 0; k < sizeof(known) / sizeof(known[0]); k++) {
            if (!strcmp(key, known[k])) break;
        }
        if (k == sizeof(known) / sizeof(known[0])) {
            Mods_Note(mod, "ui: unknown key \"%s\" in duel %s", key, name);
        } else if (!takes[which] && (!strcmp(key, "x") || !strcmp(key, "y") || !strcmp(key, "scale"))) {
            Mods_Note(mod, "ui: duel %s stays where the game has it (its words and cards follow it); \"%s\" is left out",
                      name, key);
        } else if (!(takes[which] & TAKES_X) && !strcmp(key, "x")) {
            Mods_Note(mod, "ui: duel %s is slid off the screen sideways by the game, so it keeps its place across; "
                           "\"x\" is left out (\"y\" moves it)", name);
        } else if (!(takes[which] & TAKES_LABEL) && (!strcmp(key, "label") || !strcmp(key, "digits"))) {
            Mods_Note(mod, "ui: duel %s has no \"%s\"", name, key);
        }
    }
    if (takes[which] & TAKES_X) int_member(mod, name, part, "x", -400, 400, &element->x);
    if (takes[which] & TAKES_Y) int_member(mod, name, part, "y", -300, 300, &element->y);
    if (takes[which] & TAKES_SCALE) int_member(mod, name, part, "scale", UI_SCALE_MIN, UI_SCALE_MAX, &element->scale);
    colour_member(mod, name, part, "tint", &element->tint);
    if ((value = Json_Member(part, "hide"))) element->hidden = Json_Bool(value, element->hidden);
    if ((value = Json_Member(part, "image"))) {
        const char *file = Json_String(value, NULL);
        snprintf(element->image.mod, sizeof(element->image.mod), "%s", mod);
        if (!file || !*file) {
            element->image.file[0] = 0;   /* "" or null: the game's own again */
        } else if (!Paths_Contained(file) || snprintf(element->image.file, sizeof(element->image.file), "%s/%s",
                                                      directory, file) >= (int)sizeof(element->image.file)) {
            Mods_Note(mod, "ui: duel %s \"image\": %s is outside the mod", name, file);
            element->image.file[0] = 0;
        }
    }
    int_member(mod, name, part, "width", 0, 320, &element->image.width);
    int_member(mod, name, part, "height", 0, 240, &element->image.height);
    if (takes[which] & TAKES_LABEL) {
        colour_member(mod, name, part, "digits", &element->digits);
        if ((value = Json_Member(part, "label"))) {
            const char *label = Json_String(value, NULL);
            if (!label) Mods_Note(mod, "ui: duel %s \"label\" is text", name);
            else if (strlen(label) >= sizeof(element->label))
                Mods_Note(mod, "ui: duel %s \"label\" is longer than %d letters", name, UI_LABEL - 1);
            snprintf(element->label, sizeof(element->label), "%s", label ? label : "");
        }
    }
    fit(mod, which);
}

void UiConfig_Read(const char *mod, const char *directory, const JsonValue *manifest)
{
    const JsonValue *ui = Json_Member(manifest, "ui"), *duel, *member;
    if (!ui) return;
    if (Json_TypeOf(ui) != JSON_OBJECT) {
        Mods_Note(mod, "\"ui\" is an object (notes/modding.md, \"The duel's pictures\")");
        return;
    }
    for (member = Json_At(ui, 0); member; member = Json_Next(member)) {
        if (strcmp(Json_Name(member), "duel")) Mods_Note(mod, "ui: unknown key \"%s\" (\"duel\")", Json_Name(member));
    }
    if (!(duel = Json_Member(ui, "duel"))) return;
    if (Json_TypeOf(duel) != JSON_OBJECT) {
        Mods_Note(mod, "ui: \"duel\" is an object of the duel's pictures by name (\"lp_player\": {\"x\": -200})");
        return;
    }
    for (member = Json_At(duel, 0); member; member = Json_Next(member)) {
        int i;
        for (i = 0; i < UI_ELEMENTS; i++) {
            if (!strcmp(Json_Name(member), UiConfig_ElementNames[i])) break;
        }
        if (i == UI_ELEMENTS) {
            Mods_Note(mod, "ui: no duel picture \"%s\" (lp_opponent, lp_player, field, card_bar, hand_cursor, "
                           "field_cursor)", Json_Name(member));
            continue;
        }
        read_element(mod, directory, i, member);
    }
}

void UiConfig_Reset(void)
{
    defaults();
}

const UiConfig *UiConfig_Load(void)
{
    int i;
    defaults();
    for (i = 0; i < Mods_LoadedCount(); i++) {
        int mod = Mods_Loaded(i);
        if (Mods_Active(mod)) UiConfig_Read(Mods_Id(mod), Mods_Directory(mod), Mods_Manifest(mod));
    }
    return &config;
}

const UiConfig *UiConfig_Get(void)
{
    if (!ready) defaults();
    return &config;
}
