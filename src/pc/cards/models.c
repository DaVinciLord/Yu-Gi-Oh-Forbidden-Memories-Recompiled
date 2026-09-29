/* A card's 3D model from a mod (models.h, notes/model-replacement.md). */
#include "models.h"
#include "cards.h"
#include "pc/debug/log.h"
#include "pc/guest/state.h"
#include "pc/mods/json.h"
#include "pc/mods/mods.h"
#include "pc/compat/fs.h"
#include "pc/platform/paths.h"
#include "pc/sdk/disc.h"
#include "pc/render/texture_pack.h"
#include "game/card_constants.h"
#include "game/model.h"
#include "psyq/libgte.h"
#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define SECTOR 2048
#define RECORD_SECTORS MODEL_MRG_SECTOR_COUNT
#define RECORD_BYTES ((size_t)RECORD_SECTORS * SECTOR)
/* The record's first phase: the model data the slot parses (func_8004CB0C),
 * a byte count and then an HMD without its id word. */
#define MODEL_DATA_BYTES (96 * SECTOR)
#define RECORDS_MAX 256
/* The record's textures: three 8-bit pages of 64 words by 256 rows, one
 * after another from the texture phase, and a 256-colour palette each at the
 * start of the palette phase (tools/pc/model_import.py lays them out). */
#define TEXTURE_PHASE (96 * SECTOR)
#define PALETTE_PHASE (TEXTURE_PHASE + 48 * SECTOR)
#define PAGES 3
#define PAGE_WORDS 64
#define PAGE_ROWS 256

#define SCALE_LEAST 10
#define SCALE_MOST 1000
#define SPEED_LEAST 25
#define SPEED_MOST 400
#define NEUTRAL_TINT 0xFFFFFFu

typedef struct {
    short record;       /* index into records[], or -1 for the disc's */
    short scale, speed; /* percent; 0 when no entry set them */
    short yaw;          /* a turn about the model's up axis, 4096 to a turn */
    uint32_t tint;      /* 0xRRGGBB, or NEUTRAL_TINT */
} CardModel;

static CardModel cards[CARD_TABLE_ID_END];
static unsigned char *records[RECORDS_MAX];
static char *hd_images[RECORDS_MAX];   /* a record's "hd" PNG: its pages side by side */
static int hd_sizes[RECORDS_MAX][2];
static int record_count;
static int first_lba = -1;   /* the records' sectors: first_lba + index * RECORD_SECTORS */
static int mrg_lba = -1;     /* MODEL.MRG's first sector, as the game's lookup finds it */
static unsigned signature;
/* Saved with states: what the loader was told, and what each slot draws with. */
static int pending[2], drawing[2];
/* Whether the slot's card's "yaw" and "scale" are applied by the draw: the
 * game's slots, not the 3D Monsters mod's, which turns and sizes each
 * monster itself. */
static int sized[2];

static CardModel *entry_of(int card)
{
    return card > 0 && card < CARD_TABLE_ID_END && Cards_Valid(card) ? &cards[card] : NULL;
}

static unsigned hash(unsigned value, const void *data, size_t size)
{
    const unsigned char *byte = data;
    while (size--) value = (value ^ *byte++) * 16777619u;
    return value;
}

/* "#RRGGBB" or [r, g, b]. */
static int read_tint(const JsonValue *value, uint32_t *tint)
{
    if (Json_TypeOf(value) == JSON_STRING) {
        const char *text = Json_String(value, "");
        char *end;
        unsigned long rgb;
        if (*text == '#') text++;
        if (strlen(text) != 6 || !isxdigit((unsigned char)*text)) return 0;
        rgb = strtoul(text, &end, 16);
        if (*end) return 0;
        *tint = (uint32_t)rgb;
        return 1;
    }
    if (Json_TypeOf(value) == JSON_ARRAY && Json_Count(value) == 3) {
        uint32_t rgb = 0;
        for (int i = 0; i < 3; i++) {
            const JsonValue *channel = Json_At(value, i);
            long level = Json_Number(channel, -1);
            if (Json_TypeOf(channel) != JSON_NUMBER || level < 0 || level > 255) return 0;
            rgb = rgb << 8 | (uint32_t)level;
        }
        *tint = rgb;
        return 1;
    }
    return 0;
}

