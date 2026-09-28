#ifndef MEMORIES_PC_STARTER_H
#define MEMORIES_PC_STARTER_H
/* The deck a new game starts with, as mods write it down
 * (notes/starter-deck.md).
 *
 * A mod's manifest may carry "starter": one deck, or a list of them, each
 * forty cards written down by their copies. When any applied mod offers one,
 * NameEntry_BuildStarterDeck deals a deck from this list in place of the
 * disc's seven weighted pools; the decks every applied mod offers add up, and
 * one of them is picked at random for each new game.
 *
 * Writing the deck down rather than weighting a pool is what lets a starting
 * deck hold a card the disc has not got: the disc's pools are 722 weights of
 * a fixed width, and its generator reads only the first 720 of them
 * (STARTER_DECK_WEIGHT_SCAN_COUNT), so no weight can name a card a mod added.
 * A written deck names cards by id, so a mod's own are dealt like any other.
 *
 * Nothing here runs when no mod offers a deck: the disc's pools are read as
 * they always were, and draw the random numbers they always drew. */
#include "game/card_constants.h"

#define STARTER_DECK_SIZE DECK_SIZE

/* Read every applied mod's "starter"; once, from Cards_Build. */
void Starter_Build(void);

/* Starter_Build without a mod list: one manifest's decks, for the tests. */
struct JsonValue;
void Starter_Add(const char *mod, const struct JsonValue *manifest);
void Starter_Clear(void);

/* How many decks the applied mods offer between them; 0 when none do, and
 * the disc's pools stand. */
int Starter_Count(void);

/* The total of every offered deck's weight, for the roll Starter_Deck takes;
 * 0 when no deck is offered. A deck's "weight" is 1 unless it says. */
unsigned Starter_WeightTotal(void);

/* The deck a roll of `roll` (0 to Starter_WeightTotal() - 1) picks: its forty
 * cards, in id order, in `cards`, and its name in *name when `name` is not
 * NULL. 1 when a deck was written there, 0 when no mod offers one (leaving
 * both alone). The caller draws the roll, so the random numbers a new game
 * spends stay where the game spends them. */
int Starter_Deck(unsigned roll, unsigned short cards[STARTER_DECK_SIZE], const char **name);

/* The deck at `index` (0 to Starter_Count() - 1), for the tests and the log:
 * as Starter_Deck writes it, picked by place rather than by weight. */
int Starter_DeckAt(int index, unsigned short cards[STARTER_DECK_SIZE], const char **name);

#endif
