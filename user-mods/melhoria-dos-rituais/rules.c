#include "types.h"
#include "pc/mods/modapi.h"
#include "game/duel_card.h"
#include "game/duel_check_ritual.h"
#include "game/duel_hand.h"
#include "game/duel_side_state.h"
#include "game/duel_grid.h"
#include "game/duel_ritual_controller.h"
#include "game/duel_card_record_lifecycle.h"
#include "game/card_constants.h"
#include "pc/cards/tables.h"

/* Optional lookups: this mod also works on official builds without the
 * condition-based ritual extension. Neither mod requires the other. */
static int (*custom_requirements)(int, TablesRitualRequirement *, unsigned short *);
static int (*custom_recipe)(int, unsigned short *);
static int (*base_id)(int);
static int (*card_type)(int);
static int (*card_level)(int);
static int (*in_group)(int, int);

static s32 (*o_check)(DuelRitualResult *, s32);
static void (*o_deact)(DuelCardRecord *);

static int bridge_active;
static int deact_step;
static int side;
static int where[3], slot[3], rec[3], matid[3];
static unsigned obj[3];
static int recipe_result;

static int valid_record(int r) {
    return r >= 0 && r < DUEL_CARD_RECORD_COUNT;
}

static int hand_record(int s, int h) {
    return (int)D_800907CC[s * HAND_SIZE + h];
}

static int record_already_used(int r, int upto) {
    int j;
    for (j = 0; j < upto; j++)
        if (rec[j] == r) return 1;
    return 0;
}

static void locate_unique(int id, int i) {
    int base = side * DUEL_FIELD_SIDE_GRID_SLOT_COUNT;
    int s, h, r;

    where[i] = 0;
    slot[i] = -1;
    rec[i] = -1;
    obj[i] = 0;

    for (s = 0; s < DUEL_FIELD_SIDE_GRID_SLOT_COUNT; s++) {
        r = D_800907D8[base + s];
        if (valid_record(r) &&
            !record_already_used(r, i) &&
            D_801A7AD8[r].card_id == id &&
            D_801A7AD8[r].object) {
            where[i] = 1; /* field */
            slot[i] = s;
            rec[i] = r;
            obj[i] = (unsigned)(u32)D_801A7AD8[r].object;
            return;
        }
    }

    for (h = 0; h < HAND_SIZE; h++) {
        r = hand_record(side, h);
        if (D_800E9FF0[side].hand[h] >= 0 &&
            valid_record(r) &&
            !record_already_used(r, i) &&
            D_801A7AD8[r].card_id == id) {
            where[i] = 2; /* hand */
            slot[i] = h;
            rec[i] = r;
            obj[i] = (unsigned)(u32)D_801A7AD8[r].object;
            return;
        }
    }
}

/* Retail ritual records:
   ritual card, material 1, material 2, material 3, result monster. */
static int load_recipe(int ritual) {
    int n, i;
    for (n = 0; n < 256; n++) {
        u16 *q = &gDuel_awRitualData[n * DUEL_RITUAL_RECIPE_HALFWORD_COUNT];
        int rid = q[0];

        if (!rid) break;
        if (rid != ritual) continue;

        matid[0] = q[1];
        matid[1] = q[2];
        matid[2] = q[3];
        recipe_result = q[4];

        if (recipe_result <= 0 || recipe_result > CARD_TABLE_COUNT) return 0;
        for (i = 0; i < 3; i++)
            if (matid[i] <= 0 || matid[i] > CARD_TABLE_COUNT) return 0;
        return 1;
    }
    return 0;
}

#include "selection.h"

