/* Game > Card drops (src/pc/cards/drops.c) over a made-up drop pool: every
 * card is one roll of the game's Duel_SelectCardDrop (which a code mod may
 * hook), in the community drop mod's order of draws, 1 + 7N for N cards.
 * tables.c (Tables_Scale, Tables_Pool) is linked as it is. */
#include "../../src/pc/cards/drops.c"
#include "pc/mods/json.h"
#include "pc/debug/log.h"
#include "game/duel_rewards.h"
#include <stdarg.h>
#include <stdio.h>

#define CHECK(condition)                                                        \
    do {                                                                        \
        if (!(condition)) {                                                     \
            fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #condition);     \
            exit(1);                                                            \
        }                                                                       \
    } while (0)

/* --- the game around drops.c ------------------------------------------- */

int gCard_nCount = CARD_COUNT;
signed char gDuel_bOpponentID = 1;
CardDropsState gCardDrops;
u16 gDuel_awPlayerDeck[DECK_SIZE];
DuelDropTable gDuel_awSaPowCardDrops[3];
static unsigned char chest[CARD_COUNT + 1];
static int card_drops = 1;
static unsigned seed = 1, draws;

int Settings_Get(SettingId id) { return id == SET_CARD_DROPS ? card_drops : 0; }
int Memories_Rand(void)
{
    draws++;
    seed = seed * 1103515245u + 12345u;
    return (int)((seed >> 16) & 0x7FFF);
}
int Glyphs_Code(uint32_t character) { return (int)character; }
const unsigned char *Text_Own(int id) { (void)id; return NULL; } /* no translation: the port's English */
const unsigned char *Cards_NameCodes(int id) { (void)id; return NULL; }
unsigned char *Cards_ChestSlot(void *state, int id)
{
    static unsigned char nowhere;
    (void)state;
    return id >= 1 && id <= CARD_COUNT ? &chest[id] : &nowhere;
}
int Cards_Valid(int id) { return id >= 1 && id <= gCard_nCount; }
int Cards_BaseId(int id) { return Cards_Valid(id) ? id : 0; }
int Cards_EffectId(int id) { return Cards_BaseId(id); }
int Cards_RetailType(int id) { (void)id; return -1; }
int Cards_PickVariant(int id, int use) { (void)use; return id; }
/* The game's roll (duel_result_runtime.c) over the retail rows. */
s32 Duel_SelectCardDrop(s32 pool)
{
    s32 threshold = (Memories_Rand() & (DUEL_DROP_WEIGHT_TOTAL - 1)) + 1, sum = 0, i;
    for (i = 0; i < CARD_COUNT; i++) {
        sum += gDuel_awSaPowCardDrops[pool].weights[i];
        if (sum >= threshold) return i + 1;
    }
    return 0;
}
void Duel_AwardCard(s32 id) { chest[id]++; }

/* What tables.c asks of the cards and the mods: no mod edits a pool. */
int Cards_Type(int id) { (void)id; return 0; }
int Cards_TypeNamed(const char *text) { (void)text; return -1; }
int Cards_FusionGroupNamed(const char *text) { (void)text; return 0; }
int Cards_Attribute(int id) { (void)id; return 0; }
int Cards_AttributeNamed(const char *text) { (void)text; return -1; }
int Cards_Named(const char *text) { (void)text; return -1; }
int Cards_Reference(const JsonValue *value) { (void)value; return -1; }
int Mods_EntryUsed(const char *id, const JsonValue *entry, const char *where) { (void)id; (void)entry; (void)where; return 1; }
void Mods_Note(const char *id, const char *format, ...) { (void)id; (void)format; }
int Log_Wanted(LogChannel channel) { (void)channel; return 0; }
void Log_Printf(LogChannel channel, const char *format, ...) { (void)channel; (void)format; }
int Mods_LoadedCount(void) { return 0; }
int Mods_Loaded(int index) { return index; }
int Mods_Active(int mod) { (void)mod; return 0; }
const char *Mods_Id(int mod) { (void)mod; return ""; }
const JsonValue *Mods_Manifest(int mod) { (void)mod; return NULL; }

/* --- the pool ------------------------------------------------------------ */

/* POW row: cards 5-10, 2048 in all. */
static const struct {
    int id;
    unsigned weight;
} pool[] = {{5, 700}, {6, 500}, {7, 400}, {8, 248}, {9, 100}, {10, 100}};
#define POOL_CARDS (int)(sizeof(pool) / sizeof(pool[0]))

static void reset(void)
{
    int i;
    memset(chest, 0, sizeof(chest));
    memset(gDuel_awPlayerDeck, 0, sizeof(gDuel_awPlayerDeck));
    memset(gDuel_awSaPowCardDrops, 0, sizeof(gDuel_awSaPowCardDrops));
    for (i = 0; i < POOL_CARDS; i++) gDuel_awSaPowCardDrops[0].weights[pool[i].id - 1] = (u16)pool[i].weight;
    CardDrops_Begin();
}

static int in_pool(int id)
{
    int i;
    for (i = 0; i < POOL_CARDS; i++) {
        if (pool[i].id == id) return 1;
    }
    return 0;
}

/* `wanted` cards from the same seed: the draws, the cards dealt, and SPOILS'
 * card from the pool. */
static void rolls(void)
{
    int wanted, spoils, i;
    for (wanted = 1; wanted <= 20; wanted += 19) {
        reset();
        card_drops = wanted;
        seed = 0x1234;
        draws = 0;
        spoils = CardDrops_Roll(0);
        CHECK(in_pool(spoils));
        CHECK(gCardDrops.count == wanted - 1);
        CHECK(draws == (wanted == 1 ? 1u : 1u + 7u * (unsigned)wanted));
        for (i = 0; i < gCardDrops.count; i++) CHECK(in_pool(gCardDrops.cards[i]));
    }
    card_drops = 1;
}

/* One card is the game's own roll, card for card. */
static void same_as_the_game(void)
{
    int run, cards[2][64];
    reset();
    seed = 77;
    for (run = 0; run < 64; run++) cards[0][run] = CardDrops_Roll(0);
    seed = 77;
    for (run = 0; run < 64; run++) cards[1][run] = Duel_SelectCardDrop(0);
    CHECK(!memcmp(cards[0], cards[1], sizeof(cards[0])));
}

int main(void)
{
    rolls();
    same_as_the_game();
    puts("card drops: rolls passed");
    return 0;
}
