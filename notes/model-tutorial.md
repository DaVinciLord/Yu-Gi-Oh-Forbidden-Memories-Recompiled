# Tutorial: your own 3D model for a card

This walks through putting a 3D model you found or made into the game, as
the model of a card: in the Library, in the 3D battle, and on the field with
the 3D Monsters mod. The example is a Pot of Greed model from outside the
game, given to a new card. [Model replacement](model-replacement.md) is the
reference for every key and tool used here.

What you end up with is a mod folder like this:

```
pot-of-greed/
    mod.json
    models/
        pot.bin        the model record the game loads
        pot-hd.png     its textures at 4x, for Internal 2x and up
```

## 1. What you need

- **The game's disc image** (`rpg-yfm.bin`), the one you play with. The
  tools read the template's model from it.
- **The tools**, from the source repository: `tools/pc/model_prepare.py`,
  `tools/pc/model_import.py` and `tools/pc/model_record.py`. Download the
  repository (Code > Download ZIP on GitHub) or clone it.
- **Python 3** with numpy and Pillow: `pip install numpy pillow`.
- **Blender 4.2 or newer** (free, blender.org), if your model is an FBX or
  glTF file or has more than about 1500 triangles. Blender does the heavy
  work of shrinking it; you never have to open its window.
- **A model**: an `.fbx`, `.glb`/`.gltf` or `.obj` with its texture (a
  `.png`). Anything you did not make belongs to whoever did: a mod with a
  model taken from another game is for your own copy, not for sharing.

The commands below are for a terminal opened in the repository's folder.
On Windows use `python` for `python3`, `\` in paths, and Blender's full
path, for example
`"C:\Program Files\Blender Foundation\Blender 4.2\blender.exe"`.

## 2. Look at the model

Open the model's folder. You need to know two things:

- **Which file is the colour texture.** Models often come with several
  PNGs: the one that looks like the model's colours is the one you want
  (here `M04844_tex.png`). Files named `normal`, `specular`, `roughness` or
  `mask` are not.
- **Which meshes to keep**, if the file has more than one. The Pot of
  Greed file has `body` (the pot) and `sprite` (a little creature that
  rides it). If you don't know the names, run step 3 without a name
  first: it prints how many triangles it kept, and Blender's window
  (File > Import) shows the mesh names in its Outliner.

## 3. Make it small enough

A PlayStation model is small: this game's own models are 800 triangles on
average and 1764 at most, and the tools take up to 1500. Shrink the model
with Blender:

```sh
blender -b --python tools/pc/model_prepare.py -- "Pot of Greed/M04844_Model.fbx" pot.obj 1590 body
```

- `pot.obj` is the file it writes.
- `1590` is how many triangles to keep. A little over 1500 is fine: the
  next step leaves out the ones that can never be seen (the inside of the
  mouth, here about a hundred), and says so if too many are left.
- `body` names the meshes to keep, separated by commas. Leave it out to
  keep them all.

It prints something like `pot.obj: 1590 triangles from 6972`.

## 4. Pick a template

The game plays a model with a skeleton, animations, battle moves, voices
and sounds. A new model borrows all of these from a disc monster, its
**template**, and only brings its own shape and textures. Pick the monster
whose shape and way of moving are nearest your model's:

| Your model | A template | Card id |
|---|---|---|
| a jar, pot or anything that hops | Morphing Jar | 591 |
| a dragon | Blue-eyes White Dragon | 1 |
| a person with a weapon | Celtic Guardian | 41 |
| a winged person | Harpie Lady | 62 |
| a small round creature | Kuriboh | 58 |

Card ids are in `notes/card-catalog.csv`, and the Library shows each card's
number. The template's attack is the one your model makes: a pot on
Morphing Jar's skeleton rolls in and attacks like Morphing Jar.

## 5. Make the record

```sh
python3 tools/pc/model_import.py pot.obj pot.bin --template 591 \
    --texture "Pot of Greed/M04844_tex.png" --preview pot.png
