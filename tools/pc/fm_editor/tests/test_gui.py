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


class GuiCase(unittest.TestCase):
    """The window on the fixture's game files, for each test."""

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

    def click_heading(self, tree, column):
        tree.tk.call(tree.heading(column, "command"))


class GuiTest(GuiCase):

    def test_card_heading_sort_and_pending_edit(self):
        tab, p = self.app.cards, self.app.project
        for cid, name, attack, defense, kind in (
                (2, "Sort zebra", 100, 2000, 0),
                (10, "Sort alpha", 2000, 90, 1),
                (100, "Sort Bravo", 900, 100, 2)):
            p.cards[cid] = p.cards[cid].copy(name=name, attack=attack, defense=defense, type=kind)
        tab.search.set("Sort ")
        tab.tree.selection_set("10")
        tab.select()
        tab.vars["name"].set("Pending name")
        self.app.dirty = False
        expected = {"id": ("2", "10", "100"), "name": ("10", "100", "2"),
                    "atk": ("2", "100", "10"), "def": ("10", "100", "2")}
        from fm_editor.gamedata import TYPE_NAMES
        expected["type"] = tuple(str(cid) for cid in sorted(
            (2, 10, 100), key=lambda cid: TYPE_NAMES[p.cards[cid].type].casefold()))
        for column, ascending in expected.items():
            with self.subTest(column=column):
                self.click_heading(tab.tree, column)
                self.assertEqual(tab.tree.get_children(), ascending)
                self.assertTrue(tab.tree.heading(column, "text").endswith("▲"))
                self.click_heading(tab.tree, column)
                self.assertEqual(tab.tree.get_children(), tuple(reversed(ascending)))
                self.assertTrue(tab.tree.heading(column, "text").endswith("▼"))
        self.app.update()
        self.assertEqual(tab.tree.selection(), ("10",))
        self.assertEqual(tab.vars["name"].get(), "Pending name")
        self.assertEqual(p.cards[10].name, "Sort alpha")
        self.assertFalse(self.app.dirty)
        # Filtering and editing a sort value both retain the active order.
        self.click_heading(tab.tree, "atk")
        tab.search.set("Sort a")
        tab.search.set("Sort ")
        self.assertEqual(tab.tree.get_children(), expected["atk"])
        tab.vars["name"].set("Sort alpha")
        tab.vars["attack"].set("50")
        self.assertTrue(tab.apply())
        self.assertEqual(tab.tree.get_children(), ("10", "2", "100"))

    def test_equips_and_duelist_heading_sorts(self):
        app, p = self.app, self.app.project
        for cid, attack, defense in ((2, 100, 2000), (10, 2000, 90), (100, 900, 100)):
            p.cards[cid] = p.cards[cid].copy(attack=attack, defense=defense)
        equips, duelists = app.equips, app.duelists
        equip = p.equip_cards()[0]
        p.equips[equip] = {2, 10, 100}
        equips.current = equip
        equips.fill_equips()
        equips.fill()
        before = set(equips.monsters.get_children())
        self.click_heading(equips.monsters, "atk")
        selected = tuple(sorted(before, key=lambda cid: (p.cards[int(cid)].attack, int(cid))))
        self.assertEqual(equips.monsters.get_children(), selected)
        equips.monsters.selection_set("2", "10")
        self.click_heading(equips.monsters, "atk")
        self.assertEqual(set(equips.monsters.selection()), {"2", "10"})
        equips.remove()
        self.assertEqual(p.equips[equip], {100})
        self.assertTrue(equips.monsters.heading("atk", "text").endswith("▼"))
        # The left-hand lists sort too, retaining their order on refill.
        for tree, refill in ((equips.equips, equips.fill_equips), (duelists.list, duelists.fill_list)):
            self.click_heading(tree, "id")
            self.click_heading(tree, "id")
            expected = tuple(sorted(tree.get_children(), key=int, reverse=True))
            refill()
            self.assertEqual(tree.get_children(), expected)
            self.click_heading(tree, "name")
            names = [tree.set(iid, "name").casefold() for iid in tree.get_children()]
            self.assertEqual(names, sorted(names))
        for pool in ("deck", "pow", "bcd", "tec"):
            p.pools[duelists.duelist][pool] = {2: 100, 10: 900, 100: 1048}
        self.click_heading(duelists.tree, "def")
        for pool in ("deck", "pow", "bcd", "tec"):
            duelists.pool.set(pool)
            duelists.fill()
            rows = duelists.tree.get_children()
            self.assertEqual([cid for cid in rows if cid in {"2", "10", "100"}], ["10", "100", "2"])
        duelists.tree.selection_set("10")
        duelists.weight.set("50")
        duelists.set_weight()
        self.assertEqual(p.pools[duelists.duelist]["tec"][10], 50)
        self.click_heading(duelists.tree, "w")
        weights = [int(duelists.tree.set(iid, "w")) for iid in duelists.tree.get_children()]
        self.assertEqual(weights, sorted(weights))
        self.click_heading(duelists.tree, "pct")
        self.assertEqual([int(duelists.tree.set(iid, "w")) for iid in duelists.tree.get_children()], weights)

    def test_fixed_deck_sort_with_missing_cards(self):
        from fm_editor import fixed_decks
        tab, p = self.app.duelists, self.app.project
        fixed_decks.set_deck(p, tab.duelist, {2: 2, 10: 10, 100: 28})
        deck = fixed_decks.deck_of(p, tab.duelist)
        deck.kept["Missing card"] = 1
        tab.fill()
        tree = tab.fixed.tree
        self.click_heading(tree, "id")
        self.assertEqual(tree.get_children(), ("2", "10", "100", "kept:Missing card"))
        self.click_heading(tree, "id")
        self.assertEqual(tree.get_children(), ("100", "10", "2", "kept:Missing card"))
        for column in ("atk", "def", "type", "name", "copies", "weight"):
            self.click_heading(tree, column)
            if column in ("atk", "def"):
                self.assertEqual(tree.get_children()[-1], "kept:Missing card")
        self.click_heading(tree, "copies")
        tree.selection_set("10")
        tab.fixed.copies.set("5")
        tab.fixed.set_copies()
        self.assertEqual(deck.cards[10], 5)
        self.assertEqual(tree.get_children(), ("kept:Missing card", "2", "10", "100"))

    def test_edit_and_save(self):
        app = self.app
        cards = app.cards
        cards.tree.selection_set("1")
        cards.select()
        cards.vars["name"].set("Bulbasaur")
        cards.vars["attack"].set("1180")
        cards.vars["star1"].set("Venus")
        cards.notes.insert("1.0", "Buffed for the early game. <burn: 300>")
        self.assertTrue(cards.apply())
        self.assertEqual(app.project.cards[1].name, "Bulbasaur")
        self.assertEqual(app.project.notes[1], "Buffed for the early game. <burn: 300>")
        cards.search.set("early game")
        self.assertEqual(cards.tree.get_children(), ("1",))
        cards.search.set("")
        cards.filter.set("With notes")
        self.assertEqual(cards.tree.get_children(), ("1",))
        cards.filter.set(cards.FILTERS[0])
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
        issues = app.conflicts.run()
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
                                            "stars": ["Venus", data["cards"][0]["stars"][1]],
                                            "notes": "Buffed for the early game. <burn: 300>"})
        self.assertEqual(data["cards"][1]["copy"], 1)
        self.assertIn("Teana", data["drops"])
        # and back
        app.load_mod(out)
        self.assertEqual(app.project.cards[1].name, "Bulbasaur")
        self.assertEqual(len(app.project.added), 1)

    def test_magic_card_has_an_effect_not_monster_stats(self):
        app = self.app
        cards = app.cards
        monster_widgets = cards.monster_rows

        def shown(widgets):
            return all(w.winfo_manager() for w in widgets)

        cards.tree.selection_set("1")
        cards.select()
        self.assertTrue(shown(monster_widgets))
        self.assertFalse(any(w.winfo_manager() for w in cards.effect_row))
        cards.vars["type"].set("Magic")
        self.assertFalse(any(w.winfo_manager() for w in monster_widgets))
        self.assertTrue(shown(cards.effect_row))
        # The disc's magic cards to pick from, and none for a monster made one.
        values = cards.effect_box.cget("values")
        self.assertEqual(values[0], "(none)")
        self.assertIn("Card 601", values)
        self.assertNotIn("Card 651", values)        # an equip
        self.assertEqual(cards.vars["effect"].get(), "(none)")
        cards.vars["effect"].set("Card 605")
        self.assertTrue(cards.apply())
        card = app.project.cards[1]
        self.assertEqual((card.type, card.attack, card.defense, card.level, card.star1, card.star2, card.attribute),
                         (20, 0, 0, 0, 0, 0, 6))
        self.assertEqual(app.project.card_extra[1]["effect"], 605)
        self.assertEqual(app.project.effect_of(1), 605)
        # Shown again as it was stored.
        cards.tree.selection_set("2")
        cards.select()
        cards.tree.selection_set("1")
        cards.select()
        self.assertEqual(cards.vars["effect"].get(), "Card 605")
        # A disc magic card has its own effect: no "(none)", and picking it
        # again writes nothing.
        cards.tree.selection_set("610")
        cards.select()
        self.assertTrue(shown(cards.effect_row))
        self.assertNotIn("(none)", cards.effect_box.cget("values"))
        self.assertEqual(cards.vars["effect"].get(), "Card 610")
        cards.vars["effect"].set("Card 620")
        self.assertTrue(cards.apply())
        self.assertEqual(app.project.card_extra[610], {"effect": 620})
        cards.vars["effect"].set("Card 610")
        self.assertTrue(cards.apply())
        self.assertNotIn(610, app.project.card_extra)
        # A trap lists traps.
        cards.vars["type"].set("Trap")
        self.assertIn("Card 701", cards.effect_box.cget("values"))
        self.assertNotIn("Card 601", cards.effect_box.cget("values"))
        cards.vars["type"].set("Magic")
        # Saved as the game reads it, and back.
        app.info.vars["id"].set("gui-test")
        self.assertTrue(app.info.commit())
        out = Path(self.tmp.name) / "saved-effect"
        app.project.source_dir = out
        self.assertTrue(app.save())
        data = json.loads((out / "mod.json").read_text(encoding="utf-8"))
        entry = next(e for e in data["cards"] if e.get("replace") == 1)
        self.assertEqual((entry["type"], entry["effect"]), ("Magic", 605))
        app.load_mod(out)
        self.assertEqual(app.project.effect_of(1), 605)
        from fm_editor import validate
        self.assertEqual([i.message for i in validate.validate_card(app.project, 1) if "effect" in i.message], [])

    def test_monster_again_gets_its_stats_back(self):
        app = self.app
        cards = app.cards
        disc = app.project.retail.cards[1]
        cards.tree.selection_set("1")
        cards.select()
        cards.vars["type"].set("Magic")
        self.assertTrue(cards.apply())
        self.assertEqual(app.project.cards[1].attack, 0)
        # Shown again, with the zeros it was stored with.
        cards.tree.selection_set("2")
        cards.select()
        cards.tree.selection_set("1")
        cards.select()
        from fm_editor.tabs import type_label
        cards.vars["type"].set(type_label(disc.type))
        self.assertTrue(cards.apply())
        card = app.project.cards[1]
        self.assertEqual((card.attack, card.defense, card.level, card.star1, card.star2, card.attribute),
                         (disc.attack, disc.defense, disc.level, disc.star1, disc.star2, disc.attribute))

    def test_untouched_effect_stays_as_written(self):
        app = self.app
        cards = app.cards
        # A trap's effect on a magic card: shown as none, kept unless changed.
        app.project.cards[1] = app.project.cards[1].copy(type=20, attack=0, defense=0, level=0, star1=0, star2=0,
                                                         attribute=6)
        app.project.card_extra[1] = {"effect": 701}
        cards.tree.selection_set("1")
        cards.select()
        self.assertEqual(cards.vars["effect"].get(), "(none)")
        cards.tree.selection_set("2")
        cards.select()
        self.assertEqual(app.project.card_extra[1], {"effect": 701})
        from fm_editor import validate
        self.assertTrue(any("CPU" in i.message for i in validate.validate_card(app.project, 1)))
        # Made a trap, the card shows that effect and keeps it.
        cards.tree.selection_set("1")
        cards.select()
        cards.vars["type"].set("Trap")
        self.assertEqual(cards.vars["effect"].get(), "Card 701")
        self.assertTrue(cards.apply())
        self.assertEqual(app.project.card_extra[1], {"effect": 701})

    def test_converted_equip_displays_and_edits_effect_targets(self):
        app, p = self.app, self.app.project
        equip = p.add_card(3, "converted-equip")
        p.cards[equip] = p.cards[equip].copy(type=23, attack=0, defense=0)
        p.added[equip].extra["effect"] = 651
        trap = p.add_card(5, "converted-trap")
        p.cards[trap] = p.cards[trap].copy(type=21, attack=0, defense=0)
        p.added[trap].extra["effect"] = 701
        p.cards[652] = p.cards[652].copy(type=0)
        tab = app.equips
        tab.refresh()
        self.assertFalse(tab.equips.exists("652"))
        tab.current = equip
        tab.fill()
        expected = set(p.retail.equips[651])
        self.assertEqual(set(map(int, tab.monsters.get_children())), expected)
        self.assertNotIn(trap, p.equip_targets(651))
        self.assertEqual(int(tab.equips.set(str(equip), "n")), len(expected))
        tab.monsters.selection_set("5")
        tab.remove()
        self.assertEqual(p.equip_targets(equip), expected - {5})
        self.assertEqual(set(map(int, tab.monsters.get_children())), expected)
        self.assertEqual(tab.monsters.set("5", "state"), "removed")

    def test_cards_to_equips_workflow_survives_save_and_reopen(self):
        from fm_editor.model import Project
        from fm_editor import tabs
        app = self.app
        for added in (False, True):
            with self.subTest(added=added):
                app.set_project(Project(app.retail))
                app.notebook.select(app.cards)
                app.cards.goto(1)
                app.update()
                if added:
                    app.cards.add_card()
                    app.update()
                cid = app.cards.current
                app.cards.vars["type"].set("Equip")     # no effect to choose: no targets yet
                if not added:
                    self.assertTrue(app.cards.apply())
                # Switching tabs must commit the form and populate Equips;
                # do not refresh the tab or assign its current card by hand.
                app.notebook.select(app.equips)
                app.update()
                self.assertEqual(app.project.cards[cid].type, 23)
                self.assertTrue(app.equips.equips.exists(str(cid)))
                app.equips.equips.selection_set(str(cid))
                app.update()
                self.assertEqual(app.equips.current, cid)
                baseline = app.project.equip_baseline(cid)
                self.assertEqual(set(map(int, app.equips.monsters.get_children())), baseline)
                for monster in (5, 100):
                    with mock.patch.object(tabs, "pick_card", return_value=monster):
                        app.equips.add()
                expected = baseline | {5, 100}
                self.assertEqual(app.project.equip_targets(cid), expected)
                self.assertEqual(int(app.equips.equips.set(str(cid), "n")), len(expected))
                folder = Path(self.tmp.name) / f"equip-workflow-{added}"
                app.project.source_dir = folder
                with mock.patch("fm_editor.app.messagebox.askyesno", return_value=False) as warning:
                    self.assertTrue(app.save())
                    warning.assert_not_called()
                app.load_mod(folder)
                app.notebook.select(app.equips)
                app.update()
                app.equips.equips.selection_set(str(cid))
                app.update()
                self.assertEqual(app.project.equip_targets(cid), expected)
                self.assertEqual(app.equips.monsters.set("5", "state"), "added")
                self.assertEqual(app.equips.monsters.set("100", "state"), "added")
                app.equips.revert()
                self.assertEqual(app.project.equip_targets(cid), baseline)
                app.notebook.select(app.cards)
                app.cards.goto(cid)
                app.update()
                app.cards.vars["type"].set("Dragon")
                app.notebook.select(app.equips)
                app.update()
                self.assertFalse(app.equips.equips.exists(str(cid)),
                                 (app.cards.current, app.project.cards[cid].type,
                                  app.cards.vars["type"].get(), app.cards.status.cget("text")))
                self.assertTrue(all(w.instate(["disabled"]) for w in app.equips.actions.winfo_children()))

    def test_edit_equips_shortcut_applies_and_selects_the_card(self):
        app, cards = self.app, self.app.cards
        self.assertTrue(all(w.instate(["disabled"]) for w in app.equips.actions.winfo_children()))
        cards.goto(1)
        app.update()
        self.assertEqual(cards.edit_equips_button.winfo_manager(), "")
        cards.vars["type"].set("Equip")
        self.assertEqual(cards.edit_equips_button.winfo_manager(), "grid")
        cards.edit_equips_button.invoke()
        app.update()
        self.assertIs(app.notebook.current(), app.equips)
        self.assertEqual(app.equips.current, 1)
        self.assertEqual(app.equips.equips.selection(), ("1",))
        self.assertEqual(app.project.effect_of(1), 1)          # an equip has no effect to choose
        self.assertEqual(set(map(int, app.equips.monsters.get_children())), app.project.equip_baseline(1))
        self.assertTrue(all(w.instate(["!disabled"]) for w in app.equips.actions.winfo_children()))

    def test_equip_boosts_atk_and_def(self):
        app, cards = self.app, self.app.cards
        cards.goto(651)
        app.update()
        # An equip has no Retail effect: its boosts are the whole of it.
        self.assertEqual(cards.effect_box.winfo_manager(), "")
        self.assertEqual((cards.vars["equip_attack"].get(), cards.vars["equip_defense"].get()), ("500", "500"))
        self.assertEqual(cards.hints["equip_attack"].cget("text"), "")
        cards.vars["equip_attack"].set("1200")
        cards.vars["equip_defense"].set("-300")
        self.assertTrue(cards.apply())
        self.assertEqual(app.project.equip_bonus, {651: (1200, -300)})
        app.update()
        self.assertEqual(str(cards.hints["equip_attack"].cget("text")), "Retail: +500 (restore)")
        cards.restore("equip_defense")
        self.assertTrue(cards.apply())
        self.assertEqual(app.project.equip_bonus, {651: (1200, 500)})
        cards.vars["equip_attack"].set("")       # empty: the default again
        self.assertTrue(cards.apply())
        self.assertEqual(app.project.equip_bonus, {})
        cards.vars["equip_defense"].set("1e3")
        self.assertFalse(cards.apply())
        self.assertIn("DEF boosts", str(cards.status.cget("text")))
        cards.vars["equip_defense"].set("500")
        self.assertTrue(cards.apply())
        # Megamorph's are +1000.
        cards.goto(657)
        app.update()
        self.assertEqual((cards.vars["equip_attack"].get(), cards.vars["equip_defense"].get()), ("1000", "1000"))
        # A magic card made an equip loses its magic effect and starts at +500.
        cards.goto(601)
        app.update()
        app.project.card_extra[601] = {"effect": 602}
        cards.vars["type"].set("Equip")
        self.assertEqual(cards.effect_box.winfo_manager(), "")
        self.assertTrue(cards.apply())
        self.assertNotIn(601, app.project.card_extra)
        self.assertEqual(cards.vars["equip_attack"].get(), "500")
        cards.goto(1)
        app.update()
        self.assertEqual(cards.vars["equip_attack"].get(), "")

    def test_password_takes_up_to_8_digits(self):
        cards = self.app.cards
        cards.goto(2)
        self.app.update()
        entry = next(w for w in cards.form.winfo_children()
                     if w.winfo_class() == "TEntry" and str(w.cget("textvariable")) == str(cards.vars["password"]))
        entry.delete(0, "end")
        for ch in "1234x5678 9":
            entry.insert("end", ch)
        self.assertEqual(entry.get(), "12345678")
        entry.delete(0, "end")
        entry.insert(0, "123456789")
        self.assertEqual(entry.get(), "")

    def test_export_makes_a_folder_named_after_the_mod(self):
        app = self.app
        app.info.vars["id"].set("export-test")
        with tempfile.TemporaryDirectory() as where, \
                mock.patch("fm_editor.app.filedialog.askdirectory", return_value=where):
            self.assertTrue(app.save(ask=True, export=True))
            self.assertTrue((Path(where) / "export-test" / "mod.json").is_file())
            self.assertEqual(Path(app.project.source_dir), Path(where) / "export-test")

    def test_right_click_menu_closes(self):
        from fm_editor import card_links
        app = self.app
        # Only X11 menus stay up on their own: on Windows (and macOS) a posted
        # menu is native and modal -- "post" does not return until it is
        # dismissed, which would hang here -- and closes itself on a click away.
        if app.tk.call("tk", "windowingsystem") != "x11":
            self.skipTest("posted menus are modal outside X11")
        app.deiconify()
        for close in (lambda: app.notebook.select(app.fusions),
                      lambda: app.cards.tree.event_generate("<ButtonPress-1>", x=5, y=5)):
            app.notebook.select(app.cards)
            app.update()
            menu = card_links._open_menu = tk.Menu(app.cards.tree, tearoff=False)
            menu.add_command(label="Where it's used...")
            menu.post(app.winfo_rootx(), app.winfo_rooty())
            app.update()
            close()
            app.update()
            self.assertFalse(menu.winfo_exists())
            self.assertIsNone(card_links._open_menu)

    def test_card_navigation_keeps_invalid_pending_edits(self):
        cards = self.app.cards
        cards.goto(1)
        self.app.update()
        cards.vars["attack"].set("unfinished")
        self.assertFalse(cards.goto(2))
        self.app.update()
        self.assertEqual(cards.current, 1)
        self.assertEqual(cards.tree.selection(), ("1",))
        self.assertEqual(cards.vars["attack"].get(), "unfinished")

    def test_copy_has_its_replaced_base_effect(self):
        # A copy with no "effect" plays its base's (cards.c Cards_EffectId).
        project = self.app.project
        project.card_extra[610] = {"effect": 620}
        copy = project.add_card(610)
        self.assertEqual(project.effect_of(copy), 620)
        self.assertEqual(project.effect_of(611), 611)

    def test_any_card_can_use_an_independent_retail_magic_effect(self):
        from fm_editor import manifest, validate
        from fm_editor.model import Project
        app, tab = self.app, self.app.cards
        # Monster, magic, equip, ritual and trap, plus a new copy of each.
        originals = [1, 610, 651, 681, 701]
        added = [app.project.add_card(cid) for cid in originals]
        tab.refresh()
        for cid in originals + added:
            tab.tree.selection_set(str(cid))
            tab.select()
            tab.vars["type"].set("Magic")
            tab.vars["effect"].set("Card 605")
            self.assertTrue(tab.apply())
            self.assertEqual(app.project.effect_of(cid), 605)
            self.assertEqual(app.project.cards[cid].attribute, 6)
            self.assertFalse([i for i in validate.validate_card(app.project, cid) if i.level == "error"])
        # The effect source becomes a monster with another name. The effect
        # list and numeric references must keep the original retail behavior.
        tab.tree.selection_set("605")
        tab.select()
        tab.vars["type"].set("Dragon")
        tab.vars["name"].set("New monster")
        self.assertTrue(tab.apply())
        tab.tree.selection_set("1")
        tab.select()
        self.assertEqual(tab.vars["effect"].get(), "Card 605")
        built = manifest.build(app.project)
        restored = Project(app.project.retail)
        manifest.apply(restored, built)
        for cid in originals + added:
            self.assertEqual(restored.effect_of(cid), 605)
            self.assertEqual(restored.cards[cid].type, 20)
        # Changing the source to another magic effect also leaves explicit
        # users of its original effect alone.
        app.project.card_extra[605] = {"effect": 620}
        self.assertEqual(app.project.effect_of(1), 605)

    def test_duplicate_retail_effect_names_remain_distinct(self):
        tab, project = self.app.cards, self.app.project
        project.retail.cards[605].name = project.retail.cards[606].name = "Same effect name"
        tab.tree.selection_set("1")
        tab.select()
        tab.vars["type"].set("Magic")
        self.assertIn("Same effect name (605)", tab.effect_box.cget("values"))
        tab.vars["effect"].set("Same effect name (606)")
        self.assertTrue(tab.apply())
        self.assertEqual(project.effect_of(1), 606)

    def test_trap_form_thresholds_and_independent_copy_roundtrip(self):
        from fm_editor import manifest, validate
        from fm_editor.model import Project
        tab, p = self.app.cards, self.app.project
        # This synthetic disc normally places traps at 701 onward.
        for cid in range(681, 691):
            p.retail.cards[cid].type = p.cards[cid].type = 21
        copy = p.add_card(1)
        tab.refresh()
        tab.tree.selection_set(str(copy))
        tab.select()
        tab.vars["type"].set("Trap")
        tab.vars["effect"].set("Card 681")
        self.assertTrue(all(w.winfo_manager() for w in tab.effect_row + tab.trap_rows))
        self.assertFalse(any(w.winfo_manager() for w in tab.monster_rows))
        tab.vars["trap_threshold"].set("1234")
        self.assertTrue(tab.apply())
        self.assertEqual(p.cards[copy].attribute, 7)
        self.assertEqual(tab.row(copy)[0][3:5], ("", ""))
        self.assertEqual((p.cards[copy].attack, p.cards[copy].defense, p.cards[copy].star1, p.cards[copy].star2), (0, 0, 0, 0))
        self.assertFalse([i for i in validate.validate_card(p, copy) if i.level == "error"])
        built = manifest.build(p)
        entry = next(e for e in built["cards"] if "copy" in e)
        self.assertEqual((entry["type"], entry["effect"], entry["trap_threshold"]), ("Trap", 681, 1234))
        self.assertTrue(p.cards[1].is_monster())  # the copy's base stays a monster
        restored = Project(p.retail)
        manifest.apply(restored, built)
        self.assertEqual(restored.cards[copy].type, 21)
        self.assertEqual(restored.trap_threshold_override(copy), 1234)
        for invalid in ("-1", "65536", "1.5", "bad"):
            tab.vars["trap_threshold"].set(invalid)
            self.assertFalse(tab.apply())
            self.assertEqual(p.trap_threshold_override(copy), 1234)
        for valid in ("0", "65535", ""):
            tab.vars["trap_threshold"].set(valid)
            self.assertTrue(tab.apply())
            self.assertEqual(p.trap_threshold_override(copy), int(valid) if valid else None)
        tab.vars["trap_threshold"].set("700")
        self.assertTrue(tab.apply())
        # Special traps have no attack threshold. Applying the new effect
        # clears the old threshold and does not reveal monster statistics.
        tab.vars["effect"].set("Card 687")
        self.assertFalse(any(w.winfo_manager() for w in tab.trap_rows + tab.monster_rows))
        self.assertTrue(tab.apply())
        self.assertIsNone(p.trap_threshold_override(copy))
        tab.vars["type"].set("Magic")
        tab.vars["effect"].set("Card 605")
        self.assertTrue(tab.apply())
        self.assertEqual(p.cards[copy].attribute, 6)
        self.assertEqual(next(e for e in manifest.build(p)["cards"] if "copy" in e)["type"], "Magic")

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

    def test_card_starchips_save_load_and_validation(self):
        from fm_editor import manifest
        app = self.app
        cards = app.cards
        cards.tree.selection_set("1")
        cards.select()
        self.assertEqual(cards.vars["starchips"].get(), "10")
        for invalid in ("-1", "1000000", "1.5", "abc"):
            cards.vars["starchips"].set(invalid)
            self.assertFalse(cards.apply())
            self.assertEqual(app.project.starchip_cost(1), 10)
        cards.vars["starchips"].set("0")
        self.assertTrue(cards.apply())
        cards.filter.set("Changed")
        self.assertEqual(cards.tree.get_children(), ("1",))
        out = Path(self.tmp.name) / "saved-starchips"
        app.project.source_dir = out
        self.assertTrue(app.save())
        data = json.loads((out / "mod.json").read_text(encoding="utf-8"))
        self.assertEqual(data["passwords"], {"Blue Dragon": {"starchips": 0}})
        app.load_mod(out)
        cards.tree.selection_set("1")
        cards.select()
        self.assertEqual(cards.vars["starchips"].get(), "0")
        cards.vars["starchips"].set("")
        self.assertTrue(cards.apply())
        self.assertEqual(cards.vars["starchips"].get(), "10")
        self.assertNotIn("passwords", manifest.build(app.project))
        cards.filter.set("All cards")
        cards.tree.selection_set("1")
        cards.select()
        cards.add_card()
        app.update()
        self.assertFalse(cards.price.instate(["disabled"]))
        self.assertEqual(cards.vars["starchips"].get(), "999999")
        cards.vars["starchips"].set("100")
        cards.vars["password"].set("00000723")
        self.assertTrue(cards.apply())
        added = max(app.project.added)
        self.assertEqual(app.project.starchip_cost(added), 100)
        self.assertEqual(app.project.password(added), "00000723")

    def test_card_cost_does_not_flatten_percentage_rules(self):
        from fm_editor import manifest
        app = self.app
        cards = app.cards
        cards.tree.selection_set("1")
        cards.select()
        # Editing the raw rules in Mod info must not let an unchanged Cards
        # form write its old displayed price back over those rules on Save.
        app.info.other.insert("1.0", json.dumps({"passwords": {"all": {"starchips_percent": 25}}}))
        self.assertTrue(app.commit_all())
        self.assertTrue(app.commit_all())
        self.assertEqual(cards.vars["starchips"].get(), "3")
        self.assertEqual(manifest.build(app.project)["passwords"], {"all": {"starchips_percent": 25}})
        cards.vars["starchips"].set("200")
        self.assertTrue(cards.apply())
        self.assertTrue(app.commit_all())
        self.assertEqual(manifest.build(app.project)["passwords"]["Blue Dragon"], {"starchips": 200})

    def test_card_form_scrolls_and_reveals_keyboard_focus(self):
        app = self.app
        app.deiconify()
        app.geometry("1100x640")
        cards = app.cards
        cards.tree.selection_set("1")
        cards.select()
        app.update()
        scroll = cards.card_scroll
        self.assertGreater(scroll.body.winfo_reqheight(), scroll.canvas.winfo_height())
        self.assertTrue(scroll.bar.winfo_ismapped())
        self.assertGreater(scroll.canvas.winfo_width(), 200)
        self.assertTrue(app.status.winfo_ismapped())
        add = next(w for w in cards.count.master.winfo_children() if w.winfo_class() == "TButton")
        self.assertTrue(add.winfo_ismapped())
        # Wheel over an entry scrolls the form, leaving its value untouched.
        before = cards.vars["starchips"].get()
        cards.price.event_generate("<MouseWheel>", delta=-120)
        app.update()
        self.assertGreater(scroll.canvas.yview()[0], 0)
        self.assertEqual(cards.vars["starchips"].get(), before)
        cards.price.event_generate("<Button-4>")
        app.update()
        scroll.canvas.yview_moveto(0)
        buttons = [w for w in cards.form.winfo_children() if w.winfo_class() == "TFrame"]
        apply = next(w for box in buttons for w in box.winfo_children()
                     if w.winfo_class() == "TButton" and w.cget("text") == "Apply")
        apply.focus_force()
        app.update()
        self.assertGreater(scroll.canvas.yview()[0], 0)
        self.assertGreaterEqual(apply.winfo_rooty(), scroll.canvas.winfo_rooty())
        self.assertLessEqual(apply.winfo_rooty() + apply.winfo_height(),
                             scroll.canvas.winfo_rooty() + scroll.canvas.winfo_height())
        cards.price.focus_force()
        app.update()
        # At a taller window, the scroll range contracts again. The window
        # manager may cap the requested height to the available desktop.
        first, last = scroll.canvas.yview()
        short_fraction = last - first
        app.geometry("1100x1000")
        app.update()
        first, last = scroll.canvas.yview()
        self.assertGreater(last - first, short_fraction)
        body_height = scroll.body.winfo_reqheight()
        expected = min(1.0, scroll.canvas.winfo_height() / body_height)
        self.assertAlmostEqual(last - first, expected, delta=1 / body_height)
        if expected == 1.0:
            self.assertEqual((first, last), (0.0, 1.0))

    def test_card_hints_fit_and_tabs_scroll_when_the_window_is_small(self):
        from tkinter import ttk
        app = self.app
        app.deiconify()
        app.geometry("1600x960")
        app.update()
        # Windows keeps a window within wm maxsize (the screen: 1024x768 on
        # CI), so check "no scrollbars" only where the window got the size.
        roomy = app.winfo_width() >= 1600 and app.winfo_height() >= 960
        cards = app.cards
        cards.tree.selection_set("1")
        cards.select()
        app.update()
        # The form is as wide as it asks, whatever the card: the hints, set
        # after the window was shown, are not cut off.
        scroll = cards.card_scroll
        self.assertGreaterEqual(scroll.canvas.winfo_width(), scroll.body.winfo_reqwidth())
        hint = cards.hints["name"]
        self.assertGreaterEqual(hint.winfo_width(), hint.winfo_reqwidth())
        if roomy:
            self.assertFalse(cards.page.xbar.winfo_ismapped() or cards.page.ybar.winfo_ismapped())
        # A window smaller than a tab scrolls the tab instead of cutting it off.
        app.notebook.select(app.stars)
        self.assertIs(app.notebook.current(), app.stars)
        app.minsize(1, 1)
        app.geometry("700x400")
        app.update()
        page = app.stars.page
        self.assertTrue(page.xbar.winfo_ismapped() and page.ybar.winfo_ismapped())
        self.assertGreaterEqual(app.stars.winfo_height(), app.stars.winfo_reqheight())
        page.canvas.yview_moveto(1)
        app.update()
        self.assertGreater(page.canvas.yview()[0], 0)
        app.geometry("1600x960")
        app.update()
        if roomy:
            self.assertFalse(page.xbar.winfo_ismapped() or page.ybar.winfo_ismapped())
        self.assertEqual(page.canvas.cget("background"), ttk.Style(app).lookup("TFrame", "background"))

    def test_scrolled_options_keep_text_scroll_and_dark_background(self):
        from tkinter import ttk
        app = self.app
        app.deiconify()
        app.geometry("1100x640")
        cards = app.cards
        cards.tree.selection_set("1")
        cards.select()
        app.update()
        cards.text.delete("1.0", "end")
        cards.text.insert("1.0", "line\n" * 40)
        cards.text.yview_moveto(0)
        before = cards.card_scroll.canvas.yview()
        if app.tk.call("tk", "windowingsystem") == "x11":
            cards.text.event_generate("<Button-5>")
        else:
            cards.text.event_generate("<MouseWheel>", delta=-120)
        app.update()
        self.assertGreater(cards.text.yview()[0], 0)
        self.assertEqual(cards.card_scroll.canvas.yview(), before)
        app.dark.set(True)
        app.toggle_dark()
        app.update()
        self.assertEqual(cards.card_scroll.canvas.cget("background"), ttk.Style(app).lookup("TFrame", "background"))
        app.notebook.select(app.limits)
        app.limits.advanced_shown.set(True)
        app.limits._show_advanced()
        app.update()
        scroll = app.limits.scroll
        # Windows fonts can fit the whole form at 640px. Size the viewport
        # from the form itself so this exercises overflowing content there too.
        chrome_height = app.winfo_height() - scroll.canvas.winfo_height()
        app.minsize(1, 1)
        app.geometry(f"1100x{chrome_height + scroll.body.winfo_reqheight() // 2}")
        app.update()
        self.assertGreater(scroll.body.winfo_reqheight(), scroll.canvas.winfo_height())
        scroll.canvas.yview_moveto(1)
        self.assertGreater(scroll.canvas.yview()[0], 0)

    def test_packs(self):
        from fm_editor import pngio
        from fm_editor.packs_tab import SimulateDialog
        from fm_editor.tests.test_art import gradient
        app = self.app
        tab = app.packs
        app.notebook.select(tab)
        app.update()
        tab.add_pack()
        self.assertEqual(len(app.project.packs), 1)
        tab.vars["name"].set("Dragons")
        tab.vars["price"].set("50")
        self.assertTrue(tab.commit())
        tab.add_cards([1, 2, 3])
        self.assertEqual(len(tab.tree.get_children()), 3)
        tab.tree.selection_set("0:2")
        tab.weight.set("5")
        tab.set_weight()
        self.assertEqual(str(tab.tree.item("0:2", "values")[3]), "5")
        self.assertTrue(tab.tree.item("0:0", "values")[4].endswith("%"))
        # Advanced: a guarantee needs a tier of that name.
        tab.toggle_advanced()
        tab.adv["guarantee"].set("rare=1")
        self.assertTrue(tab.commit())
        self.assertTrue(any("not a tier of the pack" in i.message for i in app.conflicts.run() if i.area == "Packs"))
        tab.adv["guarantee"].set("")
        tab.adv["stock"].set("3")
        self.assertTrue(tab.commit())
        picture = Path(self.tmp.name) / "pack.png"
        pngio.write(picture, gradient(204, 192))
        tab.use_file(str(picture))
        self.assertEqual(app.project.packs[0]["image"], "packs/pack-1.png")
        for zoom in (1, 2, 4):
            tab.zoom.set(zoom)
            tab.show_picture()
        # "image_style": "full" shows the whole picture; "card" is written as no key.
        tab.vars["image_style"].set("full")
        tab.show_picture()
        self.assertEqual(tab.photos["card"].height(), 196 * 4)
        # At 1x a pixel under half opaque is clear (black here), the rest opaque, as the game's texture.
        from fm_editor.packs_tab import full_picture
        half = pngio.Image(140, 196, bytes((200, 100, 50, 100)) * (140 * 98) + bytes((200, 100, 50, 200)) * (140 * 98))
        shown = full_picture(half, 1).rgba
        self.assertEqual(shown[:4], bytes((0, 0, 0, 255)))
        self.assertEqual(shown[-4:], bytes((200, 100, 50, 255)))
        self.assertTrue(tab.commit())
        self.assertEqual(app.project.packs[0]["image_style"], "full")
        tab.vars["image_style"].set("card")
        self.assertTrue(tab.commit())
        from fm_editor import packs as packmath
        self.assertNotIn("image_style", packmath.minimize(app.project.packs[0]))
        tab.zoom.set(1)
        dialog = SimulateDialog(tab, tab.parsed()[0])
        while dialog.running:            # opened a slice at a time, the window answering between
            app.update()
        self.assertEqual(dialog.result.draws, 1000 * 5 * 4)
        # Stop shows what came so far; the window never waits for all of them.
        dialog.count.set("1000000")   # 5 cards a pack: within the cap
        dialog.run()
        app.update()
        self.assertTrue(dialog.running)
        dialog.stop()
        self.assertFalse(dialog.running)
        self.assertLess(dialog.result.packs, 1000000)
        self.assertEqual(dialog.result.draws, dialog.result.packs * 5 * 4)
        dialog.destroy()
        self.assertFalse([i for i in app.conflicts.run() if i.area == "Packs" and i.level == "error"])
        out = Path(self.tmp.name) / "saved-packs"
        app.project.info.id = "packs-test"
        app.project.source_dir = out
        self.assertTrue(app.save())
        data = json.loads((out / "mod.json").read_text(encoding="utf-8"))
        self.assertEqual(data["packs"], [{"id": "pack-1", "name": "Dragons", "price": 50,
                                          "cards": {str(app.project.ref(1)): 1, str(app.project.ref(2)): 1,
                                                    str(app.project.ref(3)): 5},
                                          "stock": 3, "image": "packs/pack-1.png"}])
        self.assertTrue((out / "packs" / "pack-1.png").is_file())
        app.load_mod(out)
        app.notebook.select(tab)
        app.update()
        self.assertEqual(tab.vars["name"].get(), "Dragons")

    def test_packs_keep_what_is_written(self):
        """Opening a mod and moving through its packs changes nothing of it;
        a copy's picture is its own; Shop settings keep a shop's other keys."""
        from fm_editor import manifest, packs as packmath, pngio
        from fm_editor.tests.test_art import gradient
        app, tab = self.app, self.app.packs
        mod = Path(self.tmp.name) / "packs-as-written"
        mod.mkdir(exist_ok=True)
        source = {"id": "written", "name": "Written", "packs": [
            {"name": "Alpha", "cards": [1, 2, 3], "cover": 2, "price": 100.0},
            {"name": "Beta", "price": 100, "duplicates": "allow", "cards": {"4": 1, "5": 1}, "mystery": 1},
            {"name": "Gamma", "cards": [6], "include_added_cards": "no", "stock": "5"}],
            "pack_shop": {"rng": "game", "shops": [{"id": "a", "name": "A", "where": "password", "extra": 1}]}}
        (mod / "mod.json").write_text(json.dumps(source), encoding="utf-8")
        app.load_mod(mod)
        app.notebook.select(tab)
        app.update()
        before = json.dumps(app.project.packs)
        for i in (1, 2, 0, 2):
            tab.list.selection_set(str(i))
            app.update()
        self.assertFalse(app.dirty)
        self.assertEqual(json.dumps(app.project.packs), before)
        # An edit changes what it edits, and leaves the rest as written.
        tab.vars["description"].set("Three cards")
        self.assertTrue(tab.commit())
        self.assertTrue(app.dirty)
        self.assertEqual(app.project.packs[2]["stock"], "5")
        self.assertEqual(app.project.packs[2]["include_added_cards"], "no")
        tab.list.selection_set("0")
        app.update()
        tab.adv["when_nothing_left"].set("sell")
        self.assertTrue(tab.commit())
        self.assertEqual(app.project.packs[0]["cover"], 2)
        self.assertEqual(app.project.packs[0]["when_nothing_left"], "sell")
        # A copy gets a picture of its own: importing on it leaves the first's.
        picture = Path(self.tmp.name) / "packs-own.png"
        pngio.write(picture, gradient(102, 96))
        tab.use_file(str(picture))
        first = app.project.packs[0]["image"]
        tab.duplicate()
        copy_image = app.project.packs[1]["image"]
        self.assertNotEqual(copy_image, first)
        self.assertEqual(app.project.files[copy_image], app.project.files[first])
        tab.use_file(str(picture))
        tab.revert_png()
        self.assertIn(first, app.project.files)
        self.assertNotIn(copy_image, app.project.files)
        # Shop settings: OK with nothing typed changes nothing; a shop's other keys stay.
        with mock.patch("fm_editor.packs_tab.FormDialog") as form:
            tab.shop_settings()
            build, ok = form.call_args[0][2], form.call_args[0][3]
            body = tk.Frame(app)
            build(None, body)
            self.assertIsNone(ok(None))
            self.assertEqual(app.project.pack_shop, packmath.minimize_rules(source["pack_shop"]))
            tab.shop_settings()
            build, ok = form.call_args[0][2], form.call_args[0][3]
            body = tk.Frame(app)
            build(None, body)
            texts = [w for w in body.grid_slaves() if isinstance(w, tk.Text)]
            texts[0].delete("1.0", "end")
            texts[0].insert("1.0", "a | Shop A\nb\n")
            self.assertIsNone(ok(None))
        self.assertEqual(app.project.pack_shop["shops"], [{"id": "a", "name": "Shop A", "where": "password",
                                                           "extra": 1}, {"id": "b"}])
        self.assertEqual(manifest.build(app.project)["pack_shop"]["shops"][0]["where"], "password")

    def test_packs_file_greys_the_tab(self):
        """"packs" naming a file: the editor does not edit it, so nothing of a
        pack is offered, but Shop settings (the manifest's) is."""
        from fm_editor.packs_tab import PacksTab
        app, tab = self.app, self.app.packs

        def enabled():
            out = []

            def walk(widget):
                for child in widget.winfo_children():
                    if isinstance(child, PacksTab.EDITABLE) and not child.instate(["disabled"]):
                        out.append(child)
                    walk(child)
            walk(tab)
            return out

        mod = Path(self.tmp.name) / "packs-in-a-file"
        mod.mkdir(exist_ok=True)
        (mod / "mod.json").write_text(json.dumps({"id": "pf", "name": "PF", "packs": "packs.json"}), encoding="utf-8")
        (mod / "packs.json").write_text(json.dumps([{"name": "Z", "cards": [1]}]), encoding="utf-8")
        app.load_mod(mod)
        app.notebook.select(tab)
        app.update()
        self.assertEqual(enabled(), [tab.shop_button])
        mod = Path(self.tmp.name) / "packs-in-the-manifest"
        mod.mkdir(exist_ok=True)
        (mod / "mod.json").write_text(json.dumps({"id": "pm", "name": "PM", "packs": [{"name": "Z", "cards": [1]}]}),
                                      encoding="utf-8")
        app.load_mod(mod)
        app.update()
        texts = {str(w.cget("text")) for w in enabled() if isinstance(w, tk.ttk.Button)}
        self.assertTrue({"Add pack", "Simulate...", "Apply", "Import PNG...", "Add tier"} <= texts, texts)
        self.assertNotIn("Export...", texts)     # no picture of its own to export

    def test_text_preview(self):
        import dataclasses
        from fm_editor import card_text
        from fm_editor.tests.test_card_text import synthetic_wa
        app = self.app
        app.show_text_preview()
        preview = app.text_preview
        app.update()
        self.assertIn("Choose a card", preview.notes.cget("text"))
        app.cards.tree.selection_set("1")
        app.cards.select()
        preview.refresh()
        self.assertIn("no font", preview.notes.cget("text"))      # the synthetic disc has none
        wa = bytearray(app.files.wa)
        start, end = card_text.BOOT_SECTOR * 2048, (card_text.RAMP_SECTOR + 1) * 2048
        wa[start:end] = synthetic_wa()[start:end]
        app.files = dataclasses.replace(app.files, wa=bytes(wa), source="with a font")
        app.cards.text.delete("1.0", "end")
        app.cards.text.insert("1.0", "A " * 100)
        app.cards.count_lines()
        preview.refresh()
        self.assertIsNotNone(preview.image)
        self.assertEqual(preview.image.width(), (card_text.COLUMNS * 8 + card_text.GUTTER) * 2)
        self.assertIn("will not show in the game", preview.notes.cget("text"))
        # A font file cut short says so and keeps the retail picture.
        from fm_editor import preview as preview_module
        from fm_editor.tests.test_card_text import tiny_font
        with tempfile.TemporaryDirectory() as tmp:
            whole = Path(tmp) / "whole.ttf"
            tiny_font(whole)
            for size in (40, 100, len(whole.read_bytes()) // 2):
                cut = Path(tmp) / f"cut{size}.ttf"
                cut.write_bytes(whole.read_bytes()[:size])
                preview.font_path = str(cut)
                preview.mode.set(preview_module.FILE)
                preview.refresh()
                self.assertTrue(preview.face_label.cget("text"), size)
                self.assertEqual(str(preview.cget("cursor")), "")
        preview.mode.set(preview_module.RETAIL)
        preview.close()
        self.assertIsNone(app.text_preview)

    def test_preview_cancels_pending_refresh(self):
        app = self.app
        app.show_text_preview()
        preview = app.text_preview
        preview.later()
        pending = preview.pending
        self.assertIn(pending, app.tk.call("after", "info"))
        # Changing a preview option redraws immediately, while a typing
        # refresh may still be scheduled.
        preview.refresh()
        self.assertNotIn(pending, app.tk.call("after", "info"))
        preview.later()
        pending = preview.pending
        preview.close()
        self.assertNotIn(pending, app.tk.call("after", "info"))
        self.assertIsNone(app.text_preview)
        # Tk destroys child windows directly when the editor closes.
        app.show_text_preview()
        preview = app.text_preview
        preview.later()
        pending = preview.pending
        preview.destroy()
        self.assertNotIn(pending, app.tk.call("after", "info"))
        self.assertIsNone(app.text_preview)

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

    def test_remove_disc_recipes(self):
        from fm_editor import manifest
        app = self.app
        tab = app.fusions
        p = tab.project
        recipes = p.retail_recipes(3)
        dialog = tab.remove_result()
        dialog.fields["r"].set(610)                  # a magic card: no disc recipe makes it
        dialog.ok()
        self.assertIn("no recipe", dialog.error.cget("text"))
        dialog.fields["r"].set(3)
        dialog.ok()
        self.assertEqual(p.fusion_removes, [3])
        self.assertFalse([pair for pair in recipes if pair in p.fusions])
        self.assertTrue(app.dirty)
        self.assertEqual(manifest.build_fusions(p), [{"remove": "Kuriboh"}])
        # An own "fusions" list naming the pair makes its card now: the row says so.
        p.card_extra[1] = {"fusions": [{"with": 2, "result": 500}]}
        p._own_pairs = None
        tab.search.set("Blue Dragon")
        self.assertEqual(tab.tree.set("1:2", "state"), "own list")
        self.assertIn("Card 500", tab.tree.set("1:2", "result"))
        del p.card_extra[1]
        p._own_pairs = None
        tab.fill()
        self.assertEqual(tab.tree.set("1:2", "state"), "removed")
        tab.tree.selection_set("1:2")
        tab.revert()
        self.assertEqual(p.fusions[(1, 2)], 3)
        if len(recipes) > 1:
            self.assertIn({"with": ["Blue Dragon", "Mystic Elf"], "result": "Kuriboh"}, manifest.build_fusions(p))
        else:
            self.assertEqual(manifest.build_fusions(p), [])
        # A copy's own list that its base's rule answers first is no row of
        # its own: it would read "forbidden" where the game plays the rule.
        copy = p.add_card(1, "x")
        p.added[copy].extra = {"fusions": [{"with": 2, "result": 500}]}
        p.set_fusion(1, 2, 599)
        p._own_pairs = None
        tab.search.set("")
        tab.fill()
        self.assertFalse(tab.tree.exists(f"2:{copy}"))

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

    def test_history_card_conversion_and_equip_targets(self):
        from fm_editor.gamedata import TYPE_NAMES
        app = self.app
        original = app.project.cards[1].type
        app.cards.goto(1)
        app.cards.vars["type"].set(TYPE_NAMES[23])
        app.cards.show_kind()
        app.cards.vars["effect"].set(app.cards.effect_label(301))
        self.assertTrue(app.cards.apply(quiet=True))
        app.update()
        app.notebook.select(app.equips)
        app.update()
        self.assertTrue(app.equips.equips.exists("1"))
        app.project.equips[1] = {2, 3}
        app.changed()
        app.update()
        app.undo()
        app.update()
        self.assertNotIn(1, app.project.equips)
        self.assertEqual(app.project.cards[1].type, 23)
        app.undo()
        app.update()
        self.assertEqual(app.project.cards[1].type, original)
        self.assertFalse(app.equips.equips.exists("1"))
        self.assertFalse(app.dirty)
        app.redo()
        app.update()
        app.redo()
        app.update()
        self.assertEqual(app.project.equips[1], {2, 3})
        self.assertTrue(app.equips.equips.exists("1"))

    def test_invalid_form_stays_visible_when_switching_tabs(self):
        app = self.app
        app.cards.goto(1)
        app.cards.vars["attack"].set("unfinished")
        app.notebook.select(app.equips)
        app.update()
        self.assertIs(app.notebook.current(), app.cards)
        self.assertEqual(app.cards.vars["attack"].get(), "unfinished")
        self.assertTrue(app.cards.status.cget("text"))
        app.cards.vars["attack"].set("1234")
        app.notebook.select(app.equips)
        app.update()
        self.assertIs(app.notebook.current(), app.equips)
        self.assertEqual(app.project.cards[1].attack, 1234)

    def test_undo_commits_pending_text_and_keeps_selection(self):
        app = self.app
        app.cards.goto(10)
        old = app.project.cards[10].name
        app.cards.vars["name"].set("Pending undo")
        app.undo()
        app.update()
        self.assertEqual(app.project.cards[10].name, old)
        self.assertEqual(app.cards.current, 10)
        self.assertEqual(app.cards.vars["name"].get(), old)
        app.redo()
        app.update()
        self.assertEqual(app.cards.vars["name"].get(), "Pending undo")

    def test_pending_drafts_and_recovery_failure(self):
        from fm_editor import recovery
        app = self.app
        app.cards.goto(1)
        widget = app.cards.text
        app._remember_input(widget)
        widget.insert("end", "Draft text")
        app._form_input(app.cards, widget)
        self.assertTrue(app.title().startswith("*"))
        self.assertIn(app.cards, app._pending)
        app.cards.vars["attack"].set("unfinished")
        app.autosave()
        rows = [row for row in recovery.records() if row[0].parent == app.recovery.folder]
        self.assertEqual(len(rows), 1)
        forms = rows[0][2]["forms"]
        self.assertEqual(forms["cards"]["vars"]["attack"], "unfinished")
        app.discard_forms()
        self.assertNotEqual(app.cards.vars["attack"].get(), "unfinished")
        app.restore_drafts(forms)
        self.assertEqual(app.cards.vars["attack"].get(), "unfinished")
        self.assertTrue(widget.get("1.0", "end-1c").endswith("Draft text"))
        with mock.patch.object(app.recovery, "write", side_effect=OSError("disk full")):
            app.autosave()
        self.assertIn("Recovery copy failed", app.edit_state.cget("text"))
        self.assertTrue(rows[0][1].exists())

    def test_save_backup_failure_does_not_overwrite_mod(self):
        from fm_editor import manifest, recovery
        app = self.app
        folder = Path(self.tmp.name) / "history-save"
        manifest.save_mod(app.project, folder)
        before = (folder / "mod.json").read_bytes()
        app.cards.goto(1)
        app.cards.vars["name"].set("Unsaved name")
        with mock.patch.object(recovery, "backup", side_effect=OSError("backup failed")), \
                mock.patch("fm_editor.app.messagebox.showerror") as error:
            self.assertFalse(app.save())
        error.assert_called_once()
        self.assertEqual((folder / "mod.json").read_bytes(), before)
        self.assertTrue(app.dirty)
        self.assertTrue(app.save())
        self.assertFalse(app.dirty)
        app.undo()
        app.update()
        self.assertTrue(app.dirty)
        app.redo()
        app.update()
        self.assertFalse(app.dirty)


    def test_keyboard_pending_apply_and_undo_shortcuts(self):
        app = self.app
        app.deiconify()
        app.cards.goto(1)
        app.update()
        text = app.cards.text
        text.focus_force()
        app.update()
        original = text.get("1.0", "end-1c")
        text.mark_set("insert", "end-1c")
        text.event_generate("<KeyPress-x>")
        text.event_generate("<KeyRelease-x>")
        app.update()
        self.assertIn(app.cards, app._pending)
        self.assertTrue(app.title().startswith("*"))
        self.assertTrue(app.cards.apply(quiet=True))
        app.update()
        self.assertNotIn(app.cards, app._pending)
        text.event_generate("<Control-z>")
        text.event_generate("<KeyRelease-z>", state=4)
        app.update()
        self.assertEqual(text.get("1.0", "end-1c"), original)
        self.assertFalse(app._pending)
        text.event_generate("<Control-Shift-Z>")
        app.update()
        self.assertEqual(text.get("1.0", "end-1c"), original + "x")

    def test_autosave_uses_the_history_snapshot_only_when_current(self):
        from fm_editor import manifest, recovery
        app = self.app

        def copied():
            row = next(row for row in recovery.records() if row[0].parent == app.recovery.folder)
            return manifest.open_mod(app.retail, row[1])[0].cards[1].name

        app.project.cards[1].name = "Recorded"
        app.changed()
        app.update()                        # the history records it when idle
        self.assertIsNone(app._history_job)
        with mock.patch.object(recovery, "Snapshot", side_effect=AssertionError("snapshot taken twice")):
            app.autosave()
        self.assertEqual(copied(), "Recorded")
        app.project.cards[1].name = "Not recorded yet"
        app.changed()                       # no idle time: the history is behind
        self.assertIsNotNone(app._history_job)
        app.autosave()
        self.assertEqual(copied(), "Not recorded yet")

    def test_recovered_copy_survives_multiple_autosaves_and_save_as(self):
        from fm_editor import manifest, recovery
        app = self.app
        app.project.files["extra.bin"] = b"keep across autosaves"
        app.project.cards[1].name = "Crash recovery"
        prior = recovery.Recovery()
        prior.write(app.project)
        row = next(row for row in recovery.records() if row[0].parent == prior.folder)
        app.set_project(type(app.project)(app.retail))
        self.assertTrue(app.open_recovery(row[1], row[2]))
        app.update()
        self.assertTrue(app._recovered)
        self.assertEqual(app.project.cards[1].name, "Crash recovery")
        app.autosave()
        app.project.info.author = "More edits"
        app.changed()
        app.autosave()
        latest = next(row for row in recovery.records() if row[0].parent == app.recovery.folder)
        self.assertEqual((latest[1] / "extra.bin").read_bytes(), b"keep across autosaves")
        self.assertTrue(row[1].exists(), "original recovery copy remains until saved")
        source = app.project.source_dir
        destination = Path(self.tmp.name) / "recovered-save"
        with mock.patch("fm_editor.app.filedialog.askdirectory", return_value=str(destination)) as choose:
            self.assertTrue(app.save())
        choose.assert_called_once()
        self.assertFalse(app._recovered)
        self.assertFalse(source.exists())
        # Saved now: the crashed session is no longer offered at start.
        self.assertFalse(prior.folder.exists())
        reopened, _ = manifest.open_mod(app.retail, destination)
        self.assertEqual(reopened.cards[1].name, "Crash recovery")
        self.assertEqual((destination / "extra.bin").read_bytes(), b"keep across autosaves")


    def test_card_form_marks_what_differs_from_the_disc(self):
        cards, p = self.app.cards, self.app.project
        cards.tree.selection_set("1")
        cards.select()
        self.app.update()
        # As the disc has it: no disc values repeated, no caption marked.
        for key in ("name", "attack", "defense", "level", "password", "starchips", "text"):
            with self.subTest(key=key):
                self.assertEqual(cards.hints[key].cget("text"), "")
        self.assertEqual(str(cards.captions["attack"].cget("style")), "TLabel")
        retail = p.retail.cards[1].attack
        cards.vars["attack"].set(str(retail + 200))
        self.app.update()
        self.assertEqual(cards.hints["attack"].cget("text"), f"Retail: {retail} (restore)")
        self.assertEqual(str(cards.hints["attack"].cget("style")), "Changed.TLabel")
        self.assertEqual(str(cards.captions["attack"].cget("style")), "Changed.TLabel")
        self.assertEqual(cards.hints["defense"].cget("text"), "")
        # Applied, it stays marked; a click on the disc value puts it back
        # in the form, unapplied until Apply.
        self.assertTrue(cards.apply())
        self.app.update()
        self.assertEqual(p.cards[1].attack, retail + 200)
        self.assertIn("Retail:", cards.hints["attack"].cget("text"))
        cards.hints["attack"].event_generate("<Button-1>")
        self.app.update()
        self.assertEqual(cards.vars["attack"].get(), str(retail))
        self.assertEqual(cards.hints["attack"].cget("text"), "")
        self.assertIn(cards, self.app._pending)
        self.assertTrue(cards.apply())
        self.assertEqual(p.cards[1].attack, retail)
        # The card text too.
        cards.text.insert("end", " more")
        cards.text.event_generate("<KeyRelease>")
        self.app.update()
        self.assertEqual(cards.hints["text"].cget("text"), "Restore retail text")
        cards.restore("text")
        self.assertEqual(cards.text.get("1.0", "end-1c"), p.retail.cards[1].description)
        # The window's line says unapplied and unsaved apart.
        self.assertEqual(str(self.app.edit_state.cget("style")), "Warning.TLabel")
        self.assertTrue(self.app.commit_all())
        self.assertEqual(str(self.app.edit_state.cget("style")),
                         "Changed.TLabel" if self.app.dirty else "TLabel")

    def test_card_links_between_tabs(self):
        from fm_editor import card_links
        app, p = self.app, self.app.project
        # The card Cards shows is the one Art shows, and Fusions follows it
        # with that card's fusions only.
        app.cards.show_card(2)
        app.notebook.select(app.art)
        app.update()
        self.assertEqual(app.art.current, 2)
        app.notebook.select(app.fusions)
        app.update()
        self.assertEqual(app.fusions.search.get(), p.card_label(2))
        rows = [tuple(int(x) for x in iid.split(":")) for iid in app.fusions.tree.get_children()]
        self.assertIn((1, 2), rows)
        self.assertTrue(all(2 in pair or p.fusions.get(pair) == 2 for pair in rows))
        # A search of the modder's own is kept.
        app.fusions.search.set("zzz")
        app.notebook.select(app.cards)
        app.cards.show_card(3)
        app.notebook.select(app.fusions)
        app.update()
        self.assertEqual(app.fusions.search.get(), "zzz")
        # Where it's used: the fusion making card 3, and a pool with it, each
        # going to its tab.
        lines = card_links.uses(app, 3)
        self.assertIn(("Fusions", "Material in"), {(w, t[:11]) for w, t, _ in lines})
        made = next(t for w, t, _ in lines if w == "Fusions")
        self.assertNotIn("made by 0 ", made)
        d, pool = next((d, pool) for d in range(1, len(p.pools)) for pool in ("deck", "pow", "bcd", "tec")
                       if p.pools[d][pool].get(3))
        go = next(g for w, t, g in lines if w == "Duelists")
        app.open_pool(d, pool, 3)
        app.update()
        self.assertIs(app.notebook.current(), app.duelists)
        self.assertEqual((app.duelists.duelist, app.duelists.pool.get()), (d, pool))
        self.assertEqual(app.duelists.tree.selection(), ("3",))
        go()
        app.update()
        self.assertIs(app.notebook.current(), app.duelists)
        window = card_links.UsesWindow(app, 3)
        self.assertEqual(len(window.tree.get_children()), len(lines))
        window.destroy()
        # The right-click menu names Cards, Art and fusions, and opens them.
        menu = tk.Menu(app, tearoff=False)
        card_links.fill_menu(menu, app, app.duelists, 3)
        labels = [menu.entrycget(i, "label") for i in range(menu.index("end") + 1) if menu.type(i) == "command"]
        self.assertEqual(labels[:3], ["Open in Cards", "Open in Art", "Show its fusions"])
        menu.invoke(0)
        app.update()
        self.assertIs(app.notebook.current(), app.cards)
        self.assertEqual(app.cards.current, 3)
        menu.destroy()

    def test_card_opened_from_another_tab_wins(self):
        from fm_editor import card_links
        app, p = self.app, self.app.project

        def invoke(tab, cid, label):
            menu = tk.Menu(app, tearoff=False)
            card_links.fill_menu(menu, app, tab, cid)
            labels = [menu.entrycget(i, "label") if menu.type(i) == "command" else None
                      for i in range(menu.index("end") + 1)]
            menu.invoke(labels.index(label))
            app.update()
            menu.destroy()

        # The tab-changed event's follow() must not put back the Cards card.
        app.cards.show_card(2)
        app.notebook.select(app.duelists)
        app.update()
        invoke(app.duelists, 3, "Show its fusions")
        self.assertEqual(app.fusions.search.get(), p.card_label(3))
        equips = p.equip_cards()
        app.notebook.select(app.cards)
        app.cards.show_card(equips[0])
        app.notebook.select(app.duelists)
        app.update()
        invoke(app.duelists, equips[1], "Edit its equip targets")
        self.assertEqual(app.equips.current, equips[1])
        # After a refresh (Undo, another mod) a search naming a whole card
        # still follows the window's card.
        app.fusions.refresh()
        app.notebook.select(app.cards)
        app.cards.show_card(4)
        app.notebook.select(app.fusions)
        app.update()
        self.assertEqual(app.fusions.search.get(), p.card_label(4))

    def test_where_used_lists_pack_unlock_and_starter_pools(self):
        from fm_editor import card_links
        app, p = self.app, self.app.project
        p.packs.append({"name": "Locked", "cards": [1], "unlock": {"card": 5}})
        p.other["starter_pools"] = [{"name": "Mine", "draws": 4, "cards": {"5": 7}}]
        p.starter_pool_state = None
        lines = card_links.uses(app, 5)
        whats = {(w, t) for w, t, _ in lines}
        self.assertIn(("Packs", "Locked: unlocked by owning it"), whats)
        self.assertIn(("Starter pools", "Mine: weight 7 (mod.json only)"), whats)
        window = card_links.UsesWindow(app, 5)
        row = next(i for i, (w, _, _) in enumerate(window.lines) if w == "Starter pools")
        window.tree.selection_set(str(row))
        window.go()     # a line with nowhere to go does nothing
        window.destroy()

    def test_recovered_type_change_restores_effect_controls(self):
        from fm_editor.gamedata import TYPE_NAMES
        app = self.app
        app.cards.search.set("no matching card")
        app.restore_drafts({"cards": {"current": 1, "vars": {
            "type": TYPE_NAMES[22], "effect": app.cards.effect_label(681)}}})
        app.update()
        self.assertEqual(app.cards.current, 1)
        self.assertEqual(app.cards.vars["type"].get(), TYPE_NAMES[22])
        self.assertEqual(app.cards.effect_box.winfo_manager(), "grid")
        self.assertEqual(app.cards.vars["effect"].get(), app.cards.effect_label(681))
        self.assertTrue(app.cards.apply(quiet=True))
        self.assertEqual(app.project.cards[1].type, 22)



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


class MonsterEffectsGuiTest(GuiCase):
    """The Cards tab's Monster effects box and the card text's right-click
    menu."""

    def test_effects_box(self):
        app, cards = self.app, self.app.cards
        cards.tree.selection_set("1")
        cards.select()
        box = cards.effects_box
        self.assertTrue(box.winfo_manager())
        self.assertEqual(box.tree.get_children(), ())
        box.effects.append({"when": "summon", "do": "heal", "amount": 500})
        box.effects.append({"when": "face_up", "do": "boost", "target": "others", "attack": 300})
        box.store()
        self.assertEqual(app.project.monster_effects_of(1)[0][1]["when"], "face_up")
        self.assertEqual([box.tree.set(i, "when") for i in box.tree.get_children()], ["On summon", "While face up"])
        box.tree.selection_set("1")
        box.move(-1)
        self.assertEqual([e["when"] for e in app.project.monster_effects_of(1)[0]], ["face_up", "summon"])
        box.tree.selection_set("0")
        box.remove()
        self.assertEqual(app.project.monster_effects_of(1)[0], [{"when": "summon", "do": "heal", "amount": 500}])
        self.assertTrue(app.dirty)
        # Kept across selecting another card; gone for a magic card.
        cards.tree.selection_set("2")
        cards.select()
        self.assertEqual(box.tree.get_children(), ())
        cards.tree.selection_set("1")
        cards.select()
        self.assertEqual(len(box.tree.get_children()), 1)
        cards.vars["type"].set("Magic")
        self.assertFalse(box.winfo_manager())

    def test_effect_dialog(self):
        from fm_editor.monster_effects_ui import EffectDialog
        app = self.app
        dialog = EffectDialog(app, app.project, {"when": "combat", "do": "boost", "target": "battle",
                                                 "attack": -700}, str)
        self.assertEqual(dialog.vars["when"].get(), "Before combat")
        self.assertEqual(dialog.vars["target"].get(), "The monster it battles")
        # Combat offers no magic; face up only boosts.
        self.assertNotIn("Magic card effect", dialog.do_box.cget("values"))
        dialog.vars["when"].set("While face up")
        self.assertEqual(list(dialog.do_box.cget("values")), ["Boost ATK/DEF"])
        self.assertNotIn("The monster it battles", dialog.target_box.cget("values"))
        dialog.vars["type"].set("Dragon")
        dialog.ok()
        self.assertEqual(dialog.result, {"when": "face_up", "do": "boost", "target": "self", "attack": -700,
                                         "type": "Dragon"})

    def test_text_menu(self):
        from fm_editor import text_menu
        cards = self.app.cards
        cards.tree.selection_set("1")
        cards.select()
        text = cards.text
        text.delete("1.0", "end")
        text.insert("1.0", "Can attack 2x a turn.")
        text.mark_set("insert", "1.0")
        text_menu.insert_code(text, "{f8 0B 00}")
        text.tag_add("sel", "1.21", "1.23")
        text_menu.colour(text, 6)
        self.assertEqual(text.get("1.0", "end-1c"), "{f8 0B 00}Can attack {f8 0A 06}2x{f8 0A 00} a turn.")
        menu = tk.Menu(text, tearoff=False)
        text_menu.fill(menu, self.app, text, lambda: None)
        labels = [menu.entrycget(i, "label") for i in range(menu.index("end") + 1) if menu.type(i) != "separator"]
        self.assertEqual(labels, ["Cut", "Copy", "Paste", "Insert icon...", "Text colour"])
        menu.destroy()
        # The picker: every icon, no taller than the screen, the icon going
        # where the cursor was when it opened.
        text.mark_set("insert", "end-1c")
        picker = text_menu.IconPicker(self.app, text, lambda: None, 0, 0)
        self.assertEqual(sorted(picker.buttons), list(range(41)))
        self.assertLessEqual(picker.winfo_reqheight(), picker.winfo_screenheight())
        text.mark_set("insert", "1.0")
        picker.pick(0x26)
        self.assertTrue(text.get("1.0", "end-1c").endswith("a turn.{f8 0B 26}"))
        self.assertFalse(picker.winfo_exists())

    def test_effect_monster_swatch_is_orange(self):
        from fm_editor.tabs import FRAME_COLOURS
        cards = self.app.cards
        cards.tree.selection_set("1")
        cards.select()
        self.assertEqual(cards.swatch.cget("background"), FRAME_COLOURS[0])
        cards.effects_box.effects.append({"when": "summon", "do": "heal", "amount": 500})
        cards.effects_box.store()
        self.assertEqual(cards.swatch.cget("background"), FRAME_COLOURS[5])


class CardTextBoxTest(GuiCase):
    """The card text box shows codes as pictures and gives them back."""

    def test_codes_shown_and_kept(self):
        cards = self.app.cards
        cards.tree.selection_set("1")
        cards.select()
        box = cards.text
        # Game files with the Dragon icon (the fixture's have none).
        from fm_editor.tests.test_card_text import icon_wa
        with mock.patch.object(self.app.files, "wa", icon_wa()):
            self.assertTrue(box._pictures())
        box.delete("1.0", "end")
        text = "{f8 0A 05}<Effect>{f8 0A 00} {f8 0B 00}x"
        box.insert("1.0", text)
        self.assertEqual(box.get("1.0", "end-1c"), text)
        self.assertEqual(len(box.image_names()), 3)
        self.assertIn("colour5", box.tag_names("1.2"))
        # Typed by hand (Tcl's own insert, as a key does): a picture once whole.
        box.tk.call(box._w, "insert", "end", " {f8 0b 00}")
        self.assertTrue(box.bind("<KeyRelease>"))      # a key's release runs it (the window is withdrawn here)
        box.layout()
        self.assertEqual(box.get("1.0", "end-1c"), text + " {f8 0B 00}")
        self.assertEqual(len(box.image_names()), 4)
        # The clipboard carries the codes.
        box.tag_add("sel", "1.0", "end-1c")
        box.event_generate("<<Copy>>")
        self.assertEqual(box.clipboard_get(), text + " {f8 0B 00}")
        box.delete("1.0", "end")
        box.event_generate("<<Paste>>")
        self.assertEqual(box.get("1.0", "end-1c"), text + " {f8 0B 00}")
        self.assertEqual(len(box.image_names()), 4)
        # Lines broken where the game breaks them: the space shows as a line's
        # end and reads back as the space.
        long = "aaaaaaaaaaaaaaa {f8 0B 00}{f8 0B 00} b"
        box.delete("1.0", "end")
        box.insert("1.0", long)
        self.assertEqual(box.get("1.0", "end-1c"), long)
        self.assertEqual(box.index("end-1c").split(".")[0], "2")
        box.delete("1.0", "end")
        box.insert("1.0", text + " {f8 0B 00}")
        # Applied as written.
        self.assertTrue(cards.apply())
        self.assertEqual(self.app.project.cards[1].description, text + " {f8 0B 00}")


class ColumnWidthTest(GuiCase):
    def test_a_dragged_column_keeps_its_width(self):
        from types import SimpleNamespace
        from fm_editor import widgets
        app = self.app
        app.deiconify()
        app.geometry("1400x800")
        app.update()
        tree = app.cards.tree
        x = next(x for x in range(tree.winfo_width()) if tree.identify_region(x, 10) == "separator")
        widgets._free_columns(tree, SimpleNamespace(x=x, y=10))
        columns = list(tree["columns"])
        self.assertEqual([tree.column(c, "stretch") for c in columns],
                         [False] * (len(columns) - 1) + [True])
        # Narrower than it stretched to: it stays so (it took the width back before).
        tree.column("name", width=150)
        app.update()
        self.assertEqual(tree.column("name", "width"), 150)
        app.withdraw()


class CardViewPreviewTest(GuiCase):
    def test_follows_the_form(self):
        cards = self.app.cards
        cards.tree.selection_set("1")
        cards.select()
        values = cards.card_view_values()
        self.assertEqual(values[3], self.app.project.cards[1].description)
        cards.vars["type"].set("Magic")
        self.assertEqual(cards.card_view_values()[1:3], (0, 0))      # no stars on a magic card
        cards.card_view.draw()      # the fixture's files: drawn or explained, never an error
        self.assertTrue(cards.card_view.picture.cget("image") or cards.card_view.note.cget("text") is not None)
