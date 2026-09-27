# More duelists than the disc has

What a mod writes is documented separately, in
[duelist-mods.md](duelist-mods.md); this note is the design and the disc
layouts it rests on.

The PC port can have opponents past the disc's thirty-nine. A mod adds them as
a file to a duelist in a `duelists/` folder, or as a `duelists` list in its
`mod.json`, and they work wherever a duelist does.

Each new duelist starts as a **copy** of a retail one, its *base*. Portrait,
deck pool, drop pools and AI come from that duelist; the name can be its own.
The disc has none of these duelists, so wherever the game goes to the disc, or
to a table the disc laid out, it asks for the base instead
(`Duelists_BaseId`) — the same shape [more cards](more-cards.md) uses for cards
past the disc's 722, and for the same reason.

What the base gives is then edited with the tables a mod already has
([gameplay tables](gameplay-tables.md)): `drops` and `decks` name an added
duelist as readily as a retail one, so a new opponent with a deck of its own is
a `duelists` entry and a `decks` entry for it.

## The manifest

Each of `duelists`, `decks` and `drops` may be written out in the manifest, or
be the name of a file of the mod's holding exactly what the key would have
held. A roster of any size therefore lives beside the manifest rather than
inside one nobody can read:

```json
{
    "id": "shadow-duelists",
    "duelists": "tables/duelists.json",
    "decks": "tables/decks.json",
    "drops": "tables/drops.json"
}
```

Written out, the same thing is:

```json
{
    "id": "shadow-duelists",
    "name": "Shadow Duelists",
    "duelists": [
        { "id": "dark-simon", "copy": "Heishin", "name": "Dark Simon" }
    ],
    "decks": {
        "dark-simon": { "replace": true, "Blue-eyes White Dragon": 200 }
    },
    "drops": {
        "dark-simon": { "tec": { "Blue-eyes White Dragon": 40 } }
    }
}
```

| Key | Meaning |
|---|---|
| `copy` | the base: a retail duelist id (1–39) or its name as the table spells it (`"Heishin"`, any case) |
| `name` | the duelist's own name. Without one it has its base's |
| `id` | a stable key, which `"<mod-id>:<id>"` identifies the duelist by. Saves use these identities; without one an entry is identified by its place in the list, which moves when the list is edited |
| *(the face)* | a PNG at `portraits/<id>.png` beside the manifest, found by the entry's `"id"`. Any size: the middle of it is taken at the portrait's shape, reduced to the 64 colours the console's slot holds, and kept whole for the scaled picture. `"portrait"` names a path instead. Without one the duelist wears its base's face |

A duelist is named — in `drops`, `decks` and anywhere else — by its id, its
name, or its `"mod-id:id"` identity.

## What is done

`src/pc/free_duel/duelists.c` holds the list, and the table layer spans it:
`Tables_PoolFor`, `duelist_named` and `"all"` all work over
`Duelists_Count()`, and the per-duelist edit marks grow with it.
`PoolEdit.duelist` is an int, which it has to be once a mod can take the list
past 255.

The win/loss record has a slot: `Duelists_RecordSlot(state, duelist)` gives
the save block's own two halfwords for the first forty and this module's
storage past them, so a reader does not care which it has. The Free Duel
screen reads and writes through it. Storage is
`src/pc/game/free_duel_storage.c`, a game unit like `card_storage.c` and
`drops.c` — so a save state carries it, and it sorts after both so that no
existing variable moves.

Nothing the disc laid out is moved: `gFreeDuel_abGridAvailable` stays in the
overlay's `module_state.c` and the records stay at `0x51C`, pinned by their
static assert. What an added duelist needs sits beside them, as
`Cards_ChestSlot` does for cards past the disc's 722.

Those records outlive a save state too. `duelists/<code>.txt` in the user
directory keeps them by identity, in sections by save sequence, written when
the game writes a save and read when it loads one — beside the memory card's
block, as the added cards' trunk is. A save made while no duelist mod was
applied has no section of its own and reads the newest earlier one. A record
whose duelist is not in this run is dropped rather than guessed at, since its
id would belong to somebody else. Ordinary play never makes the file.

