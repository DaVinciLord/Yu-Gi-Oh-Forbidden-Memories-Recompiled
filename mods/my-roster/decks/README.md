# `decks/` — what a duelist plays

One file to a duelist, named for its id: `decks/dark-simon.json` gives a deck
to the duelist that `duelists/dark-simon.json` made.

**A duelist with no file here plays the deck of the duelist it copies.** That
is the whole fallback — you only write a file when you want something else.

```json
{
    "replace": true,
    "Blue-eyes White Dragon": 200,
    "Mystical Elf": 100,
    "Baby Dragon": 100
}
```

---

## It is a pool, not a deck list

The game does not store an opponent's forty cards. It stores a **weight for
every one of the 722 cards**, and deals a deck by drawing from them.

Dealing one card: pick a number from 1 to 2048, walk the card list adding up
weights, and take the card you land on. Repeat until forty cards are dealt,
skipping any card already dealt three times.

So a weight is a **share of 2048**, and what matters is the ratio between them:

```json
{ "replace": true, "Blue-eyes White Dragon": 1, "Mystical Elf": 3 }
```

is the same deck as

```json
{ "replace": true, "Blue-eyes White Dragon": 512, "Mystical Elf": 1536 }
```

Mystical Elf three times as often as Blue-Eyes, in both. Your numbers are
rescaled to add up to 2048 when the pool is built, so you never have to make
them add up yourself.

Because cards are drawn with repetition and capped at three copies, a heavy
card is nearly certain to appear three times, and a pool of fourteen equal
cards gives a fairly even spread of about three each.

---

## `replace`

**`"replace": true`** throws the base's pool away. Only the cards you list are
in the deck.

**Without it**, your cards take the share you give them and everything the base
had splits what is left over:

```json
{ "Blue-eyes White Dragon": 400 }
```

Blue-Eyes about a fifth of the deck (400 of 2048), the base's usual pool for
the other four fifths. This is the lighter touch — good for slipping one card
into an existing deck without rebuilding it.

If your listed weights already reach 2048 or more, the rest are dropped and
your cards are the pool in proportion, the same as `replace`.

---

## What is refused

Two mistakes leave the base's deck untouched and put a line in the Mods window:

**Fewer than 14 cards with weight.** A deck is 40 cards and at most 3 of each,
so 14 is the fewest a pool can fill one from. `{"replace": true, "Blue-eyes
White Dragon": 1}` cannot make a deck and is refused outright — this is the
single most common surprise.

**A pool that comes out empty**, for instance when every name in it is
misspelt.

Refusal is per pool, not per file. Everything else in the mod still loads.

---

## Card names

The game's own, from `notes/card-catalog.csv`. Case and punctuation are
ignored, so `blue-eyes white dragon` works — but the name must be the one
**Forbidden Memories** uses, which is not always the card's name today:

| write | not |
| --- | --- |
| `Winged Dragon #1` | Winged Dragon, Guardian of the Fortress #1 |
| `Trial of Nightmares` | Trial of Nightmare |
| `Red-eyes B. Dragon` | Red-Eyes Black Dragon |

A card id works too: `"122": 100`.

A name that matches nothing is reported and left out; the rest of the pool
still applies. A card that is not in the game at all — Wall of Illusion, say —
has no id to give it, so there is nothing to write.

---

## Naming the file

Normally the id of your own `duelists/<id>.json`. But the name is also matched
against the duelists themselves, so you can reach one you did not add:

| filename | reaches |
| --- | --- |
| `dark-simon.json` | your `duelists/dark-simon.json` |
| `Heishin.json` | the disc's Heishin, whether or not a mod renamed it |
| `all.json` | **every** duelist at once |

`all.json` is applied to each of them in turn, so `{"Raigeki": 100}` without
`replace` slips Raigeki into everyone's deck.

Your own id is tried first, so a file named after a duelist you added always
means yours.

---

## Sorting and order

Files are read in the order their names sort, and each mod's folder in mod load
order, with the user directory's read **last**. Two edits to one duelist's deck
both apply, in that order, so the later one sits on top.

---

See [`../README.md`](../README.md) for the folders as a whole, and
[`../drops/README.md`](../drops/README.md) for the pools that decide what you
*win*, which work the same way.
