"""The window, driven as a user would, on synthetic game files. Skipped
where there is no Tk or no display (Tk cannot start)."""
import json
import tempfile
import unittest
from unittest import mock

try:
    import tkinter as tk
except ImportError:     # a Python built without Tk
    tk = None
from pathlib import Path

from fm_editor.tests.test_data import fixture


class GuiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if tk is None:
            raise unittest.SkipTest("this Python has no Tk")
        try:
            probe = tk.Tk()
            probe.destroy()
        except tk.TclError as problem:
            raise unittest.SkipTest(f"no display for Tk: {problem}")
        cls.tmp = tempfile.TemporaryDirectory()
        folder = Path(cls.tmp.name) / "game"
        (folder / "DATA").mkdir(parents=True)
        f = fixture()
        (folder / "SLUS_014.11").write_bytes(f.slus)
        (folder / "DATA" / "WA_MRG.MRG").write_bytes(f.wa)
        cls.game = folder

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        from fm_editor import settings
        from fm_editor.app import App
        # Never the user's own settings (a dark mode they chose, say).
        self.settings = Path(self.tmp.name) / "config" / "settings.json"
        self.settings.unlink(missing_ok=True)
        patcher = mock.patch.object(settings, "path", lambda: self.settings)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.app = App(ask=False, autostart=False)
        self.app.withdraw()
        self.app.update()
        self.app.start(str(self.game), None, False)
        self.app.update()

    def tearDown(self):
        self.app.dirty = False
        self.app.destroy()

    def test_edit_and_save(self):
        app = self.app
        cards = app.cards
        cards.tree.selection_set("1")
        cards.select()
        cards.vars["name"].set("Bulbasaur")
        cards.vars["attack"].set("1180")
        cards.vars["star1"].set("Venus")
        self.assertTrue(cards.apply())
        self.assertEqual(app.project.cards[1].name, "Bulbasaur")
        self.assertTrue(app.dirty)
        cards.add_card()
        new = max(app.project.added)
        self.assertEqual(app.project.added[new].base, 1)
        # a pool weight
        app.duelists.duelist = 2
        app.duelists.pool.set("pow")
        app.duelists.fill()
        first = app.duelists.tree.get_children()[0]
        app.duelists.tree.selection_set(first)
        app.duelists.weight.set("0")
        app.duelists.set_weight()
        self.assertNotIn(int(first), app.project.pools[2]["pow"])
        issues = app.problems.run()
        self.assertTrue(any("add up to" in i.message for i in issues))
        app.duelists.normalize()
        self.assertEqual(sum(app.project.pools[2]["pow"].values()), 2048)
        # mod info
        app.info.vars["id"].set("gui-test")
        self.assertTrue(app.info.commit())
        out = Path(self.tmp.name) / "saved"
        app.project.source_dir = out
        self.assertTrue(app.save())
        data = json.loads((out / "mod.json").read_text(encoding="utf-8"))
        self.assertEqual(data["id"], "gui-test")
        self.assertEqual(data["cards"][0], {"replace": 1, "name": "Bulbasaur", "attack": 1180,
                                            "stars": ["Venus", data["cards"][0]["stars"][1]]})
        self.assertEqual(data["cards"][1]["copy"], 1)
        self.assertIn("Teana", data["drops"])
        # and back
        app.load_mod(out)
        self.assertEqual(app.project.cards[1].name, "Bulbasaur")
        self.assertEqual(len(app.project.added), 1)

    def test_art(self):
        from fm_editor import art, pngio
        from fm_editor.tests.test_art import gradient
        app = self.app
        app.notebook.select(app.art)
        app.update()
        app.art.goto(2)
        self.assertEqual(app.art.current, 2)
        picture = Path(self.tmp.name) / "picture.png"
        pngio.write(picture, gradient(408, 384))
        self.assertTrue(app.art.use_file("art", str(picture)))
        self.assertEqual(app.art.tree.item("2", "values")[3], "picture, thumbnail")
        self.assertTrue(app.dirty)
        out = Path(self.tmp.name) / "saved-art"
        app.project.info.id = "art-test"
        app.project.source_dir = out
        self.assertTrue(app.save())
        data = json.loads((out / "mod.json").read_text(encoding="utf-8"))
        self.assertEqual(data["textures"], "textures")
        app.load_mod(out)
        app.notebook.select(app.art)
        app.update()
        app.art.goto(2)
        self.assertEqual(art.changed_cards(app.project), {2})
        self.assertIn("Internal 4x", app.art.rows["art"]["info"].cget("text"))
        app.art.revert("art")
        self.assertEqual(art.changed_cards(app.project), set())

    def test_tabs_fill(self):
        app = self.app
        for tab in app.tabs:
            app.notebook.select(tab)
            app.update()
        app.fusions.search.set("Blue Dragon")
        self.assertTrue(app.fusions.tree.get_children())
        app.equips.equips.selection_set("651")
        app.equips.select()
        self.assertEqual(len(app.equips.monsters.get_children()), 30)
        self.assertEqual(len(app.rituals.tree.get_children()), 20)   # every ritual card, with or without a recipe

    def test_dark_mode(self):
        from fm_editor import theme
        from fm_editor.app import App
        app = self.app
        text = app.info.description
        light = text.cget("background")
        app.dark.set(True)
        app.toggle_dark()
        self.assertEqual(json.loads(self.settings.read_text(encoding="utf-8")), {"dark": True})
        self.assertEqual(app.theme.style.theme_use(), theme.DARK_THEME)
        self.assertEqual(text.cget("background"), theme.FIELD)
        self.assertEqual(str(app.cards.tree.tag_configure("changed", "foreground")), theme.TAGS["changed"][1])
        dialog = tk.Toplevel(app)       # made after the switch: the option database
        self.assertEqual(dialog.cget("background"), theme.BG)
        dialog.destroy()
        # remembered at the next start, where an importer adds its menu entry
        # after the window (and, on Windows, the strip's clone of File) is made
        other = App(ask=False, autostart=False)
        other.withdraw()
        self.assertTrue(other.dark.get())
        self.assertEqual(other.theme.style.theme_use(), theme.DARK_THEME)
        other.add_import("Probe...", lambda: None)
        if other.theme.strip is not None:
            clone = other.theme.strip.winfo_children()[0].cget("menu")      # a Tcl-made menu
            self.assertEqual(other.tk.call(clone, "index", "end"), other.file_menu.index("end"))
            self.assertEqual(other.tk.call(clone, "entrycget", other.import_index - 1, "-label"), "Probe...")
        other.destroy()
        app.dark.set(False)
        app.toggle_dark()
        self.assertEqual(json.loads(self.settings.read_text(encoding="utf-8")), {"dark": False})
        self.assertEqual(app.theme.style.theme_use(), app.theme.light)
        self.assertEqual(text.cget("background"), light)
        self.assertEqual(str(app.cards.tree.tag_configure("changed", "foreground")), theme.TAGS["changed"][0])
        self.assertTrue(app.cget("menu"))       # the window's own menu bar is back


class SettingsTest(unittest.TestCase):
    def test_missing_or_broken(self):
        from fm_editor import settings
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "sub" / "settings.json"
            with mock.patch.object(settings, "path", lambda: path):
                self.assertEqual(settings.load(), {})
                self.assertIsNone(settings.save("dark", True))
                self.assertEqual(settings.load(), {"dark": True})
                path.write_text("[not json", encoding="utf-8")
                self.assertEqual(settings.load(), {})
                path.write_text("[1, 2]", encoding="utf-8")
                self.assertEqual(settings.load(), {})


if __name__ == "__main__":
    unittest.main()