static int read_percent(const char *mod, const char *where, const JsonValue *entry, const char *key,
                        int least, int most, short *out)
{
    const JsonValue *value = Json_Member(entry, key);
    long percent;
    if (!value) return 1;
    percent = Json_Number(value, -1);
    if (Json_TypeOf(value) != JSON_NUMBER || percent < least || percent > most) {
        Mods_Note(mod, "%s: \"%s\" is a percentage, %d to %d", where, key, least, most);
        return 0;
    }
    *out = (short)percent;
    return 1;
}

/* A record file: the whole MODEL.MRG record, as tools/pc/model_record.py
 * writes it. Its size is fixed, because the loader's seventeen phases are. */
static int read_record(const char *mod, const char *where, const char *directory, const char *file)
{
    char path[1024];
    unsigned char *data;
    FILE *handle;
    long size;
    unsigned words;
    if (!Paths_Contained(file) || snprintf(path, sizeof(path), "%s/%s", directory, file) >= (int)sizeof(path)) {
        Mods_Note(mod, "%s: \"file\": %s is outside the mod", where, file);
        return -1;
    }
    if (record_count == RECORDS_MAX) {
        Mods_Note(mod, "%s: more than %d model records", where, RECORDS_MAX);
        return -1;
    }
    handle = fopen(path, "rb");
    if (!handle) {
        Mods_Note(mod, "%s: cannot read %s", where, file);
        return -1;
    }
    size = fseek(handle, 0, SEEK_END) ? -1 : ftell(handle);
    if (size != (long)RECORD_BYTES) {
        fclose(handle);
        Mods_Note(mod, "%s: %s is %ld bytes; a model record is %u", where, file, size, (unsigned)RECORD_BYTES);
        return -1;
    }
    data = malloc(RECORD_BYTES);
    rewind(handle);
    if (!data || fread(data, 1, RECORD_BYTES, handle) != RECORD_BYTES) {
        fclose(handle);
        free(data);
        Mods_Note(mod, "%s: cannot read %s", where, file);
        return -1;
    }
    fclose(handle);
    /* The byte count the setup phase copies, and the HMD's block count. */
    words = (unsigned)data[0] | (unsigned)data[1] << 8 | (unsigned)data[2] << 16 | (unsigned)data[3] << 24;
    if (!words || words > MODEL_DATA_BYTES || data[12] == 0 || data[13] || data[14] || data[15]) {
        free(data);
        Mods_Note(mod, "%s: %s does not start with model data", where, file);
        return -1;
    }
    records[record_count] = data;
    signature = hash(signature, data, RECORD_BYTES);
    return record_count++;
}

/* The width and height of a PNG, from its header; 0 when it is not one. */
static int png_size(const char *path, int *width, int *height)
{
    unsigned char head[24];
    FILE *handle = fopen(path, "rb");
    int ok;
    if (!handle) return 0;
    ok = fread(head, 1, sizeof(head), handle) == sizeof(head) && !memcmp(head, "\x89PNG\r\n\x1a\n", 8) &&
         !memcmp(head + 12, "IHDR", 4);
    fclose(handle);
    if (!ok) return 0;
    *width = head[16] << 24 | head[17] << 16 | head[18] << 8 | head[19];
    *height = head[20] << 24 | head[21] << 16 | head[22] << 8 | head[23];
    return *width > 0 && *height > 0;
}

/* A record's "hd": the PNG of its three texture pages, side by side, drawn
 * at its own resolution above the console's (as a texture pack's image). */
static int read_hd(const char *mod, const char *where, const char *directory, const char *file, int record)
{
    char path[1024];
    int width, height;
    if (!Paths_Contained(file) || snprintf(path, sizeof(path), "%s/%s", directory, file) >= (int)sizeof(path)) {
        Mods_Note(mod, "%s: \"hd\": %s is outside the mod", where, file);
        return 0;
    }
    if (!png_size(path, &width, &height)) {
        Mods_Note(mod, "%s: \"hd\": %s is not a PNG it can read", where, file);
        return 0;
    }
    if (width % PAGES || width / PAGES * PAGE_ROWS != height * (PAGE_WORDS * 2)) {
        Mods_Note(mod, "%s: \"hd\": %s is %dx%d; it holds three 128x256 pages side by side at one size "
                  "(384x256, 768x512, 1536x1024...)", where, file, width, height);
        return 0;
    }
    free(hd_images[record]);
    hd_images[record] = strdup(path);
    hd_sizes[record][0] = width;
    hd_sizes[record][1] = height;
    return hd_images[record] != NULL;
}

