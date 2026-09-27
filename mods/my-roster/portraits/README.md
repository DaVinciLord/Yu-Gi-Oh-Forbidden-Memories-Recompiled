# `portraits/` — a duelist's face

One image to a duelist, named for its id: `portraits/dark-simon.png` gives a
face to the duelist that `duelists/dark-simon.json` made.

**A duelist with no image here wears the face of the duelist it copies.**

PNG only, and **any size or shape you like**. There is nothing to configure.

---

## One file, two pictures

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

### What to give it

- **Square** is easiest, since a non-square image is cropped to its centre
  square first — the sides of a wide picture are simply thrown away. Crop it
  yourself if the framing matters.
- **Large is fine.** 512×512 or more is drawn at its own size when the internal
  resolution is high enough.
- Transparency is not kept: the portrait slot has no alpha.
- Strong, flat colour survives the 64-colour reduction better than a soft
  gradient, which can band at 1x. The full-size picture is unaffected.

---

## How the sharp one reaches the screen

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

## Naming the file

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

## Replacing a disc duelist's face

Give the replacement entry a portrait like any other:

```
duelists/heishin-remade.json    { "replace": "Heishin", ... }
portraits/heishin-remade.png
```

The disc's own duelists keep their faces unless a mod replaces them, and a
texture pack's HD portraits still apply to those, since theirs *do* come from
the disc.

---

See [`../README.md`](../README.md) for the folders as a whole and
[`../duelists/README.md`](../duelists/README.md) for the `portrait` property.
