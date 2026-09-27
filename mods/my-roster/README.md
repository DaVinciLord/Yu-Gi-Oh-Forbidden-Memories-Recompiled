# Adding and replacing duelists

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

## `duelists/<id>.json` in full

| property | what it does |
| --- | --- |
| `copy` | **required** (unless `replace`). The disc duelist this one is built from, 1 to 39, by name or id |
| `replace` | a disc duelist to take over instead of adding one. Not with `copy` |
| `name` | what the grid and the duel call it. Without one it uses its base's |
| `slot` | the id it wants, 40 to 255, which is its place: page `slot / 40`, cell `slot % 40`. Without one it takes the lowest free place |
| `portrait` | a path to its picture, if the file is not `portraits/<id>.png` |
| `unlock` | conditions the save must meet before the grid shows it — see below |
| `ai` | how it plays — see below |
| `ranks` | how a duel against it is scored — see below |

`id` inside the file is ignored: the filename is the id.

### `unlock`

Every condition given must hold. Without `unlock`, the duelist is shown from
the start.

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
| `wins` | how many wins: against `beat` when there is one (**1** by default), otherwise against everybody put together |
| `story` | a campaign story flag. `0x6E0 + n` is "duelist *n* is unlocked in Free Duel", so `1762` is Teana's |
| `card` | a card the trunk or deck must hold — by id or name |
| `copies` | how many of `card` (**1** by default) |

Nothing is stored. The conditions are read from the save's own records, trunk
and flags every time the screen opens, so an unlock follows whichever save is
loaded and a win in the duel you just left opens up what it was the condition
for.

A condition that names something not present — a duelist from a mod that is
switched off, or a misspelt card — leaves the duelist **locked**. A roster
never opens up by accident.

### `ai`

Nine numbers decide how an opponent plays. Give them as a list, or as an object
that borrows another duelist's and writes over part of it.

```json
"ai": { "copy": "Nitemare", "search": 20, "values": [20, 20, 10, 3, 2] }
```

| property | what it does |
| --- | --- |
| `copy` | take the whole row from this duelist. It may be one another mod adds |
| `search` | byte 0 on its own |
| `values` | a list, from byte 0. Shorter than nine is fine — the rest come from `copy`, or from the base |
| `sight` | whether it reads face-down cards, `true` or `false`. Not a byte in the row, so the array shorthand cannot say it |

`values` is read after `search`, so both writing byte 0 means `values` wins.

The bytes, in order: **0** how deep into its deck it may look (5 for the early
villagers, 20 for the late bosses) · **1** a life-point threshold, **stored
÷100**, so `20` means 2000 · **2** a remaining-deck threshold, below which the
fusion search is clamped · **3** fusion depth, where only **3** starts a fusion
from two cards in hand · **4** a second strategy's depth · **5–6** read by
nothing · **7** how willing it is to clear the field and hold cards back ·
**8** how often it attacks a face-down card.

[`duelists/README.md`](duelists/README.md) explains each of them, including the
two that are easy to get wrong: byte 1 is a hundredth of the life points, and
byte 3 below 3 never fuses out of hand.

Seeing face-down cards is not a byte but a flag of its own, `"sight": true` or
`false` in the `ai` object. The disc gives it to six duelists (Heishin,
Pegasus, Heishin 2nd, Seto 3rd, DarkNite and Nitemare), and a duelist that
**copies** one of them inherits it, so `sight` is only needed to say otherwise
— or to give it to a duelist whose base has none.

### `ranks`

How a duel against this duelist is scored. Each rule is up to five
`[threshold, change]` pairs: the first threshold above what you managed gives
the change, and the changes move a score that starts at 50 and settles the S to
D letter — which decides **which drop pool you roll**.

```json
"ranks": {
    "turns":        [[3, 12], [6, 4], [12, 0], [20, -20], [32767, -40]],
    "remaining lp": [[100, -20], [2000, -10], [7000, 0], [8000, 8], [32767, 12]]
}
```

The rules are `turns`, `effective attacks`, `defensive wins`, `face-down
plays`, `pure magic`, `traps triggered`, `cards used`, `remaining lp`,
`initiate fusion` and `equip magic`. A rule you leave out keeps the disc's.
Fewer than five pairs is fine — the rest are the last one — and the last
threshold ends the walk however the value compares, as the disc's `32767` does.

This is data every duelist's block carries and the disc never varies: all forty
have the same table. It is how you make one duelist harder to earn an S from,
or easier to farm the S/A pool off.

**To change one of the disc's duelists** without otherwise touching it, make a
replacement that changes nothing else:

```json
{ "replace": "Nitemare",
  "ranks": { "turns": [[3, 12], [6, 4], [12, 0], [20, -20], [32767, -40]] } }
```

---

## Weights and `replace`

A pool is cards and weights, and the weights are shares of 2048 rather than
exact numbers. `{"A": 1, "B": 3}` means B four times as often as A, and so does
`{"A": 250, "B": 750}`.

**With `"replace": true`** the base's pool is thrown away and only your cards
are in it.

**Without it** your cards take the weights you give and everything the base had
shares what is left over. `{"Blue-eyes White Dragon": 400}` means Blue-Eyes
about a fifth of the time and the base's usual pool for the rest.

Two things are refused, leaving the base's pool untouched and a note in the
Mods window:

- a deck pool with fewer than **14** cards — a deck is 40 cards and at most
  three of each, so fewer cannot fill one
- a pool that comes out empty

Card names are the game's own and are in `notes/card-catalog.csv`. Case and
punctuation do not matter, so `blue-eyes white dragon` is fine — but the name
must be the one Forbidden Memories uses, which is not always the one the card
has today. `Winged Dragon #1`, not "Winged Dragon, Guardian of the Fortress
#1". An id works too.

**`all.json`** in `decks/` or `drops/` reaches every duelist at once.

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
