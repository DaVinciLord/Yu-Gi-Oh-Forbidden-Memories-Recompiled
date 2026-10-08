"""The duelists a mod adds (roster.py), their portraits (portrait.py) and the
Duelists tab, on synthetic game files.

    python -m unittest discover -s tools/pc/fm_editor/tests -t tools/pc
"""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fm_editor import gamedata as g, manifest, pngio, portrait, roster, validate
from fm_editor.model import Project
from fm_editor.tests.fixtures import art_colour
from fm_editor.tests.test_data import fixture
from fm_editor.tests.test_gui import GuiCase


def sample(w: int, h: int) -> pngio.Image:
    """A picture with every kind of pixel: gradients, and some half seen."""
    out = bytearray()
    for y in range(h):
        for x in range(w):
            out += bytes(((x * 5 + y * 3) % 256, (x * y) % 256, (255 - x * 2) % 256, 255 if (x + y) % 7 else 100))
    return pngio.Image(w, h, bytes(out))


def flat(w: int, h: int, colour) -> pngio.Image:
    return pngio.Image(w, h, bytes(colour) * (w * h))


def png(image: pngio.Image) -> bytes:
    return pngio.encode(image)


class PortraitTest(unittest.TestCase):
    def test_the_record_is_the_games(self):
        """CardArt_PortraitFromImage's own bytes: these digests are of the
        records the port's art.c made of the same two pictures (built
        against src/pc/cards/art.c, which this module mirrors)."""
        for (w, h), digest in (((96, 72), "72defab55d7e46a34e76a77881c2d37c614e2aca8c20abb242c9303d9c810571"),
                               ((40, 130), "c07b11f2fc90df3ebb6d05b41a5e8e06c92e46697beda8dc96e782d156102e59")):
            record = portrait.record_from(sample(w, h))
            self.assertEqual(len(record), portrait.RECORD)
            self.assertEqual(hashlib.sha256(record).hexdigest(), digest, (w, h))

    def test_the_middle_square_and_its_colours(self):
        # Three bands across a 96x48 picture: the middle square is x 24 to 71.
        rows = b"".join(bytes((255, 0, 0, 255)) * 32 + bytes((0, 255, 0, 255)) * 32 + bytes((0, 0, 255, 255)) * 32
                        for _ in range(48))
        image = pngio.Image(96, 48, rows)
        self.assertEqual(portrait.crop(image), (24, 0, 48, 48))
        shown = portrait.record_image(portrait.record_from(image))
        self.assertEqual(shown.size, (48, 48))
        self.assertEqual(shown.pixel(0, 0)[:3], (255, 0, 0))
        self.assertEqual(shown.pixel(8, 0)[:3], (0, 255, 0))
        self.assertEqual(shown.pixel(47, 0)[:3], (0, 0, 255))
        record = portrait.record_from(image)
        clut = [int.from_bytes(record[portrait.PIXELS + 2 * i:portrait.PIXELS + 2 * i + 2], "little") for i in range(64)]
        self.assertEqual(clut[0], 0x8000)                   # entry 0 is never drawn: black, not see-through
        used = sorted(set(record[:portrait.PIXELS]))
        self.assertEqual(len(used), 3)
        self.assertEqual(sorted(clut[i] for i in used), [0x001F, 0x03E0, 0x7C00])
        # Black stays black: 0 is the PS1's see-through colour, so it is 0x8000.
        self.assertEqual(portrait.record_from(flat(10, 10, (0, 0, 0, 255)))[portrait.PIXELS + 2:portrait.PIXELS + 4],
                         b"\x00\x80")

    def test_sharp_above_48_only(self):
        self.assertFalse(portrait.sharp(flat(48, 48, (1, 2, 3, 255))))
        self.assertFalse(portrait.sharp(flat(200, 48, (1, 2, 3, 255))))     # its square is 48
        self.assertTrue(portrait.sharp(flat(64, 64, (1, 2, 3, 255))))
        big = portrait.in_game(flat(128, 128, (200, 10, 10, 255)), 2)
        self.assertEqual(big.size, (96, 96))
        self.assertEqual(portrait.in_game(flat(40, 40, (200, 10, 10, 255)), 3).size, (144, 144))

    def test_what_the_pack_paints_at_1x(self):
        """A picture bigger than 48x48 is the texture pack's at 1x too: its
        middle square averaged in whole-pixel boxes at 5 bits a channel
        (texture_pack.c), its black drawn from the record (soft_gpu.c).
        tests/pc/editor_duelists_runtime.py holds this to the game's frames."""
        grey = portrait.in_game(flat(96, 96, (100, 150, 200, 255)), 1)
        self.assertEqual(grey.pixel(5, 5), tuple(portrait.colour(100 >> 3 | (150 >> 3) << 5 | (200 >> 3) << 10)))
        # The darkest red and black both make the pack's black: the record
        # says which (0x8000 black where its colour is black, else 0x0001).
        self.assertEqual(portrait.in_game(flat(96, 96, (9, 0, 0, 255)), 1).pixel(0, 0), (8, 0, 0, 255))
        self.assertEqual(portrait.in_game(flat(96, 96, (0, 0, 0, 255)), 1).pixel(0, 0), (0, 0, 0, 255))
        # 48x48 or less is the record, its 64 colours.
        small = sample(48, 48)
        self.assertEqual(portrait.in_game(small, 1), portrait.record_image(portrait.record_from(small)))

    def test_the_discs_portraits(self):
        wa = fixture().wa
        image = portrait.disc_portrait(wa, 8)
        self.assertEqual(image.size, (48, 48))
        word = art_colour(48, 8)                            # row 0 of duelist 8 is entry 8
        self.assertEqual(image.pixel(0, 0), tuple(portrait.colour(word)))


