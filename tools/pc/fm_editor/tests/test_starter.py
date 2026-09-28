"""The starter decks a mod offers a new game ("starter",
notes/starter-deck.md): the manifest layer, the checks, and the tab.

    python -m unittest discover -s tools/pc/fm_editor/tests -t tools/pc
"""
import json
import tempfile
import unittest
from pathlib import Path

try:
    import tkinter as tk
except ImportError:     # a Python built without Tk
    tk = None

from fm_editor import manifest, validate
from fm_editor.gamedata import DECK_SIZE, EXODIA_FIRST_CARD_ID
from fm_editor.model import Project, StarterDeck
from fm_editor.tests.test_data import fixture


def project() -> Project:
    return Project(fixture().game())


def read(source: dict):
    p = project()
    messages = manifest.apply(p, {"id": "m", **source})
    return p, messages


def full(**cards) -> dict:
    """A deck of forty from three copies each, so nothing but what a case
    asks for is out of the ordinary."""
    deck = dict(cards)
    left, cid = DECK_SIZE - sum(deck.values()), 100
    while left > 0:
        take = min(3, left)
        deck[str(cid)] = take
        left -= take
        cid += 1
    return deck


class ManifestTest(unittest.TestCase):
    def test_one_deck_is_read_and_written_as_an_object(self):
        p, messages = read({"starter": full()})
        self.assertEqual(len(p.starter), 1)
        self.assertEqual(p.starter[0].total(), DECK_SIZE)
        self.assertTrue(p.starter[0].complete())
        self.assertEqual(messages, [])
        written = manifest.build(p)["starter"]
        self.assertIsInstance(written, dict)

    def test_several_decks_keep_their_order_and_weights(self):
        p, _ = read({"starter": [dict(full(), name="a", weight=3), dict(full(), name="b")]})
        self.assertEqual([(d.name, d.weight) for d in p.starter], [("a", 3), ("b", 1)])
        written = manifest.build(p)["starter"]
        self.assertIsInstance(written, list)
        self.assertEqual(written[0]["weight"], 3)
        self.assertNotIn("weight", written[1])      # 1 is the default, so it is not written

    def test_round_trip_is_identical(self):
        source = {"starter": [dict(full(**{"2": 3}), name="a", weight=2),
                              dict(full(**{"3": 1}), name="b")]}
        p, _ = read(source)
        again, _ = read({k: v for k, v in manifest.build(p).items() if k == "starter"})
        self.assertEqual([(d.name, d.weight, d.cards, d.kept) for d in p.starter],
                         [(d.name, d.weight, d.cards, d.kept) for d in again.starter])

    def test_a_card_it_cannot_place_is_kept_as_written(self):
        # A card a mod added, or a misspelling: either way the editor cannot
        # place it, and dropping it would throw away somebody else's deck.
        p, messages = read({"starter": full(**{"No Such Card": 4})})
        self.assertEqual(p.starter[0].kept, {"No Such Card": 4})
        self.assertTrue(any("kept as written" in m for m in messages))
        self.assertIn("No Such Card", manifest.build(p)["starter"])

    def test_a_short_deck_is_kept_so_it_can_be_finished(self):
        p, messages = read({"starter": {"2": 10}})
        self.assertEqual(len(p.starter), 1)
        self.assertFalse(p.starter[0].complete())
        self.assertTrue(any("40 cards" in m for m in messages))

    def test_copies_and_weights_out_of_range(self):
        p, messages = read({"starter": {"2": -1, "3": 40}})
        self.assertEqual(p.starter[0].cards, {3: 40})
        self.assertTrue(any("copies are a whole number" in m for m in messages))
        p, messages = read({"starter": dict(full(), weight=-1)})
        self.assertEqual(p.starter, [])         # the port leaves the whole deck out
        p, messages = read({"starter": dict(full(), weight="2")})
        self.assertEqual(p.starter, [])

    def test_zero_copies_are_no_card(self):
        p, _ = read({"starter": dict(full(), **{"2": 0})})
        self.assertNotIn(2, p.starter[0].cards)

    def test_starter_naming_a_file_stays_that_file(self):
        p, messages = read({"starter": "decks/starter.json"})
        self.assertEqual(p.starter_file, "decks/starter.json")
        self.assertEqual(manifest.build(p)["starter"], "decks/starter.json")
        self.assertTrue(any("kept as written" in m for m in messages))

    def test_a_deck_of_the_wrong_shape_is_left_out(self):
        p, messages = read({"starter": 40})
        self.assertEqual(p.starter, [])
        self.assertTrue(any("a deck, or a list of decks" in m for m in messages))
        p, messages = read({"starter": [40]})
        self.assertEqual(p.starter, [])

    def test_no_starter_key_writes_none(self):
        p, _ = read({})
        self.assertNotIn("starter", manifest.build(p))

    def test_it_is_no_longer_kept_as_an_unknown_key(self):
        p, _ = read({"starter": full()})
        self.assertNotIn("starter", p.other)