## Pages

The grid holds forty cells whatever the roster is, and shows a page of forty
duelists in them. Page 0 is the disc's own — Deck Build and the thirty-nine
opponents; a page past it shows what a mod added. `cell_duelist(cell)` turns
the cursor's cell into the duelist it stands for, and everything that means a
duelist goes through it: the win/loss record, whether the grid shows the cell,
and the opponent the duel starts with.

Pages rather than a taller grid because only one page's portraits need to be
in video memory at a time. The screen's palette strip holds 48 CLUTs, which
would otherwise cap the whole roster there.

Deck Build is duelist 0, so it is the top left of the first page only; on a
later page that cell is somebody to duel.

A page indicator says which page the grid shows and how to turn it. It is the
game's own text box with the game's own letters, composed in the text codes as
`cards/drops.c` composes the results screen's added pages, and answered for one
reserved id that `Text_Resolve` asks about. So it reads as part of the screen
and scales with the picture rather than being drawn over the top of it. It sits
along the top of the picture, above the FREE DUEL artwork: the button to go
back at the left, "PAGE n/m" centred, the button to go on at the right, and
beside each button the game's own red arrow — the sprite the card viewer puts
at the foot of its page and the hand's card cycling puts either side of a card
(texture `0x20C`, the operand before the colour choosing which way it faces).
A single page says nothing at all.

All three runs are one string in one box on channel 2. Channel 3 is Build
Deck's and the Library's, and a box either left there is what this screen would
find; the screen's own boxes are 0 (the duelist's name) and 1 (the "no deck"
message), which leaves 2.

**The size command decides whether a box is drawn from the font.** `0xF8 0x04`
is the cell size, not the colour — the colour is `0x0A`. Size 1 is the 8x8
sheet the card counts are drawn in and it sets `flags_34`'s `0x100`, after
which `DuelEffect_AppendEntry` stamps every entry `flags_11 = 0xC0` and
`func_80035E20` draws them through `sprites[2]` from that sheet. Those entries
never reach the glyph code, so they never take HD text's mark and the box
cannot be set in a font however the rest of it is configured; the build also
overwrites the channel's `field_5A`/`field_5B` with the sheet's 8x8. Size 2 is
the letters, which is what this line asks for.

## A folder to a kind, a file to a duelist

A roster need not be written out in a manifest at all. Four folders beside it,
one file to a duelist, the file's own name being the duelist's id:

```
mods/my-roster/
├── mod.json               only enables the mod
├── duelists/dark-simon.json
├── decks/dark-simon.json
├── drops/dark-simon.json
└── portraits/dark-simon.png
```

Each file holds exactly what the matching manifest entry holds, without the
id: `duelists/<id>.json` an entry of `"duelists"`, `decks/<id>.json` what
`"decks"` gives one opponent, `drops/<id>.json` what `"drops"` gives one
(the object of pools). A duelist with no deck, drop or portrait file keeps its
base's, which is what having no edit already meant. `all.json` in `decks/` or
`drops/` reaches every duelist, as the name `"all"` does.

**Read in the order the names sort**, never the order the filesystem returns
them. Which slot an entry without one takes depends on the order they are read,
and a roster has to come out the same on every machine.

The same four folders are read from **the player's own directory** as well,
last, so a character dropped in there is placed after the mods' and never moves
one of theirs. It belongs to no mod, so its duelists are identified `user:`.
The win and loss sidecars live in that same `duelists/` folder, named by the
save and ending `.txt`; only `*.json` is a duelist, so the two sit side by side.

Both ways work together and a mod may use either: a manifest's `"duelists"`
list, a file it names, and a folder of files are all read.

## Taking over one of the disc's

`"replace"` names a stock duelist instead of `"copy"`, and then the entry's
name, face, way of playing and unlock go over that duelist rather than making a
new one.

```json
{ "id": "heishin-remade", "replace": "Heishin", "name": "Heishin the Elder",
  "ai": { "copy": "Nitemare" } }
```