static s32 ritual_check(DuelRitualResult *out, s32 ritual_id) {
    s32 retail = o_check(out, ritual_id);
    int i, field_count = 0, hand_count = 0;
    int match;
    void *proxy = 0;

    /* Never interfere with a ritual the original game already accepts. */
    if (retail != 0) return retail;

    side = D_8009B1D5 & 1;
    {
        TablesRitualRequirement requirements[3];
        unsigned short result = 0, recipe[6];
        int conditional = custom_requirements &&
            custom_requirements(ritual_id, requirements, &result);
        if (conditional) {
            recipe_result = result;
            if (recipe_result <= 0 || recipe_result > CARD_TABLE_COUNT ||
                !locate_requirements(requirements)) return retail;
        } else {
            int ruled = custom_recipe ? custom_recipe(ritual_id, recipe) : -1;
            if (ruled == 0) return retail; /* An explicitly removed recipe stays removed. */
            if (ruled > 0) {
                recipe_result = recipe[4];
                if (recipe_result <= 0 || recipe_result > CARD_TABLE_COUNT) return retail;
                for (i = 0; i < 3; i++) {
                    matid[i] = recipe[i + 1];
                    if (matid[i] <= 0 || matid[i] > CARD_TABLE_COUNT) return retail;
                }
            } else if (!load_recipe(ritual_id)) return retail;
            for (i = 0; i < 3; i++) locate_unique(matid[i], i);
        }
    }

    for (i = 0; i < 3; i++) {
        if (where[i] == 1) field_count++;
        else if (where[i] == 2) hand_count++;
    }

    match = where[0] && where[1] && where[2] &&
            field_count >= 1 && (field_count + hand_count == 3);

    if (!match) return retail;

    /* First retail check has no output structure. Returning the recipe result
       here makes the original ritual pipeline load the correct 2D result art. */
    if (!out) return recipe_result;

    /* Hand cards have no DisplayObject. Reuse one genuine field material only
       as a temporary retail proxy; the deactivation hook below redirects each
       tribute to its real record. */
    for (i = 0; i < 3; i++) {
        if (where[i] == 1 && obj[i]) {
            proxy = (void *)(u32)obj[i];
            break;
        }
    }
    if (!proxy) return retail;

    for (i = 0; i < 3; i++) {
        if (where[i] == 1)
            out->tribute_objects[i] = (void *)(u32)obj[i];
        else
            out->tribute_objects[i] = proxy;
    }
    out->field_0C = 0;

    bridge_active = 1;
    deact_step = 0;
    return recipe_result;
}

static int record_index(DuelCardRecord *r) {
    if (!r) return -1;
    return (int)(r - D_801A7AD8);
}

static void ritual_deactivate(DuelCardRecord *passed_record) {
    int i, hs;

    if (!bridge_active || deact_step >= 3) {
        o_deact(passed_record);
        return;
    }

    i = deact_step++;

    /* Defensive fallback: abandon the bridge rather than touching an
       unexpected record. */
    if (!valid_record(rec[i])) {
        bridge_active = 0;
        o_deact(passed_record);
        return;
    }

    if (where[i] == 1) {
        o_deact(&D_801A7AD8[rec[i]]);
    } else if (where[i] == 2) {
        hs = slot[i];
        if (hs < 0 || hs >= HAND_SIZE || hand_record(side, hs) != rec[i]) {
            bridge_active = 0;
            o_deact(passed_record);
            return;
        }

        D_800E9FF0[side].hand[hs] = -1;
        D_801A7AD8[rec[i]].flags = 0;
        D_801A7AD8[rec[i]].object = 0;
        D_801A7AD8[rec[i]].data = 0;
    } else {
        bridge_active = 0;
        o_deact(passed_record);
        return;
    }

    if (deact_step == 3)
        bridge_active = 0;
}

static void reset_bridge(void) {
    bridge_active = 0;
    deact_step = 0;
}

static void applied(int on) {
    (void)on;
    reset_bridge();
}

int MemoriesModInit(const MemoriesModHost *host, MemoriesMod *mod) {
    if (host->api < 4) return 0;

    custom_requirements = (void *)host->symbol(host, "Tables_RitualRequirements");
    custom_recipe = (void *)host->symbol(host, "Tables_Ritual");
    base_id = (void *)host->symbol(host, "Cards_BaseId");
    card_type = (void *)host->symbol(host, "Cards_Type");
    card_level = (void *)host->symbol(host, "Cards_Level");
    in_group = (void *)host->symbol(host, "Cards_InFusionGroup");

    mod->api = 4;
    mod->overlay = 0;
    mod->overlay_signature = 0;
    mod->reset = reset_bridge;
    mod->applied = applied;

    if (!host->hook(host, (void *)Duel_CheckRitual,
                    (void *)ritual_check, (void **)&o_check))
        return 0;

    if (!host->hook(host, (void *)DuelCard_DeactivateRecord,
                    (void *)ritual_deactivate, (void **)&o_deact))
        return 0;

    return 1;
}
