"""The Values tab's numbers, a mod's "limits" (values.py, notes/gameplay-tables.md):
the form's values and back, the checks tables.c makes, the manifest round
trip, and the tab.

    python -m unittest discover -s tools/pc/fm_editor/tests -t tools/pc
"""
import json
import unittest

try:
    import tkinter as tk
except ImportError:     # a Python built without Tk
    tk = None

from fm_editor import manifest, validate, values
from fm_editor.model import Project
from fm_editor.tests.test_data import fixture


def project() -> Project:
    return Project(fixture().game())


class ValuesTest(unittest.TestCase):
    def test_flatten_and_build(self):
        written = {"stats": 30000, "defense": 20000,
                   "life_points": {"start": 16000, "max": 30000,
                                   "duelists": {"Heishin": 20000, "Seto": {"player": 100, "opponent": 200}}},
                   "two_player": {"max": 30000, "step": 1000}, "starchips": 5000000, "chest": 255}
        flat = values.flatten(written)
        self.assertEqual(flat["stats"], 30000)
        self.assertEqual(flat["life_points.start"], 16000)
        self.assertEqual(flat["two_player.step"], 1000)
        self.assertEqual(flat["duelists"], {"Heishin": (None, 20000), "Seto": (100, 200)})
        self.assertEqual(values.build(flat), written)
        # The short form of a start alone, and nothing at all.
        self.assertEqual(values.build({"life_points.start": 12000}), {"life_points": 12000})
        self.assertEqual(values.flatten({"life_points": 12000})["life_points.start"], 12000)
        self.assertIsNone(values.build({"duelists": {"Seto": (None, None)}}))
        # A key the editor does not know is kept as written.
        self.assertEqual(values.build({"stats": 5000}, {"later": 1, "stats": 9}), {"later": 1, "stats": 5000})

    def test_check(self):
        self.assertEqual(values.check(None), [])
        self.assertEqual(values.check({"stats": 30000, "life_points": 20000}), [])
        found = {(level, where) for level, where, _ in values.check(
            {"stats": 40000, "attack": "lots", "life_points": {"start": 0, "strat": 1, "duelists": {"Nobody": 5}},
             "two_player": {"start": 9000}, "chest": 256, "lp": 3})}
        self.assertEqual(found, {("warning", "stats"), ("error", "attack"), ("error", "life_points.start"),
                                 ("error", "life_points.strat"), ("warning", "life_points.duelists \"Nobody\""),
                                 ("warning", "two_player.start"), ("warning", "chest"), ("error", "lp")})
        found = {where for _, where, _ in values.check({"two_player": {"max": 4000, "step": 10000}})}
        self.assertEqual(found, {"two_player.start", "two_player.step"})
        self.assertEqual(values.check(5)[0][0], "error")

    def test_game_values(self):
        written = {"deck_copies": 40, "swords_turns": 5, "crush_card": 2000, "spellbinding_circle": 800,
                   "shadow_spell": 0, "rank_score": {"start": 60, "exodia": -10, "deck_out": 30},
                   "starchip_prize": {"S": 8, "D": 0}, "new_game_starchips": 500}
        flat = values.flatten(written)
        self.assertEqual((flat["rank_score.exodia"], flat["starchip_prize.D"], flat["shadow_spell"]), (-10, 0, 0))
        self.assertEqual(values.build(flat), written)
        self.assertEqual(values.check(written), [])
        found = {(level, where) for level, where, _ in values.check(
            {"deck_copies": 41, "swords_turns": 0, "starchip_prize": {"S": 20, "Z": 1},
             "rank_score": {"start": 150, "exodia": "lots"}, "crush_card": 40000, "new_game_starchips": -1})}
        self.assertEqual(found, {("warning", "deck_copies"), ("error", "swords_turns"), ("warning", "starchip_prize.S"),
                                 ("error", "starchip_prize.Z"), ("error", "rank_score.start"),
                                 ("error", "rank_score.exodia"), ("warning", "crush_card"),
                                 ("error", "new_game_starchips")})
        self.assertEqual(values.check({"rank_score": 5})[0][:2], ("error", "rank_score"))
        # Kept as written when the form cannot show it: a misspelt member.
        self.assertEqual(values.build({"deck_copies": 4}, {"starchip_prize": {"SS": 3}}),
                         {"deck_copies": 4, "starchip_prize": {"SS": 3}})
        self.assertIsNone(values.problem("deck_copies", ""))
        self.assertIn("whole number", values.problem("deck_copies", "x"))
        self.assertIn("left out", values.problem("rank_score.start", "100"))

    def test_same_as_the_game(self):
        """Every value's key, the game's own value and its range as tables.c
        reads them (value_keys), so the editor checks what the game does."""
        import re
        from pathlib import Path
        source = (Path(__file__).resolve().parents[4] / "src/pc/cards/tables.c").read_text()
        table = source[source.index("value_keys[TABLES_VALUE_COUNT] = {"):]
        table = table[:table.index("};")]
        constants = {"DECK_CARD_COPY_LIMIT": 3, "DECK_SIZE": 40, "TABLES_VALUE_SWORDS_MAX": 9,
                     "DUEL_CRUSH_CARD_ATTACK_THRESHOLD": 1500, "TABLES_LIMIT_STAT_MAX": 32767, "CARD_STAT_MAX": 9999,
                     "DUEL_RANK_SCORE_INITIAL": 50, "DUEL_RANK_ADJUST_EXODIA_WIN": 40,
                     "DUEL_RANK_ADJUST_DECK_OUT_WIN": -40, "TABLES_VALUE_PRIZE_MAX": 8,
                     "TABLES_LIMIT_STARCHIPS_MAX": 99999999}
        rows = re.findall(r'\{"([\w.]+)", ([-\w]+), ([-\w]+), ([-\w]+), (NULL|")', table)
        self.assertEqual(len(rows), 14)
        for key, retail, low, high, storage in rows:
            number = lambda text: constants[text] if text in constants else int(text)
            field = values.FIELD[key]
            self.assertEqual((field[2], field[3], field[4]), (number(retail), number(low), number(high)), key)
            self.assertEqual(field[6] is None, storage == "NULL", key)

    def test_manifest_and_validate(self):
        p = project()
        messages = manifest.apply(p, {"id": "m", "limits": {"stats": 30000, "starchips": 123456789}})
        self.assertEqual(p.other["limits"]["stats"], 30000)
        built = manifest.build(p)
        self.assertEqual(built["limits"], {"stats": 30000, "starchips": 123456789})
        issues = validate.validate(p)
        self.assertFalse([i for i in issues if i.area == "Mod info" and i.where == "limits"], messages)
        self.assertEqual([(i.level, i.where) for i in issues if i.area == "Values"], [("warning", "starchips")])


