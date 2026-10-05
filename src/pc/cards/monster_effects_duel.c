/* Monster effects in a duel (monster_effects_duel.h). */
#define D_8009B178_AS_SIDE_ARRAY
#include "monster_effects_duel.h"
#include "cards.h"
#include "tables.h"
#include "pc/mods/mods.h"
#include "pc/mods/events.h"
#include "pc/debug/log.h"
#include "game/card_constants.h"
#include "game/duel_card.h"
#include "game/duel_grid.h"
#include "game/duel_side_state.h"
#include "game/duel_scene_state.h"
#include "game/duel_action_lock.h"
#include "game/duel_effect.h"
#include "game/duel_check_quit_input.h"
#include "game/duel_scene_field_actions.h"
#include "game/duel_magic_effect_dispatch.h"
#include "game/duel_trap_resolution.h"
#include "game/display_object.h"
#include "game/display_object_work_slots.h"
#include "game/duel_selection_layout.h"
#include "game/display_object_core.h"
#include "game/duel_apply_card_object_flags.h"
#include "game/sound.h"
#include <string.h>

/* The mods' event numbers what happened as the cards' "when" does. */
typedef char MonsterEffects_events_match[MEMORIES_MONSTER_SUMMON == MONSTER_WHEN_SUMMON &&
    MEMORIES_MONSTER_FLIP == MONSTER_WHEN_FLIP && MEMORIES_MONSTER_DRAW == MONSTER_WHEN_DRAW &&
    MEMORIES_MONSTER_COMBAT == MONSTER_WHEN_COMBAT && MEMORIES_MONSTER_DESTROYED == MONSTER_WHEN_DESTROYED &&
    MEMORIES_MONSTER_DESTROY_OPPONENT == MONSTER_WHEN_DESTROY_OPPONENT ? 1 : -1];

/* The record of the trap that sprang; the field phase's frame timer (src/unmatched.h). */
extern u8 D_8009B1B8;
extern u16 D_8009B162;

#define S gMonsterEffects
#define PHASE_STARTUP 1
#define PHASE_HAND 4
#define PHASE_FIELD 5
#define PHASE_BATTLE 9
#define PAUSE_FRAMES 24
#define CHAIN_MAX 200           /* a guard: no field settles after this many in a row */
#define SE_HEAL 0x14            /* the LP recovery cards' sound */
#define SE_DAMAGE 0x1C          /* the direct damage cards' */
#define SE_BOOST 0x0C           /* a card put down */
#define SE_FLIP 0x0B            /* a card turned over */
#define CRUSH_CARD 661          /* whose removal a "destroy" plays */

static int monster_zone(int record)
{
    return record >= 0 && record < MONSTER_RECORDS && record % 15 >= 5 && record % 15 < 10;
}
static int owner(int record) { return record / 15; }
static int phase(void) { return gDuel_wSceneStateFlags & DUEL_SCENE_PHASE_MASK; }

static void trace(const char *what, int card, int record, const MonsterEffect *effect)
{
    LOG(LOG_DUEL_EFFECTS, "monster effects: %s card %d record %d side %d: %s %s", what, card, record, owner(record),
        MonsterEffect_WhenNames[effect->when], MonsterEffect_DoNames[effect->action]);
}

static void queue(int card, int record, int when)
{
    const MonsterEffect *effects;
    int n = Cards_MonsterEffects(card, &effects), i;
    for (i = 0; i < n; i++) {
        if (effects[i].when != when) continue;
        if (S.count == MONSTER_QUEUE_MAX) {
            LOG(LOG_DUEL_EFFECTS, "monster effects: queue full: card %d's %s effect dropped", card,
                MonsterEffect_WhenNames[when]);
            return;
        }
        S.queue[S.count].card = (short)card;
        S.queue[S.count].record = (unsigned char)record;
        S.queue[S.count].effect = (unsigned char)i;
        S.count++;
        trace("queued", card, record, &effects[i]);
    }
}

/* MEMORIES_EVENT_MONSTER, before: whether a code mod took the occasion
 * (the card's own effects are then skipped). */
static int announce(int card, int record, int when, unsigned phase)
{
    MemoriesModEvent event = {MEMORIES_EVENT_MONSTER, 0, 0, 0, 0, 0, 0};
    event.phase = phase;
    event.a = card;
    event.b = record;
    event.c = when;
    Mods_Dispatch(&event);
    return event.handled;
}

