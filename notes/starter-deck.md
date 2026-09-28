# The deck a new game starts with

A mod may write down the forty cards a new game begins with, in place of the
seven weighted pools the disc draws them from. Several decks may be offered,
and one is picked for each new game.

The disc's own generator, and why this does not extend it, is in
[starter-deck pool tables](starter-deck-pools.md).

## The manifest

`starter` is one deck, or a list of them. A deck is its cards and their
copies, adding up to forty:

```json
{
    "id": "shadow-start",
    "starter": [
        {
            "name": "Spellbinder",
            "weight": 3,
            "Mystical Elf": 3,
            "Dark Magician": 1,
            "Magical Ghost": 3
        },
        { "name": "Beatdown", "Hitotsu-Me Giant": 3 }
    ]
}
```

| Key | Meaning |
|---|---|
| `name` | the deck's own name, for the Mods window and the log. Without one the mod's name stands for it |
| `weight` | how often this deck is the one picked, against the other decks offered. 1 without one; 0 is a deck that is never picked, which is how a deck is kept in a manifest without being used |
| *(anything else)* | a card and how many copies of it, 0 to 40. A card is named as `decks` and `drops` name one: its name, its stable identity, or its id |

The decks of every applied mod add up, in the order the mods load: a mod adds
its own to the ones before it rather than replacing them. A weight is against
every offered deck, not only its own mod's.

## Where the deck comes from

`NameEntry_BuildStarterDeck` (`src/overlays/password/name_entry_main.c`) asks
for a deck before it reads the disc's pools, and takes the disc's path when no
mod offers one. Nothing else in the name-entry screen changes.

Writing the deck down is what lets a starting deck hold a card the disc has
not got. The disc's pools are 722 weights of a fixed width and its generator
reads only the first 720 of them, so no weight can name a card a mod added
(`STARTER_DECK_WEIGHT_SCAN_COUNT`, `src/game/card_constants.h`). A written
deck names cards by id, so a mod's own are dealt like any other.

## How it is done

`src/pc/cards/starter.c` reads each applied mod's `starter` once, from
`Cards_Build`, after the cards and the tables, because a deck names cards.
A deck is kept as its forty ids in id order, as an opponent's fixed deck is
(`src/pc/cards/tables.c`).

The overlay draws the roll and the port picks by it, so the random numbers a
new game spends stay where the game spends them:

```c
total = Starter_WeightTotal();
if (total && Starter_Deck(rand() % total, cards, 0)) { /* deal them */ }
```

One random number picks the deck, where the pools would have drawn one for
each card and one for every weight they walked past. A new game that takes a
mod's deck therefore leaves the RNG stream somewhere the disc would not have;
that is what letting a mod name the cards costs, and it is why a run without
a starter mod still spends exactly what it always did. The stream's shape for
the disc's own draw is in [RNG](rng.md).

Each card is marked seen through `Cards_MarkSeen`, not
`Library_UpdateCardUsedFlag`: that flag is `0x120 + id` masked to eleven bits,
so a card past the disc's own would land on another campaign flag. The port
remembers the cards a mod added beside the flags instead
(`src/pc/cards/cards.c`).

## Limits

* A deck is forty cards. The save holds forty
  (`player_deck`, `src/game/save_data.h`), so a deck of any other size is
  left out, with a line in the Mods window saying what it counted.
* A card that is not one is left out, which usually leaves the forty short,
  and both are said.
* The copies are the deck: the three-copy limit of a dealt deck does not
  apply, as it does not to an opponent's fixed deck. The author wrote down
  every copy, and a limit could only refuse the list or change it behind
  their back. What Build Deck would not take back afterwards — more than
  three copies of a card, or more than one of an Exodia piece — is said in
  the Mods window, and the deck is dealt as written.
* A weight is 0 to 1,000,000, so the weights of every offered deck still add
  up in an `unsigned`.
* Every offered deck weighing nothing leaves the disc's pools to it.
* The player does not choose: the deck is picked for them. A screen to choose
  one would read the same decks, and is not here.

## Checking it

`tests/pc/starter_deck_test.c` (`ctest -R pc_starter_deck`) covers what is
settled without a screen: a deck's size and its copies, the id order it is
dealt in, a card that is not one, copies and weights out of range, the notes
the two Build Deck rules raise, the weights a roll picks by, a roll past every
weight, a deck that weighs nothing, and the decks of several mods adding up.
It runs real manifests through the real JSON reader.

On a screen, with `examples/mods/starter-deck`: a new game dealt the deck the
log names, its forty cards in Build Deck, the Library showing them seen, and
the save loaded back in a fresh process with the deck intact. Without a
starter mod the new game's deck is the disc's, and the smoke screenshots are
unchanged.
