"""Bulk fusions (bulk_fusions.py, bulk_dialog.py) on the synthetic game:
the filters, one pair per two cards, keep or replace, the ATK rule, the
limit, undo, and the mod written and read back.

Fixture cards (tests/fixtures.py): 1-600 monsters of type id % 20, ATK
(id * 10) % 3000, attribute id % 6, level id % 12 + 1, stars id % 10 + 1 and
(id + 3) % 10 + 1; 601-650 magic, 651-680 equips, 681-700 rituals, 701-722
traps. 1 "Blue Dragon", 2 "Mystic Elf", 3 "Kuriboh"; (1, 2) makes 3.
"""
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

try:
    import tkinter as tk
except ImportError:     # a Python built without Tk
    tk = None

from fm_editor import bulk_fusions as bulk, manifest
from fm_editor.model import Project
from fm_editor.tests.test_data import fixture

ALL = set(bulk.KINDS)


def project() -> Project:
    return Project(fixture().game())


def ids(p, **filters):
    chosen, unknown = bulk.CardFilter(**filters).select(p)
    return chosen, unknown


class FilterTest(unittest.TestCase):
    def setUp(self):
        self.p = project()

    def test_each_filter(self):
        p = self.p
        self.assertEqual(ids(p, types={0})[0], list(range(20, 601, 20)))
        self.assertEqual(ids(p, kinds={"magic"})[0], list(range(601, 651)))
        self.assertEqual(ids(p, kinds={"equip", "trap"})[0], list(range(651, 681)) + list(range(701, 723)))
        self.assertEqual(ids(p, attributes={2})[0], [c for c in range(1, 601) if c % 6 == 2])
        self.assertEqual(ids(p, stars={1})[0], [c for c in range(1, 601) if c % 10 == 0 or (c + 3) % 10 == 0])
        self.assertEqual(ids(p, atk_min=2900)[0], [c for c in range(1, 601) if (c * 10) % 3000 >= 2900])
        self.assertEqual(ids(p, def_max=0, kinds={"monster"})[0], [c for c in range(1, 601) if (c * 70) % 2500 == 0])
        self.assertEqual(ids(p, level_min=12, level_max=12)[0], [c for c in range(1, 601) if c % 12 == 11])
        self.assertEqual(ids(p, name="  DRAGON ")[0], [1])
        # the text as shown, line breaks as spaces, any case
        self.assertEqual(len(ids(p, text="card 5. second LINE")[0]), 1)
        self.assertEqual(ids(p, text="card 6 text")[0], [6])

    def test_filters_combine(self):
        chosen = ids(self.p, types={3}, atk_min=1000, atk_max=2000, attributes={1, 5})[0]
        expected = [c for c in range(1, 601) if c % 20 == 3 and 1000 <= (c * 10) % 3000 <= 2000 and c % 6 in (1, 5)]
        self.assertEqual(chosen, expected)
        self.assertTrue(chosen)

    def test_card_list(self):
        chosen, unknown = ids(self.p, cards="Kuriboh, 1; 5-7\n7, nothing like it, 900-950")
        self.assertEqual(chosen, [1, 3, 5, 6, 7])
        self.assertEqual(unknown, ["nothing like it", "900-950"])
        # a list and a filter: the listed cards the filter keeps
        self.assertEqual(ids(self.p, cards="1-40", types={0})[0], [20, 40])

    def test_results_only(self):
        made = {r for r in self.p.fusions.values() if r}
        self.assertEqual(set(ids(self.p, results_only=True)[0]), made)
        self.assertEqual(bulk.fusion_results(self.p), made)


def pairs_spec(a, b, **options):
    return bulk.BulkSpec(a=bulk.CardFilter(cards=a), b=bulk.CardFilter(cards=b), **options)