/* Something happened to the monster `card` at `record`: the mods hear of
 * it, then its own effects for it are queued. */
static void occur(int card, int record, int when)
{
    int taken = announce(card, record, when, MEMORIES_BEFORE);
    if (!taken) queue(card, record, when);
    announce(card, record, when, MEMORIES_AFTER);
}

/* Whether `effect` of the card at `source` reaches the monster `card` at `target`. */
static int reaches(const MonsterEffect *effect, int source, int target, int card)
{
    switch (effect->target) {
    case MONSTER_TARGET_SELF: if (target != source) return 0; break;
    case MONSTER_TARGET_OWN: if (owner(target) != owner(source)) return 0; break;
    case MONSTER_TARGET_OTHERS: if (owner(target) != owner(source) || target == source) return 0; break;
    case MONSTER_TARGET_OPPONENT: if (owner(target) == owner(source)) return 0; break;
    case MONSTER_TARGET_ALL: break;
    case MONSTER_TARGET_BATTLE:
        /* The monster that attacked the flipped one, if it is still there. */
        if (source != S.defender || target != S.attacker || D_801A7AD8[target].card_id != S.attacker_card) return 0;
        break;
    default: return 0;
    }
    if (effect->type >= 0 && Cards_Type(card) != effect->type) return 0;
    if (effect->attribute >= 0 && Cards_Attribute(card) != effect->attribute) return 0;
    return 1;
}

static int clamp(int value, int low, int high) { return value < low ? low : value > high ? high : value; }

/* A lasting boost: the modifiers equips use (both stats share
 * stat_modifier; defense_modifier is DEF's own on top), kept within what
 * their 16 bits and the stat cap leave room for. */
static void boost(DuelCardRecord *card, int attack, int defense)
{
    int room = 2 * Tables_StatCapEither(), had_defense;
    if (room > TABLES_LIMIT_STAT_MAX) room = TABLES_LIMIT_STAT_MAX;
    had_defense = card->stat_modifier + card->defense_modifier;
    card->stat_modifier = (s16)clamp(card->stat_modifier + attack, -room, room);
    card->defense_modifier = (s16)clamp(clamp(had_defense + defense, -room, room) - card->stat_modifier,
                                        -TABLES_LIMIT_STAT_MAX, TABLES_LIMIT_STAT_MAX);
}

static void lend_turn(int side)
{
    D_8009B1D5 = (u8)side;
    D_8009B1C8 = &D_800E9FF0[side];
    D_8009B22C = D_800907D8 + side * DUEL_FIELD_SIDE_GRID_SLOT_COUNT;
}

static void change_life(int side, int amount)
{
    DuelSideState *state = &D_800E9FF0[side];
    int life = state->life_points.signed_value;
    if (amount > 0) {
        int ceiling = state->max_life_points > life ? state->max_life_points : life;
        state->life_points.unsigned_value = (u16)(life + amount > ceiling ? ceiling : life + amount);
        SD_SEPlayFull(SE_HEAL);
    } else {
        life = Mods_DamageLife(side, life, -amount, 1);
        state->life_points.unsigned_value = (u16)(life < 0 ? 0 : life);
        SD_SEPlayFull(SE_DAMAGE);
    }
}

