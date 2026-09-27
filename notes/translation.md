# Translations

A mod can put the game in another language: every line of dialogue, every
menu string, every card's name and text, the monster types, the guardian
stars and the duelists' names. Accented letters work (é, ñ, ç, ü, ø, ß,
¿, ¡ and the rest of the Latin alphabets), and a mod can bring a font for
anything else. A renamed card's name plate, the name drawn into the top of
its art, is set anew from the new name at every scale (below). Other text
drawn as pictures (the main menu's words, the results screen's headings) is
not text to the game; a [texture pack](modding.md) repaints those.

## Making one

1. Write the game's text out of your own disc:

   ```sh
   python3 tools/pc/text_listing.py extract -o text.txt
   ```

   It finds the disc image in `game/` (or name it with `--exe`). The
   listing is plain UTF-8, about 10,000 lines.

2. Translate it in any text editor, keeping every `{...}` code and every
   `[ID]` and `{:L...}` line (see below).

3. Make a mod of it:

   ```json
   {
       "id": "spanish",
       "name": "Español",
       "description": "The whole game in Spanish.",
       "text": "text.txt"
   }
   ```

   `text` may be a list of files; they are read in order, and a later
   string with the same id replaces an earlier one. A jump to a place a
   file does not define lands in the latest file read before it (this
   mod's or an earlier mod's) that does. So may `font` (below).

   An entry may also be an object naming a setting of the mod, so the
   player can leave that file out, for example to keep the cards' English
   names:

   ```json
   "text": ["text.txt", {"file": "card_names.txt", "setting": "card_names"}],
   "settings": [
       {"key": "card_names", "label": "Translated card names", "type": "bool",
        "default": 1, "restart": true}
   ]
   ```

   The file is read only while the setting is not 0 (`mod.<id>.card_names`
   in the settings, or `MEMORIES_MOD_<ID>_CARD_NAMES=0` for one run). The
   text is built once, as the game starts, so changing it takes a restart;
   `"restart": true` is what says so beside the setting in the Mods window.
   A setting the mod does not declare is noted there, and the file read.

   With `"value"` the file is read only while the setting is exactly that
   value, so each choice of a `choice` setting can have its own file:

   ```json
   "text": [
       "text.txt",
       {"file": "people_us.txt", "setting": "people", "value": 0},
       {"file": "people_jp.txt", "setting": "people", "value": 1},
       {"file": "people_br.txt", "setting": "people", "value": 2}
   ],
   "settings": [
       {"key": "people", "label": "Character names", "type": "choice",
        "default": 0, "choices": ["Original (US)", "Romanized (JP)", "Localized"],
        "restart": true}
   ]
   ```

   `font` entries take `setting` and `value` the same way.
   A build older than this form reads the object as a file with no name:
   it notes `"text":  is not a file in the mod`, leaves that entry out and
   reads the rest.

   Save the files as UTF-8. A file in another encoding (Windows-1252, or
   what Notepad calls "Unicode") is reported, with the line where it goes
   wrong, rather than read as boxes.

4. Put the mod's folder in `mods` in the user directory, apply it in
   **Game > Mods** and restart. What the game could not read, and letters it
   has no way to draw, are listed beside the mod in the Mods window and in
   `MEMORIES_TRACE=mods`; everything else is used.

A translation may be partial: strings it leaves out stay as they are, and a
jump to a place no file has lands in the game's own text. The
listing itself must not be shared as it comes out of the tool: it is the
game's text. Share your translated file.

## The listing

```text
@bank dialog

[0501]
My dear prince!
Are you going to the city
to play cards again!?{page}You are of royal blood!
...{choice 02}«Run away»
«Keep listening»
{choose 80 L15DE L140F}

{:L140F}
The Pharaoh has gotten
wind of your activities...
```

* `@bank dialog`, `@bank descriptions` and `@bank names` start the three
  banks of the game's text: dialogue and menus; card texts; and card
  names, monster types, guardian stars, duelists and places.
