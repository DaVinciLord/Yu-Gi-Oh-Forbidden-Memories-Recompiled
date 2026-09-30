#include "../types.h"
#include "duel_check_ritual.h"
#define D_8009B1D5_IS_ABSOLUTE_SCALAR
#include "duel_side_state.h"
#include "duel_card.h"
#include "card_constants.h"
#include "duel_card_layout.h"
#include "duel_grid.h"
#ifdef MEMORIES_PC
#include "pc/cards/cards.h"
#include "pc/cards/tables.h"
#endif

s32 Duel_CheckRitual(DuelRitualResult *out, s32 ritualId)
{
    DuelCardRecord *found[DUEL_RITUAL_TRIBUTE_COUNT];
    DuelCardRecord *cands[DUEL_FIELD_ROW_SIZE];
    DuelCardRecord *card;
#ifndef MEMORIES_PC
    DuelCardRecord **first;
    DuelCardRecord **dst;
#endif
    DuelCardRecord **w;
    DuelCardRecord *c;
    u16 *p;
#ifndef MEMORIES_PC
    u16 *q;
#endif
    s32 i;
    s32 j;
#ifdef MEMORIES_PC
    TablesRitualRequirement requirements[DUEL_RITUAL_TRIBUTE_COUNT];
    u16 conditional_result = 0;
    if (Tables_RitualRequirements(ritualId, requirements, &conditional_result)) {
        int match[DUEL_RITUAL_TRIBUTE_COUNT] = {-1, -1, -1};
        int order[DUEL_RITUAL_TRIBUTE_COUNT] = {0, 1, 2};
        int specificity[DUEL_RITUAL_TRIBUTE_COUNT];
        int a, b, d, x, y;
        i = DUEL_FIELD_ROW_SIZE;
        if (D_8009B1D5 != 0) i = DUEL_CARD_SIDE_RECORD_COUNT + DUEL_FIELD_ROW_SIZE;
        c = &D_801A7AD8[i];
        for (i = 0; i < DUEL_FIELD_ROW_SIZE; i++)
            cands[i] = (c[i].flags & DUEL_CARD_FLAG_OCCUPIED) ? &c[i] : 0;

        /* Decide the tribute slots in specificity order. A named card is
         * always reserved before a broad rule; otherwise the rule with more
         * conditions is narrower. This makes a broad slot unable to consume
         * the only monster a specific slot needs. */
        for (j = 0; j < DUEL_RITUAL_TRIBUTE_COUNT; j++) {
            specificity[j] = requirements[j].card ? 100 : 0;
            specificity[j] += requirements[j].type >= 0;
            specificity[j] += requirements[j].fusion_group != 0;
            specificity[j] += requirements[j].min_attack != 0;
            specificity[j] += requirements[j].min_defense != 0;
            specificity[j] += requirements[j].max_attack >= 0;
            specificity[j] += requirements[j].max_defense >= 0;
            specificity[j] += requirements[j].min_level >= 0;
            specificity[j] += requirements[j].max_level >= 0;
            specificity[j] += requirements[j].defense_gt_attack != 0;
        }
        for (x = 0; x < DUEL_RITUAL_TRIBUTE_COUNT - 1; x++)
            for (y = x + 1; y < DUEL_RITUAL_TRIBUTE_COUNT; y++)
                if (specificity[order[y]] > specificity[order[x]]) {
                    int swap = order[x]; order[x] = order[y]; order[y] = swap;
                }

        /* Try every distinct assignment. Among all valid assignments, compare
         * slots in the specificity order above. The ritual result decides
         * what "weakest" means: a DEF-dominant result spends the lowest DEF
         * first, while an ATK-dominant (or tied) result spends the lowest ATK
         * first. The other printed stat and then field position break ties.
         * Thus a specific-card slot is protected before this economy rule. */
        {
            int result_stats = gDuel_adwCardStats[conditional_result - 1];
            int result_attack = (result_stats & CARD_STAT_VALUE_MASK) * CARD_STAT_SCALE;
            int result_defense = ((result_stats >> CARD_STAT_DEFENSE_SHIFT) & CARD_STAT_VALUE_MASK) * CARD_STAT_SCALE;
            int prefer_defense = result_defense > result_attack;
        for (a = 0; a < DUEL_FIELD_ROW_SIZE; a++) {
            for (b = 0; b < DUEL_FIELD_ROW_SIZE; b++) {
                if (b == a) continue;
                for (d = 0; d < DUEL_FIELD_ROW_SIZE; d++) {
                    int slots[DUEL_RITUAL_TRIBUTE_COUNT] = {a, b, d};
                    int ok = d != a && d != b;
                    if (!ok) continue;
                    for (j = 0; j < DUEL_RITUAL_TRIBUTE_COUNT && ok; j++) {
                        int stats, attack, defense, id;
                        card = cands[slots[j]];
                        if (!card) { ok = 0; break; }
                        id = card->card_id;
                        stats = gDuel_adwCardStats[id - 1];
                        attack = (stats & CARD_STAT_VALUE_MASK) * CARD_STAT_SCALE;
                        defense = ((stats >> CARD_STAT_DEFENSE_SHIFT) & CARD_STAT_VALUE_MASK) * CARD_STAT_SCALE;
                        if (requirements[j].card && id != requirements[j].card &&
                            Cards_BaseId(id) != requirements[j].card) ok = 0;
                        if (requirements[j].type >= 0 && Cards_Type(id) != requirements[j].type) ok = 0;
                        if (requirements[j].fusion_group && !Cards_InFusionGroup(id, requirements[j].fusion_group)) ok = 0;
                        if (attack < requirements[j].min_attack || defense < requirements[j].min_defense) ok = 0;
                        if (requirements[j].max_attack >= 0 && attack > requirements[j].max_attack) ok = 0;
                        if (requirements[j].max_defense >= 0 && defense > requirements[j].max_defense) ok = 0;
                        if (requirements[j].min_level >= 0 && Cards_Level(id) < requirements[j].min_level) ok = 0;
                        if (requirements[j].max_level >= 0 && Cards_Level(id) > requirements[j].max_level) ok = 0;
                        if (requirements[j].defense_gt_attack && defense <= attack) ok = 0;
                    }
                    if (ok) {
                        int better = match[0] < 0;
                        for (x = 0; x < DUEL_RITUAL_TRIBUTE_COUNT && !better && match[0] >= 0; x++) {
                            int slot = order[x];
                            int new_id = cands[slots[slot]]->card_id;
                            int old_id = cands[match[slot]]->card_id;
                            int new_stats = gDuel_adwCardStats[new_id - 1];
                            int old_stats = gDuel_adwCardStats[old_id - 1];
                            int new_def = ((new_stats >> CARD_STAT_DEFENSE_SHIFT) & CARD_STAT_VALUE_MASK) * CARD_STAT_SCALE;
                            int old_def = ((old_stats >> CARD_STAT_DEFENSE_SHIFT) & CARD_STAT_VALUE_MASK) * CARD_STAT_SCALE;
                            int new_atk = (new_stats & CARD_STAT_VALUE_MASK) * CARD_STAT_SCALE;
                            int old_atk = (old_stats & CARD_STAT_VALUE_MASK) * CARD_STAT_SCALE;
                            if (prefer_defense) {
                                if (new_def != old_def) { better = new_def < old_def; break; }
                                if (new_atk != old_atk) { better = new_atk < old_atk; break; }
                            } else {
                                if (new_atk != old_atk) { better = new_atk < old_atk; break; }
                                if (new_def != old_def) { better = new_def < old_def; break; }
                            }
                            if (slots[slot] != match[slot]) { better = slots[slot] < match[slot]; break; }
                        }
                        if (better) {
                            match[0] = a; match[1] = b; match[2] = d;
                        }
                    }
                }
            }
        }
        }
        if (match[0] >= 0) {
            for (j = 0; j < DUEL_RITUAL_TRIBUTE_COUNT; j++) found[j] = cands[match[j]];
            if (out != 0) {
                for (i = 0; i < DUEL_RITUAL_TRIBUTE_COUNT; i++)
                    out->tribute_objects[i] = found[i]->object;
                out->field_0C = 0;
            }
            return conditional_result;
        }
        return 0;
    }
#endif
#ifdef MEMORIES_PC
    /* A mod's recipe, laid out as the disc's table is, comes first. */
    u16 own[DUEL_RITUAL_RECIPE_HALFWORD_COUNT + 1];
    s32 ruled = Tables_Ritual(ritualId, own);

    if (ruled == 0) {
        return 0;
    }
    p = ruled > 0 ? own : gDuel_awRitualData;
#else
    p = gDuel_awRitualData;
#endif
    while (1) {
        if (p[0] == 0) {
            return 0;
        }
        if (p[0] == ritualId) {
            break;
        }
        p += DUEL_RITUAL_RECIPE_HALFWORD_COUNT;
    }

    i = DUEL_FIELD_ROW_SIZE;
    if (D_8009B1D5 != 0) {
        i = DUEL_CARD_SIDE_RECORD_COUNT + DUEL_FIELD_ROW_SIZE;
    }
    c = &D_801A7AD8[i];
    i = 0;
    w = cands;
    for (i = 0; i < DUEL_FIELD_ROW_SIZE; i++) {
        *w = 0;
        if (c->flags & DUEL_CARD_FLAG_OCCUPIED) {
            *w = c;
        }
        w++;
        c++;
    }

    p++;
#ifdef MEMORIES_PC
    /* A copy of a tribute monster counts as it; a mod's recipe may also
       name the copy itself. Every tribute takes a monster that is exactly
       it first, and only then one that is a copy of it: taken in the
       recipe's order, a retail tribute could take the very copy a later
       one names while the retail monster stays on the field. */
    {
        s32 pass;

        for (j = 0; j < DUEL_RITUAL_TRIBUTE_COUNT; j++) {
            found[j] = 0;
        }
        for (pass = 0; pass < 2; pass++) {
            for (j = 0; j < DUEL_RITUAL_TRIBUTE_COUNT; j++) {
                if (found[j] != 0) {
                    continue;
                }
                for (i = 0; i < DUEL_FIELD_ROW_SIZE; i++) {
                    card = cands[i];
                    if (card != 0 && (pass == 0 ? card->card_id == p[j] :
                                      Cards_BaseId(card->card_id) == p[j])) {
                        found[j] = card;
                        cands[i] = 0;
                        break;
                    }
                }
            }
        }
        for (j = 0; j < DUEL_RITUAL_TRIBUTE_COUNT; j++) {
            if (found[j] == 0) {
                return 0;
            }
        }
    }
#else
    j = 0;
    first = cands;
    dst = found;
    q = p;
    for (j = 0; j < DUEL_RITUAL_TRIBUTE_COUNT; j++) {
        for (i = 0; i < DUEL_FIELD_ROW_SIZE; i++) {
            card = (c = first[i]);
            if (card != 0 && card->card_id == q[0]) {
                goto matched;
            }
        }
        return 0;
matched:
        *dst++ = card;
        first[i] = 0;
        q++;
    }
#endif

    if (out != 0) {
        for (i = 0; i < DUEL_RITUAL_TRIBUTE_COUNT; i++) {
            out->tribute_objects[i] = found[i]->object;
        }
        out->field_0C = 0;
    }
    return p[DUEL_RITUAL_TRIBUTE_COUNT];
}
