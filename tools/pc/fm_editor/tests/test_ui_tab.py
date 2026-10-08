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
        p = project({"ui": {"duel": {"lp_player": {"y": -20, "scale": 150, "tint": "#FF0000", "label": "ME",
                                                   "digits": 0x00FF00, "hide": False},
                                     "hand_cursor": {"x": 12, "y": -30, "scale": 400}}}})
        self.assertEqual(ui_rules.check(p, lambda name: True), [])

    def test_sliding_ones(self):
        """What the game slides off the screen sideways moves up and down
        only, no larger than leaves the screen with the game's (the numbers
        tests/pc/ui_config_test.c holds the game to)."""
        self.assertEqual([ui_rules.scale_max(n) for n in ui_rules.ELEMENTS], [161, 161, 130, 100, 400, 400])
        self.assertEqual(ui_rules.scale_max("lp_player", True), 201)
        self.assertEqual(ui_rules.scale_max("field", True, 144, 48), 50)
        self.assertEqual((ui_rules.reach("lp_player", 161), ui_rules.reach("lp_player", 162)), (64, 65))
        p = project({"ui": {"duel": {"field": {"x": 170, "scale": 200}, "lp_player": {"scale": 161},
                                     "lp_opponent": {"image": "a.png", "scale": 201}}}})
        found = [(where, message) for _, where, message in ui_rules.check(p, lambda name: True)]
        self.assertEqual([w for w, _ in found], ["ui.duel.field", "ui.duel.field"])
        self.assertIn("\"x\" is left out", found[0][1])
        self.assertIn("drawn at 130%", found[1][1])

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


