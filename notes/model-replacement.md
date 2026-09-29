# A card's 3D model from a mod

New to this? [The tutorial](model-tutorial.md) walks through making a model
of your own, from a downloaded model to a card in a duel. This page is the
reference.

A mod's `models` list gives a card a 3D model of its own, draws it with
settings of its own, or both:

```json
"models": [
    { "card": "Mushroom Man", "file": "models/pot.bin", "hd": "models/pot-hd.png", "yaw": 180 },
    { "card": "Kuriboh", "scale": 150, "tint": "#FFB0B0", "speed": 150 },
    { "card": "my-mod:sky:1", "file": "models/sky.bin", "tint": [255, 176, 96] }
]
```

| Key | Meaning |
|---|---|
| `card` | the card: a disc id, a disc name, or an added card's identity (`mod:id:n`, [More cards](more-cards.md)) |
| `file` | a model record in the mod: the whole 276-sector MODEL.MRG record, 565,248 bytes |
| `hd` | with `file`: the record's textures at a higher resolution, one PNG of its three texture pages side by side (`model_import.py` writes it); drawn at View > Internal 2x and up, like a texture pack's image |
| `yaw` | a turn about the model's up axis, in degrees (-360 to 360): `180` turns it round |
| `scale` | the model's size, percent of what it is drawn at now (10 to 1000) |
| `tint` | a colour the model's polygons are multiplied by: `"#RRGGBB"` or `[red, green, blue]`, 0 to 255; white leaves them as they are |
| `speed` | how fast it animates, percent (25 to 400) |

Every key but `card` may be left out. A later entry for the same card,
in the same mod or a later one in load order, replaces what it sets and
keeps the rest. Like `cards`, the list is read once at startup, so changing
it needs a restart. Problems (no such card, a file of the wrong size or
outside the mod, a number out of range, an `hd` image of the wrong shape)
are reported beside the mod in Game > Mods, and the entry is left out.

The model is used wherever the card's model is: the battle presentation
(the 3D fight an attack confirmed with Square plays), the Library's model
view, and the 3D Monsters mod on the field and on the big attack cards. A
card a mod added, or a magic or trap card a `replace` made a monster, can
have a model this way even though the disc has none for it.

`yaw` and `scale` turn and size the model about the point it stands on,
in all three. The 3D Monsters mod fits every monster to its zone, and
`scale` is applied over that fit.

## A model of your own

`tools/pc/model_import.py` makes a record from any textured triangle mesh.
The record takes a disc card's skeleton, animations, battle moves, voices
and sounds (its *template*) and replaces all of its geometry and textures:

```sh
# A big model (FBX, glTF) to about 1500 triangles, with Blender:
blender -b --python tools/pc/model_prepare.py -- "Pot of Greed/M04844_Model.fbx" pot.obj 1590 body
# On Morphing Jar's skeleton, with its texture:
python3 tools/pc/model_import.py pot.obj pot.bin --template 591 \
    --texture "Pot of Greed/M04844_tex.png" --preview pot.png
```

`model_prepare.py` keeps the named meshes (here `body`, leaving the pot's
companion creature out) in their rest pose, decimates them together and
writes a triangulated OBJ, +Z its front and +Y up. `model_import.py` then:

1. leaves out the triangles no view from outside the model shows (the
   inside of a mouth or a neck; `--keep-hidden` keeps them). The console
   sorts triangles by depth instead of keeping a depth buffer, and such a
   triangle would show through the body;
2. averages the normals of a vertex a UV seam split in two, so the
   lighting has no line along the seam;
3. turns the mesh to the game's axes (y down, its front where a disc
   model's front is; `--yaw` turns it first), scales it to the template's
   height (`--height` in percent) and stands it where the template stands;
4. binds every vertex to the bone of the nearest template vertex, and
   writes the whole mesh as shared-vertex polygons over those bones: each
   bone projects and lights its run of vertices, and the triangles join
   them, so the mesh bends with the template's animations without cracks;
5. cuts the textures onto the three 8-bit texture pages (128x256 texels, a
   256-colour palette each). One texture is split in halves over two pages
   (overlapping a little), with the third holding its middle for the
   triangles that cross it; two textures get one and a half pages and one
   page; three get a page each. The same pages at 4x, from the full-size
   texture, go to `OUT-hd.png`, for the entry's `hd`;
6. writes the template's record with the new model data, textures and
   palettes, and keeps everything else of it byte for byte;
7. with `--preview`, draws the record it wrote, from the front and from
   its right, straight from its bytes.

A template near the new model's shape animates it best: Morphing Jar
(591) hops and rolls a pot, a dragon's skeleton flies a dragon. The model's
battle moves are the template's too.

Limits the tool enforces: 1500 triangles, and 189,152 bytes of model data,
the most any record on the disc has. Every triangle is a 40-byte GPU packet
in a frame's 140,000-byte packet buffer, which the arena, both duellists and
the effects share; the disc's own models reach 1764 triangles (the median
is 828), and a battle of two disc models takes about 55,000 bytes. The
facial shape keys and the model's own animations are not carried over; the
template's are used.

