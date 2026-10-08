#include "card_layout.h"
#include "cards.h"
#include "pc/mods/mods.h"
#include "pc/mods/json.h"
#include "pc/platform/paths.h"
#include "pc/debug/log.h"
#include "game/card_constants.h"
#include <stdio.h>
#include <string.h>

static const char *const element_names[CARD_LAYOUT_ELEMENT_COUNT] = {
    "frame", "title", "description", "level_stars", "attribute", "atk", "def", "art"
};

/* cards.h's CARD_FRAME_* order, named as "frame"'s own sub-keys. */
static const char *const frame_kind_names[CARD_FRAME_COUNT] = {
    "monster", "magic", "trap", "ritual", "purple", "orange"
};

/* Logged only on change (MEMORIES_TRACE=card_layout), not every frame:
 * func_80028B08.c asks for atk/def/stars/attribute every frame a card
 * viewer is open, but a layout answer only actually changes when the
 * active mod's settings or manifest change. */
static CardLayoutPlacement last[CARD_LAYOUT_ELEMENT_COUNT];
static int last_set[CARD_LAYOUT_ELEMENT_COUNT];

/* The card CardLayout_SetCard last named: its frame style (the layout's
 * "frame_styles" entry the "frame_for" rules picked, or, for a layout with no
 * styles, the "frame" of its kind) -- its colour, the picture's path and
 * size, and whether it is laid out as a spell. A monster with no frame until
 * a call site sets a real card, as every call site that never draws one. */
static CardLayoutStyle current;

typedef struct {
    int mod;                   /* -1: no applied mod declares "card_layout" */
    const JsonValue *layout;   /* that mod's "card_layout" object */
} LayoutSource;

/* "frame"'s sub-object for `kind`, falling back to "monster" when `kind`
 * has none of its own -- the OLD layout form, before "frame_styles": purple/
 * orange are recolours of the monster frame (hd_assets_pack.py), and a mod
 * that has not drawn magic/trap/ritual's own yet still gets a frame, not
 * none. */
static const JsonValue *frame_for_kind(const JsonValue *layout, int kind)
{
    const JsonValue *frame_set = Json_Member(layout, "frame");
    const JsonValue *frame = Json_Member(frame_set, frame_kind_names[kind]);
    return frame ? frame : Json_Member(frame_set, frame_kind_names[CARD_FRAME_MONSTER]);
}

/* The six frame colours a style's "hand_colour" names. The disc's own labels
 * (monster, magic, trap, ritual) are accepted too. */
static const char *const colour_names[CARD_FRAME_COUNT] = {"gold", "green", "pink", "blue", "purple", "orange"};
static int colour_named(const char *text)
{
    int i;
    if (!text) return -1;
    for (i = 0; i < CARD_FRAME_COUNT; i++) {
        if (!strcmp(text, colour_names[i]) || !strcmp(text, frame_kind_names[i])) return i;
    }
    return -1;
}

int CardLayout_IsSpell(void)
{
    return current.spell_layout;
}

/* A mod's own file `file` joined with its directory, into `out`; "" for
 * none (or one outside the mod). `what` names the key, for the note. */
static void mod_file(int mod, const char *file, const char *what, char *out, size_t size)
{
    out[0] = 0;
    if (file && *file) {
        if (!Paths_Contained(file) || snprintf(out, size, "%s/%s", Mods_Directory(mod), file) >= (int)size) {
            Mods_Note(Mods_Id(mod), "card_layout: %s \"image\" \"%s\" is outside the mod", what, file);
            out[0] = 0;
        }
    }
}

/* `kind`'s "frame" image joined with the mod's own directory, into `out`;
 * "" for none (or one outside the mod). */
static void frame_path_of(int mod, const JsonValue *layout, int kind, char *out, size_t size)
{
    const JsonValue *frame = frame_for_kind(layout, kind);
    mod_file(mod, Json_String(Json_Member(frame, "image"), NULL), "\"frame\"", out, size);
}

/* The last applied mod, in load order, that declares a "card_layout" key --
 * the same "a later mod's value wins" rule every other manifest key
 * follows (notes/modding.md). Re-walked on every call rather than cached:
 * this only runs while a big card is actually being drawn (a card viewer
 * open, a duel's own field or result cards), never the main loop, so
 * walking a handful of loaded mods is nothing worth caching against. */
static LayoutSource find_source(void)
{
    LayoutSource source;
    int i;

    source.mod = -1;
    source.layout = NULL;
    for (i = 0; i < Mods_LoadedCount(); i++) {
        int mod = Mods_Loaded(i);
        const JsonValue *layout;
        if (!Mods_Active(mod)) continue;
        layout = Json_Member(Mods_Manifest(mod), "card_layout");
        if (!layout) continue;
        source.mod = mod;
        source.layout = layout;
    }
    return source;
}

