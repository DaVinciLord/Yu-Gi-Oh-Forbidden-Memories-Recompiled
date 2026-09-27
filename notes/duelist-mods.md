# Duelists a mod adds

The whole format of a roster: what each folder holds, what each file may
say, and how the parts settle against each other. The design behind it,
and the disc layouts it rests on, are in [more-duelists.md](more-duelists.md).

This is the same text as the READMEs in `mods/my-roster`, gathered into one
page. Change both, or neither.

A roster is a folder you drop characters into. There is no list to edit and no
code to compile: the manifest only switches the mod on, and everything else is
a file named after the duelist it belongs to.

```
my-roster/
├── mod.json                     switches the mod on; nothing about duelists
├── duelists/dark-simon.json     who it is
├── decks/dark-simon.json        what it plays
├── drops/dark-simon.json        what you win from it
└── portraits/dark-simon.png     its face
```

**The filename is the id.** `duelists/dark-simon.json` makes a duelist whose id
is `dark-simon`, and the other three folders reach it by the same name. Nothing
inside the files repeats it.

**Anything missing falls back.** A duelist with no `decks/` file plays the deck
of the duelist it copies; with no `drops/` file it gives that duelist's cards;
with no portrait it wears that duelist's face. Only `duelists/<id>.json` is
required.

