/* The deck a new game starts with, as mods write it down (starter.h,
 * notes/starter-deck.md).
 *
 * Each applied mod's "starter" is read into the decks here, once, in the
 * order the mods load, and they add up: a mod adds its decks to whatever the
 * mods before it offered rather than replacing them. NameEntry_BuildStarterDeck
 * asks for one before it reads the disc's pools, and takes the disc's path
 * when no mod offers any.
 *
 * A deck is forty cards written down by their copies, as an opponent's fixed
 * deck is (tables.c). The counts are the deck, so the three-copy limit of a
 * dealt deck does not apply here either: the author wrote down every copy.
 * What a player would not be able to rebuild in Build Deck afterwards is
 * said in the Mods window, and the deck is dealt as written. */
#include "starter.h"
#include "cards.h"
#include "pc/mods/mods.h"
#include "pc/mods/json.h"
#include "pc/debug/log.h"
#include "game/card_constants.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct {
    const char *mod;    /* the manifest's, which outlives these */
    const char *name;   /* its "name", or NULL for the mod's own */
    unsigned weight;
    unsigned short cards[STARTER_DECK_SIZE];
} StarterDeck;

static StarterDeck *decks;
static int deck_count, deck_room;

static void *grow(void *array, int *room, int count, size_t size)
{
    void **slot = (void **)array;
    if (count >= *room) {
        int wanted = *room ? *room * 2 : 8;
        void *bigger = realloc(*slot, (size_t)wanted * size);
        if (!bigger) return NULL;
        *slot = bigger;
        *room = wanted;
    }
    return (char *)*slot + (size_t)count * size;
}

typedef struct {
    int id, copies;
} Copies;

static int by_id(const void *left, const void *right)
{
    return ((const Copies *)left)->id - ((const Copies *)right)->id;
}

/* A deck's own keys, which are not cards. */
static int control_key(const char *name)
{
    return !strcmp(name, "name") || !strcmp(name, "weight");
}

/* The most a weight may be: enough for any mix a mod wants, and far enough
 * from an unsigned's end that the weights of every deck still add up. */
#define STARTER_WEIGHT_LIMIT 1000000

/* One deck: { "name": ..., "weight": ..., card: copies, ... }, the copies
 * adding up to the forty cards of a deck. */
static void read_deck(const char *mod, const char *where, const JsonValue *entry)
{
    Copies *list;
    StarterDeck deck, *slot;
    const JsonValue *weight_value;
    long weight;
    int i, n = 0, dealt = 0, total = 0, pieces = 0, over = 0;
    if (Json_TypeOf(entry) != JSON_OBJECT) {
        Mods_Note(mod, "%s: a starter deck is an object of cards and their copies", where);
        return;
    }
    weight_value = Json_Member(entry, "weight");
    weight = Json_Number(weight_value, 1);
    if (weight_value && (Json_TypeOf(weight_value) != JSON_NUMBER || weight < 0 || weight > STARTER_WEIGHT_LIMIT)) {
        Mods_Note(mod, "%s: a deck's \"weight\" is how often it is picked, 0 to %d", where, STARTER_WEIGHT_LIMIT);
        return;
    }
    list = calloc((size_t)Json_Count(entry) + 1, sizeof(*list));
    if (!list) return;
    for (i = 0; i < Json_Count(entry); i++) {
        const JsonValue *member = Json_At(entry, i);
        const char *name = Json_Name(member);
        long copies;
        int id;
        char at[160];
        if (control_key(name)) continue;
        snprintf(at, sizeof(at), "%s \"%s\"", where, name);
        id = Cards_Named(name);
        if (id <= 0) {
            Mods_Note(mod, "%s: no such card", at);
            continue;
        }
        copies = Json_Number(member, -1);
        if (Json_TypeOf(member) != JSON_NUMBER || copies < 0 || copies > STARTER_DECK_SIZE) {
            Mods_Note(mod, "%s: a starter deck gives each card its copies, 0 to %d", at, STARTER_DECK_SIZE);
            continue;
        }
        total += (int)copies;
        if (!copies) continue;
        /* What Build Deck would not let the player put back, once they take
         * the deck apart: its three-copy limit, and one Exodia piece each. */
        if (copies > DECK_CARD_COPY_LIMIT) over++;
        if (Cards_ExodiaPiece(id) && copies > 1) pieces++;
        list[n].id = id;
        list[n++].copies = (int)copies;
    }
    /* The save holds forty cards (SaveDataState's player_deck), so a deck of
     * any other size is not a deck this can deal. */
    if (total != STARTER_DECK_SIZE) {
        Mods_Note(mod, "%s: a starter deck is %d cards, and this one has %d; left out", where, STARTER_DECK_SIZE,
                  total);
        free(list);
        return;
    }
    if (over) {
        Mods_Note(mod, "%s: %d card%s with more than %d copies; dealt as written, and Build Deck will not take "
                       "them back", where, over, over == 1 ? "" : "s", DECK_CARD_COPY_LIMIT);
    }
    if (pieces) {
        Mods_Note(mod, "%s: %d Exodia piece%s with more than one copy; dealt as written, and Build Deck will not "
                       "take them back", where, pieces, pieces == 1 ? "" : "s");
    }
    /* In id order, as the disc's own pools are read. */
    qsort(list, (size_t)n, sizeof(*list), by_id);
    memset(&deck, 0, sizeof(deck));
    deck.mod = mod;
    deck.name = Json_String(Json_Member(entry, "name"), NULL);
    deck.weight = (unsigned)weight;
    for (i = 0; i < n; i++) {
        int copy;
        for (copy = 0; copy < list[i].copies; copy++) deck.cards[dealt++] = (unsigned short)list[i].id;
    }
    free(list);
    slot = grow(&decks, &deck_room, deck_count, sizeof(*decks));
    if (!slot) return;
    *slot = deck;
    deck_count++;
}