static void add_entry(const char *mod, const char *directory, int index, const JsonValue *entry)
{
    char where[48];
    const JsonValue *file = Json_Member(entry, "file"), *tint = Json_Member(entry, "tint");
    CardModel *model, wanted;
    int card;
    snprintf(where, sizeof(where), "models[%d]", index);
    if (Json_TypeOf(entry) != JSON_OBJECT) {
        Mods_Note(mod, "%s: an entry is an object", where);
        return;
    }
    card = Cards_Reference(Json_Member(entry, "card"));
    model = entry_of(card);
    if (!model) {
        Mods_Note(mod, "%s: \"card\" names no card", where);
        return;
    }
    wanted = *model;
    if (!read_percent(mod, where, entry, "scale", SCALE_LEAST, SCALE_MOST, &wanted.scale) ||
        !read_percent(mod, where, entry, "speed", SPEED_LEAST, SPEED_MOST, &wanted.speed))
        return;
    if (Json_Member(entry, "yaw")) {
        const JsonValue *yaw = Json_Member(entry, "yaw");
        long degrees = Json_Number(yaw, 1000);
        if (Json_TypeOf(yaw) != JSON_NUMBER || degrees < -360 || degrees > 360) {
            Mods_Note(mod, "%s: \"yaw\" is a turn in degrees, -360 to 360", where);
            return;
        }
        wanted.yaw = (short)(degrees * 4096 / 360);
    }
    if (tint && !read_tint(tint, &wanted.tint)) {
        Mods_Note(mod, "%s: \"tint\" is \"#RRGGBB\" or [red, green, blue], 0 to 255", where);
        return;
    }
    if (file) {
        const char *name = Json_String(file, NULL);
        int record;
        if (!name || !*name) {
            Mods_Note(mod, "%s: \"file\" names a model record in the mod", where);
            return;
        }
        if ((record = read_record(mod, where, directory, name)) < 0) return;
        wanted.record = (short)record;
    }
    if (Json_Member(entry, "hd")) {
        const char *name = Json_String(Json_Member(entry, "hd"), NULL);
        if (!file || wanted.record < 0) {
            Mods_Note(mod, "%s: \"hd\" goes with a \"file\" in the same entry", where);
        } else if (!name || !*name) {
            Mods_Note(mod, "%s: \"hd\" names a PNG in the mod", where);
        } else {
            read_hd(mod, where, directory, name, wanted.record);
        }
    }
    if (!file && !Json_Member(entry, "scale") && !Json_Member(entry, "speed") && !tint && !Json_Member(entry, "yaw")) {
        Mods_Note(mod, "%s: the entry changes nothing (no \"file\", \"scale\", \"yaw\", \"tint\" or \"speed\")", where);
        return;
    }
    *model = wanted;
    LOG(LOG_MODS, "models: %s gives card %d %s (scale %d%%, yaw %d/4096, speed %d%%, tint #%06X)", mod, card,
        wanted.record >= 0 ? "its own record" : "the disc's record", wanted.scale ? wanted.scale : 100,
        wanted.yaw, wanted.speed ? wanted.speed : 100, (unsigned)wanted.tint);
}

