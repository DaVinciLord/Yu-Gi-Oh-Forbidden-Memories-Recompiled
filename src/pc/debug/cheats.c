#include "pc/compat/fs.h"
#include "cheats.h"
#include "types.h"
#include "game/card_constants.h"
#include "game/save_data.h"
#include "pc/cards/cards.h"
#include "pc/platform/settings.h"
#include "game/duel_side_state.h"
#include <stdio.h>
#include <stdlib.h>

/* The duel's reward stops the balance here (func_800218F0). */
#define CHEATS_STARCHIPS_MAX 999999u

/* The chest lives in the persistent save state at 0x801D0250: one byte per
 * card, ids 1..722, read by the Library, BUILD DECK and the duel's deck
 * checks, and written out whole by SAVE. */
void Cheats_GiveAllCards(int count)
{
    int id;
    if (count < 0) {
        count = 0;
    }
    if (count > CARD_CHEST_QUANTITY_MAX) {
        count = CARD_CHEST_QUANTITY_MAX;
    }
    for (id = 0; id < CARD_COUNT; id++) {
        gLibrary_abCardChest[id] = (u8)count;
    }
    /* And the cards mods added, whose trunk is kept outside the save. */
    for (id = CARD_ID_END; id <= gCard_nCount; id++) {
        *Cards_ChestSlot(gDuel_awPlayerDeck, id) = (u8)count;
    }
    fprintf(stderr, "memories-pc: chest now holds %d of every card\n", count);
}

void Cheats_UnlockAllFreeDuelists(void)
{
    const SaveDataWorkspace *save = (const SaveDataWorkspace *)D_801D0000;
    int opponent;
    /* Before a game is started or loaded, this workspace is scratch. */
    if (save->state.player_deck[0] == 0) {
        fprintf(stderr, "memories-pc: start or load a game before unlocking Free Duel opponents\n");
        return;
    }
    /* Match FreeDuel_Init's locked range. The other grid entries (including
     * Master K) are already available; these flags do not mark story wins. */
    for (opponent = FREE_DUEL_STORY_OPPONENT_FIRST_INDEX;
         opponent < FREE_DUEL_STORY_OPPONENT_INDEX_END; opponent++) {
        Library_UpdateCardUsedFlag(FREE_DUEL_UNLOCK_FLAG_BASE + opponent);
    }
    fprintf(stderr, "memories-pc: all CPU duelists unlocked; reopen Free Duel to refresh the roster, then save to keep them\n");
}

/* SaveDataState.starchips (0x801D07E0), which the duel's reward caps at
 * 999999 (func_800218F0) and the Password screen spends. That screen copies
 * the balance for display when it opens and at each payment step, so a
 * change made while it is open shows from the next of those. */
void Cheats_SetStarchips(unsigned value)
{
    if (value > CHEATS_STARCHIPS_MAX) value = CHEATS_STARCHIPS_MAX;
    gLibrary_dwStarchips = value;
    fprintf(stderr, "memories-pc: StarChips now %u\n", value);
}

int Cheats_StartingLifePoints(void)
{
    return Settings_Get(SET_CHEAT_LIFE_POINTS);
}

int Cheats_FreeSpending(void)
{
    return Settings_Get(SET_CHEAT_FREE_SPENDING);
}

extern signed char gDuel_bOpponentID;

/* The card display reads a side's card_view_mode through this
 * (DUEL_CARD_VIEW_MODE). Duel_InitSideStates gives the CPU's record -1,
 * which draws the hand it plays from as card backs and dims it; 0, the
 * player's, draws the cards. With the cheat on the CPU's record reads 0.
 * Two-player duels (a negative opponent) keep the value their setup chose. */
s8 Cheats_CardViewMode(const DuelSideState *side)
{
    if (side->card_view_mode < 0 && side == &D_800E9FF0[1] && gDuel_bOpponentID >= 0 &&
        Settings_Get(SET_CHEAT_SHOW_HAND)) {
        return 0;
    }
    return side->card_view_mode;
}

/* MEMORIES_DEBUG_DECK: the forty cards of the deck, as ids and ranges
 * ("723-762", "1,2,723"), repeated until the deck is full. */
static void set_deck(const char *list)
{
    SaveDataWorkspace *save = (SaveDataWorkspace *)D_801D0000;
    int ids[DECK_SIZE], count = 0, i;
    const char *p = list;
    while (*p && count < DECK_SIZE) {
        char *end;
        long first = strtol(p, &end, 10), last;
        if (end == p) break;
        last = first;
        if (*end == '-') last = strtol(end + 1, &end, 10);
        for (; first <= last && count < DECK_SIZE; first++) {
            if (first >= CARD_ID_FIRST && first <= gCard_nCount) ids[count++] = (int)first;
        }
        p = *end == ',' ? end + 1 : end;
    }
    if (!count) return;
    for (i = 0; i < DECK_SIZE; i++) save->state.player_deck[i] = (u16)ids[i % count];
    fprintf(stderr, "memories-pc: deck set from %s\n", list);
}

void Cheats_Frame(void)
{
    static int wanted = -2; /* -2 unread, -1 off, else pending count */
    static const char *deck;
    const SaveDataWorkspace *save = (const SaveDataWorkspace *)D_801D0000;
    if (wanted == -2) {
        const char *value = getenv("MEMORIES_DEBUG_CHEST");
        wanted = value && *value ? atoi(value) : -1;
        deck = getenv("MEMORIES_DEBUG_DECK");
        if (deck && !*deck) deck = NULL;
    }
    if (wanted < 0 && !deck) {
        return;
    }
    /* A live save has a deck; before that the workspace is scratch. */
    if (save->state.player_deck[0] != 0) {
        if (wanted >= 0) Cheats_GiveAllCards(wanted);
        if (deck) set_deck(deck);
        wanted = -1;
        deck = NULL;
    }
}