class ValuesTabTest(unittest.TestCase):
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
        from fm_editor.values_tab import ValuesTab

        class App:
            def __init__(self):
                self.project = project()
                self.changes = 0

            def changed(self):
                self.changes += 1

        app = App()
        app.project.other["limits"] = {"life_points": {"start": 16000, "duelists": {"Heishin": 20000}}}
        notebook = ttk.Notebook(self.root)
        tab = ValuesTab(notebook, app)
        tab.refresh()
        self.assertEqual(tab.vars["life_points.start"].get(), "16000")
        # What the mod sets: its fields marked, with their revert buttons on.
        self.assertEqual(str(tab.captions["life_points.start"].cget("style")), "Changed.TLabel")
        self.assertEqual(str(tab.captions["stats"].cget("style")), "TLabel")
        self.assertEqual(str(tab.reverts["life_points.start"].cget("state")), "normal")
        self.assertEqual(str(tab.reverts["stats"].cget("state")), "disabled")
        self.assertEqual(tab.duelists.get_children(), ("Heishin",))
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
        # A section the form cannot show all of: committing it untouched (as
        # every tab switch does) leaves it as written and the mod unchanged,
        # so Conflicts still sees the misspelt key and the bad value.
        odd = {"stats": "30000", "life_points": {"start": 9000, "strat": 1}, "two_player": {"foo": 2}}
        app.project.other["limits"] = json.loads(json.dumps(odd))
        tab.refresh()
        changes = app.changes
        self.assertTrue(tab.commit())
        self.assertEqual(app.project.other["limits"], odd)
        self.assertEqual(app.changes, changes)
        # Edited, what the form cannot show is still kept.
        tab.vars["chest"].set("200")
        self.assertTrue(tab.commit())
        self.assertEqual(app.project.other["limits"], dict(odd, chest=200))
        self.assertGreater(app.changes, changes)
        json.dumps(manifest.build(app.project))


if __name__ == "__main__":
    unittest.main()
