"""A mod's "limits" (limits.py, notes/gameplay-tables.md): the form's values and
back, the checks tables.c makes, the manifest round trip, and the tab.

    python -m unittest discover -s tools/pc/fm_editor/tests -t tools/pc
"""
import json
import unittest

try:
    import tkinter as tk
except ImportError:     # a Python built without Tk
    tk = None

from fm_editor import limits, manifest, validate
from fm_editor.model import Project
from fm_editor.tests.test_data import fixture


def project() -> Project:
    return Project(fixture().game())


class LimitsTest(unittest.TestCase):
    def test_flatten_and_build(self):
        written = {"stats": 30000, "defense": 20000,
                   "life_points": {"start": 16000, "max": 30000,
                                   "duelists": {"Heishin": 20000, "Seto": {"player": 100, "opponent": 200}}},
                   "two_player": {"max": 30000, "step": 1000}, "starchips": 5000000, "chest": 255}
        flat = limits.flatten(written)
        self.assertEqual(flat["stats"], 30000)
        self.assertEqual(flat["life_points.start"], 16000)
        self.assertEqual(flat["two_player.step"], 1000)
        self.assertEqual(flat["duelists"], {"Heishin": (None, 20000), "Seto": (100, 200)})
        self.assertEqual(limits.build(flat), written)
        # The short form of a start alone, and nothing at all.
        self.assertEqual(limits.build({"life_points.start": 12000}), {"life_points": 12000})
        self.assertEqual(limits.flatten({"life_points": 12000})["life_points.start"], 12000)
        self.assertIsNone(limits.build({"duelists": {"Seto": (None, None)}}))
        # A key the editor does not know is kept as written.
        self.assertEqual(limits.build({"stats": 5000}, {"later": 1, "stats": 9}), {"later": 1, "stats": 5000})

    def test_check(self):
        self.assertEqual(limits.check(None), [])
        self.assertEqual(limits.check({"stats": 30000, "life_points": 20000}), [])
        found = {(level, where) for level, where, _ in limits.check(
            {"stats": 40000, "attack": "lots", "life_points": {"start": 0, "strat": 1, "duelists": {"Nobody": 5}},
             "two_player": {"start": 9000}, "chest": 256, "lp": 3})}
        self.assertEqual(found, {("warning", "stats"), ("error", "attack"), ("error", "life_points.start"),
                                 ("error", "life_points.strat"), ("warning", "life_points.duelists \"Nobody\""),
                                 ("warning", "two_player.start"), ("warning", "chest"), ("error", "lp")})
        found = {where for _, where, _ in limits.check({"two_player": {"max": 4000, "step": 10000}})}
        self.assertEqual(found, {"two_player.start", "two_player.step"})
        self.assertEqual(limits.check(5)[0][0], "error")

    def test_manifest_and_validate(self):
        p = project()
        messages = manifest.apply(p, {"id": "m", "limits": {"stats": 30000, "starchips": 123456789}})
        self.assertEqual(p.other["limits"]["stats"], 30000)
        built = manifest.build(p)
        self.assertEqual(built["limits"], {"stats": 30000, "starchips": 123456789})
        issues = validate.validate(p)
        self.assertFalse([i for i in issues if i.area == "Mod info" and i.where == "limits"], messages)
        self.assertEqual([(i.level, i.where) for i in issues if i.area == "Limits"], [("warning", "starchips")])


class LimitsTabTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if tk is None:
            raise unittest.SkipTest("this Python has no Tk")
        try:
            cls.root = tk.Tk()
        except tk.TclError as problem:
            raise unittest.SkipTest(f"no display for Tk: {problem}")
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def test_tab(self):
        from tkinter import ttk
        from fm_editor.limits_tab import LimitsTab

        class App:
            def __init__(self):
                self.project = project()
                self.changes = 0

            def changed(self):
                self.changes += 1

        app = App()
        app.project.other["limits"] = {"life_points": {"start": 16000, "duelists": {"Heishin": 20000}}}
        notebook = ttk.Notebook(self.root)
        tab = LimitsTab(notebook, app)
        tab.refresh()
        self.assertEqual(tab.vars["life_points.start"].get(), "16000")
        self.assertEqual(tab.vars["stats"].get(), "")
        tab.vars["stats"].set("30000")
        tab.duelist_name.set("Seto")
        tab.duelist_opponent.set("12000")
        tab._set_duelist()
        self.assertTrue(tab.commit())
        self.assertEqual(app.project.other["limits"],
                         {"stats": 30000, "life_points": {"start": 16000,
                                                          "duelists": {"Heishin": 20000, "Seto": 12000}}})
        self.assertGreater(app.changes, 0)
        tab.vars["stats"].set("many")
        self.assertFalse(tab.commit())
        tab.clear()
        self.assertNotIn("limits", app.project.other)
        json.dumps(manifest.build(app.project))


if __name__ == "__main__":
    unittest.main()