/* One effect off the queue: 1 when the duel waits for it. */
static int resolve(void)
{
    MonsterTrigger trigger = S.queue[0];
    const MonsterEffect *effects, *effect;
    int n = Cards_MonsterEffects(trigger.card, &effects), side = owner(trigger.record), record, hit = 0;
    memmove(S.queue, S.queue + 1, (size_t)(--S.count) * sizeof(S.queue[0]));
    if (trigger.effect >= n) return 0;
    effect = &effects[trigger.effect];
    trace("resolving", trigger.card, trigger.record, effect);
    S.chain++;
    switch (effect->action) {
    case MONSTER_DO_MAGIC:
        /* Played as its owner would play it: on the other side's turn the
         * turn is lent to the owner for as long as the effect runs. */
        if (side != D_8009B1D5) {
            S.swapped = 1;
            S.saved_turn = D_8009B1D5;
            lend_turn(side);
        }
        S.running = 1;
        DuelEffect_StartRetailCardEffect(effect->card, 0);
        return 1;
    case MONSTER_DO_BOOST:
        for (record = 0; record < MONSTER_RECORDS; record++) {
            DuelCardRecord *card = &D_801A7AD8[record];
            if (!monster_zone(record) || !(card->flags & DUEL_CARD_FLAG_OCCUPIED)) continue;
            if (!reaches(effect, trigger.record, record, card->card_id)) continue;
            boost(card, effect->attack, effect->defense);
            hit = 1;
        }
        if (!hit) return 0;
        SD_SEPlayFull(SE_BOOST);
        break;
    case MONSTER_DO_HEAL:
        change_life(side, effect->amount);
        break;
    case MONSTER_DO_DAMAGE:
        change_life(side ^ 1, -effect->amount);
        break;
    case MONSTER_DO_DESTROY:
        /* Crush Card's removal, on the monsters chosen here
         * (MonsterEffects_RemovalTakes): it takes the other side's, as
         * its owner plays it. */
        S.destroy_mask = 0;
        for (record = 0; record < MONSTER_RECORDS; record++) {
            const DuelCardRecord *card = &D_801A7AD8[record];
            if (!monster_zone(record) || owner(record) == side || !(card->flags & DUEL_CARD_FLAG_OCCUPIED)) continue;
            if (reaches(effect, trigger.record, record, card->card_id)) S.destroy_mask |= 1u << record;
        }
        if (!S.destroy_mask) return 0;
        if (side != D_8009B1D5) {
            S.swapped = 1;
            S.saved_turn = D_8009B1D5;
            lend_turn(side);
        }
        S.running = 1;
        DuelEffect_StartRetailCardEffect(CRUSH_CARD, 0);
        return 1;
    }
    S.pause = PAUSE_FRAMES;
    return 1;
}

/* The field as it is now, against the last look: what happened since. */
static void look(void)
{
    int record, side = D_8009B1D5, turns = D_800E9FF0[side].rank.turns_taken;
    if (S.flipped) {
        /* Flipped by the battle just over: its flip resolves first,
         * whether or not the battle destroyed it. */
        occur(S.flipped, S.defender, MONSTER_WHEN_FLIP);
        S.flipped = 0;
    }
    for (record = 0; record < MONSTER_RECORDS; record++) {
        const DuelCardRecord *card = &D_801A7AD8[record];
        int now = 0, up = 0, before = S.card[record];
        if (!monster_zone(record)) continue;
        if (card->flags & DUEL_CARD_FLAG_OCCUPIED && Cards_Valid(card->card_id)) {
            now = card->card_id;
            up = !(card->flags & DUEL_CARD_FLAG_FACE_DOWN);
        }
        if (before && now != before && !S.placed[record] && !S.ritual) {
            occur(before, record, MONSTER_WHEN_DESTROYED);
        }
        if (now && up && (now != before || S.placed[record])) {
            /* A face-down play is no summon: the card's "flip" fires
             * when it is attacked instead (MonsterEffects_Battle). One
             * turned face up any other way -- attacking, Swords -- fires
             * nothing. */
            occur(now, record, MONSTER_WHEN_SUMMON);
        }
        S.card[record] = (short)now;
        S.face_up[record] = (unsigned char)up;
        S.placed[record] = 0;
        S.battle_attack[record] = S.battle_defense[record] = 0;
    }
    S.ritual = 0;
    /* A battle's winner, still there, whose foe it destroyed. */
    for (record = 0; record < 2; record++) {
        int winner = S.fight[record], loser = S.fight[record ^ 1];
        if (monster_zone(winner) && monster_zone(loser) && S.card[winner] == S.fight_card[record] &&
            S.card[loser] != S.fight_card[record ^ 1])
            occur(S.fight_card[record], winner, MONSTER_WHEN_DESTROY_OPPONENT);
    }
    S.fight[0] = S.fight[1] = 0;
    if (side != S.turn_side || turns != S.turn_count) {
        S.turn_side = (unsigned char)side;
        S.turn_count = (unsigned char)turns;
        for (record = 15 * side + 5; record < 15 * side + 10; record++) {
            if (S.card[record] && S.face_up[record]) occur(S.card[record], record, MONSTER_WHEN_DRAW);
        }
    }
}

static void reset(void)
{
    memset(&S, 0, sizeof(S));
}

