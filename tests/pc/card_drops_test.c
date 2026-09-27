/* Game > Smart drops (src/pc/cards/drops.c): a made-up drop pool and a
 * chest with three copies of some of its cards. The cards the player has
 * three of leave the pool, the rest add up to 2048 again, a full pool
 * stands as it is, and a roll takes the same draws with the setting on or
 * off. tables.c (Tables_Scale, Tables_Pool) is linked as it is. */
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
static int smart, card_drops = 1;
static unsigned seed = 1, draws;

int Settings_Get(SettingId id) { return id == SET_SMART_DROPS ? smart : id == SET_CARD_DROPS ? card_drops : 0; }
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
int Cards_Named(const char *text) { (void)text; return -1; }
int Cards_Reference(const JsonValue *value) { (void)value; return -1; }
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

static void load(unsigned *weights)
{
    int id;
    for (id = 0; id <= CARD_COUNT; id++) weights[id] = id ? gDuel_awSaPowCardDrops[0].weights[id - 1] : 0;
}

static unsigned total(const unsigned *weights)
{
    unsigned sum = 0;
    int id;
    for (id = 1; id <= CARD_COUNT; id++) sum += weights[id];
    return sum;
}

static int in_pool(int id)
{
    int i;
    for (i = 0; i < POOL_CARDS; i++) {
        if (pool[i].id == id) return 1;
    }
    return 0;
}

/* Three copies of 5 in the chest, of 6 across the deck and the chest, and
 * of 9 once this duel's dealt copy counts; 7 has two, 8 and 10 none. */
static void partial(void)
{
    reset();
    chest[5] = 3;
    chest[6] = 2;
    gDuel_awPlayerDeck[0] = 6;
    chest[7] = 2;
    chest[9] = 2;
    gCardDrops.cards[gCardDrops.count++] = 9;
}

static void excludes_the_full_cards(void)
{
    static unsigned weights[CARD_COUNT + 1];
    int id;
    partial();
    load(weights);
    CHECK(CardDrops_SmartPool(weights, CARD_COUNT) == 3);
    CHECK(weights[5] == 0 && weights[6] == 0 && weights[9] == 0);
    CHECK(weights[7] && weights[8] && weights[10]);
    CHECK(total(weights) == DUEL_DROP_WEIGHT_TOTAL);
    /* 400 : 248 : 100 of 748, scaled to 2048 by the largest remainders. */
    CHECK(weights[7] == 1095 && weights[8] == 679 && weights[10] == 274);
    for (id = 1; id <= CARD_COUNT; id++) CHECK(in_pool(id) || weights[id] == 0);
}

static void a_full_pool_stands(void)
{
    static unsigned weights[CARD_COUNT + 1], before[CARD_COUNT + 1];
    int id;
    reset();
    for (id = 1; id <= CARD_COUNT; id++) chest[id] = 3;   /* the cheat's 3 of every card */
    load(weights);
    load(before);
    CHECK(CardDrops_SmartPool(weights, CARD_COUNT) == 0);
    CHECK(!memcmp(weights, before, sizeof(weights)));
    /* And nothing full leaves it alone too. */
    reset();
    chest[5] = 2;
    load(weights);
    CHECK(CardDrops_SmartPool(weights, CARD_COUNT) == 0);
    CHECK(!memcmp(weights, before, sizeof(weights)));
}

/* The partial chest with 9 at three too: 7, 8 and 10 have room for seven
 * more copies in all. */
static void open_chest(void)
{
    partial();
    chest[9] = 3;
}

/* `wanted` cards from the same seed; 1 + 7 * wanted draws (drops.c). */
static int roll(int on, int wanted, unsigned *used)
{
    int spoils;
    open_chest();
    card_drops = wanted;
    smart = on;
    seed = 0x1234;
    draws = 0;
    spoils = CardDrops_Roll(0);
    *used = draws;
    card_drops = 1;
    smart = 0;
    return spoils;
}

static void rolls(void)
{
    unsigned used[2], seeds[2];
    int on, i, spoils;
    /* Five cards fit in the room left: none reaches a fourth copy, SPOILS'
     * card (rolled last, after the others count) included. */
    for (on = 0; on < 2; on++) {
        spoils = roll(on, 5, &used[on]);
        seeds[on] = seed;
        CHECK(in_pool(spoils) && gCardDrops.count == 4);
        if (!on) continue;
        for (i = 0; i < gCardDrops.count; i++) {
            int id = gCardDrops.cards[i];
            CHECK(id == 7 || id == 8 || id == 10);
            CHECK(copies(id) <= DECK_CARD_COPY_LIMIT);
        }
        CHECK((spoils == 7 || spoils == 8 || spoils == 10) && copies(spoils) < DECK_CARD_COPY_LIMIT);
    }
    CHECK(used[0] == 1 + 7 * 5 && used[1] == used[0] && seeds[0] == seeds[1]);
    /* Twenty do not: the first seven fill the room, and then every card is
     * at three and the pool stands as the game has it. */
    for (on = 0; on < 2; on++) {
        spoils = roll(on, 20, &used[on]);
        seeds[on] = seed;
        CHECK(in_pool(spoils) && gCardDrops.count == 19);
    }
    CHECK(used[0] == 1 + 7 * 20 && used[1] == used[0] && seeds[0] == seeds[1]);
    {
        int dealt[CARD_COUNT + 1] = {0};
        for (i = 0; i < 7; i++) dealt[gCardDrops.cards[i]]++;
        CHECK(dealt[7] == 1 && dealt[8] == 3 && dealt[10] == 3);
    }
}

/* Off, and on with nothing full: the game's own roll, card for card. */
static void same_as_the_game(void)
{
    int on, run, cards[2][64];
    for (on = 0; on < 2; on++) {
        reset();
        chest[5] = 2;
        smart = on;
        seed = 77;
        for (run = 0; run < 64; run++) cards[on][run] = CardDrops_Roll(0);
    }
    CHECK(!memcmp(cards[0], cards[1], sizeof(cards[0])));
    smart = 0;
}

int main(void)
{
    excludes_the_full_cards();
    a_full_pool_stands();
    rolls();
    same_as_the_game();
    puts("card drops: smart pools passed");
    return 0;
}
