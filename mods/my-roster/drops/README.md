# `drops/` — what you win from a duelist

One file to a duelist, named for its id: `drops/dark-simon.json` decides what
the duelist that `duelists/dark-simon.json` made gives you for a win.

**A duelist with no file here gives the cards of the duelist it copies**, and a
pool you leave out of the file stays the base's. You only write what you want
to change.

```json
{
    "pow": { "replace": true, "Blue-eyes White Dragon": 1, "Dark Magician": 1 },
    "bcd": { "Kuriboh": 3 },
    "tec": { "replace": true, "Raigeki": 1 }
}
```

---

## The three pools, and which one you get

Every duelist carries three separate pools. Which you draw from is decided by
the **rank** you finish the duel with — not by the duelist, and not by chance:

| pool | also spelled | you draw from it when |
| --- | --- | --- |
| `pow` | `sa-pow` | you finish **S or A**, and the rank was earned on power |
| `bcd` | `b-c-d` | you finish **B, C or D** — power or technique, it makes no difference |
| `tec` | `sa-tec` | you finish **S or A**, and the rank was earned on technique |

A duel is scored into a single number that starts at 50 (see `ranks` in
[`../duelists/README.md`](../duelists/README.md)). Below 50 the rank counts as
technique and the number is mirrored; the result picks a tier from D up to S.
Tiers below A always take `bcd`, so **the two good pools are only reachable
with an A or an S**.

That is why `ranks` and `drops` are worth thinking about together: making a
duelist easier to earn an S from makes its `pow` or `tec` pool reachable, and
making it harder locks players into `bcd`.

You may give one pool, two or all three.

---

## Weights

Exactly as decks work. A pool is a weight for each of the 722 cards, and
winning draws one card from it: pick a number from 1 to 2048, walk the list
adding weights, take the card you land on.

So a weight is a **share of 2048** and only the ratios matter —
`{"A": 1, "B": 3}` and `{"A": 512, "B": 1536}` are the same pool. Your numbers
are rescaled when the pool is built.

**`"replace": true`** throws the base's pool away and yours is the whole pool.
Without it, your cards take the share you name and the base's pool splits what
is left:

```json
{ "pow": { "Blue-eyes White Dragon": 200 } }
```

Blue-Eyes about a tenth of the time, the duelist's usual drops otherwise.

A pool that comes out empty is refused and the base's stands, with a line in
the Mods window. Unlike decks there is no minimum card count — a single-card
pool is a perfectly good drop table, and is the usual way to make a duelist
farmable for one card:

```json
{ "tec": { "replace": true, "Blue-eyes White Dragon": 1 } }
```

That means an S or A on technique always gives Blue-Eyes.

---

## Card names

The game's own, from `notes/card-catalog.csv`. Case and punctuation ignored,
but the name must be the one Forbidden Memories uses — `Winged Dragon #1`, not
"Winged Dragon, Guardian of the Fortress #1"; `Trial of Nightmares`, plural. An
id works too. A name matching nothing is reported and left out.

---

## Naming the file

Normally the id of your own `duelists/<id>.json`, but the name is matched
against the duelists themselves too:

| filename | reaches |
| --- | --- |
| `dark-simon.json` | your `duelists/dark-simon.json` |
| `Simon Muran.json` | the disc's Simon Muran — spaces in filenames are fine |
| `all.json` | **every** duelist at once |

Editing a disc duelist's drops needs no `duelists/` file at all: a file named
after it here is enough.

`all.json` is applied to each duelist in turn, so this makes every opponent in
the game capable of dropping one card without disturbing anything else:

```json
{ "tec": { "Blue-eyes White Dragon": 100 } }
```

---

## Sorting and order

Files are read in the order their names sort, each mod's folder in mod load
order, and the user directory's **last**. Two edits to one pool both apply in
that order, the later on top — so `all.json` followed by a named file lets you
set a baseline and then override one duelist.

---

See [`../README.md`](../README.md) for the folders as a whole,
[`../decks/README.md`](../decks/README.md) for the pool a duelist plays from,
and `ranks` in [`../duelists/README.md`](../duelists/README.md) for the scoring
that picks which pool here you reach.