static int full_bleed_of(const LayoutSource *source)
{
    /* Off until the player turns it on. A mod's own "settings" entry's
     * "default" is the Mods window's display only -- this fallback is the
     * one that actually answers; keep both in sync if either changes. */
    return source->mod >= 0 && Mods_Setting(Mods_Id(source->mod), "full_bleed", 0) != 0;
}

/* "<key>": {"x": ..., "y": ...}, each defaulting to retail's own place. */
static void point(const JsonValue *layout, const char *key, int *x, int *y, int dx, int dy)
{
    const JsonValue *part = Json_Member(layout, key);
    *x = (int)Json_Number(Json_Member(part, "x"), dx);
    *y = (int)Json_Number(Json_Member(part, "y"), dy);
}

/* "<key>": {"x": ..., "y": ..., "width": ..., "height": ...}, same defaults
 * convention as a "title" mod's image (title_config.h's TitleImage). */
static void rect(const JsonValue *layout, const char *key, int *x, int *y, int *w, int *h,
                 int dx, int dy, int dw, int dh)
{
    const JsonValue *part = Json_Member(layout, key);
    *x = (int)Json_Number(Json_Member(part, "x"), dx);
    *y = (int)Json_Number(Json_Member(part, "y"), dy);
    *w = (int)Json_Number(Json_Member(part, "width"), dw);
    *h = (int)Json_Number(Json_Member(part, "height"), dh);
}

int CardLayout_Digits(char *path, size_t size, int *w, int *h, int *step)
{
    LayoutSource source = find_source();
    const JsonValue *digits;

    path[0] = 0;
    if (source.mod < 0 || !full_bleed_of(&source)) return 0;
    digits = Json_Member(source.layout, "digits");
    mod_file(source.mod, Json_String(Json_Member(digits, "image"), NULL), "\"digits\"", path, size);
    if (!path[0]) return 0;
    *w = (int)Json_Number(Json_Member(digits, "width"), 10);
    *h = (int)Json_Number(Json_Member(digits, "height"), 12);
    *step = (int)Json_Number(Json_Member(digits, "step"), *w);
    return *w > 0 && *h > 0 && *step > 0;
}

/* Why a layout's frame choice could not be made, said once a layout. */
static const JsonValue *noted_layout;
static char noted_what[96];
static void note_once(const LayoutSource *source, const char *what, const char *name)
{
    char key[96];
    snprintf(key, sizeof(key), "%s %s", what, name);
    if (noted_layout == source->layout && !strcmp(noted_what, key)) return;
    noted_layout = source->layout;
    snprintf(noted_what, sizeof(noted_what), "%s", key);
    Mods_Note(Mods_Id(source->mod), "card_layout: %s \"%s\"", what, name);
}

/* Whether a "frame_for" rule applies to `card`: every condition it names
 * ("class", "tag") holds, and its "setting" (a bool the mod declares), if
 * any, is on. A rule that names none applies to every card. */
static int rule_applies(const LayoutSource *source, const JsonValue *rule, int card, int cls)
{
    const char *key = Json_String(Json_Member(rule, "setting"), NULL);
    const char *text;
    if (key && !Mods_Setting(Mods_Id(source->mod), key, 0)) return 0;
    text = Json_String(Json_Member(rule, "class"), NULL);
    if (text && strcmp(text, Cards_ClassName(cls))) return 0;
    text = Json_String(Json_Member(rule, "tag"), NULL);
    if (text && !Cards_HasTag(card, text)) return 0;
    return 1;
}

/* The frame style of `card`, into `out` (with its picture's path when
 * `want_image`); 0, nothing, when the layout's style is unusable (the card is
 * then drawn as retail does). */
