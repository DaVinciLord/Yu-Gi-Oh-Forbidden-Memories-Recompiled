"""The UI tab (ui_tab.py, ui_title.py, ui_duel.py) and what it writes: the
menus laid out as title_config.c lays them out, the checks ui_config.c
makes (ui_rules.py), and each page's edits landing in "title", "menu" and
"ui" as the game reads them, saved and opened again.

    python -m unittest discover -s tools/pc/fm_editor/tests -t tools/pc
"""
import struct
import tempfile
import unittest
import zlib
from pathlib import Path
from unittest import mock

from fm_editor import manifest, pngio, ui_assets, ui_rules, validate
from fm_editor.model import Project
from fm_editor.tests.test_data import fixture
from fm_editor.tests.test_gui import GuiCase


def project(other=None) -> Project:
    p = Project(fixture().game())
    p.info.id = "uimod"
    p.other = dict(other or {})
    return p


def png(path: Path, width=16, height=8, colour=(200, 40, 40, 255)) -> Path:
    pngio.write(path, pngio.Image(width, height, bytes(colour) * (width * height)))
    return path


class SceneTest(unittest.TestCase):
    """ui_title.Scene against tests/pc/title_config_test.c's layout cases."""

    def places(self, other, menu=0):
        from fm_editor.ui_title import Scene
        return Scene(project(other)).places(menu)

    def test_retail(self):
        places = self.places({})
        self.assertEqual([places[n][1] for n in ("new_game", "load", "duel", "trade", "options")], [50, 82, 114, 146, 178])
        self.assertEqual(self.places({}, 1)["campaign"], (160, 42))

    def test_hidden_close_up(self):
        places = self.places({"title": {"entries": {"duel": {"hide": True}, "trade": {"hide": True}}}})
        self.assertEqual((places["new_game"][1], places["load"][1], places["options"][1]), (82, 114, 146))
        self.assertNotIn("duel", places)

    def test_spacing_and_own_y(self):
        places = self.places({"title": {"spacing": 40, "entries": {"options": {"y": 200}}}})
        self.assertEqual((places["new_game"][1], places["load"][1], places["options"][1]), (34, 74, 200))

    def test_all_hidden_shows_the_entries(self):
        hidden = {name: {"hide": True} for name in ("new_game", "load", "duel", "trade", "options")}
        places = self.places({"title": {"entries": hidden}})
        self.assertEqual(places["new_game"][1], 50)

    def test_buttons_and_order(self):
        from fm_editor.ui_title import Scene
        other = {"menu": {"buttons": [{"id": "credits", "label": "CREDITS"},
                                      {"id": "quick", "menu": "second", "label": "QUICK"}],
                          "order": {"first": ["new_game", "credits", "load"]}}}
        scene = Scene(project(other))
        self.assertEqual([i["name"] for i, _ in scene.order(0)],
                         ["new_game", "uimod:credits", "load", "duel", "trade", "options"])
        self.assertEqual([i["name"] for i, _ in scene.order(1)][-1], "uimod:quick")
        self.assertEqual(scene.places(0)["uimod:credits"], (160, 50 + 1 * 32 - 16))

    def test_fit(self):
        from fm_editor.ui_title import fit
        self.assertEqual(fit(1280, 960, 320, 240), (320, 240))          # 4x a whole screen
        self.assertEqual(fit(800, 64, 320, 120, want_w=200), (200, 16))
        self.assertEqual(fit(400, 112, 256, 64, guess_h=32), (100, 28))  # an item drawn at 4x


