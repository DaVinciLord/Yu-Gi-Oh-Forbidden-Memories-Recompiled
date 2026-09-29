#!/usr/bin/env python3
"""tools/pc/model_import.py on a made-up mesh: a textured box with a lid,
put on Morphing Jar's skeleton, then the record written read back the way
the game reads it. Needs the disc (game/rpg-yfm.bin, or MEMORIES_DISC);
without it the test is skipped (exit 77)."""
from __future__ import annotations

import os
import struct
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import model_import  # noqa: E402
import model_record  # noqa: E402

TEMPLATE = 591   # Morphing Jar


def box_obj(folder: Path) -> Path:
    """A box 1 wide and 2 tall, split into rows so every bone gets some of it,
    with UVs across the whole texture and an .mtl naming the texture."""
    rows, lines, faces = 8, ["mtllib box.mtl"], []
    ring = [(-0.5, -0.5), (0.5, -0.5), (0.5, 0.5), (-0.5, 0.5)]
    for r in range(rows + 1):
        for i, (x, z) in enumerate(ring):
            lines.append(f"v {x} {2 * r / rows} {z}")
            lines.append(f"vt {i / 4} {r / rows}")
    lines.append("usemtl paint")
    for r in range(rows):
        for i in range(4):
            a, b = r * 4 + i + 1, r * 4 + (i + 1) % 4 + 1
            c, d = a + 4, b + 4
            faces += [f"f {a}/{a} {b}/{b} {d}/{d}", f"f {a}/{a} {d}/{d} {c}/{c}"]
    (folder / "box.obj").write_text("\n".join(lines + faces) + "\n")
    (folder / "box.mtl").write_text("newmtl paint\nmap_Kd box.png\n")
    gradient = np.zeros((64, 64, 3), np.uint8)
    gradient[..., 0] = np.linspace(0, 255, 64)[None, :]
    gradient[..., 1] = np.linspace(0, 255, 64)[:, None]
    gradient[..., 2] = 90
    Image.fromarray(gradient).save(folder / "box.png")
    return folder / "box.obj"


def main() -> int:
    disc = Path(os.environ.get("MEMORIES_DISC", HERE.parents[1] / "game/rpg-yfm.bin"))
    if not disc.exists():
        print(f"model import: no disc at {disc}; skipped")
        return 77
    template = model_record.read_record(disc, TEMPLATE)
    with tempfile.TemporaryDirectory() as folder:
        obj = box_obj(Path(folder))
        model_data, pages, hd = model_import.convert(obj, template, None, 0.0, 100.0)
        assert hd.size == (model_import.PAGE_W * model_import.HD_SCALE * model_import.PAGES,
                           model_import.PAGE_H * model_import.HD_SCALE)
        record = model_import.write_record(template, model_data, pages)
        assert len(record) == model_record.RECORD_BYTES
        # Everything but the model data, textures and palettes is the template's.
        keep = model_import.PALETTE_PHASE + 2 * model_import.SECTOR
        assert record[keep:] == template[keep:], "the template's modules, voices and metadata changed"

        hmd = model_import.Hmd(record[:model_import.MODEL_DATA_BYTES])
        original = model_import.Hmd(template[:model_import.MODEL_DATA_BYTES])
        assert hmd.size == len(model_data) <= model_import.MODEL_DATA_BUDGET
        assert hmd.coordinates == original.coordinates, "the skeleton moved"
        assert [u[2] for u in hmd.units] == [u[2] for u in original.units]
        # Block 0, the animations, points at sections with the same contents
        # as before, wherever the old geometry's removal moved them.
        for kept, was in zip(hmd.chain(0), original.chain(0)):
            now, before = hmd.header(kept["header"]), original.header(was["header"])
            assert len(now) == len(before)
            for a, b in zip(now, before):
                if not b & 0x80000000:
                    assert a == b
                elif (b & 0x7FFFFFFF) * 4 >= original.size:
                    assert a == b, "a section past the model data moved"
                else:
                    x, y = hmd.section(a), original.section(b)
                    assert record[x:x + 64] == template[y:y + 64], "an animation section's contents changed"
        assert hmd.size < original.size + len(model_data), "the old geometry was not left out"
        # One projection run a bone, the vertex runs back to back, and the
        # triangles all in the last block, reaching only vertices a run owns.
        runs, owned = [], set()
        for block in range(1, hmd.block_count - 1):
            for element in hmd.chain(block):
                for prim in element["prims"]:
                    assert prim["type"] & 0xFF7FFFFF == model_import.SHARED_PREPASS
                    count, first, result, normals, normal_first, normal_result = prim["args"]
                    assert first == result and normal_first == normal_result
                    runs.append((first, count))
                    owned.update(range(first, first + count))
        assert runs and sorted(runs) == runs
        assert sum(1 for b in range(1, hmd.block_count - 1)
                   for e in hmd.chain(b) for p in e["prims"] if p["type"] & model_import.MAP_COORDINATES) == 1
        last = hmd.chain(hmd.block_count - 1)
        triangles = sum(p["count"] for e in last for p in e["prims"])
        assert triangles == 64, triangles
        sections = hmd.header(last[0]["header"])
        assert sections[-1] & 0x7FFFFFFF == hmd.coordinates
        for n in range(triangles):
            half = struct.unpack_from("<12H", record, hmd.section(sections[0]) + n * 24)
            assert half[3] in range(model_import.TPAGE_FIRST, model_import.TPAGE_FIRST + model_import.PAGES)
            assert (half[1] - model_import.CLUT_FIRST) % 0x40 == 0
            for corner in range(3):
                assert half[7 + corner * 2] in owned
            for uv in (half[0], half[2], half[4]):
                assert (uv & 0xFF) < model_import.PAGE_W
        # The palettes hold no transparent colour where the texture is opaque.
        colours = np.frombuffer(record[model_import.PALETTE_PHASE:model_import.PALETTE_PHASE + 512], "<u2")
        assert not (colours == 0).any()
        # The box stands where the jar stood, as tall as the jar.
        world = hmd.world()
        owner = {}
        for block in range(1, hmd.block_count - 1):
            for element in hmd.chain(block):
                for prim in element["prims"]:
                    count, first = prim["args"][0], prim["args"][1]
                    for i in range(count):
                        owner[first + i] = block - 1
        points = np.array([(world[owner[v]] @ np.r_[hmd.vector(sections[1], v), 1])[:3] for v in owner])
        jar = np.array([p for _, p in original.bone_points()])
        height, jar_height = np.ptp(points[:, 1]), np.ptp(jar[:, 1])
        assert abs(height - jar_height) <= 2, (height, jar_height)
        assert abs(points[:, 1].max() - jar[:, 1].max()) <= 2
    print("model import: passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