Where the disc is read never changes — a replacement is still its own base — so
its deck and drop pools are edited the way any duelist's are, with `"decks"` and
`"drops"` naming it. Two mods replacing the same duelist are settled as two
edits to one pool are: **the last mod to name it has it**, and the earlier is
told so.

## Where a duelist sits

The id *is* the place: `cell_duelist` is `page * 40 + cell`, so page is
`id / 40` and the cell is `id % 40`, down a column of five and across eight.

An added entry may ask for the id it wants with `"slot"`:

```json
{ "id": "dark-simon", "copy": "Simon Muran", "name": "Dark Simon", "slot": 45 }
```

Slots are handed out once every mod has been read, **explicit ones first**, so
an entry that asked for a place is never beaten to it by one that would have
taken anything; the rest then fill the lowest free slots, gaps included. Two
entries asking for the same slot are settled by load order, and the other way
round from a replacement: **the earlier mod keeps it** and the later takes the
next free place. Moving the duelist already there would rearrange a roster its
own mod laid out, while a newcomer has asked for nothing anyone else depends on.

A slot nothing was placed in is no duelist — its cell stays empty, exactly as a
locked one does — so `"slot": 90` makes three pages with most of the third
empty.

## The rank score

Each duelist's disc block is three sectors, 6,144 bytes:

| offset | size | what |
| --- | --- | --- |
| 0 | 1,460 | the deck pool (`gDuel_awOpponentDeckPool`) |
| 1,460 | 1,460 | S/A-POW drops (`gDuel_awSaPowCardDrops[0]`) |
| 2,920 | 1,460 | B/C/D drops |
| 4,380 | 1,460 | S/A-TEC drops |
| 5,840 | 304 | the rank score's rules (`gDuel_awRankScoreChange`) |

The last 304 bytes are ten rules of five threshold/change pairs, 200 bytes
used and the rest `0xFF`. After a duel each measured value walks its rule
until a threshold exceeds it and the change lands on a score that starts at
50; the total settles the S to D letter, and through `rank_tier` and
`is_tec_rank` it picks which drop pool is rolled.

**It is per duelist and the disc never varies it.** Every one of the forty
carries a byte-identical copy — read them off the image and they hash the same
— so this is a hook the game left unused rather than a dimension it plays
with. `"ranks"` in a duelist's own file is what makes one differ:

```json
{
  "replace": "Nitemare",
  "ranks": {
    "turns":        [[3, 12], [6, 4], [12, 0], [20, -20], [32767, -40]],
    "remaining lp": [[100, -20], [2000, -10], [7000, 0], [8000, 8], [32767, 12]]
  }
}
```

It belongs to the duelist and not to the mod, so it sits beside its name, its
slot and its unlock rather than in the manifest. One of the disc's own is
reached by a replacement that changes nothing else, as above.

The rules are `turns`, `effective attacks`, `defensive wins`, `face-down
plays`, `pure magic`, `traps triggered`, `cards used`, `remaining lp`,
`initiate fusion` and `equip magic`, in the game's own order; case and
punctuation do not matter. A rule left out keeps the disc's row. Up to five
pairs: fewer are filled out with the last, and the last threshold always ends
the walk however the value compares, as the disc's 32767 does.

The rows are read with the duelist and handed to the tables once it has an id
(`Tables_SetRank`), since a duelist's place is not settled until every mod has
been read.

What the disc gives every duelist, for comparison:

| rule | the disc's row |
| --- | --- |
| turns | `<5:+12 <9:+8 <29:0 <33:-8 else -12` |
| effective attacks | `<2:+4 <4:+2 <10:0 <20:-2 else -4` |
| defensive wins | `<2:0 <6:-10 <10:-20 <15:-30 else -40` |
| face-down plays | `<1:0 <11:-2 <21:-4 <31:-6 else -8` |
| pure magic | `<1:+2 <4:-4 <7:-8 <10:-12 else -16` |
| traps triggered | `<1:+2 <3:-8 <5:-16 <7:-24 else -32` |
| cards used | `<9:+15 <13:+12 <33:0 <37:-5 else -7` |
| remaining lp | `<100:-7 <1000:-5 <7000:0 <8000:+4 else +6` |
| initiate fusion | `<1:+4 <5:0 <10:-4 <15:-8 else -12` |
| equip magic | `<1:+4 <5:0 <10:-4 <15:-8 else -12` |

