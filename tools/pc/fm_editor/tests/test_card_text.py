"""The card-text preview: the card view's layout, the retail font off the
disc and the TrueType reader (card_text.py, ttf.py), on synthetic data."""
import struct
import tempfile
import unittest
from pathlib import Path

from fm_editor import card_text, ttf, validate


def rows_of(lay):
    """The text of each row, as the box lays it."""
    out = {}
    for c, column, row in lay.glyphs:
        out.setdefault(row, {})[column] = c
    return ["".join(out.get(r, {}).get(x, " ") for x in range(card_text.COLUMNS)).rstrip() for r in range(lay.rows)]


class LayoutTest(unittest.TestCase):
    def test_lines_of_twenty_letters(self):
        lay = card_text.layout("A delicate elf that lacks in offense but has a terrific defense backed by mystical power.")
        self.assertEqual(rows_of(lay), ["A delicate elf that", "lacks in offense but", "has a terrific",
                                        "defense backed by", "mystical power."])
        self.assertEqual(lay.cut_rows, [])
        self.assertEqual(lay.hidden, 0)

    def test_the_box_cuts_a_long_word(self):
        # What the game drew for this text (checked in the card view): 21
        # letters on the first row, the rest of the word on the next, and
        # the next word on a row of its own, as the port's line count still
        # holds the whole word; nine rows drawn, the rest never.
        text = "ABCDEFGHIJKLMNOPQRSTUVWXY two\n" + "\n".join(f"row {i} of the text" for i in range(3, 13))
        lay = card_text.layout(text)
        rows = rows_of(lay)
        self.assertEqual(rows[:4], ["ABCDEFGHIJKLMNOPQRSTU", "VWXY", "two", "row 3 of the text"])
        self.assertEqual(rows[card_text.SHOWN_ROWS - 1], "row 8 of the text")
        self.assertEqual(lay.cut_rows, [1])
        self.assertEqual(lay.rows, 13)
        self.assertEqual(lay.hidden, 4)
        self.assertEqual(lay.lines, validate.text_lines(text))

    def test_twenty_one_letters_fit(self):
        lay = card_text.layout("ABCDEFGHIJKLMNOPQRSTU")
        self.assertEqual((lay.rows, lay.cut_rows), (1, []))

    def test_line_breaks_and_spaces(self):
        lay = card_text.layout("one\n\ntwo   three")
        self.assertEqual(rows_of(lay), ["one", "", "two three"])
        self.assertEqual(card_text.layout("").rows, 0)

    def test_the_count_matches_the_tab(self):
        for text in ("a b c", "x" * 45, "word " * 40, "a\nb\nc\nd\ne\nf\ng\nh\ni"):
            self.assertEqual(card_text.layout(text).lines, validate.text_lines(text))


def synthetic_wa():
    """The boot package's font page and colours where the retail disc has
    them: an 'A' that is a 6 x 9 block (index 15, its outline index 1) and
    a ramp from black to white."""
    wa = bytearray((card_text.RAMP_SECTOR + 1) * 2048)
    u, v = card_text._cell_uv("A")
    base = card_text.BOOT_SECTOR * 2048
    for y in range(12):
        for x in range(8):
            index = 15 if 1 <= x <= 6 and 1 <= y <= 9 else 1 if y <= 10 else 0
            tu, tv = u + x, v + y
            at = base + tv * 128 + tu // 2
            wa[at] |= index << (4 * (tu & 1))
    ramp = card_text.RAMP_SECTOR * 2048
    for i in range(16):
        level = i * 31 // 15
        struct.pack_into("<H", wa, ramp + 2 * i, level | level << 5 | level << 10)
    return bytes(wa)


class RetailFontTest(unittest.TestCase):
    def test_cells_and_colours(self):
        font = card_text.RetailFont(synthetic_wa())
        cell = font.cell("A")
        self.assertEqual(cell[1 * 8 + 1], 15)
        self.assertEqual(cell[0], 1)
        self.assertEqual(cell[11 * 8], 0)
        self.assertEqual(font.colours[15], (248, 248, 248))
        self.assertEqual(font.cell("À"), cell)          # drawn as its plain letter
        self.assertIsNone(font.cell("☺"))

    def test_no_font(self):
        with self.assertRaises(ValueError):
            card_text.RetailFont(bytes(card_text.RAMP_SECTOR * 2048 + 64))

    def test_picture(self):
        font = card_text.RetailFont(synthetic_wa())
        image, lay = card_text.Renderer(font).render("☺A", 2)
        self.assertEqual(image.size, ((card_text.COLUMNS * 8 + card_text.GUTTER) * 2, card_text.SHOWN_ROWS * 24))
        # The A is the second glyph: its block, each texel 2 x 2 pixels.
        self.assertEqual(image.pixel(8 * 2 + 2, 2)[:3], (248, 248, 248))
        self.assertEqual(image.pixel(8 * 2 + 3, 3)[:3], (248, 248, 248))
        self.assertEqual(image.pixel(8 * 2, 0)[:3], font.colours[1])
        self.assertEqual(image.pixel(30 * 2, 30)[:3], card_text.PANEL)
        # The ninth row is the frame's; the smiley has no retail glyph: a red box.
        self.assertEqual(image.pixel(100, 8 * 24 + 5)[:3], card_text.FRAME)
        self.assertEqual(image.pixel(0, 0)[:3], card_text.MARK)


