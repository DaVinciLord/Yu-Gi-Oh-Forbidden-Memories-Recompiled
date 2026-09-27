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
* A line break is a line break in the game's text box. The text box does
  not wrap by itself: break the lines where they fit. Card texts have
  lines of 20 letters and room for 8 lines.
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

## Letters

The game's font has 91 letters, none accented. The port draws more,
the first time a text uses them:

* **An accented letter** is the retail letter with its mark drawn on, in
  both text sizes: acute, grave, circumflex, diaeresis, tilde, ring,
  cedilla, caron, macron, breve, dot, double acute and ogonek, on any letter
  Unicode combines them with (251 of them: á, Ž, ő, ę, ǎ, ẽ...). A
  capital with a mark above is set a little shorter so the mark fits the
  line. Also ¿ ¡ ı ø Ø ł Ł đ Đ ħ Ħ.
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
The Library's heading (string `F8`, "<seen/722>") is rewritten for the
number of cards there are, by its id, whether the text is the disc's or a
translation's (`Cards_Text`).

Glyph codes above the retail ones (`0x100` on, written `F1`-`F5` and a low
byte, which the game already reads as a glyph) have words of their own
(`Glyphs_Word`), and `func_80035E20` draws them from bank 15
(`Glyphs_Cell`). If a translation renames cards, their alphabetical order
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
