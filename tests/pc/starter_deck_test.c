/* The deck a new game starts with, as mods write it down
 * (src/pc/cards/starter.c, notes/starter-deck.md): real manifests through the
 * real JSON reader, over a made-up card table where a card is named by its
 * id. What is checked without a screen: a deck's size, the copies, the id
 * order it is dealt in, the notes a deck that cannot be dealt raises, the
 * weights a roll picks by, and the decks of several mods adding up.
 *
 * A deck of forty from cards nobody has more than three of takes fourteen of
 * them, so the decks here are filled out by `filler`: every case is an
 * ordinary deck but for the one thing it is checking. */
#include "../../src/pc/cards/starter.c"
#include <stdarg.h>

#define CHECK(condition)                                                        \
    do {                                                                        \
        if (!(condition)) {                                                     \
            fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #condition);     \
            exit(1);                                                            \
        }                                                                       \
    } while (0)

/* --- the port around starter.c ----------------------------------------- */

int gCard_nCount = CARD_COUNT;

/* A card is named by its id, so a deck reads as the ids it deals. Ids past
 * the disc's CARD_COUNT stand for the cards a mod adds. */
int Cards_Named(const char *text)
{
    char *end;
    long id;
    if (!text || !*text) return 0;
    id = strtol(text, &end, 10);
    return !*end && id >= CARD_ID_FIRST && id <= 2000 ? (int)id : 0;
}
int Cards_ExodiaPiece(int id)
{
    return id >= EXODIA_FIRST_CARD_ID && id < EXODIA_CARD_ID_END;
}

static int notes;
static char note[512];
void Mods_Note(const char *id, const char *format, ...)
{
    va_list arguments;
    (void)id;
    notes++;
    va_start(arguments, format);
    vsnprintf(note, sizeof(note), format, arguments);
    va_end(arguments);
}
int Log_Wanted(LogChannel channel) { (void)channel; return 0; }
void Log_Printf(LogChannel channel, const char *format, ...) { (void)channel; (void)format; }

/* Starter_Build's mod list: the tests call Starter_Add themselves. */
int Mods_LoadedCount(void) { return 0; }
int Mods_Loaded(int index) { (void)index; return 0; }
int Mods_Active(int mod) { (void)mod; return 0; }
const char *Mods_Id(int mod) { (void)mod; return "test"; }
const JsonValue *Mods_Manifest(int mod) { (void)mod; return NULL; }

/* --- the harness -------------------------------------------------------- */

/* A manifest's decks. The document lives on: a deck keeps its "name" by
 * pointer into it, exactly as a mod's manifest outlives the decks it gave. */
static void add(const char *mod, const char *text)
{
    char error[256];
    JsonDocument *document = Json_Parse(text, error, sizeof(error));
    CHECK(document != NULL);
    Starter_Add(mod, Json_Root(document));
}

static void one(const char *text)
{
    Starter_Clear();
    notes = 0;
    note[0] = 0;
    add("test", text);
}

/* The rest of a deck of forty after `used` cards: distinct cards three at a
 * time, from ids that are neither Exodia's nor a mod's. Each member comes
 * with the comma before it, to follow whatever the case wrote. */
static const char *filler(int used)
{
    static char text[512];
    int at = 0, id = 100, left = STARTER_DECK_SIZE - used;
    text[0] = 0;
    while (left > 0) {
        int n = left < DECK_CARD_COPY_LIMIT ? left : DECK_CARD_COPY_LIMIT;
        at += snprintf(text + at, sizeof(text) - (size_t)at, ",\"%d\":%d", id++, n);
        left -= n;
    }
    return text;
}

