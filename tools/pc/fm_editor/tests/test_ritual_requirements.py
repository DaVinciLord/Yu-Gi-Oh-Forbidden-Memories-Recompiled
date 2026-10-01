"""Condition-based ritual tributes: reading, writing, checking, and the recipe
dialog."""
import json
import unittest

try:
    import tkinter as tk
    from tkinter import ttk
except ImportError:     # a Python built without Tk
    tk = None

from fm_editor import gamedata as g, manifest, validate
from fm_editor.model import Project
from fm_editor.tests.test_data import fixture
from fm_editor.tests import test_gui


def reopen(retail, p: Project) -> Project:
    again = Project(retail)
    manifest.apply(again, json.loads(manifest.dumps(manifest.build(p))))
    return again


class RequirementsTest(unittest.TestCase):
    def setUp(self):
        self.retail = fixture().game()

    def load(self, rituals) -> tuple:
        p = Project(self.retail)
        messages = manifest.apply(p, {"id": "t", "rituals": rituals})
        return p, messages

    def test_round_trip(self):
        p, messages = self.load([{"card": 681, "result": 500, "tributes": [
            {"type": "Dragon", "min_attack": 0}, 5, {"fusion_group": "female", "defense_gt_attack": True}]}])
        self.assertEqual(messages, [])
        # A minimum of 0 is a requirement (any monster); a group in any case is the group.
        self.assertEqual(p.ritual_requirements[681], [
            {"type": "Dragon", "min_attack": 0}, {"card": 5}, {"fusion_group": "Female", "defense_gt_attack": True}])
        self.assertEqual(p.ritual_status(681), "changed")
        built = manifest.build(p)["rituals"]
        self.assertEqual(built, [{"card": p.ref(681), "result": p.ref(500), "tributes": [
            {"type": "Dragon", "min_attack": 0}, {"card": p.ref(5)},
            {"fusion_group": "Female", "defense_gt_attack": True}]}])
        self.assertEqual(reopen(self.retail, p).ritual_requirements, p.ritual_requirements)

    def test_plain_recipes_stay_plain(self):
        p, _ = self.load([{"card": 681, "tributes": [4, 5, 6], "result": 500}])
        self.assertEqual(p.ritual_requirements, {})
        self.assertEqual(manifest.build(p)["rituals"],
                         [{"card": p.ref(681), "tributes": [p.ref(4), p.ref(5), p.ref(6)], "result": p.ref(500)}])

    def test_later_entry_wins(self):
        p, _ = self.load([{"card": 681, "tributes": [{"type": "Dragon"}, 5, 6], "result": 500},
                          {"card": 681, "tributes": [4, 5, 6], "result": 501}])
        self.assertNotIn(681, p.ritual_requirements)
        self.assertEqual(p.rituals[681], (4, 5, 6, 501))
        p, _ = self.load([{"card": 681, "tributes": [{"type": "Dragon"}, 5, 6], "result": 500},
                          {"card": 681, "result": None}])
        self.assertNotIn(681, p.ritual_requirements)
        self.assertNotIn(681, p.rituals)

    def test_what_the_editor_cannot_place_is_kept(self):
        for tribute in ({"attribute": "Light"}, {"type": "Magic"}, {"fusion_group": "Elves"}, {},
                        {"min_level": 5, "max_level": 4}, {"min_attack": 10000}, {"defense_gt_attack": 1}):
            p, messages = self.load([{"card": 681, "tributes": [tribute, 5, 6], "result": 500}])
            self.assertIn("kept as written", " ".join(messages), tribute)
            self.assertNotIn(681, p.ritual_requirements)
            self.assertEqual(manifest.build(p)["rituals"][-1]["tributes"][0], tribute)

    def test_revert_clears_the_requirements(self):
        p, _ = self.load([{"card": 681, "tributes": [{"type": "Dragon"}, 5, 6], "result": 500}])
        p.revert_ritual(681)
        self.assertEqual(p.ritual_requirements, {})
        self.assertEqual(p.rituals[681], self.retail.rituals[681])
        self.assertEqual(p.ritual_status(681), "")

    def test_validate(self):
        p, _ = self.load([{"card": 681, "tributes": [{"type": "Dragon"}, {"card": 5}, 6], "result": 500}])
        p.cards[5].type = g.TYPE_MAGIC
        found = [i.message for i in validate.validate(p) if i.area == "Rituals"]
        self.assertTrue(any("is not a monster" in m for m in found), found)


