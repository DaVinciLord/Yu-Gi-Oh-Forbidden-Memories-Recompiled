# FM Editor

A standalone editor for mods of the PC port: cards, fusions, equips, rituals
and the opponents' deck and drop pools. It is a program of its own, not part
of the game, and needs nothing but Python 3 and Tkinter (part of Python on
Windows and macOS; on Linux maybe a package of its own: `python3-tk`, or `tk`
on Arch).

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
  does not show (`art`, `title`, `model`, `count`, `password`...) are kept
  as written. A copy with no `name` shows its base's name from the disc.
* `fusions`: one rule per pair whose result changed (`"result": null` for a
  fusion taken away). An added card fuses as its base until a rule names it,
  so taking away its pair's fusion writes a `null` rule for it.
* `equips`: per equip card, `add` and `remove` (a whole monster type as its
  name), or `replace` when that is shorter. An added card is equipped (and
  equips) as its base, so what differs for it is written in later entries,
  which the game's reading of the rules confirms before saving. `bonus` and
  `bonus_if` are kept as written.
* `rituals`: a changed recipe, or `"result": null`.
* `drops` and `decks`: per opponent and pool, the fewest listed weights that
  make the port's arithmetic (`tables.c`, mirrored in `pools.py`) come out
  at exactly the edited pool; an edit every opponent shares is written once
  as `"all"`. A fixed deck (`"fixed": true`) is kept as written; the
  Duelists tab shows the weighted deck under it.
* Every other key of an opened mod (`data`, `text`, `textures`, `audio`,
  `requires`...) is kept as written, and the folder's other files are
  copied when the mod is saved somewhere new.

Cards are named by their retail name when that finds the card again in the
port (`retail_by_name`), by number otherwise, and added cards by their
stable identity `<mod id>:<id>:1`.

## Importing a modified game

The PS1 scene's mods (Mod 13, FM 2023, rebalances...) ship patched copies of
the game's files. **File > Import a modified game** (or the `import`
command) compares a modified `.bin`, or its `SLUS_014.11` and `WA_MRG.MRG`,
with your retail files and makes a port mod of the difference, which then
opens and saves like any other:

| Changed in the modified game | Becomes |
|---|---|
| card stats, names, texts; fusions, equips, rituals; deck and drop pools | `cards`, `fusions`, `equips`, `rituals`, `decks`, `drops`. A name or text that differs only by spaces at line ends stays retail's. Drop pools a mod stores encoded (the TeaOnline drop tool writes `bias + 8 * weight + noise` and makes the draw at `0x80021860` jump to code that undoes it) are decoded as `max(0, (raw - bias) >> shift)`, with the bias and shift read from that code's `addiu` and `sra`, or, when the code is not recognized, the values that make every such pool add up to 2048. Any other pool that does not add up to 2048 is scaled to 2048 keeping each card's share. The report says which |
| other text: dialogue, menus, types, stars, duelists, places | `text.txt`, a partial [text listing](../../../notes/translation.md) (a bank whose changed strings jump is written whole) |
| other bytes of `WA_MRG.MRG` (pictures, passwords and costs, starter decks, portraits...) | `data` patches; a run longer than 4 KB becomes whole sectors in `data/`, replaced by LBA |
| code and tables of the executable (AI parameters, field bonuses, equip bonuses, the draw...) | nothing: the port runs the executable's code natively. Listed in the report by RAM address, with the `j`/`jal` instructions that reach each place; changed bytes of the text banks that the text listing does not read (a mod's code or tables in the banks' free space, text left over) are listed too |

The report is shown and saved with the mod as `import-report.txt`.

    python tools/pc/fm_editor import <modified .bin, folder or SLUS_014.11> -o <mod folder>
        [--wa <modified WA_MRG.MRG>] [--game <retail>] [--id <mod id>]

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
