#ifndef MEMORIES_PC_MONSTER_EFFECTS_DUEL_H
#define MEMORIES_PC_MONSTER_EFFECTS_DUEL_H
/* Monster effects in a duel (monster_effects.h has what a card may do).
 *
 * The duel has no one place where a monster is summoned or destroyed, so
 * the field is looked at whenever it has settled: as a hand or field phase
 * begins, no card effect or presentation running. What changed in the
 * monster zones since the last look is what happened -- a card placement
 * put down face up was summoned (a face-down one was not), one that left was
 * destroyed unless placement put another in its zone (fusion material) or a
 * ritual took it (a tribute). Each change fires once, then the look is the
 * new reference. A face-down monster attacked is flipped: as in Yu-Gi-Oh!,
 * the battle runs as ever and its flip resolves after it, at the next
 * look, before what the battle destroyed. The effects resolve one at a
 * time, a retail magic
 * card's effect through the game's own card-effect dispatch, which keeps
 * the duel waiting just as playing the card does.
 *
 * "combat" fires as a battle starts (no trap sprang), its boosts lasting
 * the battle; "face_up" boosts are worked out whenever the
 * game asks a card's ATK/DEF (Duel_CalcCardStats), so the field, the
 * battle, traps and the CPU's view of the board all see them, each source
 * once on each monster it reaches, newcomers too.
 *
 * The state is the game's (src/pc/game/trigger_state.c), in save states. */
#include "monster_effects.h"

#define MONSTER_RECORDS 30
#define MONSTER_QUEUE_MAX 48

typedef struct {
    short card;
    unsigned char record, effect;
} MonsterTrigger;

typedef struct {
    unsigned char ready;        /* the look below is this duel's */
    unsigned char running;      /* 1, 2: a magic effect's first or second handler is running */
    unsigned char swapped;      /* the turn was lent to the effect's owner: saved_turn is the real one */
    unsigned char saved_turn;
    unsigned char turn_side, turn_count;   /* the turn the last look was in */
    unsigned char ritual;       /* a ritual ran since the last look: who left were its tributes */
    unsigned char pause;        /* frames the duel waits after a boost or LP change */
    unsigned char count;        /* queue */
    unsigned char pad;
    unsigned char attacker, defender;   /* the last battle's records */
    unsigned short chain;       /* effects resolved since the field last settled */
    short flipped;              /* the card that battle flipped (the defender), its flip still to fire */
    short attacker_card;        /* the card that attacked it: a flip's "battle" target */
    unsigned char fight[2];     /* the last battle's attacker and defender records, 0 none */
    short fight_card[2];
    unsigned int destroy_mask;  /* the records a "destroy" takes, while its Crush Card runs */
    short card[MONSTER_RECORDS];
    unsigned char face_up[MONSTER_RECORDS];
    unsigned char placed[MONSTER_RECORDS];  /* placement put a card here since the last look */
    short battle_attack[MONSTER_RECORDS], battle_defense[MONSTER_RECORDS];
    MonsterTrigger queue[MONSTER_QUEUE_MAX];
} MonsterEffectsState;

extern MonsterEffectsState gMonsterEffects;

/* DuelScene_Update, before the scene's step: 1 to skip the step this frame. */
int MonsterEffects_Update(void);
/* Placement committed a card to `record` (func_8001B170, the ritual):
 * `equip` when it put a field monster back on its zone (an equip, or a
 * fusion onto it). */
void MonsterEffects_Placed(int record, int equip);
/* A card effect started (DuelEffect_StartCardEffect): a ritual's. */
void MonsterEffects_EffectStarted(int ritual);
/* A battle begins (DuelScene_UpdateBattle, once the attack trap is known). */
void MonsterEffects_Battle(void);
/* The CPU puts this monster down face up (its effects want it seen). */
int MonsterEffects_PlayFaceUp(int card);
/* Crush Card's removal (DuelEffect_ApplyMonsterRemoval) as a
 * "destroy" runs it: -1 as ever, else whether it takes `record`. */
int MonsterEffects_RemovalTakes(int record);
/* What face-up monsters and the battle add to a card's ATK and DEF. */
void MonsterEffects_Stats(const void *record, int *attack, int *defense);

#endif