class PlanTest(unittest.TestCase):
    def setUp(self):
        self.p = project()
        self.p.fusions = {(1, 2): 3}          # a table small enough to follow
        self.p.retail.fusions = {(1, 2): 3}

    def test_one_pair_per_two_cards(self):
        plan = bulk.plan(self.p, pairs_spec("21-24", "21-24", result=599, stronger=False))
        self.assertEqual((plan.pairs, plan.self_pairs, plan.duplicates), (6, 4, 6))
        self.assertEqual({pair for pair, _, _ in plan.changes},
                         {(21, 22), (21, 23), (21, 24), (22, 23), (22, 24), (23, 24)})
        plan = bulk.plan(self.p, pairs_spec("21-24", "21-24", result=599, stronger=False, allow_self=True))
        self.assertEqual((plan.pairs, plan.self_pairs), (10, 0))
        # sets that only overlap: B+A of a pair already counted is a duplicate
        plan = bulk.plan(self.p, pairs_spec("21, 22", "22, 23", result=599, stronger=False))
        self.assertEqual({pair for pair, _, _ in plan.changes}, {(21, 22), (21, 23), (22, 23)})
        self.assertEqual((plan.self_pairs, plan.duplicates), (1, 0))

    def test_keep_or_replace(self):
        spec = pairs_spec("2", "1", result=500)       # ATK 2000 beats 10 and 20
        plan = bulk.plan(self.p, spec)
        self.assertEqual((plan.kept, len(plan.changes)), (1, 0))
        self.assertFalse(plan.ok())
        self.assertTrue(plan.warnings)
        spec.overwrite = True
        plan = bulk.plan(self.p, spec)
        self.assertEqual(plan.changes, [((1, 2), 3, 500)])
        self.assertEqual((plan.added, plan.replaced), (0, 1))
        # already making that card: nothing to do either way
        plan = bulk.plan(self.p, pairs_spec("1", "2", result=3, stronger=False, overwrite=True))
        self.assertEqual((plan.same, len(plan.changes)), (1, 0))

    def test_stronger_than_both(self):
        # 150 has ATK 1500; 100 has 1000, 200 has 2000
        plan = bulk.plan(self.p, pairs_spec("100", "200, 101", result=150))
        self.assertEqual([pair for pair, _, _ in plan.changes], [(100, 101)])
        self.assertEqual(plan.weaker, 1)
        plan = bulk.plan(self.p, pairs_spec("100", "200, 101", result=150, stronger=False))
        self.assertEqual(len(plan.changes), 2)
        self.assertEqual(bulk.plan(self.p, pairs_spec("100", "150", result=150)).weaker, 1)   # equal is not more

    def test_ladder(self):
        # the weakest of 120 (1200), 180 (1800), 250 (2500) with more ATK than both
        spec = pairs_spec("100, 170, 240", "10", ladder="250, 180, 120")
        plan = bulk.plan(self.p, spec)
        self.assertEqual(sorted((pair, after) for pair, _, after in plan.changes),
                         [((10, 100), 120), ((10, 170), 180), ((10, 240), 250)])
        spec.a = bulk.CardFilter(cards="290")
        self.assertEqual(bulk.plan(self.p, spec).no_result, 1)
        spec.ladder = "250, 610"
        self.assertTrue(any("not one" in e for e in bulk.plan(self.p, spec).errors))

    def test_result_must_be_a_monster(self):
        plan = bulk.plan(self.p, pairs_spec("1", "5", result=610))
        self.assertTrue(plan.errors)
        self.assertRaises(ValueError, bulk.apply, self.p, plan)
        self.assertTrue(bulk.plan(self.p, pairs_spec("1", "5")).errors)            # no result
        self.assertTrue(bulk.plan(self.p, bulk.BulkSpec(result=500)).errors)      # no filter at all

    def test_added_cards_fuse_as_their_base(self):
        copy = self.p.add_card(1)
        self.assertEqual(bulk.effective(self.p, copy, 2), 3)
        self.assertEqual(bulk.effective(self.p, copy, copy), None)
        plan = bulk.plan(self.p, pairs_spec(str(copy), "2", result=500))
        self.assertEqual(plan.kept, 1)
        # a forbidden pair (0) fuses with nothing: free to add
        self.p.set_fusion(copy, 2, None)
        self.assertEqual(self.p.fusions[(2, copy)], 0)
        plan = bulk.plan(self.p, pairs_spec(str(copy), "2", result=500))
        self.assertEqual(plan.changes, [((2, copy), 0, 500)])
        self.assertEqual(plan.added, 1)

    def test_remove(self):
        self.p.set_fusion(5, 6, 400)
        spec = pairs_spec("1, 5", "2, 6", mode="remove")
        plan = bulk.plan(self.p, spec)
        self.assertEqual(sorted(pair for pair, _, _ in plan.changes), [(1, 2), (5, 6)])
        self.assertEqual(plan.not_fusing, 2)
        spec.result = 3                                      # only those making Kuriboh
        plan = bulk.plan(self.p, spec)
        self.assertEqual([pair for pair, _, _ in plan.changes], [(1, 2)])
        bulk.apply(self.p, plan)
        self.assertNotIn((1, 2), self.p.fusions)
        self.assertEqual(manifest.build_fusions(self.p), [{"with": ["Blue Dragon", "Mystic Elf"], "result": None},
                                                          {"with": ["Card 5", "Card 6"], "result": "Card 400"}])

    def test_rule_count_and_budget(self):
        spec = pairs_spec("1-30", "31-60", result=599, stronger=False, overwrite=True)
        plan = bulk.plan(self.p, spec)
        self.assertEqual((plan.rules_before, plan.rules_after), (0, 900))
        bulk.apply(self.p, plan)
        self.assertEqual(bulk.rule_count(self.p), 900)
        self.assertEqual(len(manifest.build_fusions(self.p)), 900)
        # putting a retail pair back to its retail result takes a rule away
        plan = bulk.plan(self.p, pairs_spec("1", "2", result=3, stronger=False, overwrite=True))
        self.assertEqual(plan.rules_after, 900)             # (1, 2) still makes 3: nothing to do
        with mock.patch.object(bulk, "RULE_BUDGET", 1000):
            plan = bulk.plan(self.p, pairs_spec("61-100", "101-140", result=599, stronger=False))
            self.assertEqual(plan.rules_after, 2500)
            self.assertTrue(any("past the 1000" in e for e in plan.errors))
            self.assertFalse(plan.ok())
            # taking rules away is never refused: the pairs go back to no rule
            plan = bulk.plan(self.p, pairs_spec("1-30", "31-60", mode="remove"))
            self.assertEqual((plan.errors, plan.rules_after), ([], 0))

    def test_apply_and_undo(self):
        before = dict(self.p.fusions)
        plan = bulk.plan(self.p, pairs_spec("1-10", "1-10", result=599, stronger=False, overwrite=True))
        batch = bulk.apply(self.p, plan)
        self.assertEqual(self.p.fusions[(1, 2)], 599)
        self.assertEqual(len(self.p.fusions), 45)
        self.p.set_fusion(3, 4, 598)                         # edited after the batch: stays
        self.assertEqual(bulk.undo(self.p, batch), (44, 1))
        self.assertEqual(self.p.fusions, {**before, (3, 4): 598})
        self.assertRaises(ValueError, bulk.undo, project(), batch)

    def test_whole_table_is_fast(self):
        p = project()
        spec = bulk.BulkSpec(a=bulk.CardFilter(kinds=ALL), b=bulk.CardFilter(kinds=ALL), result=599,
                             stronger=False, overwrite=True, allow_self=True)
        start = time.perf_counter()
        plan = bulk.plan(p, spec)
        took = time.perf_counter() - start
        self.assertEqual(plan.pairs, 722 * 723 // 2)
        self.assertEqual(plan.duplicates, 722 * 721 // 2)
        self.assertEqual(len(plan.changes) + plan.same, plan.pairs)
        self.assertLess(took, 5.0)
        self.assertLessEqual(len(plan.samples), bulk.SAMPLE)


class ModTest(unittest.TestCase):
    def test_written_and_read_back(self):
        p = project()
        p.info.id = "bulk-test"
        spec = bulk.BulkSpec(a=bulk.CardFilter(types={0}), b=bulk.CardFilter(types={15}), result=599,
                             overwrite=True)
        plan = bulk.plan(p, spec)
        self.assertTrue(plan.ok())
        bulk.apply(p, plan)
        with tempfile.TemporaryDirectory() as folder:
            manifest.save_mod(p, Path(folder) / "bulk-test")
            again, _ = manifest.open_mod(p.retail, Path(folder) / "bulk-test")
        self.assertEqual(again.fusions, p.fusions)


class DialogTest(unittest.TestCase):
    """The window, as a user fills it, on the synthetic game."""

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
        from fm_editor.app import App
        self.app = App(ask=False, autostart=False)
        self.app.withdraw()
        self.app.update()
        self.app.start(str(self.game), None, False)
        self.app.update()

    def tearDown(self):
        self.app.dirty = False
        self.app.destroy()

    def test_bulk_add_and_undo(self):
        from fm_editor import bulk_dialog
        app = self.app
        tab = app.fusions
        before = dict(app.project.fusions)
        dialog = bulk_dialog.open_bulk(tab)
        dialog.a.types.selection_set(0)                  # Dragon
        dialog.b.types.selection_set(15)                 # Thunder
        dialog.b.texts["atk_max"].set("2500")
        dialog.result.set(599)
        dialog.overwrite.set("overwrite")
        plan = dialog.refresh()
        self.assertEqual(dialog.a.count.cget("text"), "30 cards")
        self.assertEqual(plan.errors, [])
        self.assertTrue(dialog.tree.get_children())
        self.assertIn("to add", dialog.summary.cget("text"))
        with mock.patch.object(bulk_dialog.messagebox, "askokcancel", return_value=False):
            dialog.apply()
        self.assertEqual(app.project.fusions, before)     # cancelled: nothing changed
        with mock.patch.object(bulk_dialog.messagebox, "askokcancel", return_value=True):
            dialog.apply()
        self.assertTrue(app.dirty)
        self.assertEqual(app.project.fusions[(20, 35)], 599)
        self.assertEqual(str(dialog.undo_button["state"]), "normal")
        with mock.patch.object(bulk_dialog.messagebox, "showinfo"):
            dialog.undo()
        self.assertEqual(app.project.fusions, before)
        # a bad bound says so and cannot be applied
        dialog.a.texts["atk_min"].set("lots")
        self.assertIsNone(dialog.refresh())
        self.assertIn("not a whole number", dialog.problem.cget("text"))
        self.assertIn("disabled", dialog.apply_button.state())
        dialog.destroy()

    def test_bulk_remove(self):
        from fm_editor import bulk_dialog
        app = self.app
        dialog = bulk_dialog.open_bulk(app.fusions)
        dialog.mode.set("remove")
        dialog.mode_changed()
        dialog.a.texts["cards"].set("Blue Dragon")
        dialog.b.texts["cards"].set("Mystic Elf")
        plan = dialog.refresh()
        self.assertEqual([pair for pair, _, _ in plan.changes], [(1, 2)])
        with mock.patch.object(bulk_dialog.messagebox, "askokcancel", return_value=True):
            dialog.apply()
        self.assertNotIn((1, 2), app.project.fusions)
        self.assertEqual(app.project.fusion_status((1, 2)), "removed")
        dialog.destroy()


if __name__ == "__main__":
    unittest.main()
