"""Pictures of the campaign map drawn from the player's disc, for the Map tab.

The map is a 3D model: the overworld package's 134-sector block (WA sector
+6, loaded at 0x80100000) is an HMD (src/pc/sdk/libgs_unit.c reads the same
layout): a header, a primitive header section, a coordinate section and
blocks of primitives. Block 0 uploads the textures and their palettes
(GsU_02000001: image rectangle, offset; palette rectangle, offset); block 1
holds the terrain as fog-shaded textured triangles (type 0x0002000D,
func_80033DB0: twelve halfwords uv0, clut, uv1, tpage, uv2, pad, then
normal and vertex for each corner) and quads (0x00020015, func_80034830:
fourteen halfwords uv0, clut, uv1, tpage, uv2, n0, uv3, v0, n1, v1, n2, v2,
n3, v3). CampaignMap_SetLocation scales the model by 1365/4096 and turns
it by its coordinate's rotation (func_8005922C).

A place's camera is ViewState_ApplyOrbit's: the viewpoint is `distance`
from the target (x, 0, z), raised by `pitch` and turned by `heading`, with
the projection 300 (GsSetProjection) centred at 160, 120. The picture is the
game's closely, not exactly: affine texturing, back faces culled, the light
a fit to the game's frames (a little under two thirds ambient, the rest
from above), the far fog of CampaignMap_UpdateView (2000 to 2400) and, on
the world map, the spotlight mask of CampaignMap_SetLocation (clear within
32 of 160, 144, black from 192 out, 1.25 times wider than tall)."""
from __future__ import annotations

import math
import struct
from array import array

from . import pngio

SECTOR = 2048
MODEL_SECTOR = 6                # the block's first sector in the package
MODEL_SECTORS = 134
SCALE = 1365 / 4096
PROJECTION = 300
FOG = (2000, 2400)
AMBIENT, DIFFUSE = 0.61, 0.58
LIGHT = (0.10, -0.99, 0.02)     # towards the light, in the model's axes (y down)
SPOTLIGHT = (160, 144, 32, 192, 1.25)


class ModelError(Exception):
    pass