class RosterTest(unittest.TestCase):
    def setUp(self):
        self.p = Project(fixture().game())
        self.p.info.id = "shadow"
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name) / "shadow"

    def test_places_on_the_grid(self):
        """Asked-for slots first in read order, then the lowest free place,
        never going back below the last one handed out (place_pending)."""
        p = self.p
        a = roster.add_copy(p, 1, "A")
        b = roster.add_copy(p, 2, "B", slot=40)
        c = roster.add_copy(p, 3, "C", slot=40)          # taken: goes where there is room
        d = roster.add_copy(p, 4, "D", slot=85)
        places = roster.placement(p)
        self.assertEqual(places[b], 40)
        self.assertEqual(places[d], 85)
        # Read order is the folder's files by name: a, c.
        self.assertEqual((places[a], places[c]), (41, 42))
        self.assertEqual(roster.pages(p), 3)
        self.assertEqual(roster.page_of(85), 3)
        self.assertEqual(roster.cell_of(45), (1, 0))       # the sixth cell: row 2, column 1
        self.assertEqual(roster.where(45), "page 2, row 2, column 1")
        text = "\n".join(str(i) for i in validate.validate(p) if i.area == "Duelists")
        self.assertIn("slot 40 is taken by B", text)
        self.assertEqual(roster.named(p, "85"), d)
        self.assertEqual(roster.named(p, "shadow:a"), a)
        self.assertEqual(roster.named(p, "c"), c)           # by its name
        self.assertEqual(roster.named(p, "Heishin"), 8)

    def test_checks(self):
        p = self.p
        a = roster.add_copy(p, 1, "A")
        b = roster.add_copy(p, 2, "B")
        b.key = "a"
        c = roster.add_copy(p, 3, "C")
        c.extra["slot"] = 200
        c.pools["deck"] = {1: 2048}
        a.base = 0
        text = "\n".join(str(i) for i in validate.validate(p) if i.area == "Duelists")
        self.assertIn("the id a is used 2 times", text)
        self.assertIn("copies no disc duelist", text)
        self.assertIn("slot 200 is no id from 40 to 127", text)
        self.assertIn("at least 14 cards; it has 1", text)
        self.assertNotIn("unknown key 'duelists'", "\n".join(str(i) for i in validate.validate(p)))

    def test_the_folders_round_trip(self):
        """Saved as the folders, opened again the same; saved again, the same
        files; a duelist removed takes its files with it."""
        p = self.p
        a = roster.add_copy(p, 1, "Dark Simon")
        roster.set_portrait(p, a, png(sample(96, 72)))
        a.pools["deck"] = {cid: 2048 // 16 for cid in range(1, 17)}
        a.pools["tec"] = {722: 2048}
        a.extra["unlock"] = {"beat": "Heishin", "wins": 2}
        a.extra["ai"] = {"copy": "Nitemare", "search": 20}
        b = roster.add_copy(p, 15, "Pegasus Prime", slot=45)
        roster.set_portrait(p, 8, png(flat(64, 64, (10, 200, 30, 255))))
        roster.set_name(p, 8, "Heishin the Elder")
        p.pools[8]["pow"] = {1: 2048}
        manifest.save_mod(p, self.folder)
        files = sorted(f.relative_to(self.folder).as_posix() for f in self.folder.rglob("*") if f.is_file())
        self.assertEqual(files, ["decks/dark-simon.json", "drops/dark-simon.json", "duelists/dark-simon.json",
                                 "duelists/heishin.json", "duelists/pegasus-prime.json", "mod.json",
                                 "portraits/dark-simon.png", "portraits/heishin.png"])
        read = lambda rel: json.loads((self.folder / rel).read_text())  # noqa: E731
        self.assertEqual(read("duelists/dark-simon.json"), {"copy": "Simon Muran", "name": "Dark Simon",
                                                            "unlock": {"beat": "Heishin", "wins": 2},
                                                            "ai": {"copy": "Nitemare", "search": 20}})
        self.assertEqual(read("duelists/pegasus-prime.json"), {"copy": "Pegasus", "name": "Pegasus Prime", "slot": 45})
        self.assertEqual(read("duelists/heishin.json"), {"replace": "Heishin", "name": "Heishin the Elder"})
        deck = read("decks/dark-simon.json")
        self.assertTrue(deck["replace"])
        self.assertEqual(len(deck), 17)
        self.assertEqual(read("drops/dark-simon.json"), {"tec": {"replace": True, "Card 722": 2048}})
        built = read("mod.json")
        self.assertNotIn("duelists", built)
        self.assertEqual(built["drops"], {"Heishin": {"pow": {"replace": True, "Blue Dragon": 2048}}})
        again, messages = manifest.open_mod(p.retail, self.folder)
        self.assertEqual([(e.key, e.base, e.replace, e.name, e.slot, e.origin) for e in again.roster],
                         [("dark-simon", 1, False, "Dark Simon", None, "folder"),
                          ("heishin", 8, True, "Heishin the Elder", None, "folder"),
                          ("pegasus-prime", 15, False, "Pegasus Prime", 45, "folder")])
        mine = {e.key: e for e in again.roster}
        self.assertEqual(mine["dark-simon"].pools, {k: {c: w for c, w in v.items() if w} for k, v in a.pools.items()})
        self.assertEqual(mine["pegasus-prime"].pools, p.retail.pools[15])
        self.assertEqual(mine["dark-simon"].portrait, a.portrait)
        self.assertEqual(mine["dark-simon"].extra, a.extra)
        self.assertEqual(again.pools[8]["pow"], {1: 2048})
        before = {f: f.read_bytes() for f in self.folder.rglob("*") if f.is_file()}
        manifest.save_mod(again, self.folder)
        self.assertEqual({f: f.read_bytes() for f in self.folder.rglob("*") if f.is_file()}, before)
        # Out with one; its pools and face go too, the rest stays.
        roster.remove(again, mine["dark-simon"])
        roster.revert_portrait(again, 8)
        manifest.save_mod(again, self.folder)
        files = sorted(f.relative_to(self.folder).as_posix() for f in self.folder.rglob("*") if f.is_file())
        self.assertEqual(files, ["duelists/heishin.json", "duelists/pegasus-prime.json", "mod.json"])

    def test_a_written_roster_is_read_as_written(self):
        """The spec's own layout, by hand: keys the editor has no field for
        and a file it cannot place stay exactly as they were."""
        f = self.folder
        for rel, value in (("mod.json", {"id": "shadow", "name": "Shadow"}),
                           ("duelists/dark-simon.json", {"copy": "simon muran", "name": "Dark Simon",
                                                         "ranks": {"turns": [[3, 12], [32767, -40]]},
                                                         "unlock": {"story": 1762}}),
                           ("duelists/broken.json", {"copy": "Nobody"}),
                           ("decks/dark-simon.json", {"replace": True, **{f"Card {c}": 100 for c in range(10, 30)}}),
                           ("drops/dark-simon.json", {"sa-pow": {"Kuriboh": 3}, "tec": {"replace": True,
                                                                                       "Nonesuch": 1, "Card 9": 1}}),
                           ("drops/other-mod-person.json", {"pow": {"Card 4": 1}}),
                           ("decks/Heishin.json", {"Card 5": 400})):
            path = f / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(value))
        portrait_png = png(flat(80, 60, (250, 10, 10, 255)))
        (f / "portraits").mkdir()
        (f / "portraits/dark-simon.png").write_bytes(portrait_png)
        p, messages = manifest.open_mod(self.p.retail, f)
        self.assertEqual([e.key for e in p.roster], ["dark-simon"])
        e = p.roster[0]
        self.assertEqual(e.portrait, portrait_png)
        self.assertEqual(set(e.pools["deck"]), set(range(10, 30)))
        self.assertEqual(e.pools["tec"], {9: 2048})
        self.assertEqual(e.kept["tec"], {"Nonesuch": 1})
        self.assertIn(3, e.pools["pow"])
        self.assertEqual(p.pools[8]["deck"][5], 400)
        self.assertTrue(any("broken" in m for m in messages))
        self.assertTrue(any("other-mod-person" in m for m in messages))
        out = Path(self.tmp.name) / "copy"
        manifest.save_mod(p, out)
        read = lambda rel: json.loads((out / rel).read_text())  # noqa: E731
        self.assertEqual(read("duelists/dark-simon.json"), json.loads((f / "duelists/dark-simon.json").read_text()))
        self.assertEqual(read("duelists/broken.json"), {"copy": "Nobody"})              # left as it is
        self.assertEqual(read("drops/other-mod-person.json"), {"pow": {"Card 4": 1}})
        self.assertFalse((out / "decks/Heishin.json").exists())                         # now in mod.json
        self.assertIn("Card 5", str(read("mod.json")["decks"]["Heishin"]))
        self.assertEqual(read("drops/dark-simon.json")["tec"], {"replace": True, "Card 9": 2048, "Nonesuch": 1})
        self.assertEqual((out / "portraits/dark-simon.png").read_bytes(), portrait_png)
        # And the pools it wrote come back as the same pools.
        again, _ = manifest.open_mod(p.retail, out)
        self.assertEqual(again.roster[0].pools, e.pools)
        self.assertEqual(again.pools[8], p.pools[8])

    def test_an_id_with_a_space(self):
        """duelists/Dark Simon.json is the spec's own example: read, edited and
        written back under its name, its pools found by it."""
        f = self.folder
        (f / "duelists").mkdir(parents=True)
        (f / "decks").mkdir()
        (f / "mod.json").write_text(json.dumps({"id": "shadow"}))
        (f / "duelists/Dark Simon.json").write_text(json.dumps({"copy": "Heishin"}))
        (f / "decks/Dark Simon.json").write_text(json.dumps({"Card 5": 300}))
        p, messages = manifest.open_mod(self.p.retail, f)
        e = roster.find(p, "Dark Simon")
        self.assertIsNotNone(e)
        self.assertEqual(e.pools["deck"][5], 300)
        self.assertEqual([i for i in validate.validate(p) if i.area == "Duelists"], [])
        e.name = "Dark Simon"
        manifest.save_mod(p, f)
        self.assertEqual(json.loads((f / "duelists/Dark Simon.json").read_text()), {"copy": "Heishin",
                                                                                    "name": "Dark Simon"})
        self.assertEqual(json.loads((f / "decks/Dark Simon.json").read_text())["Card 5"], 300)

    def test_a_manifest_list_stays_a_list(self):
        p = Project(self.p.retail)
        data = {"id": "shadow", "duelists": [{"id": "dark-simon", "copy": "Heishin", "name": "Dark Simon",
                                              "unlock": {"beat": "Heishin"}},
                                             {"copy": "Teana", "name": "Teana Two"},
                                             {"copy": "Nobody At All", "id": "x"}],
                "decks": {"shadow:dark-simon": {"Card 2": 1000}}}
        messages = manifest.apply(p, data)
        self.assertEqual([e.key for e in p.roster], ["dark-simon", "teana-two"])
        self.assertTrue(any("has no id" in m for m in messages))
        built = manifest.build(p)
        self.assertEqual(built["duelists"], [data["duelists"][0], {"id": "teana-two", "copy": "Teana",
                                                                   "name": "Teana Two"}, data["duelists"][2]])
        self.assertNotIn("decks", built)                    # its deck is in decks/dark-simon.json
        drops, decks = manifest._pool_tables(p)
        self.assertEqual(decks[p.roster[0]]["Card 2"], 1000)

    def test_all_reaches_the_mods_own(self):
        """"all" edits every duelist in the game, the mod's own among them."""
        p = self.p
        e = roster.add_copy(p, 3, "C")
        manifest.read_pools(p, {"all": {"pow": {"Card 7": 100}}}, False, [])
        self.assertEqual(e.pools["pow"][7], 100)
        self.assertEqual(p.pools[3]["pow"][7], 100)
        drops, _ = manifest._pool_tables(p)
        self.assertEqual(list(drops), ["all"])              # one edit for everybody, the copy too

    def test_a_card_taken_out_leaves_the_copies_pools(self):
        p = self.p
        added = p.add_card(1)
        e = roster.add_copy(p, 3, "C")
        e.pools["deck"][added] = 50
        p.remove_card(added)
        self.assertNotIn(added, e.pools["deck"])

    def test_undo_keeps_the_roster_and_the_files_on_disk(self):
        """Undo brings the roster back, but not an older idea of which files
        are on disk: saved, undone and saved again leaves no file behind."""
        from fm_editor import history
        p = self.p
        before = history.Snapshot(p)
        roster.add_copy(p, 3, "C")
        snap = history.Snapshot(p)
        restored = snap.restore(p.retail)
        self.assertEqual([e.key for e in restored.roster], ["c"])
        self.assertIsNot(restored.roster[0], p.roster[0])
        manifest.save_mod(p, self.folder)
        self.assertTrue((self.folder / "duelists/c.json").exists())
        undone = before.restore(p.retail, self.folder, p.roster_owned)
        self.assertEqual(undone.roster, [])
        manifest.save_mod(undone, self.folder)
        self.assertFalse((self.folder / "duelists/c.json").exists())