/* "starter": one deck, or a list of them. */
static void read_starter(const char *mod, const JsonValue *value)
{
    char where[64];
    int i;
    if (!value) return;
    if (Json_TypeOf(value) == JSON_OBJECT) {
        read_deck(mod, "starter", value);
        return;
    }
    if (Json_TypeOf(value) != JSON_ARRAY) {
        Mods_Note(mod, "\"starter\" is a deck, or a list of decks");
        return;
    }
    for (i = 0; i < Json_Count(value); i++) {
        snprintf(where, sizeof(where), "starter %d", i + 1);
        read_deck(mod, where, Json_At(value, i));
    }
}

void Starter_Add(const char *mod, const JsonValue *manifest)
{
    read_starter(mod, Json_Member(manifest, "starter"));
}

void Starter_Clear(void)
{
    free(decks);
    decks = NULL;
    deck_count = deck_room = 0;
}

void Starter_Build(void)
{
    static int built;
    int i;
    if (built) return;
    built = 1;
    for (i = 0; i < Mods_LoadedCount(); i++) {
        int mod = Mods_Loaded(i);
        if (Mods_Active(mod)) Starter_Add(Mods_Id(mod), Mods_Manifest(mod));
    }
    if (deck_count) {
        LOG(LOG_MODS, "starter: %d deck%s offered, %u weight between them", deck_count, deck_count == 1 ? "" : "s",
            Starter_WeightTotal());
    }
}

int Starter_Count(void)
{
    return deck_count;
}

unsigned Starter_WeightTotal(void)
{
    unsigned total = 0;
    int i;
    for (i = 0; i < deck_count; i++) total += decks[i].weight;
    return total;
}

static int write_deck(const StarterDeck *deck, unsigned short cards[STARTER_DECK_SIZE], const char **name)
{
    memcpy(cards, deck->cards, sizeof(deck->cards));
    if (name) *name = deck->name;
    if (Log_Wanted(LOG_MODS)) {
        char text[STARTER_DECK_SIZE * 12];
        int at = 0, i;
        for (i = 0; i < STARTER_DECK_SIZE; i++) {
            int copies = 1;
            while (i + 1 < STARTER_DECK_SIZE && deck->cards[i + 1] == deck->cards[i]) i++, copies++;
            at += snprintf(text + at, sizeof(text) - (size_t)at, " %dx%d", copies, deck->cards[i]);
        }
        LOG(LOG_MODS, "starter: \"%s\" from %s (copies x card):%s", deck->name ? deck->name : "a deck", deck->mod,
            text);
    }
    return 1;
}

int Starter_DeckAt(int index, unsigned short cards[STARTER_DECK_SIZE], const char **name)
{
    if (index < 0 || index >= deck_count) return 0;
    return write_deck(&decks[index], cards, name);
}

int Starter_Deck(unsigned roll, unsigned short cards[STARTER_DECK_SIZE], const char **name)
{
    unsigned acc = 0;
    int i;
    for (i = 0; i < deck_count; i++) {
        acc += decks[i].weight;
        if (roll < acc) return write_deck(&decks[i], cards, name);
    }
    /* Past every weight: the roll came from a total these decks no longer
     * add up to, or they all weigh nothing. The last one that weighs
     * anything is a deck; no deck at all leaves the disc's pools to it. */
    for (i = deck_count - 1; i >= 0; i--) {
        if (decks[i].weight) return write_deck(&decks[i], cards, name);
    }
    return 0;
}