void Models_Build(void)
{
    static int built;
    int i, card;
    if (built) return;
    built = 1;
    for (card = 0; card < CARD_TABLE_ID_END; card++) {
        cards[card].record = -1;
        cards[card].tint = NEUTRAL_TINT;
    }
    signature = 2166136261u;
    for (i = 0; i < Mods_LoadedCount(); i++) {
        int mod = Mods_Loaded(i), index = 0;
        const JsonValue *list = Json_Member(Mods_Manifest(mod), "models"), *entry;
        if (!Mods_Active(mod) || !list) continue;
        if (Json_TypeOf(list) != JSON_ARRAY) {
            Mods_Note(Mods_Id(mod), "\"models\" is not an array");
            continue;
        }
        for (entry = Json_At(list, 0); entry; entry = Json_Next(entry), index++)
            add_entry(Mods_Id(mod), Mods_Directory(mod), index, entry);
    }
    if (Memories_DiscFileInfo("\\DATA\\MODEL.MRG;1", &mrg_lba, NULL)) mrg_lba = -1;
    if (record_count) {
        /* Past the disc and whatever a mod's larger files were given, with a
         * guard sector as they have. */
        first_lba = Mods_DiscEnd() + 1;
        if (mrg_lba < 0 || first_lba < 0 ||
            (long long)first_lba + (long long)record_count * RECORD_SECTORS > MEMORIES_DISC_MAX_LBA - 1) {
            fprintf(stderr, "memories-pc: no room past the disc for %d model records; the disc's are used\n",
                    record_count);
            for (card = 0; card < CARD_TABLE_ID_END; card++) cards[card].record = -1;
            first_lba = -1;
        } else {
            LOG(LOG_MODS, "models: %d records at sectors %d to %d", record_count, first_lba,
                first_lba + record_count * RECORD_SECTORS - 1);
            /* Each "hd" image, known by where its record's pages are read
             * from: the pages and palettes are delivered from these sectors. */
            for (i = 0; i < record_count; i++) {
                uint32_t start = (uint32_t)(first_lba + i * RECORD_SECTORS) * SECTOR;
                int page, w;
                if (!hd_images[i]) continue;
                w = hd_sizes[i][0] / PAGES;
                for (page = 0; page < PAGES; page++) {
                    if (!TexturePack_AddDisc(start + TEXTURE_PHASE + (uint32_t)page * 16 * SECTOR, PAGE_WORDS, PAGE_ROWS,
                                             8, start + PALETTE_PHASE + (uint32_t)page * 512, 256, hd_images[i],
                                             page * w, 0, w, hd_sizes[i][1]))
                        fprintf(stderr, "memories-pc: models: %s page %d could not be added\n", hd_images[i], page);
                }
                signature = hash(signature, hd_images[i], strlen(hd_images[i]));
            }
        }
    }
    for (card = 0; card < CARD_TABLE_ID_END; card++) {
        const CardModel *model = &cards[card];
        if (model->record < 0 && !model->scale && !model->speed && !model->yaw && model->tint == NEUTRAL_TINT)
            continue;
        signature = hash(signature, &card, sizeof(card));
        signature = hash(signature, model, sizeof(*model));
    }
}

int Models_HasRecord(int card)
{
    const CardModel *model = entry_of(card);
    return model && model->record >= 0 && first_lba >= 0;
}

/* Model_LoadMonsterMerge's arithmetic from a zero-based model id to its
 * record in MODEL.MRG, or -1 for the ids that have none. */
static int disc_record(int model)
{
    if (model < 0 || model >= MODEL_MRG_ID_END ||
        (model >= MODEL_MRG_FIRST_GAP_START && model < MODEL_MRG_FIRST_GAP_END) ||
        (model >= MODEL_MRG_SECOND_GAP_START && model < MODEL_MRG_SECOND_GAP_END) ||
        model == MODEL_MRG_SINGLE_GAP_ID)
        return -1;
    if (model >= MODEL_MRG_LAST_ID) model--;
    if (model >= MODEL_MRG_SECOND_GAP_END) model -= MODEL_MRG_GAP_SIZE;
    if (model >= MODEL_MRG_FIRST_GAP_END) model -= MODEL_MRG_GAP_SIZE;
    return model;
}

int Models_RecordLba(int card)
{
    int record;
    if (!entry_of(card)) return -1;
    if (Models_HasRecord(card)) return first_lba + cards[card].record * RECORD_SECTORS;
    if (mrg_lba < 0 || (record = disc_record(Cards_ModelId(card) - 1)) < 0) return -1;
    return mrg_lba + record * RECORD_SECTORS;
}

int Models_Look(int card)
{
    const CardModel *model = entry_of(card);
    if (model && (Models_HasRecord(card) || model->scale || model->speed || model->yaw || model->tint != NEUTRAL_TINT))
        return card;
    return Cards_ModelId(card);
}

void Models_SetSlotCard(int slot, int card)
{
    if (slot >= 0 && slot < 2) pending[slot] = card;
}