## When an added duelist appears

The disc's thirty-nine are unlocked by campaign story flags, which an added
duelist has none of, so it was shown from the start. A mod may give one an
`"unlock"` instead: an object of conditions the running save must meet, **all**
of them.

```json
{
  "id": "blue-heishin",
  "copy": "Heishin",
  "name": "Blue Heishin",
  "unlock": { "beat": "Dark Simon", "wins": 2 }
}
```

| member | what it asks |
| --- | --- |
| `beat` | a duelist to have beaten — an id, a name, or an identity |
| `wins` | how many wins: against `beat` if there is one (1 by default), else in all against everybody |
| `story` | a campaign story flag, the same ones the disc's own unlocks use |
| `card` | a card the trunk or deck must hold — an id, a name, or an identity |
| `copies` | how many of `card` (1 by default) |

Nothing is stored. Every condition is read from the save's own records, trunk
and flags each time the grid opens, so an unlock follows the save that is
loaded, needs no sidecar of its own and nothing to migrate — and a win in the
duel you just left opens up whatever it was the condition for, because the
screen is built again on the way back.

`beat` and `card` are kept as the manifest wrote them and looked up when they
are tested: the card list is not built when a manifest is read, and either may
name something a mod that loads later adds. A name that resolves to nothing
leaves the condition **unmet**, so a roster never opens up by accident.

A stock duelist a mod replaced may carry conditions too, and they stand **in
place of** its campaign flag rather than beside it, which is how a mod can open
one up early or hold one back.

A locked duelist is an empty cell, exactly as a locked retail one is. Pages are
counted from how many duelists there are and not from how many are unlocked, so
a duelist keeps its place on the grid as the conditions around it are met.

**L1 and R1 turn the page.** The screen reads only the pad's directions,
Cancel and Confirm, so the shoulder buttons were free, and they already mean
"by a page" on the Library's grid.

`FreeDuel_ShowPage` does the turning, and it allocates nothing. A cell's
texture slot and palette are fixed by the cell, so the forty sprites
`FreeDuel_Init` builds stand for whatever is put in those slots: a page
changes only the texels in them, and a cell the page does not fill has
`DISPLAY_OBJECT_FLAG_RENDERABLE` cleared rather than being released. That is
what makes a page cost nothing in video memory over the grid the disc already
had. Init builds all forty now, shown or not, since a cell with no sprite
could not be made to appear later.

The name and the win/loss box are only rebuilt when the cursor arrives
somewhere, so a page turn asks `FreeDuel_PlaceCursor` for that itself.

So an added duelist can be named by `drops` and `decks` today, is a real entry
with a base, a name and an identity, keeps a record across saves, and has a
place on the grid that L1 and R1 reach.

## Its own face and name

A duelist's face is a PNG at **`portraits/<id>.png`** beside the manifest,
named for the entry's own `"id"` — no key to write. (`"portrait"` still names
a path for anything that does not suit.) It becomes a whole portrait record
through `CardArt_PortraitFromImage`, beside the card art converters and using
the same resampling and palette reduction, which `FreeDuel_ShowPage` uploads
in the base's place.

**One file, both pictures.** The same PNG is reduced to the 48x48 of 64
colours the console's slot holds *and* kept whole for the scaled picture,
which draws it at its own size. So a portrait is as sharp as the file is.

That second half needed a way for the texture pack to key an image the disc
never carried. The pack matches on one value — `TextureDump_Tags[word]`, the
disc byte offset the bytes in that VRAM word came from — and a record built in
memory has none, which is exactly what stopped an added duelist wearing the
pack's picture of whoever it copies.

So there is now a space above every disc offset, `TEXTURE_MOD_OFFSET_BASE`,
that the port keys its own images in:

- `TextureDump_ModImage(bytes, n, offset)` tags an upload in that space. It is
  `TextureDump_Delivered` with a made-up place instead of a sector, and reuses
  the delivery machinery whole — the copy it keeps, and the comparison that
  drops the tag when the words are written over since.