class MapModel:
    """The terrain of one overworld package: vertices, normals, polygons,
    and VRAM as its image uploads leave it."""

    def __init__(self, blob: bytes):
        self.blob = blob
        self.vram = array("H", bytes(1024 * 512 * 2))
        self.polygons = []          # (uvs, clut, tpage, vertices, normals)
        self.images = []            # dicts: the image uploads (x, y, words, rows, offset, clut...)
        self.vertices = []
        self.normals = []
        self.matrix = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
        self.translation = (0, 0, 0)
        self.parse()

    def word(self, index: int) -> int:
        return struct.unpack_from("<I", self.blob, index * 4)[0]

    def parse(self):
        blob, word = self.blob, self.word
        if len(blob) < 64 or word(0) != 0x50:
            raise ModelError("the map block is not an HMD")
        # The primitive header section: a count, then per header its
        # section count and the sections' word offsets (top bit set).
        at = word(2)
        headers = {}
        position = at + 1
        for _ in range(word(at)):
            count = word(position)
            headers[position] = [word(position + 1 + i) & 0x7FFFFFFF for i in range(count)]
            position += 1 + count
        terrain = None
        for b in range(word(3)):
            block = word(4 + b)
            if not block:
                continue
            # A block: the next block (0xFFFFFFFF: none), its header, the
            # number of primitive types, then the types.
            count = word(block + 2) & 0xFFFF
            sections = headers.get(word(block + 1))
            if sections is None:
                raise ModelError("a block names no primitive header")
            cursor = block + 3
            for _ in range(count):
                kind, head = word(cursor), word(cursor + 1)
                size, items = head & 0xFFFF, (head >> 16) & 0x7FFF
                if kind in (0x02000000, 0x02000001):
                    self.upload(cursor + 2, items, kind & 1, sections)
                elif kind & 0xFFFF in (0x000D, 0x0015):
                    self.read_polygons(sections[0] + word(cursor + 2), items, kind & 0xFFFF == 0x0015)
                    terrain = sections
                cursor += 1 + size
        if terrain is None:
            raise ModelError("the map block has no terrain")
        vertices, normals, coordinates = terrain[1], terrain[2], terrain[3]
        count = (normals - vertices) // 2
        self.vertices = [struct.unpack_from("<hhh", blob, (vertices + 2 * i) * 4) for i in range(count)]
        count = (terrain[0] - normals) // 2
        self.normals = [struct.unpack_from("<hhh", blob, (normals + 2 * i) * 4) for i in range(count)]
        unit = coordinates * 4 + 4          # the first GsCOORDUNIT: flg, coord MATRIX, workm, rot, super
        self.translation = struct.unpack_from("<3i", blob, unit + 4 + 20)
        rx, ry, rz = struct.unpack_from("<3h", blob, unit + 68)
        self.matrix = rotation_yxz(rx, ry, rz)

    def upload(self, at: int, items: int, with_clut: int, sections):
        for _ in range(items):
            parts = []
            for k in range(1 + with_clut):
                x, y, w, h = struct.unpack_from("<hhhh", self.blob, at * 4)
                offset = (sections[k] + self.word(at + 2)) * 4
                parts.append((x, y, w, h, offset))
                for row in range(h):
                    line = struct.unpack_from(f"<{w}H", self.blob, offset + row * w * 2)
                    start = ((y + row) & 511) * 1024 + (x & 1023)
                    self.vram[start:start + w] = array("H", line)
                at += 3
            self.images.append(parts)

    def read_polygons(self, at: int, items: int, quad: bool):
        stride = 14 if quad else 12
        for i in range(items):
            r = struct.unpack_from(f"<{stride}H", self.blob, at * 4 + i * stride * 2)
            if quad:
                self.polygons.append(((r[0], r[2], r[4], r[6]), r[1], r[3], (r[7], r[9], r[11], r[13]),
                                      (r[5], r[8], r[10], r[12])))
            else:
                self.polygons.append(((r[0], r[2], r[4]), r[1], r[3], (r[7], r[9], r[11]), (r[6], r[8], r[10])))

    def polygon_blocks(self) -> list:
        """The image upload each polygon's texture lies in (the last one to
        cover it, as VRAM keeps it), or None."""
        if getattr(self, "_blocks", None) is None:
            blocks = []
            for uvs, clut, tpage, _, _ in self.polygons:
                depth = (tpage >> 7) & 3
                per = 4 if depth == 0 else 2 if depth == 1 else 1
                px, py = (tpage & 15) * 64, ((tpage >> 4) & 1) * 256
                us, vs = [u & 255 for u in uvs], [u >> 8 for u in uvs]
                left, right = px + min(us) // per, px + max(us) // per
                top, bottom = py + min(vs), py + max(vs)
                found = None
                for index in range(len(self.images) - 1, -1, -1):
                    x, y, w, h, _ = self.images[index][0]
                    if x <= left and right < x + w and y <= top and bottom < y + h:
                        found = index
                        break
                blocks.append(found)
            self._blocks = blocks
        return self._blocks

    def world(self, v):
        m, t = self.matrix, self.translation
        return tuple(sum(m[i][j] * v[j] for j in range(3)) * SCALE + t[i] for i in range(3))

    def shades(self):
        """The light each normal gets, turned with the model."""
        m = self.matrix
        out = []
        for n in self.normals:
            turned = [sum(m[i][j] * n[j] for j in range(3)) / 4096 for i in range(3)]
            out.append(AMBIENT + DIFFUSE * max(0.0, sum(turned[i] * LIGHT[i] for i in range(3))))
        return out


def rotation_yxz(rx, ry, rz):
    """RotMatrixYXZ: Ry * Rx * Rz, angles in 4096ths of a turn."""
    def c(a):
        return math.cos(a * 2 * math.pi / 4096)

    def s(a):
        return math.sin(a * 2 * math.pi / 4096)
    mx = ((1, 0, 0), (0, c(rx), -s(rx)), (0, s(rx), c(rx)))
    my = ((c(ry), 0, s(ry)), (0, 1, 0), (-s(ry), 0, c(ry)))
    mz = ((c(rz), -s(rz), 0), (s(rz), c(rz), 0), (0, 0, 1))

    def mul(a, b):
        return tuple(tuple(sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)) for i in range(3))
    return mul(mul(my, mx), mz)


def model_blob(wa: bytes, package_sector: int) -> bytes:
    start = (package_sector + MODEL_SECTOR) * SECTOR
    return bytes(wa[start:start + MODEL_SECTORS * SECTOR])


_MODELS = {}


def model(wa: bytes, package_sector: int) -> MapModel:
    """The package's map, parsed once per disc."""
    key = (id(wa), len(wa), package_sector)
    if key not in _MODELS:
        _MODELS[key] = MapModel(model_blob(wa, package_sector))
    return _MODELS[key]