static int resolve_style(const LayoutSource *source, int card, CardLayoutStyle *out, int want_image)
{
    int cls = Cards_Class(card);
    const JsonValue *styles = Json_Member(source->layout, "frame_styles");
    const JsonValue *style = NULL;
    const char *name = NULL;
    const JsonValue *rule;
    int override = Cards_FrameOverride(card);

    memset(out, 0, sizeof(*out));
    out->width = 140;
    out->height = 196;
    out->spell_layout = cls == CARD_CLASS_SPELL || cls == CARD_CLASS_EQUIP || cls == CARD_CLASS_RITUAL_SPELL ||
                        cls == CARD_CLASS_TRAP;
    if (!styles) {
        /* A layout from before "frame_styles": "frame" holds a picture a kind
         * (monster, magic, trap, ritual, purple, orange). The kind is the
         * card's own frame colour, else its class's; a ritual spell with no
         * ritual picture of its own (or magic's) wears magic's. */
        const JsonValue *frame_set = Json_Member(source->layout, "frame");
        const JsonValue *frame;
        const char *own, *magic;
        int kind = override;
        if (kind < 0) {
            if (cls == CARD_CLASS_EFFECT_MONSTER) kind = CARD_FRAME_ORANGE;
            else if (cls == CARD_CLASS_SPELL || cls == CARD_CLASS_EQUIP) kind = CARD_FRAME_MAGIC;
            else if (cls == CARD_CLASS_TRAP) kind = CARD_FRAME_TRAP;
            else if (cls == CARD_CLASS_RITUAL_SPELL) kind = CARD_FRAME_RITUAL;
            else kind = CARD_FRAME_MONSTER;
        }
        own = Json_String(Json_Member(Json_Member(frame_set, "ritual"), "image"), NULL);
        magic = Json_String(Json_Member(frame_for_kind(source->layout, CARD_FRAME_MAGIC), "image"), NULL);
        if (kind == CARD_FRAME_RITUAL && (!own || !*own || (magic && !strcmp(own, magic)))) kind = CARD_FRAME_MAGIC;
        frame = frame_for_kind(source->layout, kind);
        out->colour = kind;
        snprintf(out->name, sizeof(out->name), "%s", frame_kind_names[kind]);
        out->width = (int)Json_Number(Json_Member(frame, "width"), 140);
        out->height = (int)Json_Number(Json_Member(frame, "height"), 196);
        if (want_image)
            mod_file(source->mod, Json_String(Json_Member(frame, "image"), NULL), "\"frame\"", out->image,
                     sizeof(out->image));
        return 1;
    }
    /* A card with a frame colour of its own (a cards mod's "frame") takes the
     * style of that colour's name when the layout has one; otherwise the
     * first rule that applies; otherwise the layout's "default_style". */
    if (override >= 0 && Json_Member(styles, colour_names[override])) name = colour_names[override];
    for (rule = Json_At(Json_Member(source->layout, "frame_for"), 0); !name && rule; rule = Json_Next(rule)) {
        if (rule_applies(source, rule, card, cls)) name = Json_String(Json_Member(rule, "style"), NULL);
    }
    if (!name) name = Json_String(Json_Member(source->layout, "default_style"), "gold");
    style = Json_Member(styles, name);
    if (!style) {
        note_once(source, "no \"frame_styles\" entry named", name);
        return 0;
    }
    out->colour = colour_named(Json_String(Json_Member(style, "hand_colour"), name));
    if (out->colour < 0) {
        note_once(source, "\"hand_colour\" is not gold, green, pink, blue, purple or orange in style", name);
        return 0;
    }
    snprintf(out->name, sizeof(out->name), "%s", name);
    out->width = (int)Json_Number(Json_Member(style, "width"), 140);
    out->height = (int)Json_Number(Json_Member(style, "height"), 196);
    if (want_image)
        mod_file(source->mod, Json_String(Json_Member(style, "image"), NULL), "\"frame_styles\" style", out->image,
                 sizeof(out->image));
    return 1;
}

int CardLayout_StyleOf(int card_id, CardLayoutStyle *style)
{
    LayoutSource source = find_source();
    if (!full_bleed_of(&source)) return 0;
    return resolve_style(&source, card_id, style, 0);
}

void CardLayout_SetCard(int card_id)
{
    LayoutSource source = find_source();
    CardLayoutStyle style;
    int cls = Cards_Class(card_id);

    memset(&current, 0, sizeof(current));
    current.spell_layout = cls == CARD_CLASS_SPELL || cls == CARD_CLASS_EQUIP || cls == CARD_CLASS_RITUAL_SPELL ||
                           cls == CARD_CLASS_TRAP;
    current.width = 140;
    current.height = 196;
    if (full_bleed_of(&source) && resolve_style(&source, card_id, &style, 1)) current = style;
}

int CardLayout_FullBleed(void)
{
    LayoutSource source = find_source();
    return full_bleed_of(&source);
}

const char *CardLayout_FramePath(void)
{
    return current.image;
}

int CardLayout_FramePaths(char (*paths)[1024], int max)
{
    LayoutSource source = find_source();
    const JsonValue *styles, *style;
    int count = 0, kind;

    if (source.mod < 0 || !full_bleed_of(&source)) return 0;
    styles = Json_Member(source.layout, "frame_styles");
    if (styles) {
        for (style = Json_At(styles, 0); style && count < max; style = Json_Next(style)) {
            int i;
            mod_file(source.mod, Json_String(Json_Member(style, "image"), NULL), "\"frame_styles\" style", paths[count], 1024);
            if (!paths[count][0]) continue;
            for (i = 0; i < count && strcmp(paths[i], paths[count]); i++) {}
            if (i == count) count++;   /* styles that share a picture add nothing */
        }
        return count;
    }
    for (kind = 0; kind < CARD_FRAME_COUNT && count < max; kind++) {
        int i;
        frame_path_of(source.mod, source.layout, kind, paths[count], 1024);
        if (!paths[count][0]) continue;
        for (i = 0; i < count && strcmp(paths[i], paths[count]); i++) {}
        if (i == count) count++;
    }
    return count;
}