- `TexturePack_AddImage(file, offset, words, rows, bpp, clut_offset, entries)`
  registers the picture at the same place. These entries are the port's and
  not a pack directory's, so they outlive a pack being loaded or unloaded and
  a mod carrying one picture needs no pack at all.
- A duelist's place is its id's: a stride of 4,096, the picture at the start
  and its palette at + 2,304, which is where `prepare` looks for it — the
  palette is matched by the tag on the CLUT's own first word.

Nothing downstream of the tag knows the difference: `locate`, the sibling
runs, the maps and the scaled sampling are offset arithmetic and unchanged.

A duelist with no picture of its own uploads its base's record and gets the
pack's picture of the base, which is what it should get.

The name is the shape `Cards_Text` has: `Duelists_Text(id, text)` answers for
the string the Free Duel screen names a duelist by — `D_8009B32E` holds
`index - 31960`, so duelist 1 is text `0x8329` — and is hung off the same two
calls in `text_lookup_string.c` and `text_box_build_step.c`. The name is stored
in the game's own glyph codes, made the way cards.c makes a card's, so a letter
the game does not have is reported rather than drawn as rubbish.

## Reading face-down cards

The disc settles this in the AI script's own bytecode, which tests the opponent
id against six duelists — Heishin (8), Pegasus (15), Heishin 2nd (35), Seto 3rd
(36), DarkNite (37) and Nitemare (38) — and hands the searches a register
saying whether to pass a face-down card over. Since `AiScript_LoadOpponentID`
gives the script the **base's** id, a duelist a mod added already inherits the
answer for the duelist it copies.

`"sight"` in a duelist's `"ai"` says so outright. It is not a byte in the row —
the row is nine numbers and this is not one of them — so only the object form
of `"ai"` can carry it.

Four searches read that register, and the override goes at each of them rather
than at the id, because the id is what the bytecode compares and only the
bytecode knows which register it put the answer in:

| | |
| --- | --- |
| `AiScript_FindDefenseStopper` | `ai_script_find_card.c` |
| `AiScript_FindBestAttack` | `ai_script_find_best_attack.c` |
| two combo searches | `ai_script_combo.c` |

All four use the same sense — 0 reads face-down cards, non-zero passes them
over — and `Duelists_HidesFaceDown` returns what the script asked for when the
duelist says nothing, so an unmodified roster behaves exactly as before.

Substituting a different id in `AiScript_LoadOpponentID` would have been
smaller, and was rejected: the register the bytecode derives is not the only
thing it does with that id, and without a disassembler there is no way to know
what else would move.

## The mod API

`duelist_id` sits beside `card_id` in the host (`modapi.h`, API 5):

```c
int id = host->duelist_id(host, "my-roster:dark-simon");
```

An added duelist's id depends on which mods are applied, in what order, and
what slots they asked for, so a code mod cannot write it down in advance. It
resolves an identity to the id this run, and answers 0 for a duelist that is
not here -- and for one of the disc's own, whose id already names it.

`Duelists_Find` is the resolver, handed to the mod layer at the end of
`Duelists_Build` the way `cards.c` hands over `Cards_FindIdentity`, so
`mods.c` needs to know nothing about duelists. It answers -1 for a duelist it
does not have and the host reports that as 0, which is what `card_id` promises
for a card.

Raising the API to 5 costs applied mods nothing: the check refuses a mod built
for an API *newer* than the host's, so everything declaring 4 still loads.

## What is not

* nothing outstanding that this note names.

## Verification

`duelists.c`, `free_duel_storage.c`, `tables.c` and `cards.c` compile clean
under `-Wall -Wextra`, and `screen_runtime.c` under the build's own flags. The
retail path is untouched: its preprocessor sees no reference to any of this.

`tests/pc/duelists_test.c` (`ctest -R pc_duelists`) covers what is settled
without a screen: slots and their collisions, replacement precedence, the AI
row's layering, face-down sight, every unlock condition, the rank rules, the
folder reader and the mod API's resolver. It runs real manifests through the
real JSON reader, and is checked by mutation -- better than twenty deliberate
breaks, each of which fails it.
