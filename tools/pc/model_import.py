#!/usr/bin/env python3
"""A new 3D model for a card, from a mesh of your own (notes/model-replacement.md).

    model_import.py MODEL.obj OUT.bin --template CARD [--texture PNG]
                    [--disc game/rpg-yfm.bin] [--yaw DEG] [--height PERCENT]
                    [--preview PNG]

MODEL.obj is a triangle mesh with UVs (and normals, else they are made),
its textures named by the .mtl beside it (map_Kd) or given with --texture.
A PS1 model is small: keep it near a thousand triangles (tools/pc/
model_prepare.py decimates a big FBX or glTF with Blender) and its
textures are cut to 8-bit, 256 colours a page.

The record keeps the template card's skeleton, animations, battle moves,
voices and sounds, and replaces its geometry and textures with the mesh's:

- the mesh is turned to the game's axes (y down; the OBJ's front, +Z,
  turned to where a disc model's front is), scaled to the template's height
  and stood where the template stands;
- each vertex is bound to the template bone whose own vertices are
  nearest, then to the bone most of its mesh neighbours have, and the
  whole mesh is written as shared-vertex HMD polygons
  over those bones, so it bends with the template's animations the way the
  template's skin does, without cracks;
- the textures' UV islands are packed onto three 128x256 texture pages of
  8-bit texels (a 256-colour palette each), each with texels in proportion
  to the surface it covers, and written again at 4x beside the record
  (OUT-hd.png), which an entry's "hd" draws at an internal resolution above
  the console's.

--preview draws the result the way the record will be read, before any game
does, which is a check of the conversion itself.
"""
from __future__ import annotations

import argparse
import math
import struct
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import model_record  # noqa: E402

SECTOR = 2048
MODEL_DATA_BYTES = 96 * SECTOR
# The largest model data on the disc; what follows it in the slot's arena
# is the game's (field_DE0, where the animation keeps its saved poses).
MODEL_DATA_BUDGET = 189_152
# A Gouraud-textured triangle is a 40-byte GPU packet. A frame's packet
# buffer is 140,000 bytes for the arena, both duellists and the effects; the
# battle with two disc models takes about 55,000. The disc's models reach
# 1764 triangles (the median is 828), so 1500 is one the game already meets;
# past the buffer the port leaves a mod's model out of a frame rather than
# overflow it (func_800540B4).
TRIANGLES_BUDGET = 1500
HD_SCALE = 4                        # the "hd" image: each page at 4x, 512x1024
TEXTURE_PHASE = 96 * SECTOR
PALETTE_PHASE = TEXTURE_PHASE + 48 * SECTOR
PAGE_W, PAGE_H = 128, 256          # one 8-bit texture page, in texels
PAGES = 3
TPAGE_FIRST = 0x9A                  # page 0, 8-bit, y 256, as the disc's models write it
CLUT_FIRST = 0x28                   # palette row 0; each row is 0x40 more
SHARED_TRIANGLE = 0x0100000D        # shared-vertex, Gouraud, textured triangle
SHARED_PREPASS = 0x01000000         # shared-vertex projection of one bone's vertices
MAP_COORDINATES = 0x00800000        # on the first primitive: map the coordinate section
UNMAPPED = 0x80000000