CardLayoutPlacement CardLayout_Get(CardLayoutElement element)
{
    CardLayoutPlacement p = {1, 0, 0, 0, 0};
    LayoutSource source = find_source();
    int full_bleed = full_bleed_of(&source);
    int spell = CardLayout_IsSpell();

    switch (element) {
    case CARD_LAYOUT_FRAME: {
        /* The current card's frame style, "width" x "height" (140x196 unless
         * the style says) -- the whole box CardLayout_DrawFrame (func_80028B08.c) draws its
         * texture into; 140x196 with no mod's own size given is this
         * feature's own first measured value, kept as the sensible
         * default, not a retail equivalent (retail has no unified frame
         * concept to default to). */
        p.visible = !full_bleed;
        p.w = current.width;
        p.h = current.height;
        break;
    }
    case CARD_LAYOUT_TITLE:
        p.visible = !full_bleed;
        break;
    case CARD_LAYOUT_DESCRIPTION:
        /* Always visible, independent of full_bleed: the description
         * TextBox's own backdrop (func_800283F4.c's D_8009B240) is on
         * screen either way, so hiding only the text would leave it
         * looking empty for no reason. */
        p.visible = 1;
        break;
    case CARD_LAYOUT_LEVEL_STARS:
        /* Magic/trap/ritual never reach this call (func_80028B08.c's own
         * obj->field_68 < 0x14 gate, unrelated to full_bleed): none of the
         * three have a level to draw stars for, in retail or full-bleed. */
        if (full_bleed) point(source.layout, "stars", &p.x, &p.y, 0x77, 0x20);
        else { p.x = 0x77; p.y = 0x20; }
        break;
    case CARD_LAYOUT_ATTRIBUTE:
        /* Monster/purple/orange: the mod's "attribute" rect. Magic/trap/
         * ritual: "spell"."icon" instead -- a different place for the same
         * element (func_80028B08.c still draws retail's own elemental
         * texture there, unchanged; those three kinds just have no
         * meaningful one, same as they have no ATK/DEF/level). */
        if (full_bleed) {
            if (spell) rect(Json_Member(source.layout, "spell"), "icon", &p.x, &p.y, &p.w, &p.h, 0x6E, 0xD, 0, 0);
            else rect(source.layout, "attribute", &p.x, &p.y, &p.w, &p.h, 0x6E, 0xD, 0, 0);
        } else { p.x = 0x6E; p.y = 0xD; }
        break;
    case CARD_LAYOUT_ATK:
        /* Spell: never reached (same gate as CARD_LAYOUT_LEVEL_STARS). */
        if (full_bleed) point(source.layout, "atk", &p.x, &p.y, 0x61, 0x9D);
        else { p.x = 0x61; p.y = 0x9D; }
        break;
    case CARD_LAYOUT_DEF:
        if (full_bleed) point(source.layout, "def", &p.x, &p.y, 0x61, 0xAB);
        else { p.x = 0x61; p.y = 0xAB; }
        break;
    case CARD_LAYOUT_ART:
        /* w/h at 0 (retail) unless full-bleed and the mod gives a rect:
         * func_80028B08.c reads w != 0 as "stretch the art", so an empty
         * "art" key here (no mod, or full_bleed off) correctly draws
         * nothing special. Spell reads "spell"."art" instead of "art" --
         * magic/trap/ritual's own art box, not monster's. */
        if (full_bleed) {
            if (spell) rect(Json_Member(source.layout, "spell"), "art", &p.x, &p.y, &p.w, &p.h, 0, 0, 0, 0);
            else rect(source.layout, "art", &p.x, &p.y, &p.w, &p.h, 0, 0, 0, 0);
        }
        break;
    default:
        break;
    }

    if (element >= 0 && element < CARD_LAYOUT_ELEMENT_COUNT &&
        (!last_set[element] || last[element].visible != p.visible ||
         last[element].x != p.x || last[element].y != p.y ||
         last[element].w != p.w || last[element].h != p.h)) {
        LOG(LOG_CARD_LAYOUT, "%s: visible=%d x=%d y=%d w=%d h=%d (full_bleed=%d kind=%s)",
            element_names[element], p.visible, p.x, p.y, p.w, p.h, full_bleed, current.name);
        last[element] = p;
        last_set[element] = 1;
    }
    return p;
}
