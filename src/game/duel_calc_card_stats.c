#include "../types.h"
#include "card_constants.h"
#include "duel_card.h"
#ifdef MEMORIES_PC
#include "pc/cards/tables.h"
#endif

/* Effective attack and defense for one card, packed into a single word:
 * defense in the high half, attack in the low half. Both modifiers apply to
 * both stats, and each half is clamped to 0..CARD_STAT_MAX independently.
 *
 * Callers take one half or the other -- `& 0xFFFF` or a (u16) cast for the
 * attack, `>> 16` for the defense -- so the packing is the whole point of the
 * return value and it must stay a full word.
 */
s32 Duel_CalcCardStats(DuelCardRecord *card)
{
    s32 attack = card->attack + card->stat_modifier + card->terrain_modifier;
    s32 defense;
    if (attack < 0) attack = 0;
#ifdef MEMORIES_PC
    /* A mod's "limits" may move either cap (tables.h); both halves stay
       within 16 bits, as the callers read them. */
    if (attack > Tables_StatCap(0)) attack = Tables_StatCap(0);
#else
    if (attack > CARD_STAT_MAX) attack = CARD_STAT_MAX;
#endif
    defense = card->defense + card->stat_modifier + card->terrain_modifier;
    if (defense < 0) defense = 0;
#ifdef MEMORIES_PC
    if (defense > Tables_StatCap(1)) defense = Tables_StatCap(1);
#else
    if (defense > CARD_STAT_MAX) defense = CARD_STAT_MAX;
#endif
    return (defense << 16) | attack;
}