* `[ID]` starts a string: its number, in hexadecimal. Its text starts on
  the next line. Card `n`'s name is `8000 + n` and its text `D100 + n`
  (`[8001]` and `[D101]` are Blue-eyes White Dragon's); the descriptions
  carry the card's name as a comment.
* A line break is a line break in the game's text box. Break the lines
  where they fit: a line wider than its box goes on at the start of the
  next row, which pushes the rest of the text down a row. Card texts have
  lines of 20 letters and room for 8 lines. A letter is 8 pixels wide, so
  a box has as many columns as its width in pixels over 8, and the width is
  the box's, not the string's: `[0021]`, the guardian star choice, has 22
  columns, and `[0022]`, the two-player duel's quit box, 10.
* In a menu with choices (`{choice ...}` then `{choose ...}`) that row is
  worse: when it pushes the choices past the bottom of the box, the console
  stops for good, with no frame after (the menu is laid out in one go and
  waits for a button nothing reads). The port cuts that line at the box's
  edge instead, and says so in `MEMORIES_TRACE=mods`; a menu that fits is
  drawn as the console draws it. Keep menu lines within their box. A line
  break of your own in a menu does not stop the game, but it counts as one
  of the choices' lines, so the last choice is lost.
* A menu with more lines than its box has rows under where it starts (four
  choices in the three rows left in the name box, or a menu that goes on
  from the rows of an earlier one) stops the console the same way. The port
  leaves the lines past the box out and offers only the choices in it
  (`{choose}` then takes the first targets), and says so in
  `MEMORIES_TRACE=mods`. Start a menu on a fresh box (after a `{page}`, or
  `{f8 1A}` as the name screen's own text does) and give it no more lines
  than the box has rows.
* A text box has room for so many letters at once: 254 in the dialogue
  box and some menus, 159 in most menus. What is past that on a page is
  left out, and a page with more than 254 is reported. A menu writes its
  text in one go: what is past its box's last line, or past a `{page}`, is
  left out too (the console would wait for a button there forever).
* A string ends at `{end}`, or at a code that jumps away (`{jump}`,
  `{choose}`, `{f8 17}`, `{f8 18}`, `{f8 28}`). What follows it up to the
  next `[ID]` or `{:L...}` is ignored, so blank lines and `# comments` can
  go there. A string that reaches the next item without one is reported:
  its blank lines and comments would be text.
* `{:LXXXX}` on a line of its own is a place something jumps to: a
  choice's answer, a branch, a shared ending. Its text belongs with it; keep
  the line. The listing names each after its place in the game's own text.
* `{cont}` marks a string that runs on into the next item without ending;
  keep the two in that order.

The codes:

| Code | What it is |
|---|---|
| `{page}` | wait for the button, then a fresh box |
| `{nl}` | a line break where the listing cannot write one (before a new item) |
| `{sp}` | a space at the end of a line, which an editor would strip |
| `{choice NN}` | the choice that follows: the next lines are its answers, one per line |
| `{choose 80 La Lb ...}` | where each answer goes, in order |
| `{jump L}`, `{call L}` | go on at `L`; insert the text at `L` (`{call L125A}` is the player's name) |
| `{if FFFF L}`, `{set FFFF}` | go to `L` if a story flag is set; set one |
| `{state ...}`, `{fx ...}` | pictures, pauses and effects of the story |
| `{f8 ...}` | the text's formatting and inserts: `{f8 00 20}` the card's name, `{f8 00 40}` its text, `{f8 03 ...}` a number, `{f8 0A NN}` a colour, `{f8 01 NN}`/`{f8 02 NN}`/`{f8 06 ...}` positions, `{f8 0E ...}`/`{f8 10 ...}` music and sound |
| `{g NN}` | a glyph by its number: the few symbols with no character to type |

Move a code with the words it belongs to; do not change its numbers. The
retail glyphs can be typed as themselves: letters, digits, `! " # $ % & '
( ) * + , - . / : ; < = > ?`, `«` `»`, `·`, `α β γ`, `← →`, `♂ ♀`; typographic
quotes and dashes are taken as their plain ones.

## The port's own strings

A few words the port adds to the game's screens are drawn in the game's
letters, inside the game's picture, and a translation gives them in the
same listing, in the dialogue bank, with ids no retail string has
(`FE00`-`FEFF`, `TEXT_OWN_*` in `src/pc/text/text.h`). They are not in the
extracted listing; add them:

```text
@bank dialog

[FE00]
NEW{end}

[FE01]
%d MORE CARD{end}

[FE02]
%d MORE CARDS{end}

[FE03]
PAGE %d OF %d{end}

[FE10]
DECK SLOTS{end}

[FE41]
Simon Muran{end}
```

| Id | Where | Room |
|---|---|---|
| `FE00` | Card drops' added result pages: after a card the player had none of | ends at the plate's end; each letter past 3 takes one from the card's name |
| `FE01`, `FE02` | the same pages' heading, left: one card past the first, or more | with `FE03` right-aligned on the same line: 33 letters for both, numbers and spaces included |
| `FE03` | the heading, right, when there is more than one page | as above |
| `FE10` | the card shop's menu (string `0011`): the entry under BUILD DECK | the menu's box shows 44 letters in all (spaces are none); retail's four lines have 35, so 9; a line is 15 wide |
| `FE41`-`FE67` | the opponent's name in place of COM (View > Opponent's name for COM): `FE40` + the duelist's id, 1-39 (the names bank's `8328` + id is the same duelist) | 14 letters, spaces and full stops (H.M. Anubisius, the longest English one); past that, the first 14 |

Letters and spaces only: a string with other codes is not used (the port's
English is). `%d` is where the port puts a number, in the order above
(`FE03`: the page, then how many). The headings are in the small letters,
which have no accents: an accented letter is drawn as its plain one.

The shop's menu with the entry is rebuilt from the translation's string
`0011` when it has one: its four lines as they are, `FE10` (or the English)
added under the second, centred as the others are, and its `{choice}` given
the fifth entry. A `0011` that is not four lines of letters, spaces,
`{f8 02}` steps and `{f8 0A}` colours, or five lines past the box's 44
letters, leaves the menu the translation's four entries, and the log
(`MEMORIES_TRACE=mods`) says so. A translation whose own four lines have
more letters than retail's has less room for `FE10`: the pt-BR menu has 38,
so 6.

The opponent's name in place of COM (`FE41`-`FE67`) is set in the text's
font, not the game's letters, so it may have accents (Simão): letters,
spaces and full stops of Latin-1; a string with anything else is not used
(the log says so). Without it, a translation that renames the duelist in
the names bank (`8329`-`834F`, as pt-BR's does) has that name shown, made
short as the English ones are (`Tables_ShortenName`): up to its first
character that is not a letter, a space or a full stop (Jono 2º Duelo:
Jono), whole up to 14; longer, its first words as initials when every word
starts with a capital (Sumo Mago Martis: S.M. Martis), else its last word
(Mago da Montanha: Montanha). A name the translation gives as the English
(Weevil Underwood) keeps the English short one (Weevil). Without either,
the English. The result screens show the same name over COM's column,
an accented letter as its plain one (their small letters have none).

| Id | Duelist | Id | Duelist | Id | Duelist |
|---|---|---|---|---|---|
| `FE41` | Simon Muran | `FE4E` | Yami Bakura | `FE5B` | Desert Mage |
| `FE42` | Teana | `FE4F` | Pegasus | `FE5C` | High Mage Martis |
| `FE43` | Jono | `FE50` | Isis | `FE5D` | Meadow Mage |
| `FE44` | Villager 1 | `FE51` | Kaiba | `FE5E` | High Mage Kepura |
| `FE45` | Villager 2 | `FE52` | Mage Soldier | `FE5F` | Labyrinth Mage |
| `FE46` | Villager 3 | `FE53` | Jono 2nd | `FE60` | Seto 2nd |
| `FE47` | Seto | `FE54` | Teana 2nd | `FE61` | Guardian Sebek |
| `FE48` | Heishin | `FE55` | Ocean Mage | `FE62` | Guardian Neku |
| `FE49` | Rex Raptor | `FE56` | High Mage Secmeton | `FE63` | Heishin 2nd |
| `FE4A` | Weevil Underwood | `FE57` | Forest Mage | `FE64` | Seto 3rd |
| `FE4B` | Mai Valentine | `FE58` | High Mage Anubisius | `FE65` | DarkNite |
| `FE4C` | Bandit Keith | `FE59` | Mountain Mage | `FE66` | Nitemare |
| `FE4D` | Shadi | `FE5A` | High Mage Atenza | `FE67` | Duel Master K |

The port's other words (the save slot and deck slot menus, the host
window's menus) are drawn in the host's font over the game, not in the
game's letters, and are not part of a translation's text.

## Letters

The game's font has 91 letters, none accented. The port draws more,
the first time a text uses them:

* **An accented letter** is the retail letter with its mark drawn on, in
  all three text sizes (16x16, 8x12 and the 8x8 of the duel results'
  headings): acute, grave, circumflex, diaeresis, tilde, ring, cedilla,
  caron, macron, breve, dot, double acute and ogonek, on any letter Unicode
  combines them with (251 of them: á, Ž, ő, ę, ǎ, ẽ...; Vietnamese below). Also
  ¿ ¡ ı ø Ø ł Ł đ Đ ħ Ħ, and `:` in the 8x8 font, which has none (two of its
  `·`, in the letters' colours).
* **How a mark fits** a cell with no room above the letter. In the 16x16
  font a capital is squeezed down to leave the mark its rows. The small
  fonts have none to spare: an 8x12 capital's outline is on the cell's top
  row (body 9 rows, a small letter's 7), an 8x8 capital's too (body 6, small
  4), so squeezing would leave a small letter. There the capital gives up
  **one** row of its body, the inner row most like a neighbour, nearer the
  middle on a tie (a thick stroke thins, a thin one stays), and the mark's
  two rows go on the cell's top two, its lower row where the letter's top
  outline was, touching the letter: É, Ê, Ã, Õ read as capitals, a row
  shorter than the others. A small letter whose outline row is where the
  mark's outline goes below it (é, ã, ô in 8x12, all of them in 8x8)
  shares that row instead of being squeezed. The 8x8 font's cedilla is one
  pixel on its bottom row, under the letter.
* **Vietnamese** (all 134 letters past ASCII: ả ạ ơ ư ế ặ ự...) is composed
  the same way, with three more marks and letters of two:
  * the **hook above** (ả) is drawn like the other marks; the **dot
    below** (ạ) goes on the row under the letter, the pixel of the letter
    above it turned to outline so it stays a dot (the small fonts' last row
    is the letters' foot); under a tail (ỵ) it goes beside it, under the
    right arm; the **horn** (ơ ư) is a stroke of two pixels (three in
    16x16) out and up from the letter's top right. Any letter Unicode gives
    one of these marks is drawn too (ḍ, ṣ, ṭ...).
  * **Two marks** (^, the breve or the horn, and a tone): in the 8x12 and
    8x8 fonts, which have no rows to stack them, the tone goes **beside**
    the ^ or breve, on its right, in the same two rows, as compact
    Vietnamese fonts do (Ấ is ^´ over A; the breve beside a tone is drawn
    as a v, so that the two fit), so a capital gives up only the row it
    gives up for one mark. In 16x16 the tone is **stacked** over the ^ or
    breve, to its right. The 8x8 font leaves the tone out (keeping the ^ or
    breve) if the two do not fit its cell; none of the Vietnamese ones needs
    to. Horn and dot below take no rows above, so ớ, ợ, ậ are a mark above
    and one of these.
  * The table (`src/pc/text/accents.inc`) is written by
    `tools/pc/glyph_accents.py` from Python's `unicodedata`.
  * HD text sets these from the font as it does é, fitted to the composed
    cell; the dot below touches the letter in ọ ộ ợ ụ ự ệ ỵ and their capitals
    (Ộ's circumflex too; readable, a drop under the letter, about 2% of the
    letters of a Vietnamese text) and ỵ reads poorly. At 1x they stand apart. A renamed card's
    title plate (Times, `cards/art.c`) fits a name whose marks reach past
    its top (two-mark capitals) into its rows instead of cutting them.
* **Text is composed (NFC)** when a listing is compiled: a letter followed
  by combining marks (U+0300-U+036F), as some editors and macOS save them,
  is one letter (e + U+0302 + U+0301 is ế), whatever order the marks are in;
  a mark with nothing to compose with stays a glyph of its own after it.
  Only the listing does this; a mod's card names and host menus read the
  UTF-8 as it is, so save those composed.
* `MEMORIES_GLYPH_SHEET=file.ppm` writes the pictures of every letter the
  text added (8x12, 16x16 and 8x8, one column each, outline black) the first
  time one is drawn, and `file.ppm.txt` with their code points: a way to see
  all of a translation's letters without finding each on screen.
* **ß ẞ æ Æ œ Œ ð Ð þ Þ º ª ° €** are built in, drawn from Noto Sans Bold
  (SIL Open Font License) and given the retail letters' outline and
  shading.
* **Anything else** (Greek, Cyrillic...) is set in a font: first the
  mod's `"font"` files (`.ttf`, `.otf`), then the system's sans-serif.
  Ship a font with the mod if it needs one: the system's differs between
  machines, and a machine may have none.

The added letters live in the software GPU's texture bank 15, not in the
console's VRAM, and take their colours from the text's own palettes, so they
fade, flash and change colour as the retail ones do. Up to 672 of them.

## How the port does it

The text is data in the game's executable: three banks at `0x801B0000`
(menus and dialogue), `0x801C0000` (card texts) and `0x801D0000` (names),
each string found by its id through a table. Their bytecode is described in
[the text control codes](text-control-bytecode.md); `text_listing.py`
decodes all of it, following every jump from every string, and `check`
assembles the listing again and compares it with the retail bytes (all
128,166 of them match).

At startup `src/pc/text/translation.c` compiles each mod's listing
(`listing.c`) into a buffer of its own. The game turns a string id into
text in four places (`TextBox_BuildStep`, `Text_LookupString`, the
card-name and string inserts in `duel_effect_command.c`), which ask
`Text_Resolve` first. A jump in the game's text replaces the low 16 bits of
the text pointer, which only works inside a 64 KB bank; the compiled text
is anywhere and any size, so its jumps are indices into a table of its own
places, and the five jump handlers (`{jump}`, `{call}`, `{if}`, `{choose}`,
`{f8 17/18}`) ask `Text_Retarget`. A place the listing does not define is
the retail address, which is how `{call L125A}` still reaches the name the
game writes there. Each compiled file keeps its places, so a later file's
jump to one it does not define lands in the latest earlier file that does,
before it falls back to the retail text.

The game keeps a text box's letters in a slice of the entry table
`D_800EB288` (620 entries: 255, 160, 160 and 45 for the four text
channels). The console's text always fits; the port's
`DuelEffect_AppendEntry` stops adding letters when the channel's slice is
full, rather than writing into the next channel's (or past the table), and
`func_80039A14`/`func_80039A60`, which build a menu's text in one go, stop
at a page that waits for a button (state 4) instead of looping forever.
A menu with choices has the same loop in `func_80039794`, which steps the
text unbounded while `flags_34 & 0x1000` (the choices' layout) is up; there
`TextBox_BuildStep` drops a letter past the box's right edge when its wrap
would leave the choices' last line below the box (`Text_CutsMenuGlyph`).
The other way into state 4 inside that loop is `Text_NewLine`: a new line
whose row is past the box before the menu's last line (`field_56 <
gDialog_bChoiceCount`, so `Text_TryCompleteChoiceLayout` does not take
over). There the port skips the wait and cuts the menu
(`src/pc/text/menu_cut.c`, by text channel `index_57`): the letters of the
lines after it are dropped in `TextBox_BuildStep`, and once the layout
completes `gDialog_bChoiceCount` is cut to the lines that were down less the
heading rows (`D_8009B34C & 0x30`), at least one. A menu that fits never
takes either path, so the console's frames are unchanged
(`tests/pc/menu_cut_test.c`). The Library's heading (string `F8`, "<seen/722>") is rewritten for the
number of cards there are, by its id, whether the text is the disc's or a
translation's (`Cards_Text`).

Glyph codes above the retail ones (`0x100` on, written `F1`-`F5` and a low
byte, which the game already reads as a glyph) have words of their own
(`Glyphs_Word`), and `func_80035E20` draws them from bank 15
(`Glyphs_Cell`). The 8x8 font is another path: `DuelEffect_AppendEntry`
keeps only the glyph's index in that font (bits 20-27 of its word, the
retail letter's for an accented one, 0 for `:`, which the retail game then
drops), so on the port it also writes the glyph's Shift-JIS into the entry
(`code_00`, which the retail 8x8 path leaves stale) and gives `:` a stand-in
index (`Glyphs_TinyIndex`); the draw asks `Glyphs_TinyCell`, which makes the
8x8 picture from the font at (704, 0) and puts it on page 4 of the bank,
with the 8x8 palettes (row `0xFA`, from x 656) copied beside the others.
Retail text never has an accented letter or `:` in the 8x8 font (its only
8x8 strings are the results' headings, YOU/COM and the ♂/♀ marks), so its
pictures are the same as before, byte for byte. The built-in letters (ß,
æ...) and characters set in a font (Greek...) still have no 8x8 picture and
are left out there, as before.
If a translation renames cards, their alphabetical order
(`gCard_asNameSortKey`) is worked out again from the new names, accents
sorting as their plain letters. The names and texts of cards a mod adds
([more cards](more-cards.md)) are UTF-8 too and take the same letters.

The name on the top of a card's big picture (Triangle in a duel, the
Library, Build Deck) is not text either: it is a 96x14 4-bit plate in the
card's art record on the disc (`+0x2840`, [art.c](../src/pc/cards/art.c)),
drawn subtractively over the gold frame, and `func_800289BC` uploads it with
the picture. So when a translation rewrites a card's name (string
`0x8000 + id`, `Text_Overridden`), `Cards_PatchArtRecord`, which that loader
already calls before its uploads, puts a plate set from the new name in
place of the English one (`translated_plate` in `cards.c`, made once per
card by `CardArt_TitleFromName`, as the plate of a mod card with a name of
its own is). There is no background to keep: index 0 is clear and is the
whole of every retail plate's border, the gold showing through. The name is
set in the same serif face and layout HD text uses for titles (Times at 13
pixels, baseline under row 11, squeezed into columns 3 to 93 when longer
than 90 pixels), and each texel takes the plate ink of the nearest tone:
what inks 1 to 7 take from the gold was measured on a retail plate in the
game (1 all, 7 about a fifth), so stems land at 1 and edges at 6 and 7, as
the retail plates have them. This is the plate at 1x and at any internal
scale without HD text; with HD text at scale 2 and up, the title is set
from the name at that size over it, as before (`HdText_Title`). A card
whose translated name is the retail one, a card a mod's `cards[]` names
(its own plate wins), and a system with no serif face keep the plate they
had; with no mod renaming cards the art is the disc's, byte for byte.
`tests/pc/card_plate_test.c` (ctest `pc_card_plate`, where FreeType is
found) checks the plates: inks 0 to 7 only, clear edges, a long name
squeezed inside, accents inside the plate.

Running the recorded smoke cases with the untranslated listing installed
as a mod gives the same pictures as without it, byte for byte, jumps into
the listing's own text and to the player's name included.
`tests/pc/text_listing_test.c` (ctest `pc_text_listing`) covers the
compiler.

## The official languages

Game > Language (notes/pc-build.md, "Language") puts in the game the
European releases' own translations, English (Europe), French, German,
Italian and Spanish, read at startup from the player's PAL disc and
handed to the same machinery as a mod's text. Nothing of those discs is in
the repository: the port knows where the text is and how to read it, and
which letter each language's font draws on a code; the words come off the
disc.

**Where the text is.** Unlike the US disc, the PAL discs keep no text in
the executable. DATA/WA_MRG.MRG has a pack per language (English, French,
German, Italian, Spanish) from sector 6498, 110 sectors apart; after the
language's font and interface textures come three files, each a u16 id
(0x0F, 0x10 and 0x11, plus 3 a language) and a u16 0:

- A, 0xF000 bytes: a table of u16 offsets at +4, the menus (0x000-0x0FF),
  the card texts (0x100-0x3FF, the US `D100`+) and the story's lines
  (0x400-0x4F9, the US `0500`-`05F9`, into file B), then the menus and the
  card texts;
- B, 0x10000 bytes: the story's lines;
- C, 0x7180 bytes: the names (0x360, the US `8000`+), offsets as the US
  names bank's.

The string ids are the US ones. A disc of France, Germany, Italy or Spain
has all four languages (the Italian and Spanish ones the final text of
all four); the English one only English.

**How it is read** (src/pc/text/pal_text.c, src/pc/text/language.c). The
codes are the US text's, decoded as tools/pc/text_listing.py does, into a
listing in memory with the US ids that `TextListing_Compile` compiles; the
listing is, byte for byte, the one the research extractor wrote for each
of the five discs, but for the two points marked below. What differs from
the US text:

- `F8 1B` (no operand) is the player's name: `{call L125A}`;
- the name buffers are at A+`F800`, `F814` and `F848`: the US `122B`,
  `1238` and `125A`;
- `F8 03` reads its number 0x15D7C lower in RAM: moved to the US address;
- menus `06`, `10` (the debug menu with ENDING and LANGUAGE), `18`, `19`,
  `50`, `EE`-`F1` (the PAL name keyboard), `F3` and `F7` mean something
  else, or nothing, on PAL: they keep the US string; so do the result
  pages, `40`-`45` (below; the extractor swapped `40` and `44`);
- the menus' labels are renamed from `LF000` up, as the story's text in the
  same bank uses the offsets;
- `F8 1C`, which only the two-player results use, is left out: the US
  engine reads it as a glyph (phase 2; the extractor kept it);
- the glyph codes are the PAL executable's (its Shift-JIS table, read off
  the same disc), and the accented letters sit on placeholder codes that
  each language's font draws its own way (the tables in pal_text.c).

**Sources.** Where the text comes from is one table in language.c
(`sources`: whether a source has the language, and its listing): today
only the PAL discs. A pack the release ships (phase 1b: a tool writes
each language's listing with `PalText_Listing`, from the discs) goes in
that table ahead of the discs, which stay a source; the rest (the port's
own strings, the compiling, the spacing) does not change. Images with
words stay disc-only.

**Under the mods.** The language is compiled first and a mod's string
stands over it, string by string, so pt-BR over Spanish is pt-BR where it
has a string. Its labels are the PAL banks' offsets, so a mod's undefined
label still means the US text there, never the language's. With a language
on, the port's features that look for a translated string (the shop's menu
with DECK SLOTS, the opponent's name over COM on the results) behave as
with a full translation mod.

**The port's own strings** (FE00-FE10 above) come with the language where
written: Spanish has them (NUEVA, `%d CARTA MÁS`, `%d CARTAS MÁS`,
`PÁGINA %d DE %d`, RANURAS; the small letters draw MÁS as MAS). The
Spanish shop menu's four lines have 43 letters of the box's 44, so DECK
SLOTS stays out of it (F6 still opens the slots). French, German and
Italian keep the port's English for now: phase 2, for a speaker to write.
The opponent's name over COM needs no string: the names bank's Spanish
names are shortened as a translation's are.

**Widths.** The PAL text is longer than the US (French has about a hundred
dialogue lines past the US 36 columns) and still fits on the console:
the PAL font is spaced by letter. The EU executable's glyph routine
(func_80036A78, the US func_80036C14) returns an adjustment that
TextBox_BuildStep adds to the 8 pixels of a cell (0x5A): in the dialogue
boxes' mode a space takes 7 pixels, `f`, `i`, `l`, `.` and `,` take 6 and
are drawn a pixel left, and the apostrophe takes 2, drawn 3 left (the
same code is in the French/German/Italian/Spanish executable). The boxes
are as wide as the US ones and wrap the same way (TextBox_WrapLineIfNeeded,
unchanged), so the text was written for that spacing: many PAL lines lean
on the box's edge to wrap. With a PAL language on, the port spaces
letters the same (`Language_Advance`, a hook in TextBox_BuildStep; not the
small letters of flag 0x100, nor 0x80), and a line breaks where the
console breaks it; with English (US) nothing changes. The PAL also has
line heights of 16 (US 12) in boxes 0x40 high (US 0x30), four lines
either way: the port keeps the US heights. A menu line that would still
pass its box is cut there (Text_CutsMenuGlyph), as a mod's.

Known in phase 1: RESULTS keeps the US pages (strings `40`-`45`, in
English, beside the language's YOU and COM columns). The PAL pages are laid
out by code of their own (func_80020EAC and the pages in reverse order):
their `40` begins with DEFENSE STATISTICS where the US has the win
condition, no PAL string says TOTAL ANNIHILATION, and `41`/`42` jump into
`40`'s tail, so under the US screens an attrition or Exodia win would show
one page twice and never the statistics. The images with words (main menu,
game over, the results' headings) stay English. Six German card texts have more than
the 8 lines the duel's card viewer shows (untested; the text box waits for
a button past its height rather than stopping, as with the dialogue).

**Phase 2.** The PAL result pages (func_80020EAC's layout, then their
strings) and the other modes of the
spacing (2 and 3: the Library's title and a few menus); the images per
language, from SU.MRG (the main menu, sector 136 per language) and WA_MRG
(game over, sector 10135 + 41 per language) as a texture pack made at
startup; `F8 1C` in the two-player results; and the port's own strings in
French, German and Italian, reviewed by speakers.