class ChecksTest(unittest.TestCase):
    def issues(self, source):
        p, _ = read(source)
        return [i for i in validate.validate(p) if i.area == "Starter decks"]

    def test_a_complete_deck_is_quiet(self):
        self.assertEqual(self.issues({"starter": full()}), [])

    def test_a_short_deck_is_an_error(self):
        found = self.issues({"starter": {"2": 10}})
        self.assertTrue(any(i.level == "error" and "40 cards" in i.message for i in found))

    def test_over_three_copies_warns_but_is_allowed(self):
        found = self.issues({"starter": full(**{"2": 4})})
        self.assertTrue(any(i.level == "warning" and "Build Deck" in i.message for i in found))
        self.assertFalse([i for i in found if i.level == "error"])

    def test_two_of_an_exodia_piece_warns(self):
        found = self.issues({"starter": full(**{str(EXODIA_FIRST_CARD_ID): 2})})
        self.assertTrue(any(i.level == "warning" and "Exodia" in i.message for i in found))

    def test_every_deck_weighing_nothing_warns(self):
        found = self.issues({"starter": [dict(full(), weight=0)]})
        self.assertTrue(any("never picked" in i.message or "none is ever picked" in i.message for i in found))


@unittest.skipIf(tk is None, "this Python has no Tk")
class TabTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
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

    def test_a_deck_built_in_the_tab_is_saved(self):
        app, tab = self.app, self.app.starter
        app.project.starter.append(StarterDeck(name="Spellbinder", weight=2, cards={2: 3, 3: 37}))
        tab.refresh()
        self.assertEqual(len(tab.list.get_children()), 1)
        self.assertTrue(tab.tree.exists("2"))
        # the total line counts the forty
        self.assertIn(f"{DECK_SIZE} / {DECK_SIZE}", tab.total.cget("text"))
        with tempfile.TemporaryDirectory() as out:
            folder = Path(out) / "mod"
            manifest.save_mod(app.project, folder)
            written = json.loads((folder / "mod.json").read_text(encoding="utf-8"))
        self.assertEqual(written["starter"]["name"], "Spellbinder")
        self.assertEqual(written["starter"]["weight"], 2)

    def test_setting_copies_and_removing_a_card(self):
        app, tab = self.app, self.app.starter
        app.project.starter.append(StarterDeck(name="d", cards={2: 3, 3: 37}))
        tab.refresh()
        tab.tree.selection_set("2")
        tab.copies.set("5")
        tab.set_copies()
        self.assertEqual(app.project.starter[0].cards[2], 5)
        tab.tree.selection_set("3")
        tab.remove_card()
        self.assertNotIn(3, app.project.starter[0].cards)
        # setting a card to zero copies takes it out, as the pools do
        tab.tree.selection_set("2")
        tab.copies.set("0")
        tab.set_copies()
        self.assertEqual(app.project.starter[0].cards, {})

    def test_an_empty_tab_shows_no_deck(self):
        tab = self.app.starter
        tab.refresh()
        self.assertIsNone(tab.current())
        self.assertEqual(tab.title.cget("text"), "No starter deck")


if __name__ == "__main__":
    unittest.main()