def words(data: bytes) -> np.ndarray:
    return np.frombuffer(data[:len(data) // 4 * 4], dtype="<u4")


class Hmd:
    """The model data of a record: an HMD whose id word holds its size."""

    def __init__(self, data: bytes):
        self.data = bytes(data)
        w = self.w = words(self.data)
        self.size, _, self.header_section, self.block_count = (int(x) for x in w[:4])
        at = self.header_section
        count = int(w[at])
        at += 1
        self.headers: list[tuple[int, list[int]]] = []
        for _ in range(count):
            entries = int(w[at])
            self.headers.append((at, [int(x) for x in w[at + 1:at + 1 + entries]]))
            at += 1 + entries
        self.blocks = [int(x) for x in w[4:4 + self.block_count]]
        self.coordinates = None
        for block in range(self.block_count):
            for element in self.chain(block):
                if any(p["type"] & MAP_COORDINATES for p in element["prims"]):
                    self.coordinates = self.header(element["header"])[-1] & 0x7FFFFFFF
                    break
            if self.coordinates is not None:
                break
        if self.coordinates is None:
            raise SystemExit("the template has no coordinate section")
        self.units = []
        c = self.coordinates
        for i in range(int(w[c])):
            base = (c + 1 + i * 20) * 4
            m = np.array(struct.unpack_from("<9h", self.data, base + 4), float).reshape(3, 3) / 4096
            t = np.array(struct.unpack_from("<3i", self.data, base + 24), float)
            parent = struct.unpack_from("<I", self.data, base + 76)[0]
            self.units.append((m, t, (parent - (c + 1)) // 20 if parent else -1))

    def header(self, at: int) -> list[int]:
        for position, entries in self.headers:
            if position == at:
                return entries
        raise SystemExit(f"no primitive header at word {at}")

    def chain(self, block: int) -> list[dict]:
        out, p, w = [], self.blocks[block], self.w
        while p:
            following, header, count = int(w[p]), int(w[p + 1]), int(w[p + 2])
            c, prims = p + 3, []
            for _ in range(count & 0xFFFF):
                size = int(w[c + 1]) & 0xFFFF
                prims.append({"type": int(w[c]), "count": (int(w[c + 1]) >> 16) & 0x7FFF,
                              "args": [int(x) for x in w[c + 2:c + 1 + size]]})
                c += 1 + size
            out.append({"at": p, "header": header, "prims": prims})
            if following == 0xFFFFFFFF:
                break
            p = following & 0x7FFFFFFF
        return out

    def world(self) -> list[np.ndarray]:
        done: dict[int, np.ndarray] = {}

        def get(i: int) -> np.ndarray:
            if i not in done:
                m, t, parent = self.units[i]
                matrix = np.eye(4)
                matrix[:3, :3], matrix[:3, 3] = m, t
                done[i] = get(parent) @ matrix if parent >= 0 else matrix
            return done[i]
        return [get(i) for i in range(len(self.units))]

    def section(self, pointer: int) -> int:
        return (pointer & 0x7FFFFFFF) * 4

    def vector(self, pointer: int, index: int) -> np.ndarray:
        return np.array(struct.unpack_from("<3h", self.data, self.section(pointer) + index * 8), float)

    def bone_points(self) -> list[tuple[int, np.ndarray]]:
        """Every vertex the template draws, in world space, with its bone:
        the ordinary polygons' vertices and the shared-vertex runs."""
        world, out = self.world(), []
        for block in range(1, self.block_count - 1):
            unit = block - 1
            for element in self.chain(block):
                sections = self.header(element["header"])
                for prim in element["prims"]:
                    kind = prim["type"]
                    if kind >> 24 == 1 and kind & 0xFFFF == 0 and prim["args"]:
                        count, first = prim["args"][0], prim["args"][1]
                        for i in range(count):
                            out.append((unit, (world[unit] @ np.r_[self.vector(sections[1], first + i), 1])[:3]))
                    elif kind >> 24 == 0 and kind & 0xFFFF in (0x9, 0xD, 0x11, 0x15):
                        low = kind & 0xFFFF
                        quad, gouraud = low in (0x11, 0x15), low in (0xD, 0x15)
                        stride = {0x9: 0x14, 0xD: 0x18, 0x11: 0x18, 0x15: 0x1C}[low]
                        start = self.section(sections[0]) + prim["args"][0] * 4
                        for n in range(prim["count"]):
                            half = struct.unpack_from("<%dH" % (stride // 2), self.data, start + n * stride)
                            corners = 4 if quad else 3
                            vertices = ([half[7 + i * 2] for i in range(corners)] if gouraud
                                        else [half[(8 if quad else 7) + i] for i in range(corners)])
                            for v in vertices:
                                out.append((unit, (world[unit] @ np.r_[self.vector(sections[1], v), 1])[:3]))
        return out

    def shared_winding(self) -> int:
        """+1 when the template's shared triangles run v0, v1, v2 anticlockwise
        about their normal, -1 when clockwise: the order a new one keeps."""
        votes = 0
        # The runs' world positions are only known through their bones; the
        # ordinary polygons, which also cull, are enough to decide.
        world = self.world()
        for block in range(1, self.block_count - 1):
            unit = block - 1
            for element in self.chain(block):
                sections = self.header(element["header"])
                for prim in element["prims"]:
                    if prim["type"] >> 24 != 0 or prim["type"] & 0xFFFF != 0xD:
                        continue
                    start = self.section(sections[0]) + prim["args"][0] * 4
                    for n in range(prim["count"]):
                        half = struct.unpack_from("<12H", self.data, start + n * 0x18)
                        p = [world[unit][:3, :3] @ self.vector(sections[1], half[7 + i * 2]) for i in range(3)]
                        normal = sum(world[unit][:3, :3] @ self.vector(sections[2], half[6 + i * 2]) for i in range(3))
                        votes += 1 if np.dot(np.cross(p[1] - p[0], p[2] - p[0]), normal) > 0 else -1
        return 1 if votes >= 0 else -1


# --- the mesh -----------------------------------------------------------------

def read_obj(path: Path, texture: Path | None):
    positions, uvs, normals, triangles = [], [], [], []
    material, materials, textures = None, {}, {}
    folder = path.parent
    for line in path.read_text(errors="replace").splitlines():
        part = line.split()
        if not part:
            continue
        if part[0] == "v":
            positions.append([float(x) for x in part[1:4]])
        elif part[0] == "vt":
            uvs.append([float(part[1]), float(part[2]) if len(part) > 2 else 0.0])
        elif part[0] == "vn":
            normals.append([float(x) for x in part[1:4]])
        elif part[0] == "usemtl":
            material = " ".join(part[1:])
        elif part[0] == "mtllib":
            library = folder / " ".join(part[1:])
            if library.exists():
                current = None
                for entry in library.read_text(errors="replace").splitlines():
                    bits = entry.split()
                    if not bits:
                        continue
                    if bits[0] == "newmtl":
                        current = " ".join(bits[1:])
                    elif bits[0] == "map_Kd" and current:
                        materials[current] = folder / bits[-1]
        elif part[0] == "f":
            corners = []
            for corner in part[1:]:
                index = (corner.split("/") + ["", ""])[:3]
                corners.append(tuple(int(x) - 1 if x else -1 for x in index))
            for i in range(1, len(corners) - 1):
                triangles.append((corners[0], corners[i], corners[i + 1], material))
    if not triangles:
        raise SystemExit(f"{path}: no faces")
    for _, _, _, name in triangles:
        source = texture or materials.get(name)
        if source is None:
            raise SystemExit(f"{path}: material {name} names no texture; give one with --texture")
        textures.setdefault(str(source), None)
    return np.array(positions, float), np.array(uvs, float), np.array(normals, float), triangles, materials


# --- the textures ---------------------------------------------------------------

def atlas(images: dict[str, Image.Image], triangles: list[dict], hd_scale: int = HD_SCALE):
    """Pack the textures' UV islands onto the three 8-bit pages.

    An island (triangles joined by shared UVs) gets texels in proportion to
    the surface it covers on the model, so a face that is a small corner of
    its texture but a large part of the model is not starved by the parts
    that fill the texture; unused parts of a texture take no room at all.
    Islands are packed in shelves with a margin round each (so filtering
    never reads a neighbour), never across a page, and as large as the
    three pages allow. Returns, per triangle, its page and its texel
    coordinates, and the page images at 1x and at `hd_scale`."""
    count = len(triangles)
    parent = list(range(count))

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    owner = {}
    for index, triangle in enumerate(triangles):
        for uv_id in triangle["uv_ids"]:
            key = (triangle["image"], uv_id)
            if key in owner:
                a, b = root(owner[key]), root(index)
                if a != b:
                    parent[a] = b
            else:
                owner[key] = index
    islands: dict[int, list[int]] = {}
    for index in range(count):
        islands.setdefault(root(index), []).append(index)

    pad = 2
    boxes = []
    for members in islands.values():
        image = images[triangles[members[0]]["image"]]
        uv = np.concatenate([triangles[m]["uv"] for m in members])
        shift = np.floor(uv.min(0) + 1e-9)            # a tiling island, into [0, 1]
        x = (uv[:, 0] - shift[0]) * image.width
        y = (1 - (uv[:, 1] - shift[1])) * image.height
        x0, x1 = max(0.0, x.min()), min(float(image.width), x.max())
        y0, y1 = max(0.0, y.min()), min(float(image.height), y.max())
        width, height = max(x1 - x0, 1.0), max(y1 - y0, 1.0)
        area = sum(triangles[m]["area"] for m in members) or 1e-9
        # Texels a unit of the model's surface: its triangles' own area in the
        # texture, not the island's box, which can be mostly other things.
        corners = np.stack([x, y], 1).reshape(-1, 3, 2)
        e1, e2 = corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0]
        drawn = float(np.abs(e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]).sum()) / 2
        boxes.append({"members": members, "image": image, "shift": shift, "x0": x0, "y0": y0,
                      "w": width, "h": height, "density": math.sqrt(area / max(drawn, 1.0))})

    def pack(scale):
        """Shelves on three pages at `scale` texels per unit of density; None
        when they do not fit."""
        sized = []
        for box in boxes:
            k = scale * box["density"]
            k = min(k, (PAGE_W - 2 * pad) / box["w"], (PAGE_H - 2 * pad) / box["h"])
            sized.append((box, k, math.ceil(box["w"] * k) + 2 * pad, math.ceil(box["h"] * k) + 2 * pad))
        sized.sort(key=lambda item: -item[3])
        places, page, x, y, shelf = [], 0, 0, 0, 0
        for box, k, w, h in sized:
            if x + w > PAGE_W:
                x, y, shelf = 0, y + shelf, 0
            if y + h > PAGE_H:
                page, x, y, shelf = page + 1, 0, 0, 0
                if page == PAGES:
                    return None
            places.append((box, k, page, x, y, w, h))
            x += w
            shelf = max(shelf, h)
        return places

    low, high = 0.0, 1.0
    while pack(high) is not None and high < 1e9:
        low, high = high, high * 2
    for _ in range(40):
        middle = (low + high) / 2
        if pack(middle) is not None:
            low = middle
        else:
            high = middle
    places = pack(low)
    if places is None:
        raise SystemExit("the textures' islands do not fit on three pages")

    backgrounds = [Image.new("RGBA", (PAGE_W, PAGE_H), (0, 0, 0, 255)) for _ in range(PAGES)]
    hd_pages = [Image.new("RGBA", (PAGE_W * hd_scale, PAGE_H * hd_scale), (0, 0, 0, 255)) for _ in range(PAGES)]
    placed = [None] * count
    for box, k, page, px, py, w, h in places:
        image = box["image"]
        # The island's crop with the margin's worth of the texture round it.
        margin = pad / k
        crop = (box["x0"] - margin, box["y0"] - margin, box["x0"] + box["w"] + margin, box["y0"] + box["h"] + margin)
        piece = image.transform((w, h), Image.EXTENT, crop, Image.BILINEAR)
        backgrounds[page].paste(piece, (px, py))
        big = image.transform((w * hd_scale, h * hd_scale), Image.EXTENT, crop, Image.BICUBIC)
        hd_pages[page].paste(big, (px * hd_scale, py * hd_scale))
        for m in box["members"]:
            uv = triangles[m]["uv"]
            x = (uv[:, 0] - box["shift"][0]) * image.width
            y = (1 - (uv[:, 1] - box["shift"][1])) * image.height
            tu = np.clip(px + pad + (x - box["x0"]) * k, px, px + w - 1)
            tv = np.clip(py + pad + (y - box["y0"]) * k, py, py + h - 1)
            placed[m] = (page, np.stack([np.clip(tu, 0, PAGE_W - 1), np.clip(tv, 0, PAGE_H - 1)], 1))
    return placed, backgrounds, hd_pages


def colour15(rgb) -> int:
    r, g, b = (int(c) * 31 // 255 for c in rgb[:3])
    word = b << 10 | g << 5 | r
    return word or 0x0421      # 0x0000 is the transparent colour


def quantise(page_images):
    """Each page to 256 colours: (texel indices, 15-bit palette) per page."""
    out = []
    for image in page_images:
        rgb = image.convert("RGB")
        indexed = rgb.quantize(colors=256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
        palette = indexed.getpalette()[:256 * 3]
        palette += [0] * (256 * 3 - len(palette))
        words15 = [colour15(palette[i * 3:i * 3 + 3]) for i in range(256)]
        out.append((np.array(indexed, np.uint8), words15))
    return out


# --- cleaning the mesh ------------------------------------------------------------

def fibonacci_directions(count: int) -> np.ndarray:
    i = np.arange(count) + 0.5
    polar = np.arccos(1 - 2 * i / count)
    turn = math.pi * (1 + 5 ** 0.5) * i
    return np.stack([np.cos(turn) * np.sin(polar), np.cos(polar), np.sin(turn) * np.sin(polar)], 1)


def seen_from_outside(points: np.ndarray, faces: np.ndarray, views: int = 96, size: int = 224) -> np.ndarray:
    """Which faces (anticlockwise seen from outside) show their front from
    some direction around the model. Faces nobody outside sees -- the
    inside of a mouth or a neck -- would be depth-sorted over the body on
    the console, which has no depth buffer, and cost triangles."""
    seen = np.zeros(len(faces), bool)
    centre = (points.min(0) + points.max(0)) / 2
    radius = np.linalg.norm(points - centre, axis=1).max() or 1
    corners = points[faces] - centre                               # (F, 3, 3)
    face_normals = np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0])
    for direction in fibonacci_directions(views):
        forward = -direction                                        # the camera looks along this
        up = np.array([0.0, 1.0, 0.0]) if abs(forward[1]) < 0.9 else np.array([1.0, 0.0, 0.0])
        right = np.cross(up, forward)
        right /= np.linalg.norm(right)
        up = np.cross(forward, right)
        xs = (corners @ right / radius * 0.5 + 0.5) * (size - 1)
        ys = (corners @ up / radius * 0.5 + 0.5) * (size - 1)
        zs = corners @ forward
        front = face_normals @ direction > 0
        depth = np.full((size, size), np.inf)
        owner = np.full((size, size), -1)
        for f in range(len(faces)):
            x, y, z = xs[f], ys[f], zs[f]
            x0, x1 = int(max(0, x.min())), int(min(size - 1, x.max())) + 1
            y0, y1 = int(max(0, y.min())), int(min(size - 1, y.max())) + 1
            if x1 <= x0 or y1 <= y0:
                continue
            gx, gy = np.meshgrid(np.arange(x0, x1) + 0.5, np.arange(y0, y1) + 0.5)
            d = (x[1] - x[0]) * (y[2] - y[0]) - (x[2] - x[0]) * (y[1] - y[0])
            if abs(d) < 1e-12:
                continue
            w1 = ((gx - x[0]) * (y[2] - y[0]) - (x[2] - x[0]) * (gy - y[0])) / d
            w2 = ((x[1] - x[0]) * (gy - y[0]) - (gx - x[0]) * (y[1] - y[0])) / d
            w0 = 1 - w1 - w2
            inside = (w0 >= -1e-6) & (w1 >= -1e-6) & (w2 >= -1e-6)
            if not inside.any():
                continue
            zz = w0 * z[0] + w1 * z[1] + w2 * z[2]
            region = depth[y0:y1, x0:x1]
            nearer = inside & (zz < region)
            region[nearer] = zz[nearer]
            owner[y0:y1, x0:x1][nearer] = f
        visible = np.unique(owner[owner >= 0])
        seen[visible[front[visible]]] = True
    return seen


def weld_normals(positions: np.ndarray, normals: np.ndarray, triangles) -> np.ndarray:
    """One normal where a UV seam split a vertex: the copies' normals are
    averaged when they lean the same way (a real crease keeps both), so
    the lighting has no line along the seam."""
    extent = float(np.ptp(positions, axis=0).max()) or 1.0
    groups: dict[tuple, set[int]] = {}
    for a, b, c, _ in triangles:
        for v, _, n in (a, b, c):
            if n >= 0:
                groups.setdefault(tuple(np.round(positions[v] / extent * 20000).astype(int)), set()).add(n)
    out = normals.copy()
    for members in groups.values():
        if len(members) < 2:
            continue
        indices = list(members)
        vectors = normals[indices]
        vectors = vectors / (np.linalg.norm(vectors, axis=1, keepdims=True) + 1e-12)
        mean = vectors.sum(0)
        mean /= np.linalg.norm(mean) or 1
        for index, vector in zip(indices, vectors):
            if vector @ mean > 0.5:
                out[index] = mean
    return out


def smooth_binding(binding: np.ndarray, triangles, count: int, rounds: int = 4) -> np.ndarray:
    """Each vertex takes the bone most of its mesh neighbours have, when more
    of them have it than have its own. The nearest template vertex is often
    another bone's near a joint; a lone vertex bound to a bone its
    neighbours are not stretches a spike across the model when that bone
    moves. Measured on the disc's own models (each exported and bound
    again), this halves the vertices bound to the wrong bone or better."""
    neighbours = [set() for _ in range(count)]
    for a, b, c, _ in triangles:
        a, b, c = a[0], b[0], c[0]
        neighbours[a] |= {b, c}
        neighbours[b] |= {a, c}
        neighbours[c] |= {a, b}
    for _ in range(rounds):
        changed = binding.copy()
        for vertex in range(count):
            if not neighbours[vertex]:
                continue
            votes: dict[int, int] = {int(binding[vertex]): 1}
            for other in neighbours[vertex]:
                votes[int(binding[other])] = votes.get(int(binding[other]), 0) + 1
            bone, most = max(votes.items(), key=lambda item: (item[1], item[0] == binding[vertex]))
            if most > votes[int(binding[vertex])]:
                changed[vertex] = bone
        if (changed == binding).all():
            break
        binding = changed
    return binding


# --- the conversion -------------------------------------------------------------

def convert(obj: Path, template_record: bytes, texture: Path | None, yaw: float, height: float,
            keep_hidden: bool = False):
    positions, uvs, normals, triangles, materials = read_obj(obj, texture)
    if keep_hidden is False:
        faces = np.array([[a[0], b[0], c[0]] for a, b, c, _ in triangles])
        seen = seen_from_outside(positions, faces)
        dropped = len(triangles) - int(seen.sum())
        triangles = [t for t, keep in zip(triangles, seen) if keep]
        if dropped:
            print(f"{obj}: {dropped} triangles nobody outside the model sees left out")
    if len(triangles) > TRIANGLES_BUDGET:
        raise SystemExit(f"{len(triangles)} triangles; keep a model to {TRIANGLES_BUDGET} "
                         "(tools/pc/model_prepare.py decimates)")
    if len(normals):
        normals = weld_normals(positions, normals, triangles)
    hmd = Hmd(template_record[:MODEL_DATA_BYTES])
    world = hmd.world()
    bones = hmd.bone_points()
    if not bones:
        raise SystemExit("the template draws nothing to stand the model on")
    bone_of = np.array([b for b, _ in bones])
    bone_at = np.array([p for _, p in bones])

    # The game's axes: y down, and the OBJ's front (+Z, as Blender exports its
    # -Y front and glTF faces) turned the way a disc model faces, which is
    # -z: a half turn about the x axis, which keeps the mesh from being
    # mirrored.
    turn = math.radians(yaw)
    rotation = np.array([[math.cos(turn), 0, math.sin(turn)], [0, 1, 0], [-math.sin(turn), 0, math.cos(turn)]])
    flip = np.diag([1.0, -1.0, -1.0])
    game = positions @ rotation.T @ flip.T
    game_normals = (normals @ rotation.T @ flip.T) if len(normals) else normals
    low, high = bone_at.min(0), bone_at.max(0)
    mesh_low, mesh_high = game.min(0), game.max(0)
    scale = (high[1] - low[1]) / max(mesh_high[1] - mesh_low[1], 1e-9) * height / 100
    centre = np.array([(low[0] + high[0]) / 2, 0, (low[2] + high[2]) / 2])
    mesh_centre = np.array([(mesh_low[0] + mesh_high[0]) / 2, 0, (mesh_low[2] + mesh_high[2]) / 2])
    game = (game - mesh_centre) * scale + centre
    game[:, 1] += high[1] - game[:, 1].max()           # the feet where the template's are

    # Smooth normals where the OBJ has none.
    if not len(game_normals):
        game_normals = np.zeros_like(game)
        for a, b, c, _ in triangles:
            n = np.cross(game[b[0]] - game[a[0]], game[c[0]] - game[a[0]])
            for corner in (a, b, c):
                game_normals[corner[0]] += n
        triangles = [((a[0], a[1], a[0]), (b[0], b[1], b[0]), (c[0], c[1], c[0]), m) for a, b, c, m in triangles]

    # Bind each vertex to the bone of the nearest template vertex.
    binding = np.empty(len(game), int)
    for start in range(0, len(game), 256):
        chunk = game[start:start + 256]
        distance = ((chunk[:, None, :] - bone_at[None, :, :]) ** 2).sum(2)
        binding[start:start + 256] = bone_of[distance.argmin(1)]
    binding = smooth_binding(binding, triangles, len(game))

    # Vertices and normals, each run grouped by bone, each in its bone's space.
    vertex_keys: dict[int, dict[int, None]] = {}
    normal_keys: dict[int, dict[tuple[int, int], None]] = {}
    for a, b, c, _ in triangles:
        for corner in (a, b, c):
            bone = int(binding[corner[0]])
            vertex_keys.setdefault(bone, {})[corner[0]] = None
            normal_keys.setdefault(bone, {})[(corner[0], corner[2])] = None
    vertex_index, normal_index, runs = {}, {}, []
    vertex_data, normal_data = bytearray(), bytearray()
    for bone in sorted(vertex_keys):
        inverse = np.linalg.inv(world[bone])
        first_vertex, first_normal = len(vertex_index), len(normal_index)
        for v in vertex_keys[bone]:
            vertex_index[v] = len(vertex_index)
            x, y, z = np.round((inverse @ np.r_[game[v], 1])[:3]).astype(int)
            vertex_data += struct.pack("<4h", *(int(np.clip(k, -32768, 32767)) for k in (x, y, z)), 0)
        for key in normal_keys[bone]:
            normal_index[key] = len(normal_index)
            n = inverse[:3, :3] @ (game_normals[key[1]] if key[1] >= 0 else np.array([0, -1.0, 0]))
            n = n / (np.linalg.norm(n) or 1)
            normal_data += struct.pack("<4h", *(int(round(k * 4096)) for k in n), 0)
        runs.append((bone, first_vertex, len(vertex_keys[bone]), first_normal, len(normal_keys[bone])))

    # Textures.
    image_of, sources = {}, {}
    for _, _, _, name in triangles:
        path = texture or materials[name]
        sources.setdefault(str(path), Image.open(path).convert("RGBA"))
        image_of[name] = str(path)
    if len({image_of[m] for _, _, _, m in triangles}) > PAGES * 4:
        raise SystemExit("too many textures for one model")
    atlas_triangles = []
    for a, b, c, m in triangles:
        corners = [a, b, c]
        atlas_triangles.append({
            "image": image_of[m],
            "uv": np.array([uvs[k[1]] for k in corners]) if a[1] >= 0 else np.zeros((3, 2)),
            "uv_ids": [k[1] if k[1] >= 0 else -1 - k[0] for k in corners],
            "area": float(np.linalg.norm(np.cross(game[b[0]] - game[a[0]], game[c[0]] - game[a[0]]))) / 2,
        })
    placed, page_images, hd_images = atlas(sources, atlas_triangles)
    pages = quantise(page_images)

    # An OBJ's faces run anticlockwise seen from outside, and the turn to the
    # game's axes is a rotation, so they still do; the template says which
    # way round the game culls. One order for the whole mesh: a face's own
    # smoothed normals can point across a sharp edge, and a face turned by
    # them would be culled from outside (a hole).
    keep = hmd.shared_winding() > 0
    polygon_data = bytearray()
    for (a, b, c, _), (page, texel) in zip(triangles, placed):
        order = [a, b, c]
        tex = [texel[0], texel[1], texel[2]]
        if not keep:
            order = [a, c, b]
            tex = [texel[0], texel[2], texel[1]]
        uv = [int(t[0]) | int(t[1]) << 8 for t in tex]
        record = [uv[0], CLUT_FIRST + 0x40 * page, uv[1], TPAGE_FIRST + page, uv[2], 0]
        for corner in order:
            record += [normal_index[(corner[0], corner[2])], vertex_index[corner[0]]]
        polygon_data += struct.pack("<12H", *record)

    hd = Image.new("RGBA", (hd_images[0].width * PAGES, hd_images[0].height))
    for page, image in enumerate(hd_images):
        hd.paste(image, (page * image.width, 0))
    return build_hmd(hmd, runs, vertex_data, normal_data, polygon_data, len(triangles)), pages, hd


def compact(hmd: Hmd) -> tuple[bytearray, dict, list[int]]:
    """The template's model data without its geometry.

    What the new model keeps of the template -- the header words, the
    coordinates, the primitive headers, the animation block's chain and its
    sections -- is copied in order, and what only the old geometry used (its
    vertex, normal and polygon sections and its blocks' chains) is left
    out, so a large template (Blue-Eyes' is 124 KB) leaves room for the new
    geometry. Every word offset that names something kept is moved with it:
    the header section's place, the block pointers, the chains' next and
    header words, the primitive headers' section entries and the
    coordinates' parents. A section entry past the model data (the battle
    modules' areas of the slot's arena) is left as it is.

    Returns the data, the old-to-new offset map as a function, and the old
    offsets of the kept primitive headers."""
    w = hmd.w
    size = hmd.size // 4

    def masked(value: int) -> int:
        return value & 0x7FFFFFFF

    # Every thing with a start: ranges run from one start to the next.
    kept_sections = {hmd.coordinates}
    for element in hmd.chain(0):
        kept_sections.update(masked(e) for e in hmd.header(element["header"]) if e & UNMAPPED)
    all_sections = {masked(e) for _, entries in hmd.headers for e in entries if e & UNMAPPED}
    chains_kept = {e["at"] for e in hmd.chain(0)}
    chains_all = {e["at"] for b in range(hmd.block_count) for e in hmd.chain(b)}
    header_words = hmd.header_section
    header_end = header_words + 1 + sum(1 + len(entries) for _, entries in hmd.headers)
    starts = sorted({s for s in all_sections | chains_all | {header_words, 4 + hmd.block_count} if s < size})
    live = [(0, starts[0])]                 # the header words and the block pointers
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else size
        if start == header_words:
            end = max(end, header_end)
        keep = (start in kept_sections or start in chains_kept or start == header_words or
                (start not in all_sections and start not in chains_all))
        if keep:
            live.append((start, end))
    # Merge and build the map.
    live.sort()
    merged = []
    for start, end in live:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    out = bytearray()
    places = []
    for start, end in merged:
        places.append((start, end, len(out) // 4))
        out += hmd.data[start * 4:end * 4]

    def moved(old: int, dead_ok: bool = False) -> int:
        if old >= size:
            return old
        for start, end, new in places:
            if start <= old < end:
                return new + old - start
        if dead_ok:
            return 0   # a section of the old geometry: named by nothing that is drawn
        raise SystemExit(f"model data word {old} is used but was left out")

    def put_word(at_old: int, value: int) -> None:
        struct.pack_into("<I", out, moved(at_old) * 4, value)

    put_word(2, moved(header_words))
    for block in range(hmd.block_count):
        if block == 0 and hmd.blocks[0]:
            put_word(4 + block, moved(hmd.blocks[0]))
        else:
            put_word(4 + block, 0)
    for element in hmd.chain(0):
        following = int(w[element["at"]])
        if following != 0xFFFFFFFF:
            put_word(element["at"], (following & UNMAPPED) | moved(following & 0x7FFFFFFF))
        header = int(w[element["at"] + 1])
        put_word(element["at"] + 1, moved(header))
    for position, entries in hmd.headers:
        for index, entry in enumerate(entries):
            if entry & UNMAPPED:
                put_word(position + 1 + index, UNMAPPED | moved(masked(entry), True))
    c = hmd.coordinates
    for unit in range(int(w[c])):
        at = c + 1 + unit * 20 + 19
        parent = int(w[at])
        if parent:
            put_word(at, moved(parent))
    return out, moved, [position for position, _ in hmd.headers]


def build_hmd(hmd: Hmd, runs, vertex_data: bytes, normal_data: bytes, polygon_data: bytes, triangles: int) -> bytes:
    """The template's model data without its geometry (compact), then the new
    sections, a new primitive header section (the template's headers and
    one for the new geometry) and new block chains for every bone."""
    out, moved, header_positions = compact(hmd)

    def here() -> int:
        return len(out) // 4

    def put(data: bytes) -> int:
        at = here()
        out.extend(data)
        while len(out) % 4:
            out.extend(b"\0")
        return at

    polygons = put(polygon_data)
    vertices = put(vertex_data)
    vertex_results = put(bytes(len(vertex_data)))
    normals = put(normal_data)
    normal_results = put(bytes(len(normal_data)))

    # The primitive headers again, the template's (with their sections moved)
    # and one for the new geometry, whose last section is the coordinate
    # section it maps.
    section = here()
    new_header = {}
    out += struct.pack("<I", len(hmd.headers) + 1)
    for position, entries in hmd.headers:
        new_header[position] = here()
        out += struct.pack("<I", len(entries))
        for entry in entries:
            out += struct.pack("<I", UNMAPPED | moved(entry & 0x7FFFFFFF, True) if entry & UNMAPPED else entry)
    shared = here()
    out += struct.pack("<7I", 6, polygons | UNMAPPED, vertices | UNMAPPED, vertex_results | UNMAPPED,
                       normals | UNMAPPED, normal_results | UNMAPPED, moved(hmd.coordinates) | UNMAPPED)
    struct.pack_into("<I", out, 8, section)

    # The animation block (0) points at its headers' new copies; each bone
    # gets its projection run, and the last block the triangles.
    for element in hmd.chain(0):
        struct.pack_into("<I", out, moved(element["at"]) * 4 + 4, new_header[element["header"]])
    first = True
    by_bone = {bone: (fv, vc, fn, nc) for bone, fv, vc, fn, nc in runs}
    for block in range(1, hmd.block_count - 1):
        bone = block - 1
        if bone not in by_bone and not first:
            struct.pack_into("<I", out, 16 + block * 4, 0)
            continue
        fv, vc, fn, nc = by_bone.get(bone, (0, 0, 0, 0))
        kind = SHARED_PREPASS | (MAP_COORDINATES if first else 0)
        first = False
        chain = put(struct.pack("<3I", 0xFFFFFFFF, shared, UNMAPPED | 1) +
                    struct.pack("<8I", kind, UNMAPPED | 7, vc, fv, fv, nc, fn, fn))
        struct.pack_into("<I", out, 16 + block * 4, chain)
    prims = b""
    count = 0
    for at in range(0, triangles, 0x7FFF):
        n = min(0x7FFF, triangles - at)
        prims += struct.pack("<3I", SHARED_TRIANGLE, UNMAPPED | n << 16 | 2, at * 6)
        count += 1
    last = put(struct.pack("<3I", 0xFFFFFFFF, shared, UNMAPPED | count) + prims)
    struct.pack_into("<I", out, 16 + (hmd.block_count - 1) * 4, last)
    struct.pack_into("<I", out, 0, len(out))
    if len(out) > MODEL_DATA_BUDGET:
        raise SystemExit(f"{len(out)} bytes of model data; the budget is {MODEL_DATA_BUDGET} "
                         "(fewer triangles, or a smaller template)")
    return bytes(out)


def write_record(template: bytes, model_data: bytes, pages) -> bytes:
    record = bytearray(template)
    record[:MODEL_DATA_BYTES] = model_data + bytes(MODEL_DATA_BYTES - len(model_data))
    for page, (texels, _) in enumerate(pages):
        for strip in range(16):
            at = TEXTURE_PHASE + (page * 16 + strip) * SECTOR
            record[at:at + SECTOR] = texels[strip * 16:strip * 16 + 16].tobytes()
    palettes = bytearray(2 * SECTOR)
    for row, (_, colours) in enumerate(pages):
        struct.pack_into("<256H", palettes, row * 512, *colours)
    record[PALETTE_PHASE:PALETTE_PHASE + 2 * SECTOR] = palettes
    return bytes(record)


def preview(path: Path, record: bytes, size: int = 480) -> None:
    """Draw the record's shared triangles in their bones' rest pose, from
    the front and from the side, straight from the bytes written."""
    hmd = Hmd(record[:MODEL_DATA_BYTES])
    world = hmd.world()
    element = hmd.chain(hmd.block_count - 1)[0]
    sections = hmd.header(element["header"])
    owner = {}
    for block in range(1, hmd.block_count - 1):
        for chain in hmd.chain(block):
            for prim in chain["prims"]:
                if prim["type"] >> 24 == 1 and prim["type"] & 0xFFFF == 0:
                    count, first = prim["args"][0], prim["args"][1]
                    for i in range(count):
                        owner[first + i] = block - 1
    textures = {}
    for page in range(PAGES):
        texels = np.zeros((PAGE_H, PAGE_W), np.uint8)
        for strip in range(16):
            at = TEXTURE_PHASE + (page * 16 + strip) * SECTOR
            texels[strip * 16:strip * 16 + 16] = np.frombuffer(record[at:at + SECTOR], np.uint8).reshape(16, 128)
        colours = np.frombuffer(record[PALETTE_PHASE + page * 512:PALETTE_PHASE + page * 512 + 512], "<u2")
        rgb = np.stack([(colours & 31) * 255 // 31, (colours >> 5 & 31) * 255 // 31, (colours >> 10 & 31) * 255 // 31], 1)
        textures[page] = rgb.astype(np.uint8)[texels]
    tris = []
    start = hmd.section(sections[0])
    for prim in element["prims"]:
        for n in range(prim["count"]):
            half = struct.unpack_from("<12H", record, start + (prim["args"][0] + n) * 24)
            points = [(world[owner[half[7 + i * 2]]] @ np.r_[hmd.vector(sections[1], half[7 + i * 2]), 1])[:3]
                      for i in range(3)]
            tris.append((points, [half[0], half[2], half[4]], half[3] - TPAGE_FIRST))
    views = []
    all_points = np.array([p for t in tris for p in t[0]])
    centre = (all_points.min(0) + all_points.max(0)) / 2
    extent = (all_points.max(0) - all_points.min(0)).max()
    for yaw in (0.0, -math.pi / 2):   # from the front (-z), and from its right
        image = np.full((size, size, 3), 40, np.uint8)
        depth = np.full((size, size), 1e9)
        rotation = np.array([[math.cos(yaw), 0, math.sin(yaw)], [0, 1, 0], [-math.sin(yaw), 0, math.cos(yaw)]])
        for points, uv, page in tris:
            p = [(rotation @ (q - centre)) / extent * size * 0.85 + size / 2 for q in points]
            if (p[1][0] - p[0][0]) * (p[2][1] - p[0][1]) - (p[2][0] - p[0][0]) * (p[1][1] - p[0][1]) <= 0:
                continue   # the driver's NCLIP: drawn only when it faces the camera
            x0, x1 = int(max(0, min(q[0] for q in p))), int(min(size - 1, max(q[0] for q in p)) + 1)
            y0, y1 = int(max(0, min(q[1] for q in p))), int(min(size - 1, max(q[1] for q in p)) + 1)
            if x1 <= x0 or y1 <= y0:
                continue
            xs, ys = np.meshgrid(np.arange(x0, x1) + 0.5, np.arange(y0, y1) + 0.5)
            d = (p[1][0] - p[0][0]) * (p[2][1] - p[0][1]) - (p[2][0] - p[0][0]) * (p[1][1] - p[0][1])
            w1 = ((xs - p[0][0]) * (p[2][1] - p[0][1]) - (p[2][0] - p[0][0]) * (ys - p[0][1])) / d
            w2 = ((p[1][0] - p[0][0]) * (ys - p[0][1]) - (xs - p[0][0]) * (p[1][1] - p[0][1])) / d
            w0 = 1 - w1 - w2
            mask = (w0 >= 0) & (w1 >= 0) & (w2 >= 0)
            if not mask.any():
                continue
            z = (w0 * p[0][2] + w1 * p[1][2] + w2 * p[2][2])[mask]
            u = (w0 * (uv[0] & 255) + w1 * (uv[1] & 255) + w2 * (uv[2] & 255))[mask]
            v = (w0 * (uv[0] >> 8) + w1 * (uv[1] >> 8) + w2 * (uv[2] >> 8))[mask]
            yy, xx = np.nonzero(mask)
            keep = z < depth[yy + y0, xx + x0]
            depth[yy[keep] + y0, xx[keep] + x0] = z[keep]
            image[yy[keep] + y0, xx[keep] + x0] = textures[page][np.clip(v[keep].astype(int), 0, 255),
                                                                   np.clip(u[keep].astype(int), 0, 127)]
        views.append(Image.fromarray(image))
    sheet = Image.new("RGB", (size * 2, size))
    for i, view in enumerate(views):
        sheet.paste(view, (i * size, 0))
    sheet.save(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("model", type=Path, help="a triangle mesh (.obj) with UVs")
    parser.add_argument("out", type=Path, help="the model record to write")
    parser.add_argument("--template", type=int, required=True,
                        help="the card whose skeleton, animations, moves and voices the model takes")
    parser.add_argument("--texture", type=Path, help="one texture for every material")
    parser.add_argument("--disc", type=Path, default=Path("game/rpg-yfm.bin"))
    parser.add_argument("--yaw", type=float, default=0.0, help="degrees to turn the mesh about its up axis")
    parser.add_argument("--height", type=float, default=100.0, help="percent of the template's height")
    parser.add_argument("--preview", type=Path, help="draw the record written, front and side")
    parser.add_argument("--hd", type=Path, help="the HD textures to write (default: OUT with -hd.png)")
    parser.add_argument("--keep-hidden", action="store_true",
                        help="keep the triangles no view from outside the model shows")
    arguments = parser.parse_args()
    template = model_record.read_record(arguments.disc, arguments.template)
    model_data, pages, hd = convert(arguments.model, template, arguments.texture, arguments.yaw, arguments.height,
                                    arguments.keep_hidden)
    record = write_record(template, model_data, pages)
    arguments.out.write_bytes(record)
    print(f"{arguments.out}: {len(model_data)} bytes of model data on the skeleton of card {arguments.template}")
    hd_path = arguments.hd or arguments.out.with_name(arguments.out.stem + "-hd.png")
    hd.save(hd_path)
    print(f"{hd_path}: its textures at {HD_SCALE}x, for the entry's \"hd\"")
    if arguments.preview:
        preview(arguments.preview, record)
        print(f"{arguments.preview}: the record drawn")
    return 0


if __name__ == "__main__":
    sys.exit(main())