class DuelistsTabTest(GuiCase):
    def test_add_picture_place_and_remove(self):
        app, tab = self.app, self.app.duelists
        p = app.project
        app.notebook.select(tab)
        app.update()
        # Page 1 is the disc's forty, each with its face.
        self.assertEqual(tab.list.get_children(), ("page:1",))
        self.assertEqual(len(tab.list.get_children("page:1")), 40)
        self.assertTrue(tab.list.item("8", "image"))
        tab.goto((8, "deck"))
        dialog = tab.add()
        self.assertEqual(dialog.title(), "Add a duelist")
        children = [w for w in dialog.winfo_children()]
        self.assertTrue(children)
        name = next(v for k, v in vars_of(dialog).items() if k == "name")
        name.set("Dark Heishin")
        dialog.ok()
        e = roster.find(p, "dark-heishin")
        self.assertIsNotNone(e)
        self.assertEqual(e.base, 8)
        self.assertEqual(tab.duelist, "dark-heishin")
        self.assertEqual(tab.list.get_children(), ("page:1", "page:2"))
        self.assertEqual(tab.list.set("+dark-heishin", "id"), "40")
        self.assertIn("page 2, row 1, column 1", tab.place_label.cget("text"))
        # Its pools are Heishin's, edited as the disc duelists' are.
        self.assertEqual(tab.current_pool(), p.pools[8]["deck"])
        first = tab.tree.get_children()[0]
        tab.tree.selection_set(first)
        tab.weight.set("0")
        tab.set_weight()
        self.assertNotIn(int(first), e.pools["deck"])
        self.assertIn(int(first), p.pools[8]["deck"])
        self.assertEqual(tab.tree.heading("retail", "text"), "Base")
        # A picture: the three views fill, and the list's face is its own.
        picture = Path(self.tmp.name) / "face.png"
        pngio.write(picture, flat(100, 100, (240, 40, 40, 255)))
        tab.use_picture(str(picture))
        self.assertEqual(e.portrait, picture.read_bytes())
        self.assertIn("100×100", tab.canvases["picture"][1].cget("text"))
        self.assertIn("own size", tab.canvases["sharp"][1].cget("text"))
        self.assertIn("face", tab.list.set("+dark-heishin", "state"))
        # Name and place: slot 45 is the sixth cell of page 2.
        dialog = tab.edit()
        fields = vars_of(dialog)
        fields["auto"].set(False)
        fields["slot"].set("45")
        dialog.ok()
        self.assertEqual(e.slot, 45)
        self.assertEqual(tab.list.set("+dark-heishin", "id"), "45")
        self.assertIn((1, 0), tab.cell_at)
        # Duplicate, then remove the copy: the original is shown again.
        tab.duplicate()
        self.assertEqual(len(roster.copies(p)), 2)
        with mock.patch("tkinter.messagebox.askyesno", return_value=True):
            tab.remove_duelist()
        self.assertEqual([c.key for c in roster.copies(p)], ["dark-heishin"])
        # A disc duelist's name and face make its replacement, and go with them.
        tab.goto((3, None))
        dialog = tab.edit()
        vars_of(dialog)["name"].set("Joey")
        dialog.ok()
        self.assertEqual(roster.replacement(p, 3).name, "Joey")
        self.assertEqual(tab.list.item("3", "text").strip(), "Joey")
        dialog = tab.edit()
        vars_of(dialog)["name"].set("Jono")
        dialog.ok()
        self.assertIsNone(roster.replacement(p, 3))
        tab.use_picture(str(picture))
        self.assertIsNotNone(roster.replacement(p, 3))
        tab.revert_picture()
        self.assertIsNone(roster.replacement(p, 3))
        # The page map: a click on a cell shows that duelist.
        tab.goto((8, None))
        tab.page_shown = 2
        tab.fill_map()
        cell = tab.map.coords(tab.map.find_all()[5])
        tab.map_click(type("E", (), {"x": int(cell[0]) + 2, "y": int(cell[1]) + 2})())
        self.assertEqual(tab.duelist, "dark-heishin")

    def test_heading_sorts_within_each_page(self):
        app, tab = self.app, self.app.duelists
        roster.add_copy(app.project, 1, "Zed")
        roster.add_copy(app.project, 2, "Abe")
        tab.refresh()
        tab.list.sorting.choose("#0")
        names = [tab.list.item(i, "text").strip() for i in tab.list.get_children("page:2")]
        self.assertEqual(names, ["Abe", "Zed"])
        self.assertEqual(tab.list.get_children(), ("page:1", "page:2"))
        tab.list.sorting.choose("id")
        tab.list.sorting.choose("id")
        self.assertEqual(tab.list.get_children("page:1")[0], "39")


def vars_of(dialog) -> dict:
    """The fields a FormDialog's build made (the tab keeps them in a closure)."""
    for cell in dialog.on_ok.__closure__ or ():
        value = cell.cell_contents
        if isinstance(value, dict) and "name" in value:
            return value
    raise AssertionError("no fields")


if __name__ == "__main__":
    unittest.main()