def eye(camera):
    """(viewpoint, target) of a place's camera (ViewState_ApplyOrbit)."""
    distance, heading, pitch, tx, tz = camera
    turn = 2 * math.pi / 4096
    level = -distance * math.cos(pitch * turn)
    rise = -distance * math.sin(pitch * turn)
    return (tx + level * math.cos(heading * turn), rise, tz + level * math.sin(heading * turn)), (tx, 0, tz)


def _texel(vram, tpage, clut, u, v):
    """The colour word a polygon's texture has at u, v; None where clear."""
    px, py, depth = (tpage & 15) * 64, ((tpage >> 4) & 1) * 256, (tpage >> 7) & 3
    if depth == 0:
        index = (vram[(py + v) * 1024 + px + (u >> 2)] >> ((u & 3) * 4)) & 15
    elif depth == 1:
        index = (vram[(py + v) * 1024 + px + (u >> 1)] >> ((u & 1) * 8)) & 255
    else:
        word = vram[((py + v) & 511) * 1024 + ((px + u) & 1023)]
        return None if word == 0 else word
    word = vram[(clut >> 6) * 1024 + (clut & 63) * 16 + index]
    # The game uploads every palette entry but the first with the
    # semi-transparency bit set: only a zero first entry is clear.
    return None if index == 0 and word == 0 else word