int MonsterEffects_Update(void)
{
    int now = phase(), waiting;
    if (now == PHASE_STARTUP) {
        if (S.ready) reset();
        return 0;
    }
    if (S.running == 1) {
        /* The first handler is done (most only clear the flags); the
         * second is the effect, as DuelScene_UpdateCardUse runs them. */
        S.running = 2;
        DuelEffect_StartRetailCardEffect(gDuel_wEffectCardID, 1);
        return 1;
    }
    if (S.running == 2) {
        S.running = 0;
        S.destroy_mask = 0;
        if (S.swapped) {
            S.swapped = 0;
            lend_turn(S.saved_turn);
        }
    }
    if (S.pause) {
        S.pause--;
        return 1;
    }
    /* Only as a hand or field phase begins, before its first step: within
     * one the field is not settled (the hand lifts a field monster for a
     * fusion frames before placement takes it). Every way back to them --
     * a card put down, a battle, a card's effect, a new turn -- starts one. */
    if ((now != PHASE_HAND && now != PHASE_FIELD) || (gDuel_wSceneStateFlags & DUEL_SCENE_FLAG_INITIALIZED) ||
        gDuel_bEffectState || gDuel_wCardEffectFlags || gDuel_bQuitDialogState)
        return 0;
    /* A side out of LP: the field phase ends the duel; no more effects. */
    if (!D_800E9FF0[0].life_points.signed_value || !D_800E9FF0[1].life_points.signed_value) {
        S.count = 0;
        if (now == PHASE_HAND) gDuel_wSceneStateFlags = PHASE_FIELD;
        return 0;
    }
    if (!S.ready) {
        reset();
        S.ready = 1;
        S.turn_side = (unsigned char)D_8009B1D5;
        S.turn_count = D_800E9FF0[D_8009B1D5].rank.turns_taken;
        look();
        S.count = 0;
        return 0;
    }
    look();
    /* A code mod may have started a card effect of its own for what it
     * heard: the duel waits for it, and the field is looked at again. */
    if (gDuel_wCardEffectFlags) return 1;
    if (S.count && S.chain >= CHAIN_MAX) {
        LOG(LOG_DUEL_EFFECTS, "monster effects: %d effects in a row: the rest are dropped", S.chain);
        S.count = 0;
    }
    /* One that finds nothing to do (a boost or destroy with no monster
     * left) gives way to the next at once: past this look the phase goes
     * on, and the rest would wait for the player's next move. */
    waiting = 0;
    while (S.count && !waiting) waiting = resolve();
    if (!waiting && !S.count) S.chain = 0;
    return waiting;
}

int MonsterEffects_PlayFaceUp(int card)
{
    const MonsterEffect *effects;
    int n = Cards_MonsterEffects(card, &effects), i, summon = 0, flip = 0, seen = 0;
    for (i = 0; i < n; i++) {
        summon |= effects[i].when == MONSTER_WHEN_SUMMON;
        flip |= effects[i].when == MONSTER_WHEN_FLIP;
        seen |= effects[i].when == MONSTER_WHEN_DRAW || effects[i].when == MONSTER_WHEN_FACE_UP;
    }
    return summon || (seen && !flip);
}

int MonsterEffects_RemovalTakes(int record)
{
    if (!S.destroy_mask) return -1;
    return record >= 0 && record < MONSTER_RECORDS && (S.destroy_mask >> record & 1);
}

void MonsterEffects_FilterTargets(unsigned *objects)
{
    int i, n = 0;
    if (!S.destroy_mask) return;
    for (i = 0; objects[i]; i++) {
        const DisplayObject *object = (const DisplayObject *)(uintptr_t)objects[i];
        if (object->field_6A < MONSTER_RECORDS && (S.destroy_mask >> object->field_6A & 1)) objects[n++] = objects[i];
    }
    objects[n] = 0;
}

void MonsterEffects_Placed(int record, int equip)
{
    /* A card put back on its own zone (the 0x4000 placement, which an equip
     * and a fusion onto a field monster both take) is a new card only when
     * it is another card: the fusion's result, not the equipped monster. */
    if (monster_zone(record) && (!equip || D_801A7AD8[record].card_id != S.card[record])) S.placed[record] = 1;
}

void MonsterEffects_EffectStarted(int ritual)
{
    if (ritual) S.ritual = 1;
}

