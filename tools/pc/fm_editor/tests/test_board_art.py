"""The duel board's textures (board_art.py) and the UI tab's Duel board page
(ui_board.py) on boards painted here: where each piece is (checked against
the HD recipe's capture), the pack entries and palette patches a mod gets,
tints read back from their patches, saving and opening again, and the
page's own controls.

    python -m unittest discover -s tools/pc/fm_editor/tests -t tools/pc
"""
import json
import random
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fm_editor import board_art as ba, gamedata, manifest, pngio, validate
from fm_editor.model import Project
from fm_editor.tests.test_data import fixture
from fm_editor.tests.test_gui import GuiCase

ROOT = Path(__file__).resolve().parents[4]


def paint_boards(wa: bytes) -> bytes:
    """Each field's board: texel (x, y) of a column is (x + y + field) % 15 + 1,
    every palette's colour i a mix of the field, the palette and i."""
    data = bytearray(wa)
    for t_index, terrain in enumerate(ba.TERRAINS):
        start = ba.phase_offset(terrain)
        for column in range(2):
            for y in range(256):
                for x in range(0, 256, 2):
                    lo, hi = ((x + y + t_index) % 15 + 1), ((x + 1 + y + t_index) % 15 + 1)
                    data[start + column * ba.COLUMN_BYTES + y * 128 + x // 2] = lo | hi << 4
        for p_index, part in enumerate(ba.PARTS):
            at = start + part.palette
            for i in range(16):
                word = 0 if i == 0 else ((i * 2) & 31) | ((p_index + 3 * t_index) % 32) << 5 | (31 - i) << 10
                if i == 15:
                    word |= 0x8000
                data[at + 2 * i:at + 2 * i + 2] = word.to_bytes(2, "little")
    return bytes(data)


_game = None


def game():
    global _game
    if _game is None:
        f = fixture()
        _game = gamedata.read_game(f.slus, paint_boards(f.wa))
    return _game


def project() -> Project:
    p = Project(game())
    p.info.id = "boardmod"
    return p


def solid(width, height, colour=(200, 40, 40, 255)):
    return pngio.Image(width, height, bytes(colour) * (width * height))


class WhereTest(unittest.TestCase):
    def test_against_the_hd_recipe(self):
        """The recipe's floor bands and wall readings (captured from a duel)
        are the pieces' rectangles, offsets and palettes on every field."""
        recipe = json.loads((ROOT / "tools/pc/hd_recipes/duel.json").read_text(encoding="utf-8"))
        names = dict(zip(("normal", "forest", "wasteland", "mountain", "meadow", "sea", "dark"), ba.TERRAINS))
        checked = 0
        for sheet in recipe["sheets"]:
            field, _, what = sheet["what"].partition(" field: ")
            if field not in names or not what.startswith(("floor tiles", "the platform's sides")):
                continue
            terrain = names[field]
            palette = int(sheet["palette"], 16) - ba.phase_offset(terrain)
            part = next(p for p in ba.PARTS if p.palette == palette)
            column_start = ba.phase_offset(terrain) + part.column * ba.COLUMN_BYTES
            self.assertEqual(int(sheet["offset"], 16), column_start, sheet["what"])
            for x, y, w, h in sheet["rects"]:
                self.assertTrue(part.x <= x and x + w <= part.x + part.w and part.y <= y and y + h <= part.y + part.h,
                                f"{sheet['what']}: {x, y, w, h} outside {part.label}")
            checked += 1
        self.assertEqual(checked, 7 * 15)

    def test_pieces_share_no_word(self):
        for column in (0, 1):
            cells = set()
            for part in (p for p in ba.PARTS if p.column == column):
                mine = {(x // 4, y) for x in range(part.x, part.x + part.w) for y in range(part.y, part.y + part.h)}
                self.assertFalse(cells & mine, part.label)
                cells |= mine
                self.assertEqual(part.x % 4, 0)
                self.assertEqual(part.w % 4, 0)
            # The palettes are words of the phase no piece covers.
            for part in ba.PARTS:
                at = part.palette - column * ba.COLUMN_BYTES
                if 0 <= at < ba.COLUMN_BYTES:
                    self.assertNotIn(((at % 128) // 2, at // 128), cells)

    def test_entry(self):
        part = ba.BY_KEY["wall_right"]
        entry = ba.entry("forest", part, "board/forest/wall_right.png")
        base = (0x16C6 + 235 + 203) * 2048
        self.assertEqual((entry["offset"], entry["words"], entry["rows"], entry["stride"], entry["clut_offset"]),
                         (base + 0x8000 + 128 // 2, 32, 64, 64, base + 0xF140))


class TintTest(unittest.TestCase):
    def test_word(self):
        self.assertEqual(ba.tint_word(0, 0x000000), 0)                 # clear stays clear
        self.assertEqual(ba.tint_word(0x7FFF, 0xFFFFFF), 0x7FFF)
        self.assertEqual(ba.tint_word(0x801F, 0x000000), 0x8000)       # black, with the bit
        self.assertEqual(ba.tint_word(0x001F, 0x00FFFF), 0x0001)       # black without it
        self.assertEqual(ba.tint_word(0x7FFF, 0xFF8000), 31 | 16 << 5)

    def test_read_back(self):
        rng = random.Random(3)
        for trial in range(300):
            retail = [0] + [rng.randrange(1, 65536) for _ in range(15)]
            if trial % 3 == 0:
                retail = [0] + [rng.randrange(1, 32) | rng.choice((0, 0x8000)) for _ in range(15)]
            words = ba.tinted(retail, rng.randrange(0x1000000))
            found = ba.recover_tint(retail, words)
            self.assertIsNotNone(found)
            self.assertEqual(ba.tinted(retail, found), words)
            self.assertEqual(ba.recover_tint(retail, ba.tinted(retail, found)), found)
        self.assertIsNone(ba.recover_tint([0, 0x0421, 0x0842], [0, 0x0421, 0x0400]))


class ModTest(unittest.TestCase):
    def test_piece_image(self):
        data = game().board
        part = ba.BY_KEY["opponent_front"]
        image = ba.piece_image(data, "normal", part)
        self.assertEqual(image.size, (256, 52))
        index = (0 + 52 + 0) % 15 + 1
        word = ((index * 2) & 31) | 1 << 5 | (31 - index) << 10
        self.assertEqual(image.pixel(0, 0), ba.colour(word))

    def test_floor_split_and_joined(self):
        p = project()
        image = pngio.Image(512, 508, bytes(b for y in range(508) for x in range(512)
                                            for b in (y // 2 % 256, x // 2, 90, 255)))
        self.assertEqual(ba.set_floor(p, ["sogen"], image), [])
        rows = {k: v.image for (t, k), v in ba.state(p).pictures.items() if t == "sogen"}
        self.assertEqual(rows["opponent_back"].size, (512, 104))
        self.assertEqual(rows["centre"].size, (512, 92))
        self.assertEqual(rows["centre"].pixel(0, 0)[0], 104)            # the third row of the picture
        self.assertEqual(ba.floor_image(p, "sogen"), image)

    def test_saved_and_opened_again(self):
        p = project()
        ba.set_floor(p, ["normal"], solid(256, 254))
        self.assertEqual(ba.set_piece(p, list(ba.TERRAINS), ba.BY_KEY["trim"], solid(300, 40)),
                         ["300x40 is not 128x16's shape: stretched to fit"])
        ba.set_tint(p, ["forest"], ba.FLOOR, 0x8080FF)
        ba.set_tint(p, list(ba.TERRAINS), [ba.BY_KEY["wall_middle"]], 0xFF4040)
        self.assertIsNotNone(ba.common_tint(p, "forest", ba.FLOOR))
        p.other["data"] = [{"file": ba.ARCHIVE_FILE, "patch": [{"at": "0x10", "bytes": "01 02"}]}]
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "m"
            manifest.save_mod(p, folder)
            written = json.loads((folder / "mod.json").read_text(encoding="utf-8"))
            entries = json.loads((folder / "textures" / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(len(entries), 5 + 7)
            self.assertEqual({e["file"] for e in entries if e["offset"] in
                              {ba.image_offset(t, ba.BY_KEY["trim"]) for t in ba.TERRAINS}}, {"board/all/trim.png"})
            self.assertTrue((folder / "textures" / "board" / "all" / "trim.png").is_file())
            self.assertEqual(written["data"][0]["patch"], [{"at": "0x10", "bytes": "01 02"}])
            ours = written["data"][1]["patch"]
            self.assertTrue(all(any(ba.palette_offset(t, q) <= int(run["at"], 16) < ba.palette_offset(t, q) + 32
                                    for t in ba.TERRAINS for q in ba.PARTS) for run in ours))
            opened, messages = manifest.open_mod(game(), folder)
            self.assertEqual(messages, [])
            # The same palettes, and the same tints on the page (a piece's own
            # reading of its patch may differ from the one set with others).
            self.assertEqual(ba.patches(opened), ba.patches(p))
            self.assertEqual(set(ba.state(opened).tints), set(ba.state(p).tints))
            for terrain in ba.TERRAINS:
                for parts in [ba.FLOOR] + [[q] for q in ba.PARTS]:
                    self.assertEqual(ba.common_tint(opened, terrain, parts), ba.common_tint(p, terrain, parts))
            self.assertEqual(ba.digest(opened), ba.digest(p))
            self.assertEqual(opened.other["data"],
                             [{"file": ba.ARCHIVE_FILE, "patch": [{"at": "0x10", "bytes": "01 02"}]}])
            self.assertFalse([str(i) for i in validate.validate(opened) if i.area in ("UI", "Art")])
            again = Path(tmp) / "m2"
            manifest.save_mod(opened, again)
            self.assertEqual((again / "mod.json").read_text(encoding="utf-8"),
                             (folder / "mod.json").read_text(encoding="utf-8"))
            self.assertEqual((again / "textures" / "manifest.json").read_text(encoding="utf-8"),
                             (folder / "textures" / "manifest.json").read_text(encoding="utf-8"))

    def test_a_palette_patch_that_is_no_tint_stays(self):
        p = project()
        part = ba.BY_KEY["centre_step"]
        at = ba.palette_offset("umi", part) + 2
        p.other["data"] = [{"file": ba.ARCHIVE_FILE, "patch": [{"at": f"0x{at:X}", "bytes": "FF 7F"}]}]
        messages = ba.read_patches(p)
        self.assertEqual(len(messages), 1)
        self.assertIn("is no tint", messages[0])
        self.assertEqual(ba.state(p).tints, {})
        self.assertEqual(len(p.other["data"][0]["patch"]), 1)

    def test_checks(self):
        p = project()
        ba.set_piece(p, ["yami"], ba.BY_KEY["wall_corners"], solid(64, 64, (0, 0, 0, 0)))
        ba.state(p).tints[("yami", "wall_corners")] = 0x808080
        issues = [i.message for i in validate.validate(p) if i.area == "UI"]
        self.assertTrue(any("tint shows nowhere" in m for m in issues), issues)
        self.assertTrue(any("see-through" in m for m in issues), issues)


class BoardPageTest(GuiCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        wa = cls.game / "DATA" / "WA_MRG.MRG"
        wa.write_bytes(paint_boards(wa.read_bytes()))

    def setUp(self):
        super().setUp()
        self.tab = self.app.ui
        self.app.notebook.select(self.tab)
        self.tab.page_name.set("board")
        self.tab.show_page()
        self.app.update()
        self.page = self.tab.pages["board"]
        self.folder = Path(tempfile.mkdtemp())

    def png(self, name, w, h, colour=(30, 160, 60, 255)):
        path = self.folder / name
        pngio.write(path, solid(w, h, colour))
        return path

    def test_edits(self):
        page = self.page
        self.assertIsNotNone(page.sketch)
        # Clicking the sketch's near wall chooses its middle.
        k, (ox, oy) = page.sketch.k, page.offset
        page.clicked(mock.Mock(x=ox + 160 * k, y=oy + 200 * k))
        self.assertEqual(page.chosen, "wall_middle")
        page.all_fields.set(True)
        page.replace(self.png("middle.png", 128, 128))
        st = ba.state(self.app.project)
        self.assertEqual({t for t, k in st.pictures}, set(ba.TERRAINS))
        self.assertEqual(self.tab.pages["board"].tree.set("wall_middle", "state"), "replaced")
        self.assertTrue(self.app.dirty)
        # A tint of the game's floor, on Forest alone.
        page.all_fields.set(False)
        page.field.set("forest")
        page.choose_field()
        page.select("floor")
        page.set_tint(0x80A0FF)
        self.assertEqual(len([k for k in st.tints if k[0] == "forest"]), 5)
        self.assertNotEqual(page.tint.value, ba.WHITE)
        # A replaced piece takes no tint.
        page.select("wall_middle")
        page.set_tint(0x404040)
        self.assertNotIn(("forest", "wall_middle"), st.tints)
        self.pause()
        out = self.folder / "export.png"
        page.export(str(out))
        self.assertEqual(pngio.read(out).size, (64, 64))
        page.revert()
        self.assertNotIn(("forest", "wall_middle"), st.pictures)
        self.assertIn(("normal", "wall_middle"), st.pictures)
        page.revert_all()
        self.assertFalse(st.pictures or st.tints)
        # Undo brings the edits back, pictures and all.
        self.pause()
        self.app.undo()
        self.app.update()
        st = ba.state(self.app.project)
        self.assertEqual(len(st.pictures), 7)
        self.assertEqual(ba.picture(self.app.project, st.pictures[("normal", "wall_middle")]).size, (128, 128))
        self.assertEqual(len([k for k in st.tints if k[0] == "forest"]), 5)

    def test_saved_and_opened_again(self):
        page = self.page
        page.select("floor")
        page.replace(self.png("floor.png", 1024, 1016))
        page.select("trim")
        page.replace(self.png("trim.png", 512, 64, (250, 200, 40, 255)))
        page.select("corner_triangles")
        page.set_tint(0xFF6060)
        folder = self.folder / "mod"
        manifest.save_mod(self.app.project, folder)
        opened, messages = manifest.open_mod(self.app.retail, folder)
        self.assertEqual(messages, [])
        self.assertEqual(ba.digest(opened), ba.digest(self.app.project))
        self.app.set_project(opened)
        self.tab.refresh()
        self.app.update()
        self.assertEqual(self.page.tree.set("trim", "state"), "replaced")
        self.assertEqual(self.page.tree.set("corner_triangles", "state"), "tinted")