def _rasterize(size, faces, vram, out, depth):
    """Draw faces: ((x, y, z, u, v, shade) * 3, tpage, clut), nearest z first
    kept; shade multiplies the texel."""
    width, height = size
    for corners, tpage, clut, override in faces:
        (x0, y0, z0, u0, v0, s0), (x1, y1, z1, u1, v1, s1), (x2, y2, z2, u2, v2, s2) = corners
        area = (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0)
        if area == 0:
            continue
        inv = 1.0 / area
        left, right = max(int(min(x0, x1, x2)), 0), min(int(max(x0, x1, x2)) + 1, width - 1)
        top, bottom = max(int(min(y0, y1, y2)), 0), min(int(max(y0, y1, y2)) + 1, height - 1)
        for y in range(top, bottom + 1):
            yy = y + 0.5
            for x in range(left, right + 1):
                xx = x + 0.5
                a = ((x1 - xx) * (y2 - yy) - (x2 - xx) * (y1 - yy)) * inv
                b = ((x2 - xx) * (y0 - yy) - (x0 - xx) * (y2 - yy)) * inv
                c = 1.0 - a - b
                if a < 0 or b < 0 or c < 0:
                    continue
                z = a * z0 + b * z1 + c * z2
                at = y * width + x
                if z >= depth[at]:
                    continue
                tu, tv = int(a * u0 + b * u1 + c * u2) & 255, int(a * v0 + b * v1 + c * v2) & 255
                if override is not None:
                    rgba, iw, ih, ox, oy, tw, th = override
                    ix = min(iw - 1, max(0, (tu - ox) * iw // tw))
                    iy = min(ih - 1, max(0, (tv - oy) * ih // th))
                    p = (iy * iw + ix) * 4
                    if rgba[p + 3] < 128:
                        continue
                    red, green, blue = rgba[p], rgba[p + 1], rgba[p + 2]
                else:
                    word = _texel(vram, tpage, clut, tu, tv)
                    if word is None:
                        continue
                    red, green, blue = (word & 31) * 8, ((word >> 5) & 31) * 8, ((word >> 10) & 31) * 8
                depth[at] = z
                shade = a * s0 + b * s1 + c * s2
                o = at * 4
                out[o] = min(255, int(red * shade))
                out[o + 1] = min(255, int(green * shade))
                out[o + 2] = min(255, int(blue * shade))
                out[o + 3] = 255


def _override(mdl: MapModel, index: int, overrides):
    """The rasterizer's view of a mod's picture for a polygon's texture:
    (pixels, width, height, texture origin u, v in its page, texture size)."""
    if not overrides:
        return None
    block = mdl.polygon_blocks()[index]
    uvs, clut, tpage, _, _ = mdl.polygons[index]
    image = overrides.get((block, clut)) if block is not None else None
    if image is None:
        return None
    x, y, w, h, _ = mdl.images[block][0]
    depth = (tpage >> 7) & 3
    per = 4 if depth == 0 else 2 if depth == 1 else 1
    px, py = (tpage & 15) * 64, ((tpage >> 4) & 1) * 256
    return image.rgba, image.width, image.height, (x - px) * per, y - py, w * per, h


def render(mdl: MapModel, camera, spotlight: bool = False, size=(320, 240), overrides=None) -> pngio.Image:
    """The place's screen as its camera sees the map (320x240); overrides:
    {(image upload, palette word): picture} drawn in place of those
    textures (a mod's texture pack)."""
    vp, vr = eye(camera)
    f = [vr[i] - vp[i] for i in range(3)]
    length = math.sqrt(sum(a * a for a in f)) or 1.0
    f = [a / length for a in f]
    r = [f[2], 0.0, -f[0]]          # (down x forward): y down, as the PS1's axes
    length = math.sqrt(r[0] * r[0] + r[2] * r[2])
    # Straight down, GsSetRefView2 skips the turn about y: x stays across.
    r = [a / length for a in r] if length > 1e-9 else [1.0, 0.0, 0.0]
    u = [f[1] * r[2] - f[2] * r[1], f[2] * r[0] - f[0] * r[2], f[0] * r[1] - f[1] * r[0]]
    width, height = size
    k = width / 320
    near, far = FOG
    projected = []
    for v in mdl.vertices:
        w = mdl.world(v)
        p = (w[0] - vp[0], w[1] - vp[1], w[2] - vp[2])
        z = p[0] * f[0] + p[1] * f[1] + p[2] * f[2]
        if z <= 16:
            projected.append(None)
            continue
        fog = 0.0 if z <= near else min(1.0, far * (z - near) / (z * (far - near)))
        projected.append((width / 2 + PROJECTION * k * (p[0] * r[0] + p[1] * r[1] + p[2] * r[2]) / z,
                          height / 2 + PROJECTION * k * (p[0] * u[0] + p[1] * u[1] + p[2] * u[2]) / z, z, 1.0 - fog))
    shades = mdl.shades()
    faces = []
    for index, (uvs, clut, tpage, vertices, normals) in enumerate(mdl.polygons):
        points = [projected[i] if i < len(projected) else None for i in vertices]
        if any(p is None for p in points):
            continue
        for tri in ((0, 1, 2),) if len(vertices) == 3 else ((0, 1, 2), (1, 3, 2)):
            corners = []
            for i in tri:
                x, y, z, clear = points[i]
                light = shades[normals[i]] if normals[i] < len(shades) else 1.0
                corners.append((x, y, z, uvs[i] & 255, uvs[i] >> 8, light * clear))
            (xa, ya, _, _, _, _), (xb, yb, _, _, _, _), (xc, yc, _, _, _, _) = corners
            if (xb - xa) * (yc - ya) - (xc - xa) * (yb - ya) <= 0:
                continue            # a back face (NCLIP)
            faces.append((corners, tpage, clut, _override(mdl, index, overrides)))
    out = bytearray(width * height * 4)
    for i in range(3, len(out), 4):
        out[i] = 255
    _rasterize(size, faces, mdl.vram, out, [1e30] * (width * height))
    if spotlight:
        cx, cy, inner, outer, wide = SPOTLIGHT
        for y in range(height):
            for x in range(width):
                t = math.hypot((x / k + 0.5 - cx) / wide, y / k + 0.5 - cy)
                if t <= inner:
                    continue
                cut = 255 * min(1.0, (t - inner) / (outer - inner))
                o = (y * width + x) * 4
                for c in range(3):
                    out[o + c] = max(0, int(out[o + c] - cut))
    return pngio.Image(width, height, bytes(out))


def render_top(mdl: MapModel, centre, span: float, size, overrides=None) -> pngio.Image:
    """The map from straight above, turned as the world's cameras mostly
    look: +z to the right, -x up; `span` world units across the picture's
    shorter side, `centre` its middle (x, z)."""
    width, height = size
    scale = min(width, height) / span
    cx, cz = centre
    shades = mdl.shades()
    points = []
    for v in mdl.vertices:
        w = mdl.world(v)
        points.append((width / 2 + (w[2] - cz) * scale, height / 2 + (w[0] - cx) * scale, w[1]))
    faces = []
    for index, (uvs, clut, tpage, vertices, normals) in enumerate(mdl.polygons):
        if any(i >= len(points) for i in vertices):
            continue
        for tri in ((0, 1, 2),) if len(vertices) == 3 else ((0, 1, 2), (1, 3, 2)):
            corners = [(points[vertices[i]][0], points[vertices[i]][1], points[vertices[i]][2], uvs[i] & 255,
                        uvs[i] >> 8, shades[normals[i]] if normals[i] < len(shades) else 1.0) for i in tri]
            faces.append((corners, tpage, clut, _override(mdl, index, overrides)))
    out = bytearray(width * height * 4)
    for i in range(3, len(out), 4):
        out[i] = 255
    _rasterize(size, faces, mdl.vram, out, [1e30] * (width * height))
    return pngio.Image(width, height, bytes(out))