The same four folders are read from your own user directory as well, so a
character can be added without touching any mod. See [Your own
folder](#your-own-folder) at the end.

---

## Adding a duelist

One file:

**`duelists/dark-simon.json`**

```json
{
    "copy": "Simon Muran",
    "name": "Dark Simon"
}
```

That is a complete duelist. It appears on the Free Duel grid at the first free
place, playing Simon Muran's deck with his drops, face and way of playing, but
under its own name.

`copy` is the only required property. It names one of the disc's 39 opponents
(1 to 39) — by name, or by id. The copied duelist is called the **base**, and
it is where everything comes from that this duelist does not say for itself.

### Its own deck

**`decks/dark-simon.json`**

```json
{
    "replace": true,
    "Blue-eyes White Dragon": 200,
    "Mystical Elf": 100,
    "Baby Dragon": 100
}
```

Weights, not a card list: the game draws 40 cards from the pool, so a card with
twice the weight turns up about twice as often. See [Weights and
`replace`](#weights-and-replace) below — a deck pool needs at least **14**
cards or the edit is refused and the base's deck stands.

### Its own drops

**`drops/dark-simon.json`**

```json
{
    "pow": { "replace": true, "Blue-eyes White Dragon": 1, "Dark Magician": 1 },
    "bcd": { "Kuriboh": 3 },
    "tec": { "replace": true, "Raigeki": 1 }
}
```

Three pools, and which one you draw from depends on the rank you finish with:

| pool | also spelled | when you get it |
| --- | --- | --- |
| `pow` | `sa-pow` | an S or A rank won on power |
| `bcd` | `b-c-d` | a B, C or D rank, either way |
| `tec` | `sa-tec` | an S or A rank won on technique |

You may give one pool, two or all three. A pool you leave out stays the base's.

### Its own face

**`portraits/dark-simon.png`** — any size, any proportions. The middle of it is
taken at the portrait's shape and reduced to the 48×48 of 64 colours the
console's slot holds, **and** the file itself is kept whole for the scaled
picture. So one file gives both: the portrait is as sharp as your image is at
View → Internal 2x and above, and correct at 1x.

---

## Replacing one of the disc's duelists

Use `replace` instead of `copy`, and the entry takes over that duelist rather
than making a new one:

**`duelists/heishin-remade.json`**

```json
{
    "replace": "Heishin",
    "name": "Heishin the Elder",
    "ai": { "copy": "Nitemare" }
}
```

Heishin keeps his place on the grid, his win and loss record and his campaign
appearances, but the grid and the duel now call him Heishin the Elder and he
plays like Nitemare.

- `decks/heishin-remade.json` and `drops/heishin-remade.json` change what he
  plays and gives — **named for your file's id, not for him.**
- `portraits/heishin-remade.png` gives him a new face.
- `slot` is meaningless on a replacement: he has his duelist's place already.
- An `unlock` on a replacement stands **in place of** his campaign flag, not
  beside it. That is how you make a duelist available from the start, or hold
  one back until something else has happened.
- The old name still works everywhere it is used to name him: another mod's
  `decks/Heishin.json` keeps finding him.

**Two mods replacing the same duelist:** the one that loads later has him. Two
mods asking for the same `slot` go the other way — the earlier keeps it and the
later takes the next free place, because moving a duelist that is already
placed would rearrange a roster its own mod laid out.

---

---

## The `duelists/` folder


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

### How the folder is read

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

### `copy` — building on one of the disc's

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

### `replace` — taking over one of the disc's

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

### `name`

What the Free Duel grid and the duel call it. Without one it uses its base's.

Only letters the game has can be shown; anything it cannot draw is left out and
noted in the Mods window.

### `slot` — where it sits on the grid

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

### `portrait`

A path to its picture, for when the file is not `portraits/<id>.png`:

```json
{ "copy": "Heishin", "portrait": "art/faces/mine.png" }
```

Relative to the mod, and it cannot reach outside it. You rarely want this — see
[the `portraits/` folder](#the-portraits-folder).

---

### `unlock` — when it appears

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

### `ai` — how it plays

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

#### The nine bytes

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

##### `sight` — reading face-down cards

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

#### What the row still cannot set

**The strategy distributions** — the 70/15/15 sort of figures in the research
note's tables — are constants in the bytecode, not bytes in this row.

`notes/ai-hard-mode-research.md` §6 has the measured row of every duelist, and
the evidence behind each of these.

**Seeing face-down cards is not one of these.** It is written into the game's
own script for six duelists — Heishin, Pegasus, Heishin 2nd, Seto 3rd, DarkNite
and Nitemare. A duelist that **copies** one of them inherits it; no number here
can switch it on.

---

### `ranks` — how a duel against it is scored

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

## The `decks/` folder


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

### It is a pool, not a deck list

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

### `replace`

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

### What is refused

Two mistakes leave the base's deck untouched and put a line in the Mods window:

**Fewer than 14 cards with weight.** A deck is 40 cards and at most 3 of each,
so 14 is the fewest a pool can fill one from. `{"replace": true, "Blue-eyes
White Dragon": 1}` cannot make a deck and is refused outright — this is the
single most common surprise.

**A pool that comes out empty**, for instance when every name in it is
misspelt.

Refusal is per pool, not per file. Everything else in the mod still loads.

---

### Card names

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

### Naming the file

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

### Sorting and order

Files are read in the order their names sort, and each mod's folder in mod load
order, with the user directory's read **last**. Two edits to one duelist's deck
both apply, in that order, so the later one sits on top.

---

## The `drops/` folder


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

### The three pools, and which one you get

Every duelist carries three separate pools. Which you draw from is decided by
the **rank** you finish the duel with — not by the duelist, and not by chance:

| pool | also spelled | you draw from it when |
| --- | --- | --- |
| `pow` | `sa-pow` | you finish **S or A**, and the rank was earned on power |
| `bcd` | `b-c-d` | you finish **B, C or D** — power or technique, it makes no difference |
| `tec` | `sa-tec` | you finish **S or A**, and the rank was earned on technique |

A duel is scored into a single number that starts at 50 (see `ranks` in
[the `duelists/` folder](#the-duelists-folder)). Below 50 the rank counts as
technique and the number is mirrored; the result picks a tier from D up to S.
Tiers below A always take `bcd`, so **the two good pools are only reachable
with an A or an S**.

That is why `ranks` and `drops` are worth thinking about together: making a
duelist easier to earn an S from makes its `pow` or `tec` pool reachable, and
making it harder locks players into `bcd`.

You may give one pool, two or all three.

---

### Weights

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

### Card names

The game's own, from `notes/card-catalog.csv`. Case and punctuation ignored,
but the name must be the one Forbidden Memories uses — `Winged Dragon #1`, not
"Winged Dragon, Guardian of the Fortress #1"; `Trial of Nightmares`, plural. An
id works too. A name matching nothing is reported and left out.

---

### Naming the file

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

### Sorting and order

Files are read in the order their names sort, each mod's folder in mod load
order, and the user directory's **last**. Two edits to one pool both apply in
that order, the later on top — so `all.json` followed by a named file lets you
set a baseline and then override one duelist.

---

## The `portraits/` folder


One image to a duelist, named for its id: `portraits/dark-simon.png` gives a
face to the duelist that `duelists/dark-simon.json` made.

**A duelist with no image here wears the face of the duelist it copies.**

PNG only, and **any size or shape you like**. There is nothing to configure.

---

### One file, two pictures

The Free Duel grid's slot is tiny: 48×48 pixels, 8 bits a pixel, through a
64-entry palette. That is what the console had and what the game still uploads.

Your PNG becomes both of these:

1. **The console's portrait.** Centre-cropped to a square, box-averaged down to
   48×48, and reduced to a palette of 64 colours. This is what the game draws at
   View → Internal 1x, and it is what the grid's cell genuinely contains.
2. **The picture itself, kept whole.** At Internal 2x and above, the renderer
   draws your file at its own resolution instead of the 48×48 cell.

So a portrait is as sharp as the file you give it, with no second image and no
"hd" folder. Give it one good picture.

#### What to give it

- **Square** is easiest, since a non-square image is cropped to its centre
  square first — the sides of a wide picture are simply thrown away. Crop it
  yourself if the framing matters.
- **Large is fine.** 512×512 or more is drawn at its own size when the internal
  resolution is high enough.
- Transparency is not kept: the portrait slot has no alpha.
- Strong, flat colour survives the 64-colour reduction better than a soft
  gradient, which can band at 1x. The full-size picture is unaffected.

---

### How the sharp one reaches the screen

Worth knowing, because it explains a limitation elsewhere.

The texture pack matches images by **where their pixels came from on the
disc**: every VRAM word carries a tag saying which disc byte it was read from,
and a pack image is keyed to that. A picture built in memory has no such tag,
which is exactly why an added duelist does *not* wear a texture pack's HD
picture of whoever it copies — there is nothing to match.

A mod's portrait is given a tag of its own, in a range above every real disc
offset, and registered with the pack at that same place. The image and its
palette are tagged separately, because the pack matches a palette by the tag on
the palette's own first word. From there nothing else knows the difference: the
same machinery that draws an HD picture of a disc texture draws yours.

You do not need a `textures` pack in your mod for this. One picture needs no
pack at all.

---

### Naming the file

The duelist's id, which is the name of its `duelists/` file:

| `duelists/` file | portrait |
| --- | --- |
| `dark-simon.json` | `dark-simon.png` |
| `Yugi.json` | `Yugi.png` — capitals must match |
| `heishin-remade.json` (a replacement) | `heishin-remade.png` |

A replacement is named after **your** file's id, not after the duelist it takes
over: `duelists/heishin-remade.json` replacing Heishin wants
`portraits/heishin-remade.png`.

If a file cannot be named this way, point at it from the duelist instead:

```json
{ "copy": "Heishin", "portrait": "art/faces/mine.png" }
```

The path is relative to the mod and cannot reach outside it.

Unlike the other three folders, nothing here is scanned — a portrait is looked
for by name when its duelist is read. An unused image costs nothing, and this
README is ignored.

---

### Replacing a disc duelist's face

Give the replacement entry a portrait like any other:

```
duelists/heishin-remade.json    { "replace": "Heishin", ... }
portraits/heishin-remade.png
```

The disc's own duelists keep their faces unless a mod replaces them, and a
texture pack's HD portraits still apply to those, since theirs *do* come from
the disc.

---

## `mod.json`

Only what makes it a mod:

```json
{
    "id": "my-roster",
    "name": "My Roster",
    "enabled": true,
    "min_api": 4,
    "game": "slus_01411"
}
```

`enabled` is only the default — the Mods window switches it either way.


---

## Your own folder

The same four folders are read from your user directory, so you can add a
character without touching a mod:

| system | where |
| --- | --- |
| Linux | `~/.local/share/YFM Re-Decomp/` (or `$XDG_DATA_HOME/YFM Re-Decomp/`) |
| Windows | `Documents\My Games\YFM Re-Decomp\` |

`MEMORIES_USER_DIR` overrides it if you would rather keep it somewhere else.

Put `duelists/`, `decks/`, `drops/` and `portraits/` there and they work
exactly as a mod's do. They are read **last**, so a character you add is placed
after every mod's and never moves one of theirs.

Your win and loss records live in that same `duelists/` folder, named by the
save and ending `.txt`. Only `*.json` is read as a duelist, so the two sit side
by side without trouble.

---

## When something is wrong

The Mods window lists what could not be read: a card name that names nothing, a
duelist a condition points at that is not here, a slot already taken, a file
that is not valid JSON. Nothing is guessed at — an entry that cannot be
understood is left out and the rest still load.

Files are read **in the order their names sort**, not the order the folder
happens to list them, so a roster places itself the same way on every machine.