class RulesTest(unittest.TestCase):
    def test_clean(self):
        p = project({"ui": {"duel": {"lp_player": {"x": -20, "scale": 150, "tint": "#FF0000", "label": "ME",
                                                   "digits": 0x00FF00, "hide": False}}}})
        self.assertEqual(ui_rules.check(p, lambda name: True), [])

    def test_mistakes(self):
        p = project({"ui": {"duel": {"card_bar": {"x": 4}, "field": {"label": "F", "scale": 999},
                                     "lp": {}, "hand_cursor": {"tint": "red", "image": "../x.png"},
                                     "field_cursor": {"image": "ui/missing.png"}}, "menu": 1},
                     "title": {"images": [{"x": 3}] + [{"image": "a.png"}] * 8}})
        found = {(where, message.split(" ")[0]) for _, where, message in ui_rules.check(p, lambda n: n == "a.png")}
        self.assertIn(("ui.menu", "unknown"), found)
        self.assertIn(("ui.duel.card_bar", "the"), found)
        self.assertIn(("ui.duel.field", "has"), found)
        self.assertIn(("ui.duel.field", "\"scale\""), found)
        self.assertIn(("ui.duel.lp", "no"), found)
        self.assertIn(("ui.duel.hand_cursor", "\"tint\""), found)
        self.assertIn(("ui.duel.hand_cursor", "\"image\""), found)
        self.assertIn(("ui.duel.field_cursor", "ui/missing.png"), found)
        self.assertIn(("title.images", "at"), found)
        self.assertIn(("title.images[0]", "a"), found)

    def test_validate_takes_the_keys(self):
        p = project({"title": {"logo": {"tint": "#FF0000"}}, "menu": {"spacing": 28}, "ui": {"duel": {}}})
        issues = validate.validate(p)
        self.assertFalse([i for i in issues if i.area == "Mod info" and i.where in ("title", "menu", "ui")])


class AssetsTest(unittest.TestCase):
    def test_vram_sprite(self):
        vram = ui_assets.Vram()
        # A 4-bit texel 3 at u 1 of page (64, 0), palette 0 at (0, 10): red.
        vram.words[0 * 1024 + 64] = 0x0030
        vram.words[10 * 1024 + 3] = 0x001F
        image = vram.sprite(64, 0, 4, 0, 10, 0, 0, 2, 1)
        self.assertEqual(image.pixel(0, 0), (0, 0, 0, 0))
        self.assertEqual(image.pixel(1, 0), (255, 0, 0, 255))
        self.assertEqual(vram.sprite(64, 0, 4, 0, 10, 0, 0, 2, 1, mirrored=True).pixel(0, 0), (255, 0, 0, 255))

    def test_columns(self):
        vram = ui_assets.Vram()
        data = bytearray(2048 * 17)
        struct.pack_into("<H", data, 2048 * 16, 0x1234)      # sector 16: the second column's first tile
        vram.columns(bytes(data), 0, 17, 512, 256)
        self.assertEqual(vram.words[256 * 1024 + 512 + 64], 0x1234)

    def test_without_the_disc(self):
        self.assertFalse(ui_assets.TitleArt(None).ok)
        self.assertFalse(ui_assets.DuelArt(b"").ok)

    def test_tint_and_subtract(self):
        image = pngio.Image(1, 1, bytes((200, 100, 50, 255)))
        self.assertEqual(ui_assets.tint(image, 0x808080).pixel(0, 0)[:3], (100, 50, 25))
        self.assertEqual(ui_assets.subtract(image, 64).pixel(0, 0), (136, 36, 0, 255))
        self.assertEqual(ui_assets.parse_colour("#80c0ff"), 0x80C0FF)
        self.assertEqual(ui_assets.parse_colour("nope", 7), 7)


