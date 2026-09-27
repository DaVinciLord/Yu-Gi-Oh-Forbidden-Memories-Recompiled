# FM Editor

A standalone editor for mods of the PC port: cards, fusions, equips, rituals
and the opponents' deck and drop pools. It is a program of its own, not part
of the game, and needs nothing but Python 3 (Tkinter comes with it).

**The mod is the diff.** The editor reads the retail tables from your own
game files, lets you change them, and on save writes a mod folder whose
`mod.json` holds only what differs from retail, in the schema the port
reads ([modding](../../../notes/modding.md), [more cards](../../../notes/more-cards.md),
[gameplay tables](../../../notes/gameplay-tables.md)). Opening a mod folder
lays its `mod.json` over retail, so a saved mod can be opened and edited
again. It writes mod folders only: never the disc, never `game/`.

## Running it

    python tools/pc/fm_editor [--game <folder or .bin>] [--mod <mod folder>]

The window has a tab per table:

| Tab | What you edit |
|---|---|
| Cards | search and filter the 722 cards; name, card text (with the game's 20-letter, 8-line wrapping counted), ATK/DEF, type, attribute, level, guardian stars; the retail value beside each field. **Add a card** copies the selected one as a new card with a stable id |
| Fusions | every pair and its result (search by a card, or show the changed ones); add, change, remove (the pair no longer fuses) or revert |
| Equips | per equip card, the monsters it may equip; add one, add or remove a whole type, remove, revert |
| Rituals | per ritual card, its three tributes and the monster it summons |
| Duelists | per opponent, the deck pool and the S/A-POW, B/C/D and S/A-TEC drop pools: weights, their chance, the retail weight, and the total against 2048 (**Normalize** scales a pool back to 2048 the way the port does) |
| Mod info | id, name, version, author, description, `settings`, and the other `mod.json` keys, kept as written |
| Problems | the loader's checks; double-click a line to go to it |

**File > Save** writes the mod folder (Ctrl+S); the first save asks where
(an empty folder, or a parent where a folder named after the mod id is
made; the port's player mods are in `Documents\My Games\YFM Re-Decomp\mods`).
Enable the mod in the game under **Game > Mods** and restart. **File > Open
mod folder** opens a mod over retail. Save refuses nothing, but lists what
the loader would refuse first.

## Game files

The editor looks for the game where the port does: `MEMORIES_DISC`, the disc
the port was last pointed at (`disc-path.txt` in the user directory),
`game/` beside the program, the program's folder, `game/` in the user
directory, and `./game`. It takes a raw `.bin` image (the one the port runs
from), an ISO, or a folder holding `SLUS_014.11` and `DATA/WA_MRG.MRG`.

What it reads (layouts in `gamedata.py`):

| Table | Where |
|---|---|
| card stats, level and attribute | `SLUS_014.11`, `0x801D4244` and `0x801D5332` |
| card names and texts | the executable's text banks, through `tools/pc/text_listing.py` |
| equips, fusions, rituals | `WA_MRG.MRG`, the duel package at `0xB63000` (+0x22000, +0x24800, +0x34800) |
| deck and drop pools | `WA_MRG.MRG` `0xE99800 + 0x1800 * opponent` |

The 15 "glitch" fusions the game's table reader makes by reading past an odd
record are shown as retail fusions and marked.

## What it writes

* `cards`: a `replace` entry per changed retail card with only the changed
  keys, and a `copy` entry per added card with a stable `id`. Keys the editor
  does not show (`art`, `title`, `model`, `count`...) are kept as written.
* `fusions`: one rule per pair whose result changed (`"result": null` for a
  fusion taken away).
* `equips`: per equip card, `add` and `remove` (a whole monster type as its
  name), or `replace` when that is shorter.
* `rituals`: a changed recipe, or `"result": null`.
* `drops` and `decks`: per opponent and pool, the fewest listed weights that
  make the port's arithmetic (`tables.c`, mirrored in `pools.py`) come out
  at exactly the edited pool; an edit every opponent shares is written once
  as `"all"`.
* Every other key of an opened mod (`data`, `text`, `textures`, `audio`,
  `requires`...) is kept as written, and the folder's other files are
  copied when the mod is saved somewhere new.

Cards are named by their retail name when that finds the card again in the
port (`retail_by_name`), by number otherwise, and added cards by their
stable identity `<mod id>:<id>:1`.

## Checks

Before saving, the editor runs the loader's checks (`validate.py`): the mod
id, settings, ATK/DEF in tens up to 5110, levels, a copy staying on its
base's side, equip and ritual cards of the right type, a deck pool of at
least 14 cards, a drop pool with a card left, and pools adding up to 2048.

## Command line

    python tools/pc/fm_editor check <mod folder> [--game <folder or .bin>] [--print]

opens a mod over retail, lists what the loader would complain about, and
with `--print` shows the `mod.json` the editor would write for it.

## Tests

    python -m unittest discover -s tools/pc/fm_editor/tests -t tools/pc

(ctest `pc_fm_editor`). The tests build synthetic game files at the retail
offsets (`tests/fixtures.py`); they need no game data.