```

- `pot.bin` is the model record, `pot-hd.png` its HD textures (written
  beside it).
- `--texture` is the colour texture. Leave it out if the `.obj`'s `.mtl`
  names it (`map_Kd`); `model_prepare.py` does not keep textures there.
- `--disc game/rpg-yfm.bin` is where it looks for the disc; give yours if
  it is elsewhere.
- `--preview pot.png` draws the record the way the game will read it.

Open `pot.png`. The left half is the model **from the front**, the right
half from its right side. It should stand upright, be textured, and have no
holes.

- **It faces away** (the left half shows its back): add `--yaw 180` and run
  it again. `--yaw 90` or `--yaw -90` turn it a quarter.
- **It lies on its side or is upside down**: the model's up is not +Y.
  Turn it upright in Blender and export it again, or ask whoever made it.
- **It is the wrong size next to the template**: `--height 80` makes it
  80% of the template's height, `--height 120` 120%.

It stops with a message if the model is too big (too many triangles, or too
much data); run step 3 with a smaller number.

## 6. Make the mod

Make a folder for the mod, with a `models` folder in it, and copy
`pot.bin` and `pot-hd.png` into `models`. Then write `mod.json` beside it.

To give the model to a card of the game, name that card:

```json
{
    "id": "pot-model",
    "name": "Pot model",
    "version": "1.0",
    "author": "you",
    "description": "Mushroom Man is a pot.",
    "enabled": true,
    "models": [
        { "card": "Mushroom Man", "file": "models/pot.bin", "hd": "models/pot-hd.png" }
    ]
}
```

To add a new card that has it, add the card too (see
[More cards](more-cards.md) for everything a card can have). The new card
is named in `models` by its stable identity: the mod's `id`, the card's
`id`, and `1`.

```json
{
    "id": "pot-of-greed",
    "name": "Pot of Greed",
    "version": "1.0",
    "author": "you",
    "enabled": true,
    "cards": [
        { "copy": "Morphing Jar", "id": "pog", "name": "Pot of Greed", "attack": 1000, "defense": 1000 }
    ],
    "models": [
        { "card": "pot-of-greed:pog:1", "file": "models/pot.bin", "hd": "models/pot-hd.png" }
    ]
}
```

## 7. Install it and look at it

Put the mod folder in the `mods` folder of your user directory:

- Windows: `Documents\My Games\YFM Re-Decomp\mods`
- Linux: `~/.local/share/YFM Re-Decomp/mods`

Start the game, open **Game > Mods**, and make sure the mod is on. Models
are read when the game starts, so restart after turning it on or changing
anything in the mod. If an entry has a problem, the Mods window says which
and why beside the mod.

Where to see the model:

- **The Library**: open the card (the Library shows cards you have seen).
  Its 3D model turns beside it.
- **The 3D battle**: in a duel, attack with the card and confirm the
  target with **Square** instead of X.
- **On the field**: turn on the **3D Monsters** mod in Game > Mods; face-up
  monsters stand on their cards.
- **In HD**: View > Internal 4x. The `hd` textures are drawn from 2x up.

## 8. Change how it looks

Each entry in `models` can also say how the model is drawn. These work for
a model of your own and for the game's own models:

```json
{ "card": "pot-of-greed:pog:1", "file": "models/pot.bin", "hd": "models/pot-hd.png",
  "yaw": 180, "scale": 120, "speed": 150, "tint": "#FFE0E0" }
```

| Key | What it does | Example |
|---|---|---|
| `yaw` | turns it around its up axis, in degrees | `180` faces it the other way; `90` a quarter turn |
| `scale` | its size, in percent | `50` is half as big, `200` twice |
| `speed` | how fast it animates, in percent (25 to 400) | `50` is slow motion |
| `tint` | a colour it is multiplied by; white changes nothing | `"#8080FF"` is bluer, `[255, 200, 200]` pinker |

These are read when the game starts too; restart to see a change. Keep
`scale` modest: the battle camera frames the template's size, so a big
model can leave the picture.

## When something is wrong

| What you see | What to do |
|---|---|
| The model faces the wrong way | `"yaw": 180` in the entry, or `--yaw 180` when making it |
| Too big or too small | `"scale"` in the entry, or `--height` when making it |
| Parts are missing, or you can see through it | run `model_import.py` without `--keep-hidden`; make sure the model's faces point outwards (Blender: Mesh > Normals > Recalculate Outside) |
| The texture is on the wrong parts | the wrong PNG was given to `--texture`; use the colour one |
| Blocky textures at Internal 4x | add the `"hd"` line, and keep `pot-hd.png` in the mod |
| The Mods window says the file is not a model record | copy `pot.bin` again; the file must be exactly 565,248 bytes |
| `model_import.py` says too many triangles | run step 3 again with a smaller number |
| Nothing changed | restart the game; check the mod is on and the card name is spelled as the game spells it |

Some things a model of your own does not bring: its own animations and
facial expressions (it moves the template's way), and its own attack (it
attacks the template's way).
