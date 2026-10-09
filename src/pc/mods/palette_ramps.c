/* Manifest-defined text palette ramps. */
#include "palette_ramps.h"
#include "json.h"
#include "mods.h"
#include "psyq/libgpu.h"
#include <stdlib.h>
#include <stdio.h>
#include <string.h>

enum { RETAIL_RAMP_SLOTS = 8, RAMP_ENTRIES = 16, RAMP_X = 640, RAMP_Y = 232, RAMP_BANK_Y = 240, RAMP_BANK_SLOTS = 256, RAMP_NAME_MAX = 64 };

typedef struct {
    char name[RAMP_NAME_MAX];
    unsigned short clut;
} NamedRamp;

static NamedRamp named[RAMP_BANK_SLOTS];
static int named_count;

unsigned short PaletteRamps_Clut(const char *name)
{
    int i;
    for (i = 0; i < named_count; i++) if (!strcmp(named[i].name, name)) return named[i].clut;
    return 0;
}

static int byte(const JsonValue *value, unsigned *out)
{
    long n = Json_Number(value, -1);
    if (Json_TypeOf(value) != JSON_NUMBER || n < 0 || n > 255) return 0;
    *out = (unsigned)n;
    return 1;
}

static int rgb(const JsonValue *value, unsigned *out)
{
    const char *text = Json_String(value, NULL);
    int i;
    if (text && text[0] == '#' && strlen(text) == 7) {
        for (i = 0; i < 6; i++) {
            int d = text[i + 1] >= '0' && text[i + 1] <= '9' ? text[i + 1] - '0' :
                    text[i + 1] >= 'a' && text[i + 1] <= 'f' ? text[i + 1] - 'a' + 10 :
                    text[i + 1] >= 'A' && text[i + 1] <= 'F' ? text[i + 1] - 'A' + 10 : -1;
            if (d < 0) return 0;
            out[i / 2] = (out[i / 2] << 4) | (unsigned)d;
        }
        return 1;
    }
    return Json_TypeOf(value) == JSON_ARRAY && Json_Count(value) == 3 &&
           byte(Json_At(value, 0), &out[0]) && byte(Json_At(value, 1), &out[1]) &&
           byte(Json_At(value, 2), &out[2]);
}

static void apply(const unsigned short *base, int y, const unsigned *color)
{
    unsigned short ramp[RAMP_ENTRIES];
    RECT rect = {RAMP_X, y, RAMP_ENTRIES, 1};
    int i;
    for (i = 0; i < RAMP_ENTRIES; i++) {
        unsigned lum = base[i] & 31u;
        ramp[i] = base[i] ? (unsigned short)((lum * color[2] / 255u << 10) |
                                              (lum * color[1] / 255u << 5) |
                                               lum * color[0] / 255u) : 0;
        if (base[i] && !ramp[i]) ramp[i] = 0x8000;
    }
    LoadImage(&rect, (u32 *)ramp);
}

void PaletteRamps_ApplyManifest(const unsigned short *base)
{
    int i;
    if (!base) return;
    named_count = 0;
    for (i = 0; i < Mods_LoadedCount(); i++) {
        const int mod = Mods_Loaded(i);
        const JsonValue *entry;
        if (!Mods_Active(mod)) continue;
        for (entry = Json_At(Json_Member(Mods_Manifest(mod), "palette_ramps"), 0);
             entry; entry = Json_Next(entry)) {
            char *end;
            long slot = strtol(Json_Name(entry), &end, 10);
            unsigned color[3] = {0, 0, 0};
            char full_name[RAMP_NAME_MAX];
            if (!rgb(entry, color)) {
                Mods_Note(Mods_Id(mod), "palette_ramps: '%s' must be [red, green, blue] or #RRGGBB", Json_Name(entry));
            } else if (!*end) {
                if (slot < 0 || slot >= RETAIL_RAMP_SLOTS)
                    Mods_Note(Mods_Id(mod), "palette_ramps: built-in slot %ld must be from 0 to 7", slot);
                else apply(base, RAMP_Y + (int)slot, color);
            } else if (named_count == RAMP_BANK_SLOTS ||
                       snprintf(full_name, sizeof(full_name), "%s:%s", Mods_Id(mod), Json_Name(entry)) >=
                       (int)sizeof(full_name)) {
                Mods_Note(Mods_Id(mod), "palette_ramps: cannot add '%s'", Json_Name(entry));
            } else {
                snprintf(named[named_count].name, sizeof(named[named_count].name), "%s", full_name);
                named[named_count].clut = (unsigned short)((RAMP_BANK_Y + named_count) << 6 | (RAMP_X >> 4));
                apply(base, RAMP_BANK_Y + named_count, color);
                named_count++;
            }
        }
    }
    DrawSync(0);
}
