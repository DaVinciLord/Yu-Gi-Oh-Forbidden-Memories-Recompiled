# `duelists/` — who a duelist is

One file to a duelist. **The filename is the id**: `dark-simon.json` makes a
duelist whose id is `dark-simon`, and `decks/`, `drops/` and `portraits/` reach
it by that same name. Nothing inside the file repeats it — an `"id"` property
here is ignored.

This is the only folder a duelist needs. The other three are all optional.

```json
{
    "copy": "Simon Muran",
    "name": "Dark Simon"
}
```

That is complete. It appears on the grid at the first free place, playing Simon
Muran's deck, giving his cards, wearing his face and playing his way — but
under its own name.

---

## How the folder is read

Only `*.json` is read. Anything else is ignored, which is what lets your save's
win and loss records (`<save code>.txt`) live in this same folder when it is the
user directory's.

Files are read **in the order their names sort**, not the order the folder
lists them. This matters: a duelist without a `slot` takes the lowest free
place, so read order decides where it lands. Sorting means a roster places
itself identically on every machine.

Each mod's folder is read in mod load order, and **the user directory's is read
last**, so a character you add yourself is placed after every mod's and never
pushes one of theirs aside.

---

## `copy` — building on one of the disc's

```json
{ "copy": "Heishin" }
```

Required, unless you use `replace`. It names one of the disc's 39 opponents,
**1 to 39**, by name or by id. That duelist is the **base**.

The base is where everything comes from that this file does not say: the deck,
the three drop pools, the portrait, and the nine numbers that decide how it
plays. It is also where the game reads the disc — an added duelist has no block
of its own on the disc, so every read goes to its base's.

Names ignore case and punctuation, so `heishin`, `Heishin` and `HEISHIN` are the
same. The full list is in `notes/more-duelists.md`.

## `replace` — taking over one of the disc's

```json
{ "replace": "Heishin", "name": "Heishin the Elder" }
```

Instead of adding a duelist, the entry takes over an existing one. It keeps its
place on the grid, its win and loss record and its campaign appearances, but
its name, face, way of playing and unlock become this file's.

- Use `replace` **or** `copy`, not both.
- `slot` is meaningless here: it has a place already.
- `decks/`, `drops/` and `portraits/` files for it are named after **this
  file's id**, not the duelist's. `duelists/heishin-remade.json` wants
  `decks/heishin-remade.json`.
- The duelist still answers to its original name everywhere else, so another
  mod's `decks/Heishin.json` keeps finding it.

**Two mods replacing the same duelist:** the one loading later has it.

A replacement that changes only one thing is a normal way to tweak a disc
duelist — this changes nothing but how duels against Nitemare are scored:

```json
{ "replace": "Nitemare", "ranks": { "turns": [[3, 12], [32767, -40]] } }
```

---

## `name`

What the Free Duel grid and the duel call it. Without one it uses its base's.

Only letters the game has can be shown; anything it cannot draw is left out and
noted in the Mods window.

## `slot` — where it sits on the grid

```json
{ "copy": "Heishin", "slot": 45 }
```

The id it wants, **40 to 255**, which *is* its place on the grid:

- page = `slot / 40`
- cell = `slot % 40`, filling five columns down and eight across

So 40 is the first cell of page 2, 45 is the sixth, and 80 starts page 3.

Without a `slot` it takes the lowest free place. Slots are handed out once
every mod has been read, **explicit ones first**, so an entry that asked for a
place is never beaten to it by one that would have taken anything.

**Two entries wanting the same slot:** the earlier mod keeps it and the later
takes the next free place, and is told so. This is the opposite of how `replace`
resolves, deliberately — moving a duelist that is already placed would
rearrange a roster its own mod laid out, while a newcomer has asked for nothing
anyone depends on.

A slot nothing was placed in is not a duelist: its cell stays empty, exactly as
a locked one does. So `"slot": 90` makes three pages with most of the third
blank.

## `portrait`

A path to its picture, for when the file is not `portraits/<id>.png`:

```json
{ "copy": "Heishin", "portrait": "art/faces/mine.png" }
```

Relative to the mod, and it cannot reach outside it. You rarely want this — see
[`../portraits/README.md`](../portraits/README.md).

---

## `unlock` — when it appears

Every condition given must hold. Without `unlock` it is shown from the start.

```json
"unlock": {
    "beat": "Dark Simon",
    "wins": 2,
    "story": 1762,
    "card": "Blue-eyes White Dragon",
    "copies": 1
}
```

| condition | what it asks |
| --- | --- |
| `beat` | a duelist you must have beaten — by id, name or identity |
| `wins` | how many wins: against `beat` when there is one (**1** by default), otherwise against every duelist put together |
| `story` | a campaign story flag. `0x6E0 + n` is "duelist *n* is unlocked in Free Duel", so `1762` is Teana's |
| `card` | a card the trunk or deck must hold — by id or name |
| `copies` | how many of `card` (**1** by default) |

**Nothing is stored.** Each condition is read from the save's own records,
trunk and flags every time the Free Duel screen is built. So an unlock follows
whichever save is loaded, needs no file of its own, and a win in the duel you
just left opens up whatever it was the condition for — the screen is built
again on the way back.

A condition naming something that is not here — a duelist from a mod that is
switched off, a misspelt card — leaves the duelist **locked**, never open. A
roster does not open up by accident.

Chaining works: gate B behind A, and C behind B.

**On a replacement**, `unlock` stands *in place of* the campaign flag that
would normally decide, not beside it. That is how you make a disc duelist
available from the start, or hold one back.

---

## `ai` — how it plays

Nine numbers. Give them as a list, or as an object that borrows another
duelist's row and writes over part of it.

```json
"ai": { "copy": "Nitemare", "search": 20, "values": [20, 20, 10, 3, 2] }
```

| property | what it does |
| --- | --- |
| `copy` | take the whole row from this duelist. It may be one another mod adds — rows are settled after every mod has been read |
| `search` | byte 0 on its own |
| `values` | a list, from byte 0. Shorter than nine is fine; the rest come from `copy`, or from the base |
| `sight` | whether it reads face-down cards — see below. Not a byte in the row |

That row reads: look 20 cards deep, change behaviour below 2000 life points
(byte 1 is the threshold ÷100), clamp the fusion search once 10 cards are left,
and fuse at depth 3 and 2. Bytes 5 to 8 are not listed, so they come from
Nitemare's row.

`values` is read after `search`, so when both write byte 0, `values` wins.

A plain list is the same as `values`:

```json
"ai": [20, 20, 10, 3, 2, 0, 0, 75, 25]
```

### The nine bytes

**Byte 0 — deck search window, 5 to 20.** How many cards deep into its deck it
may look for something to play. This is the biggest difficulty dial there is:
Simon Muran and the villagers see **5** and are effectively playing off the top
of the deck, while Heishin sees **20** and finds his fusion material almost
every turn whatever he drew.

**Byte 1 — life-point threshold, stored ÷100.** Below this many life points it
changes how it plays. The retail rows use 1000, 2000 and 3000, and the byte
holds `10`, `20` and `30`; the script multiplies by 100 when it reads it. **So
write `20` for a 2000 threshold, not `2000`.**

**Byte 2 — remaining-deck threshold**, normally 5, 10 or 20. Once its deck is
down to this many cards the fusion search is clamped to depth 1 whatever byte 3
says: it stops attempting elaborate combos when it is close to decking out.

**Byte 3 — fusion depth for its first strategy, 1 to 3.** The search sets its
limit to this **plus one**, and that makes a sharp, easily missed cliff:

- a **field** card as the seed recurses from operand **1** upward
- a **hand** card as the seed only recurses at **3**

So operand 1 or 2 will combine a field monster with a hand card, but **never
starts a two-card fusion purely from the hand**. Only `3` does. Simon, Teana,
Villager 3, Mage Soldier and Seto 2nd sit at 1 — and byte 2's low-deck clamp
brings everyone there eventually. If you want a duelist that fuses out of hand,
byte 3 must be `3`; nothing else in the row substitutes for it.