void MonsterEffects_Battle(void)
{
    const DisplayObject *attacker = (const DisplayObject *)D_800E9EF0[0];
    const DisplayObject *defender = (const DisplayObject *)D_800E9EF0[1];
    int records[2], i, played = 0;
    if (!S.ready || D_8009B22A || !attacker) return;
    records[0] = attacker->field_6A;
    records[1] = defender ? defender->field_6A : -1;
    /* A face-down defender is flipped by the battle: as Yu-Gi-Oh! has it,
     * its flip resolves after the damage is worked out (with the card as
     * it is), at the next look, before what the battle destroyed. */
    S.flipped = 0;
    if (monster_zone(records[1]) && monster_zone(records[0]) && (D_8009B178[1] & DUEL_CARD_FLAG_FACE_DOWN)) {
        S.flipped = D_801A7AD8[records[1]].card_id;
        S.defender = (unsigned char)records[1];
        S.attacker = (unsigned char)records[0];
        S.attacker_card = D_801A7AD8[records[0]].card_id;
    }
    /* Who won it is seen at the next look (DESTROY_OPPONENT). */
    for (i = 0; i < 2; i++) {
        S.fight[i] = (unsigned char)(monster_zone(records[i]) ? records[i] : 0);
        S.fight_card[i] = (short)(monster_zone(records[i]) ? D_801A7AD8[records[i]].card_id : 0);
    }
    for (i = 0; i < 2; i++) {
        const MonsterEffect *effects;
        int record = records[i], other = records[i ^ 1], card, n, e;
        if (!monster_zone(record)) continue;
        card = D_801A7AD8[record].card_id;
        /* Face up from here: its face_up boosts count in the battle. */
        if (card == S.card[record]) S.face_up[record] = 1;
        n = announce(card, record, MONSTER_WHEN_COMBAT, MEMORIES_BEFORE) ? 0 : Cards_MonsterEffects(card, &effects);
        for (e = 0; e < n; e++) {
            const MonsterEffect *effect = &effects[e];
            if (effect->when != MONSTER_WHEN_COMBAT) continue;
            trace("battle", card, record, effect);
            played = 1;
            if (effect->action == MONSTER_DO_HEAL) {
                change_life(owner(record), effect->amount);
            } else if (effect->action == MONSTER_DO_DAMAGE) {
                change_life(owner(record) ^ 1, -effect->amount);
            } else if (effect->action == MONSTER_DO_BOOST) {
                int to = effect->target == MONSTER_TARGET_BATTLE ? other : record;
                if (!monster_zone(to) || !reaches(&(MonsterEffect){.target = MONSTER_TARGET_ALL, .type = effect->type,
                                                                  .attribute = effect->attribute},
                                                  record, to, D_801A7AD8[to].card_id))
                    continue;
                S.battle_attack[to] = (short)clamp(S.battle_attack[to] + effect->attack, -TABLES_LIMIT_STAT_MAX,
                                                   TABLES_LIMIT_STAT_MAX);
                S.battle_defense[to] = (short)clamp(S.battle_defense[to] + effect->defense, -TABLES_LIMIT_STAT_MAX,
                                                    TABLES_LIMIT_STAT_MAX);
            }
        }
        announce(card, record, MONSTER_WHEN_COMBAT, MEMORIES_AFTER);
    }
    if (played) SD_SEPlayFull(SE_BOOST);
}

void MonsterEffects_Stats(const void *pointer, int *attack, int *defense)
{
    const DuelCardRecord *card = pointer;
    int target = (int)(card - D_801A7AD8), source;
    if (!S.ready || !monster_zone(target)) return;
    if (phase() == PHASE_BATTLE) {
        *attack += S.battle_attack[target];
        *defense += S.battle_defense[target];
    }
    for (source = 0; source < MONSTER_RECORDS; source++) {
        const MonsterEffect *effects;
        int n, e;
        if (!S.card[source] || !S.face_up[source]) continue;
        n = Cards_MonsterEffects(S.card[source], &effects);
        for (e = 0; e < n; e++) {
            if (effects[e].when != MONSTER_WHEN_FACE_UP || !reaches(&effects[e], source, target, card->card_id))
                continue;
            *attack += effects[e].attack;
            *defense += effects[e].defense;
        }
    }
}