class DialogTest(unittest.TestCase):
    # The window as test_gui starts it, without its tests.
    setUpClass = classmethod(test_gui.GuiTest.setUpClass.__func__)
    tearDownClass = classmethod(test_gui.GuiTest.tearDownClass.__func__)
    setUp = test_gui.GuiTest.setUp
    tearDown = test_gui.GuiTest.tearDown

    def widgets(self, root, kind):
        out = []
        for child in root.winfo_children():
            if isinstance(child, kind):
                out.append(child)
            out += self.widgets(child, kind)
        return out

    def open(self, ritual):
        tab = self.app.rituals
        tab.tree.selection_set(str(ritual))
        before = set(self.widgets(self.app, tk.Toplevel))
        tab.edit()
        self.app.update()
        dialog = next(w for w in self.widgets(self.app, tk.Toplevel) if w not in before)
        save = next(b for b in self.widgets(dialog, ttk.Button) if b.cget("text") == "Save")
        error = next(l for l in self.widgets(dialog, ttk.Label) if str(l.cget("style")) == "Error.TLabel")
        return dialog, save, error

    def test_a_typed_card_is_checked(self):
        p = self.app.project
        dialog, save, error = self.open(681)
        entry = self.widgets(dialog, ttk.Entry)[0]      # tribute 1's Specific Card
        entry.delete(0, "end")
        entry.insert(0, "No Such Card")
        save.invoke()
        self.assertIn("Tribute 1: no card", error.cget("text"))
        self.assertTrue(dialog.winfo_exists())
        entry = self.widgets(dialog, ttk.Entry)[0]      # drawn again, the typed text kept
        self.assertEqual(entry.get(), "No Such Card")
        entry.delete(0, "end")
        entry.insert(0, p.card_label(7))
        save.invoke()
        self.assertFalse(dialog.winfo_exists())
        self.assertEqual(p.rituals[681][0], 7)
        self.assertNotIn(681, p.ritual_requirements)

    def test_a_grab_refused_at_first(self):
        # A double-click opens the dialog before it is on screen, and Tk
        # refuses the grab: the dialog is still built, and grabs later.
        from unittest import mock
        real, calls = tk.Toplevel.grab_set, []

        def refuse_once(window):
            calls.append(window)
            if len(calls) == 1:
                raise tk.TclError("grab failed: window not viewable")
            return real(window)

        with mock.patch.object(tk.Toplevel, "grab_set", refuse_once):
            dialog, save, error = self.open(681)
            self.app.after(50, lambda: None)
            for _ in range(20):
                self.app.update()
                if len(calls) > 1:
                    break
                self.app.after(10)
        self.assertGreater(len(calls), 1)
        self.assertTrue(self.widgets(dialog, ttk.Entry))
        dialog.destroy()

    def test_a_ritual_without_a_recipe_starts_empty(self):
        p = self.app.project
        ritual = next(r for r in p.ritual_cards() if r not in p.rituals)
        dialog, save, error = self.open(ritual)
        self.assertEqual(self.widgets(dialog, ttk.Entry)[:-1], [])      # only Summons: no "card 0" rows
        save.invoke()
        self.assertIn("Tribute 1: needs at least one requirement", error.cget("text"))
        dialog.destroy()
        self.assertNotIn(ritual, p.rituals)


if __name__ == "__main__":
    unittest.main()