class DuelScreenTest(unittest.TestCase):
    """duel_screen.py: the duel's opening screen under the Duel page's pictures."""

    def test_without_the_disc(self):
        from fm_editor import duel_screen
        image = duel_screen.board_backdrop(None)
        self.assertEqual(image.size, (320, 240))
        self.assertEqual(image.pixel(160, 120), (0, 0, 0, 255))


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
        page.moved("lp_player", -230, 12)       # up and down only: the x is left out
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
        page.moved("card_bar", 10, 10)          # stays put: nothing written
        page.set_colour("tint", 0xC0C0FF)
        page.select("field_cursor")
        page.hidden.set(True)
        page.set_hidden()
        duel = self.app.project.other["ui"]["duel"]
        self.assertEqual(duel["lp_player"], {"y": 12, "scale": 120, "tint": "#FF8080", "digits": "#80FF80",
                                             "label": "ME", "image": "ui/duel-lp-player.png"})
        self.assertEqual(duel["card_bar"], {"tint": "#C0C0FF"})
        self.assertEqual(duel["field_cursor"], {"hide": True})
        self.assertIn("ui/duel-lp-player.png", self.app.project.files)
        self.assertTrue(self.app.dirty)
        # Back to the game's: the element and then the whole key go.
        page.select("field_cursor")
        page.reset()
        self.assertNotIn("field_cursor", self.app.project.other["ui"]["duel"])
        with mock.patch("fm_editor.ui_tab.messagebox.askyesno", return_value=True):
            self.tab.revert_page(page)
        self.assertNotIn("ui", self.app.project.other)
        self.assertNotIn("ui/duel-lp-player.png", self.app.project.files)

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

    def edit_every_page(self):
        duel = self.page("duel")
        duel.select("field")
        duel.moved("field", 0, 40)
        with self.choose(self.picture):
            duel.choose_image()
        title = self.page("title")
        with self.choose(self.picture):
            title.add_picture()
        title.select("logo")
        title.moved("logo", 0, -10)
        menu = self.page("menu")
        menu.add_button()
        menu.chosen = "trade"
        menu.toggle_hidden()
        self.app.project.other["keep"] = {"a": 1}
        self.app.flush_history()

    def test_revert_to_retail_and_undo(self):
        self.edit_every_page()
        other = self.app.project.other
        before = {key: other[key] for key in ("title", "menu", "ui")}
        self.assertEqual(sorted(n for n in self.app.project.files if n.startswith("ui/")),
                         ["ui/duel-field.png", "ui/title-picture.png"])
        self.assertEqual(self.tab.revert_button.instate(["disabled"]), False)
        with mock.patch("fm_editor.ui_tab.messagebox.askyesno", return_value=False) as asked:
            self.tab.revert_all()
        self.assertIn("2 picture(s) in ui/", asked.call_args[0][1])
        self.assertIn("1 button(s) of the mod's own", asked.call_args[0][1])
        self.assertEqual(self.app.project.other["ui"], before["ui"])           # said no: nothing changed
        with mock.patch("fm_editor.ui_tab.messagebox.askyesno", return_value=True):
            self.tab.revert_all()
        self.assertEqual(list(self.app.project.other), ["keep"])               # the tab's keys only
        self.assertFalse([n for n in self.app.project.files if n.startswith("ui/")])
        self.assertTrue(self.tab.revert_button.instate(["disabled"]))
        for name in ("title", "menu", "duel"):
            self.page(name)                                                      # each draws as the game's
        # One undo step brings all of it back, the pictures too.
        self.app.undo()
        self.app.update()
        self.assertEqual({key: self.app.project.other[key] for key in ("title", "menu", "ui")}, before)
        self.assertIn("ui/duel-field.png", self.app.project.files)
        self.assertIn("ui/title-picture.png", self.app.project.files)
        self.app.redo()
        self.assertEqual(list(self.app.project.other), ["keep"])

    def test_revert_page(self):
        self.edit_every_page()
        menu_before = self.app.project.other["menu"]
        self.app.project.other["title"]["spacing"] = 40          # the menus' own, under "title"
        with mock.patch("fm_editor.ui_tab.messagebox.askyesno", return_value=True):
            self.tab.revert_page(self.tab.pages["title"])
        self.assertEqual(self.app.project.other["title"], {"spacing": 40})
        self.assertEqual(self.app.project.other["menu"], menu_before)
        self.assertNotIn("ui/title-picture.png", self.app.project.files)
        self.assertIn("ui/duel-field.png", self.app.project.files)
        with mock.patch("fm_editor.ui_tab.messagebox.askyesno", return_value=True):
            self.tab.revert_page(self.tab.pages["menu"])
        self.assertNotIn("menu", self.app.project.other)
        self.assertNotIn("title", self.app.project.other)
        self.assertIn("ui", self.app.project.other)
        self.assertTrue(self.tab.pages["menu"].revert_page.instate(["disabled"]))

    def test_drag_at_a_bigger_zoom(self):
        """The preview grows with the room; a drag is in the game's pixels at any zoom."""
        from types import SimpleNamespace as Event
        page = self.page("duel")
        with mock.patch.object(page.view, "winfo_width", return_value=1000), \
                mock.patch.object(page.view, "winfo_height", return_value=800):
            page.view.seen = None
            page.view.fit()
        self.assertEqual(page.stage.zoom, 3)
        x, y, w, h = page.stage.boxes["field"]
        at = (int((x + w / 2) * 3), int((y + h / 2) * 3))
        page.stage._press(Event(x=at[0], y=at[1]))
        self.assertEqual(page.chosen, "field")
        page.stage._motion(Event(x=at[0] + 31, y=at[1] - 14))      # 10.3 and -4.7 of the game's pixels
        self.assertEqual(page.vars["y"].get(), "-5")                # the form, live; up and down only
        page.stage._release(Event(x=at[0] + 31, y=at[1] - 14))
        self.assertEqual(self.app.project.other["ui"]["duel"]["field"], {"y": -5})
        page.stage._nudge(Event(state=0), 1, 0)                    # an arrow across: nothing
        page.stage._nudge(Event(state=1), 0, 1)                    # Shift: eight
        self.assertEqual(self.app.project.other["ui"]["duel"]["field"], {"y": 3})
        # The hand's cursor moves both ways; the card bar not at all.
        x, y, w, h = page.stage.boxes["hand_cursor"]
        at = (int((x + w / 2) * 3), int((y + h / 2) * 3))
        page.stage._press(Event(x=at[0], y=at[1]))
        page.stage._motion(Event(x=at[0] + 30, y=at[1] - 15))
        page.stage._release(Event(x=at[0] + 30, y=at[1] - 15))
        self.assertEqual(self.app.project.other["ui"]["duel"]["hand_cursor"], {"x": 10, "y": -5})
        page.stage._press(Event(x=160 * 3, y=230 * 3))
        self.assertEqual(page.chosen, "card_bar")
        page.stage._motion(Event(x=170 * 3, y=200 * 3))
        page.stage._release(Event(x=170 * 3, y=200 * 3))
        page.stage._nudge(Event(state=0), 1, 1)
        self.assertNotIn("card_bar", self.app.project.other["ui"]["duel"])
        with mock.patch.object(page.view, "winfo_width", return_value=700), \
                mock.patch.object(page.view, "winfo_height", return_value=2000):
            page.view.seen = None
            page.view.fit()
        self.assertEqual(page.stage.zoom, 2)

    def test_hold_the_games(self):
        page = self.page("duel")
        page.moved("lp_player", 0, 40)
        self.tab.comparing_now(True)
        self.assertEqual(self.app.project.other["ui"]["duel"]["lp_player"], {"y": 40})   # drawn without it only
        self.assertEqual(page.stage.boxes["lp_player"][1], ui_assets.DUEL_RECTS["lp_player"][1])
        self.tab.comparing_now(False)
        self.assertEqual(page.stage.boxes["lp_player"][1], ui_assets.DUEL_RECTS["lp_player"][1] + 40)

    def test_rough_edges(self):
        from fm_editor.ui_duel import rough_edges
        from fm_editor.ui_tab import brightens
        self.assertEqual(rough_edges("lp_player", {}), [])
        self.assertEqual(rough_edges("lp_player", {"y": 40, "scale": 161}), [])     # slides with the game's
        self.assertEqual(len(rough_edges("lp_player", {"x": 4})), 1)                # a hand-written x
        self.assertEqual(len(rough_edges("field", {"scale": 200})), 1)               # drawn at 130 %
        self.assertEqual(rough_edges("hand_cursor", {"x": 4, "scale": 400}), [])
        self.assertEqual(len(rough_edges("lp_opponent", {"label": "RIVAL\u00c9", "image": "ui/a.png"})), 2)
        self.assertTrue(brightens(0xFFFF40))
        self.assertFalse(brightens(0xFFFFFF))
        self.assertFalse(brightens(0x404040))

    def test_pages_draw_without_the_disc(self):
        for name in ("title", "menu", "duel"):
            page = self.page(name)
            page.fill()
        self.assertFalse(self.tab.title_art().ok)