int main(void)
{
    unsigned short cards[STARTER_DECK_SIZE];
    const char *name;
    char text[1024];
    int i;

    /* No "starter" at all: the disc's pools stand. */
    one("{\"id\":\"quiet\"}");
    CHECK(Starter_Count() == 0);
    CHECK(Starter_WeightTotal() == 0);
    CHECK(!Starter_Deck(0, cards, &name));
    CHECK(notes == 0);

    /* One deck of forty, dealt in id order whatever order it was written in. */
    snprintf(text, sizeof(text), "{\"starter\":{\"name\":\"Giants\",\"700\":3,\"3\":3,\"41\":3%s}}", filler(9));
    one(text);
    CHECK(Starter_Count() == 1);
    CHECK(Starter_WeightTotal() == 1);   /* a deck without a weight weighs 1 */
    CHECK(notes == 0);
    CHECK(Starter_Deck(0, cards, &name));
    CHECK(name && !strcmp(name, "Giants"));
    CHECK(cards[0] == 3 && cards[2] == 3);
    CHECK(cards[3] == 41 && cards[5] == 41);
    CHECK(cards[6] == 100);
    CHECK(cards[37] == 700 && cards[39] == 700);
    for (i = 1; i < STARTER_DECK_SIZE; i++) CHECK(cards[i - 1] <= cards[i]);   /* in id order */

    /* A card the disc has not got is dealt like any other: naming the cards
     * is the whole point of writing a deck down. */
    one("{\"starter\":{\"900\":3,\"901\":3,\"902\":3,\"903\":3,\"904\":3,\"905\":3,\"906\":3,"
        "\"907\":3,\"908\":3,\"909\":3,\"910\":3,\"911\":3,\"912\":3,\"913\":1}}");
    CHECK(Starter_Count() == 1 && notes == 0);
    CHECK(Starter_Deck(0, cards, NULL));
    CHECK(cards[0] == 900 && cards[STARTER_DECK_SIZE - 1] == 913);

    /* Not forty cards: the save holds forty, so neither size is a deck. */
    snprintf(text, sizeof(text), "{\"starter\":{\"3\":2%s}}", filler(3));
    one(text);
    CHECK(Starter_Count() == 0 && notes == 1);
    CHECK(strstr(note, "40 cards") && strstr(note, "39"));
    snprintf(text, sizeof(text), "{\"starter\":{\"3\":3%s,\"200\":1}}", filler(3));
    one(text);
    CHECK(Starter_Count() == 0 && notes == 1 && strstr(note, "41"));

    /* A card that is not one: noted, and the forty are short without it. */
    snprintf(text, sizeof(text), "{\"starter\":{\"Blue-eyes\":3%s}}", filler(3));
    one(text);
    CHECK(Starter_Count() == 0);
    CHECK(notes == 2);   /* no such card, then the size */

    /* Copies outside 0 to forty: noted, and that card is left out. */
    snprintf(text, sizeof(text), "{\"starter\":{\"3\":-1%s}}", filler(0));
    one(text);
    CHECK(Starter_Count() == 1 && notes == 1 && strstr(note, "copies"));

    /* A weight outside its own range, and one that is not a number. */
    snprintf(text, sizeof(text), "{\"starter\":{\"weight\":-1%s}}", filler(0));
    one(text);
    CHECK(Starter_Count() == 0 && notes == 1 && strstr(note, "weight"));
    snprintf(text, sizeof(text), "{\"starter\":{\"weight\":\"2\"%s}}", filler(0));
    one(text);
    CHECK(Starter_Count() == 0 && notes == 1 && strstr(note, "weight"));

    /* Zero copies are no card at all, and leave the forty to the others. */
    snprintf(text, sizeof(text), "{\"starter\":{\"3\":0%s}}", filler(0));
    one(text);
    CHECK(Starter_Count() == 1 && notes == 0);
    CHECK(Starter_Deck(0, cards, NULL) && cards[0] == 100);

    /* What Build Deck would not take back is said, and the deck is dealt as
     * written: the author wrote down every copy. */
    snprintf(text, sizeof(text), "{\"starter\":{\"5\":4%s}}", filler(4));
    one(text);
    CHECK(Starter_Count() == 1 && notes == 1);
    CHECK(strstr(note, "more than 3 copies"));
    CHECK(Starter_Deck(0, cards, NULL) && cards[0] == 5 && cards[3] == 5 && cards[4] == 100);
    snprintf(text, sizeof(text), "{\"starter\":{\"17\":2%s}}", filler(2));
    one(text);
    CHECK(Starter_Count() == 1 && notes == 1 && strstr(note, "Exodia"));
    /* One piece each raises nothing. */
    snprintf(text, sizeof(text), "{\"starter\":{\"17\":1,\"18\":1,\"19\":1,\"20\":1,\"21\":1%s}}", filler(5));
    one(text);
    CHECK(Starter_Count() == 1 && notes == 0);

    /* A list of decks, picked by their weights: 3 and 1 of 4. */
    snprintf(text, sizeof(text), "{\"starter\":[{\"name\":\"a\",\"weight\":3,\"3\":3%s},"
                                 "{\"name\":\"b\",\"4\":3%s}]}", filler(3), filler(3));
    one(text);
    CHECK(Starter_Count() == 2);
    CHECK(Starter_WeightTotal() == 4);
    for (i = 0; i < 3; i++) {
        CHECK(Starter_Deck((unsigned)i, cards, &name) && !strcmp(name, "a"));
    }
    CHECK(Starter_Deck(3, cards, &name) && !strcmp(name, "b"));

    /* A weight of nothing is a deck that is never picked. */
    snprintf(text, sizeof(text), "{\"starter\":[{\"name\":\"never\",\"weight\":0,\"3\":3%s},"
                                 "{\"name\":\"always\",\"4\":3%s}]}", filler(3), filler(3));
    one(text);
    CHECK(Starter_Count() == 2 && Starter_WeightTotal() == 1);
    CHECK(Starter_Deck(0, cards, &name) && !strcmp(name, "always"));

    /* Every deck weighing nothing leaves the disc's pools to it. */
    snprintf(text, sizeof(text), "{\"starter\":[{\"weight\":0,\"3\":3%s}]}", filler(3));
    one(text);
    CHECK(Starter_Count() == 1 && Starter_WeightTotal() == 0);
    CHECK(!Starter_Deck(0, cards, NULL));

    /* A roll past every weight still deals a deck rather than nothing. */
    snprintf(text, sizeof(text), "{\"starter\":{\"3\":3%s}}", filler(3));
    one(text);
    CHECK(Starter_Deck(99, cards, NULL) && cards[0] == 3);
    /* And a deck without a name has none. */
    CHECK(Starter_DeckAt(0, cards, &name) && name == NULL);

    /* The decks of several mods add up, in the order the mods load. */
    Starter_Clear();
    notes = 0;
    snprintf(text, sizeof(text), "{\"starter\":{\"name\":\"one\",\"3\":3%s}}", filler(3));
    add("first", text);
    snprintf(text, sizeof(text), "{\"starter\":[{\"name\":\"two\",\"4\":3%s},"
                                 "{\"name\":\"three\",\"5\":3%s}]}", filler(3), filler(3));
    add("second", text);
    CHECK(Starter_Count() == 3 && Starter_WeightTotal() == 3 && notes == 0);
    CHECK(Starter_DeckAt(0, cards, &name) && !strcmp(name, "one") && cards[0] == 3);
    CHECK(Starter_DeckAt(1, cards, &name) && !strcmp(name, "two") && cards[0] == 4);
    CHECK(Starter_DeckAt(2, cards, &name) && !strcmp(name, "three") && cards[0] == 5);
    CHECK(!Starter_DeckAt(3, cards, &name));
    CHECK(!Starter_DeckAt(-1, cards, &name));

    /* "starter" of the wrong shape is noted, not read. */
    one("{\"starter\":40}");
    CHECK(Starter_Count() == 0 && notes == 1 && strstr(note, "list of decks"));
    one("{\"starter\":[40]}");
    CHECK(Starter_Count() == 0 && notes == 1 && strstr(note, "object of cards"));

    Starter_Clear();
    printf("starter deck: ok\n");
    return 0;
}