def tiny_font(path):
    """A TrueType file with one glyph, a square with a square hole, for 'A'."""
    def table(tag, body):
        return tag, body
    outer = [(100, 100), (100, 700), (700, 700), (700, 100)]      # clockwise, y up
    inner = [(300, 300), (500, 300), (500, 500), (300, 500)]
    points = outer + inner
    ends = struct.pack(">hh", 3, 7)
    flags = bytes([1] * 8)
    xs = b"".join(struct.pack(">h", x - px) for (x, _), (px, _) in zip(points, [(0, 0)] + points))
    ys = b"".join(struct.pack(">h", y - py) for (_, y), (_, py) in zip(points, [(0, 0)] + points))
    glyph = struct.pack(">hhhhh", 2, 100, 100, 700, 700) + ends + struct.pack(">H", 0) + flags + xs + ys
    glyph += b"\0" * (-len(glyph) % 4)
    glyf = glyph
    loca = struct.pack(">HHH", 0, 0, len(glyph) // 2)                # glyph 0 empty, glyph 1 the square
    head = bytearray(54)
    struct.pack_into(">H", head, 18, 1000)
    struct.pack_into(">h", head, 50, 0)
    hhea = bytearray(36)
    struct.pack_into(">H", hhea, 34, 2)
    maxp = struct.pack(">IH", 0x5000, 2)
    hmtx = struct.pack(">HhHh", 500, 0, 800, 100)
    segments = [(0x41, 0x41, 1 - 0x41), (0xFFFF, 0xFFFF, 1)]
    cmap4 = struct.pack(">HHHHHHH", 4, 16 + 8 * len(segments), 0, 2 * len(segments), 0, 0, 0)
    cmap4 += b"".join(struct.pack(">H", e) for _, e, _ in segments) + b"\0\0"
    cmap4 += b"".join(struct.pack(">H", s) for s, _, _ in segments)
    cmap4 += b"".join(struct.pack(">h", d) for _, _, d in segments)
    cmap4 += b"\0\0" * len(segments)
    cmap = struct.pack(">HHHHI", 0, 1, 3, 1, 12) + cmap4
    name = "Tiny".encode("utf-16-be")
    names = struct.pack(">HHH", 0, 1, 18) + struct.pack(">6H", 3, 1, 0x409, 4, len(name), 0) + name
    tables = [table(b"cmap", cmap), table(b"glyf", glyf), table(b"head", bytes(head)), table(b"hhea", bytes(hhea)),
              table(b"hmtx", hmtx), table(b"loca", loca), table(b"maxp", maxp), table(b"name", names)]
    out = bytearray(struct.pack(">IHHHH", 0x10000, len(tables), 0, 0, 0))
    offset = 12 + 16 * len(tables)
    bodies = b""
    for tag, body in tables:
        out += struct.pack(">4sIII", tag, 0, offset + len(bodies), len(body))
        bodies += body + b"\0" * (-len(body) % 4)
    Path(path).write_bytes(bytes(out) + bodies)


class TrueTypeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.path = Path(cls.tmp.name) / "tiny.ttf"
        tiny_font(cls.path)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_reads_the_font(self):
        font = ttf.Font(self.path)
        self.assertEqual(font.name, "Tiny")
        self.assertTrue(font.has(0x41))
        self.assertFalse(font.has(0x42))
        self.assertAlmostEqual(font.advance(0x41), 0.8)
        for got, want in zip(ttf.bbox(font.outline(0x41)), (0.1, 0.1, 0.7, 0.7)):
            self.assertAlmostEqual(got, want)
        self.assertIsNone(font.outline(0x42))

    def test_fill_keeps_the_hole(self):
        font = ttf.Font(self.path)
        square = [[(x * 10, (1 - y) * 10) for x, y in c] for c in font.outline(0x41)]   # 1 unit = 10 px, y down
        cover = ttf.fill(square, 10, 10)
        self.assertEqual(cover[5 * 10 + 1], 255)       # the ring
        self.assertEqual(cover[6 * 10 + 3], 0)         # the hole
        self.assertEqual(cover[0], 0)                  # outside
        heavy = ttf.embolden(square, 1.0, 1.0)
        self.assertLess(ttf.bbox(heavy)[0], ttf.bbox(square)[0])
        self.assertGreater(ttf.bbox(heavy)[2], ttf.bbox(square)[2])

    def test_refuses_what_it_cannot_read(self):
        other = Path(self.tmp.name) / "cff.otf"
        other.write_bytes(b"OTTO" + bytes(64))
        with self.assertRaises(ttf.FontError):
            ttf.Font(other)
        other.write_bytes(b"not a font at all")
        with self.assertRaises(ttf.FontError):
            ttf.Font(other)

    def test_a_face_without_lines_keeps_the_retail_letters(self):
        # The port sets nothing in a face whose lines it cannot measure; the
        # preview draws the retail cell as it does.
        retail = card_text.RetailFont(synthetic_wa())
        plain, _ = card_text.Renderer(retail).render("A", 2)
        renderer = card_text.Renderer(retail, ttf.Font(self.path))
        hd, _ = renderer.render("A", 2)
        self.assertFalse(renderer.face_ok)
        self.assertEqual(hd, plain)


if __name__ == "__main__":
    unittest.main()