`tools/pc/test_model_import.py` (ctest `pc_model_import`, skipped without
the disc) converts a made-up box and reads the record back the way the game
does.

## Starting from a disc model

`tools/pc/model_record.py` starts from a model the disc has:

```sh
python3 tools/pc/model_record.py extract 1 bewd.bin --disc game/rpg-yfm.bin
python3 tools/pc/model_record.py info bewd.bin
python3 tools/pc/model_record.py recolor bewd.bin bewd-red.bin --hue 180 --saturation 150
```

`extract` writes the record of a card's model (from a `.bin`, an `.iso` or
`MODEL.MRG` itself); `recolor` turns every colour of its palettes round the
colour wheel and changes their saturation and brightness. The record keeps
everything it came with: the model, its textures, its animations, its
voices and the battle moves it makes (Blue-Eyes' record fights with White
Lightning whichever card it is given to).

A record the tools did not write works too, as long as it has the loader's
layout. `info` lists it; the phases, in order:

| Sectors | What |
|---:|---|
| 96 | model data: a byte count, then an HMD without its id word |
| 48 | textures, 64x16 VRAM blocks: three 8-bit pages of 128x256 texels |
| 2 | palettes: a 256-colour row a page |
| 1 + 16 | stance 0 (attack): a palette row and a texture strip |
| 1 + 16 | stance 1 (defence): the same |
| 4 x 10 | the stances' battle modules, for slot 0 and slot 1 |
| 2 x 2 | the primary battle modules, for slot 0 and slot 1 |
| 1 | the animation sequence bank |
| 50 | voices |
| 1 | metadata: the sound triggers and the slot's settings block |

The model data's polygons name texture page `0x9A + page` and palette
`0x28 + 0x40 * row`, as the disc's own models do; the loader moves both to
the slot's part of VRAM (`func_8004D134`). The port checks the size and
that the record starts with model data (a byte count no bigger than the 96
sectors, and an HMD block count), not that the rest makes sense: a record
with broken battle modules breaks the battle.

## How it works

The card keeps the model id the game gives it (`Cards_ModelId`), because
the battle indexes the card tables with that id. Only the record the loader
fetches changes. `src/pc/cards/models.c` reads every record at startup and
serves them from sectors past the disc and past every virtual file the
mods' larger replacements were given (`Mods_DiscEnd`). The drive model asks
it first (`libds.c` `read_raw`), so `Model_LoadMonsterMerge` requests the
record as an offset from MODEL.MRG's start and the game's own seventeen
phases load it, voices and all.

`Model_LoadMonsterMerge` is given a model id, not a card, so whoever knows
the card says which one a model slot is about to load
(`Models_SetSlotCard`): the battle, for both of its slots
(`duel_scene_battle.c`), and the Library (`library_runtime.c`). The title's
random models clear it. A slot takes the card's record only while the model
id it is asked for is still that card's, which is what keeps a card's model
from leaking into a later load for another card.

The settings are applied for the card the slot last loaded:

- `yaw` and `scale`: in the draw (`func_800540B4`, a PC wrapper around the
  retail body). Sorting HMD block 0 runs the animation, which poses every
  part, so right after it the body's anchor coordinate (the slot's
  `field_D1C`, the unit the body hangs from; the root otherwise) is turned
  and sized about its own origin, the point the model stands on. The root
  is not that point: a duel model hangs a few hundred units from it. After
  the draw the anchor is put back and the slot's world matrices are
  recomputed, so nothing else sees the change;
- `tint`: `func_800540B4` multiplies the primitive templates' colour, which
  the lighting multiplies in turn, and lights the slot every frame rather
  than from its colour cache, as the game does for a coloured slot;
- `speed`: `func_800556E8` multiplies the animation step;
- `hd`: each page of the record is known to the texture pack by the disc
  offset it is delivered from (`TexturePack_AddDisc`), with its palette's,
  so the texture tracer paints the page's VRAM words with the PNG's pages
  as it does a pack's images.

A slot with a mod's record is left out of a frame whose packet buffer has
no room left for it (`Model_HasInsufficientBufferSpace`), rather than
overflowing into what follows the buffer. The disc's models are drawn as
they always were.

The 3D Monsters mod loads records itself: it asks `Models_RecordLba` for the
card's, draws and steps each monster under its card's `tint` and `speed`
(`Models_UseCard`), turns it by `yaw` where it places it (the body's offset
turned with it), and multiplies its fitted size by `scale`.

The records' contents, the `hd` images and the settings are part of the mod
profile save states are checked against (`Models_Signature`), and the
slots' cards are saved with a state.

## Limits

- 256 records; each is held in memory (565 KB), and they take 276 sectors
  each of the virtual disc, which ends at LBA 449849.
- A record has the loader's fixed size: a model bigger than 96 sectors of
  model data, or with more textures than the blocks hold, needs loader
  work first ([the larger-file plan](larger-disc-files-plan.md)).
- `scale` does not move the camera: the battle frames a model as big as
  the record's own, so a large scale can leave the picture.
- The console draws triangles in depth order, without a depth buffer.
  Close, concave parts (lips over a pot's side) can still show a sliver
  through each other from some angles, as on the console.