class UiTabTest(GuiCase):
    def setUp(self):
        super().setUp()
        self.tab = self.app.ui
        self.app.notebook.select(self.tab)
        self.app.update()
        self.folder = Path(tempfile.mkdtemp())
        self.picture = png(self.folder / "art.png", 64, 20)

    def choose(self, path):
        return mock.patch("fm_editor.ui_tab.filedialog.askopenfilename", return_value=str(path))

    def page(self, name):
        self.tab.page_name.set(name)
        self.tab.show_page()
        self.app.update()
        return self.tab.pages[name]

    def test_duel_page(self):
        page = self.page("duel")
        page.select("lp_player")
        page.moved("lp_player", -230, 12)
        page.wheel("lp_player", 1)
        page.wheel("lp_player", 1)
        page.tint.set(0xFF8080)
        page.set_colour("tint", 0xFF8080)
        page.set_colour("digits", 0x80FF80)
        page.vars["label"].set("ME")
        page.typed("label")
        with self.choose(self.picture):
            page.choose_image()
        page.select("card_bar")
        page.moved("card_bar", 10, 10)          # stays put: noted, nothing written
        page.set_colour("tint", 0xC0C0FF)
        page.select("field_cursor")
        page.hidden.set(True)
        page.set_hidden()
        duel = self.app.project.other["ui"]["duel"]
        self.assertEqual(duel["lp_player"], {"x": -230, "y": 12, "scale": 120, "tint": "#FF8080", "digits": "#80FF80",
                                             "label": "ME", "image": "ui/duel-lp-player.png"})
        self.assertEqual(duel["card_bar"], {"tint": "#C0C0FF"})
        self.assertEqual(duel["field_cursor"], {"hide": True})
        self.assertIn("ui/duel-lp-player.png", self.app.project.files)
        self.assertTrue(self.app.dirty)
        # Back to the game's: the element and then the whole key go.
        page.select("field_cursor")
        page.reset()
        self.assertNotIn("field_cursor", self.app.project.other["ui"]["duel"])
        page.reset_all()
        self.assertNotIn("ui", self.app.project.other)

    def test_title_page(self):
        page = self.page("title")
        page.select("background")
        page.background.set("color", "#102040")
        page.background.picture.set(False)
        page.background.set("picture", False, True)
        with self.choose(self.picture):
            page.add_picture()
        page.moved(("picture", 0), 10, -60)
        page.add_text()
        page.text_vars["text"].set("v1.0")
        page.text_typed("text")
        page.moved(("text", 0), 100, 0)
        page.select("logo")
        page.moved("logo", 0, -20)
        page.set_layer("tint", "#FFD060", "#FFFFFF")
        page.select("copyright")
        page.layer_hidden.set(True)
        page.set_layer("hide", True)
        title = self.app.project.other["title"]
        self.assertEqual(title["background"], {"color": "#102040", "picture": False})
        self.assertEqual(title["images"], [{"image": "ui/title-picture.png", "x": 170, "y": 60}])
        self.assertEqual(title["text"][0]["text"], "v1.0")
        self.assertEqual(title["text"][0]["x"], 260)
        self.assertEqual(title["logo"], {"y": -20, "tint": "#FFD060"})
        self.assertEqual(title["copyright"], {"hide": True})
        page.select(("picture", 0))
        page.remove_picture()
        self.assertNotIn("images", self.app.project.other["title"])

    def test_menu_page(self):
        page = self.page("menu")
        page.add_button()
        name = f"{self.app.project.info.id}:button1"
        self.assertEqual(page.chosen, name)
        page.item_vars["label"].set("CREDITS")
        page.item_typed("label")
        page.move(-1)
        page.move(-1)
        page.chosen = "trade"
        page.toggle_hidden()
        page.chosen = "options"
        page.item_vars["label"].set("SETTINGS")
        page.item_typed("label")
        page.chosen = name
        page.fill_form()
        page.action_box.current(page.action_choices.index("quit"))
        page.set_action()
        menu = self.app.project.other["menu"]
        self.assertEqual(menu["buttons"][0]["label"], "CREDITS")
        self.assertEqual(menu["buttons"][0]["action"], "quit")
        self.assertEqual(menu["order"]["first"], ["new_game", "load", "duel", "button1", "trade", "options"])
        self.assertEqual(menu["entries"]["trade"], {"hide": True})
        self.assertEqual(menu["entries"]["options"], {"label": "SETTINGS"})
        page.remove()
        self.assertNotIn("buttons", self.app.project.other["menu"])
        self.assertNotIn("button1", self.app.project.other["menu"]["order"]["first"])

    def test_saved_and_opened_again(self):
        page = self.page("duel")
        page.select("field")
        page.moved("field", 240, 0)
        with self.choose(self.picture):
            page.choose_image()
        title = self.page("title")
        with self.choose(self.picture):
            title.add_picture()
        folder = self.folder / "mod"
        manifest.save_mod(self.app.project, folder)
        self.assertTrue((folder / "ui" / "duel-field.png").is_file())
        self.assertTrue((folder / "ui" / "title-picture.png").is_file())
        opened, messages = manifest.open_mod(self.app.retail, folder)
        self.assertEqual(opened.other["ui"], self.app.project.other["ui"])
        self.assertEqual(opened.other["title"], self.app.project.other["title"])
        self.assertFalse([i for i in validate.validate(opened) if i.area == "UI"], messages)
        # Shown again from the folder (the pictures are read from it).
        self.app.set_project(opened)
        self.page("duel").draw()
        self.page("title").draw()

    def test_pages_draw_without_the_disc(self):
        for name in ("title", "menu", "duel"):
            page = self.page(name)
            page.fill()
        self.assertFalse(self.tab.title_art().ok)