int Models_SlotRecord(int slot, int model, int *offset)
{
    int card;
    if (slot < 0 || slot >= 2) return 0;
    card = pending[slot];
    /* The card set for the slot is only this load's if the model id is its. */
    if (!entry_of(card) || Cards_ModelId(card) - 1 != model) {
        drawing[slot] = 0;
        return 0;
    }
    drawing[slot] = card;
    sized[slot] = 1;
    if (!Models_HasRecord(card)) return 0;
    *offset = first_lba + cards[card].record * RECORD_SECTORS - mrg_lba;
    LOG(LOG_MODS, "models: slot %d loads card %d's own record", slot, card);
    return 1;
}

int Models_UseCard(int slot, int card)
{
    int previous;
    if (slot < 0 || slot >= 2) return 0;
    previous = drawing[slot] | sized[slot] << 24;
    drawing[slot] = card & 0xFFFFFF;
    sized[slot] = (card >> 24) & 1;
    return previous;
}

int Models_Scale(int card)
{
    const CardModel *model = entry_of(card);
    return model && model->scale ? model->scale : 100;
}

int Models_Speed(int card)
{
    const CardModel *model = entry_of(card);
    return model && model->speed ? model->speed : 100;
}

uint32_t Models_Tint(int card)
{
    const CardModel *model = entry_of(card);
    return model ? model->tint : NEUTRAL_TINT;
}

int Models_Yaw(int card)
{
    const CardModel *model = entry_of(card);
    return model ? model->yaw : 0;
}

void Models_Turn(int card, MATRIX *m)
{
    MATRIX turn, out;
    int yaw = Models_Yaw(card);
    if (!yaw) return;
    memset(&turn, 0, sizeof(turn));
    turn.m[0][0] = turn.m[1][1] = turn.m[2][2] = 4096;
    RotMatrixY(yaw, &turn);
    MulMatrix0(m, &turn, &out);
    memcpy(m->m, out.m, sizeof(m->m));
}

int Models_SlotOwnRecord(int slot)
{
    return slot >= 0 && slot < 2 && Models_HasRecord(drawing[slot]);
}

int Models_SlotShaped(int slot)
{
    return slot >= 0 && slot < 2 && sized[slot] && (Models_Yaw(drawing[slot]) || Models_Scale(drawing[slot]) != 100);
}

void Models_ShapeSlotRoot(int slot, MATRIX *m)
{
    int card = slot >= 0 && slot < 2 ? drawing[slot] : 0, fixed = Models_Scale(card) * 4096 / 100;
    Models_Turn(card, m);
    if (fixed != 4096) {
        VECTOR size;
        size.vx = size.vy = size.vz = fixed;
        size.pad = 0;
        ScaleMatrix(m, &size);
    }
}

int Models_SlotStep(int slot, int step)
{
    int percent = slot >= 0 && slot < 2 ? Models_Speed(drawing[slot]) : 100, scaled;
    if (percent == 100 || step <= 0) return step;
    scaled = step * percent / 100;
    return scaled > 0 ? scaled : 1;
}

int Models_SlotTinted(int slot)
{
    return slot >= 0 && slot < 2 && Models_Tint(drawing[slot]) != NEUTRAL_TINT;
}

/* A template's colour (its low three bytes, red first) times the tint. */
uint32_t Models_SlotTint(int slot, uint32_t colour)
{
    uint32_t tint = slot >= 0 && slot < 2 ? Models_Tint(drawing[slot]) : NEUTRAL_TINT, out = colour & 0xFF000000u;
    if (tint == NEUTRAL_TINT) return colour;
    for (int shift = 0; shift < 24; shift += 8) {
        unsigned level = (colour >> shift) & 0xFF, factor = (tint >> (16 - shift)) & 0xFF;
        out |= (uint32_t)(level * factor / 255) << shift;
    }
    return out;
}

int Models_DiscSector(int lba, void *out)
{
    int relative;
    if (first_lba < 0 || lba < first_lba) return 0;
    relative = lba - first_lba;
    if (relative >= record_count * RECORD_SECTORS) return 0;
    memcpy(out, records[relative / RECORD_SECTORS] + (size_t)(relative % RECORD_SECTORS) * SECTOR, SECTOR);
    return 1;
}

unsigned Models_Signature(void)
{
    return signature == 2166136261u ? 0 : signature;
}

void Models_State(MemoriesState *state)
{
    MemoriesStateField fields[] = {{pending, sizeof(pending)}, {drawing, sizeof(drawing)}, {sized, sizeof(sized)}};
    Memories_StateChunk(state, "models", fields, sizeof(fields) / sizeof(fields[0]));
}