**Byte 4 — the second strategy's depth, 1 to 3.** The script passes this
**minus one** to its evaluator, so it is offset from byte 3's meaning. Treat it
with some suspicion: the evaluator begins at depth 0 and can store a
one-addition improvement there, but reports success only when the depth is
nonzero, so not every improvement it finds is acted on. It is not a dependable
equip optimiser.

**Bytes 5 and 6 — read by nothing.** Neither retail script touches them. The
late bosses carry 4 and 5 here, which looks like a deeper search setting and is
not; the research note calls this out as a false lead.

**Byte 7 — duster and hold percentage**, 25, 50 or 75. How willing it is to use
field-clearing cards, and to hold a burn or heal card back for a better moment.

**Byte 8 — blind-attack percentage**, 0, 25, 50 or 75. How often it attacks a
face-down card it cannot identify. Jono and Rex Raptor are 75 and attack
recklessly. Pegasus is **0** — he never guesses, because he can see face-down
cards and has no need to.

#### `sight` — reading face-down cards

```json
"ai": { "copy": "Heishin", "sight": true }
```

Whether its searches may read a face-down card's identity and stats. `true`
sees them, `false` does not.

The disc decides this in the AI script's own bytecode, which tests the opponent
id against six duelists — Heishin, Pegasus, Heishin 2nd, Seto 3rd, DarkNite and
Nitemare — and hands the searches a flag. **Without `sight`, a duelist inherits
the answer for the duelist it `copy`s**, since the script is handed the base's
id. So a copy of Heishin already sees face-down cards; `sight` is only needed
to say otherwise, or to give it to a duelist whose base has none.

It is the one part of how a duelist plays that is not a number in the row, so
the array shorthand cannot express it — use the object form.

A replacement may set it for one of the disc's own:

```json
{ "replace": "Nitemare", "ai": { "sight": false } }
```

### What the row still cannot set

**The strategy distributions** — the 70/15/15 sort of figures in the research
note's tables — are constants in the bytecode, not bytes in this row.

`notes/ai-hard-mode-research.md` §6 has the measured row of every duelist, and
the evidence behind each of these.

**Seeing face-down cards is not one of these.** It is written into the game's
own script for six duelists — Heishin, Pegasus, Heishin 2nd, Seto 3rd, DarkNite
and Nitemare. A duelist that **copies** one of them inherits it; no number here
can switch it on.

---

## `ranks` — how a duel against it is scored

```json
"ranks": {
    "turns":        [[3, 12], [6, 4], [12, 0], [20, -20], [32767, -40]],
    "remaining lp": [[100, -20], [2000, -10], [7000, 0], [8000, 8], [32767, 12]]
}
```

Each rule is up to five `[threshold, change]` pairs. After a duel, what you
managed on that rule walks the pairs until a threshold is above it, and that
pair's change lands on a score starting at 50. The total settles your S to D
letter — **and the letter decides which drop pool you roll**, so this changes
what a duelist is worth farming.

The ten rules, in the game's order:

`turns` · `effective attacks` · `defensive wins` · `face-down plays` ·
`pure magic` · `traps triggered` · `cards used` · `remaining lp` ·
`initiate fusion` · `equip magic`

A rule left out keeps the disc's. Fewer than five pairs is fine — the rest
repeat the last — and the final threshold ends the walk however the value
compares, as the disc's `32767` does.

This is per-duelist data the disc carries but never varies: all forty have a
byte-identical table. Reading the one above, a duel won by turn 3 is +12 but
one dragged past 20 turns is −40, which is far harsher than the disc's −12.

---

See [`../README.md`](../README.md) for the folders as a whole, and
[`../decks/README.md`](../decks/README.md),
[`../drops/README.md`](../drops/README.md),
[`../portraits/README.md`](../portraits/README.md) for the other three.
