"""What mods change in common (overlaps.py): the same lines as the game's
Mods window (src/pc/mods/overlap.c) for the mods in tests/pc/mod_overlaps,
the load order the game would give them, and the Conflicts tab's check of
the mod being edited against the other installed mods.

    python -m unittest discover -s tools/pc/fm_editor/tests -t tools/pc
"""
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from fm_editor import manifest, overlaps, validate
from fm_editor.model import Project
from fm_editor.tests.test_data import fixture

FIXTURE = Path(__file__).resolve().parents[4] / "tests" / "pc" / "mod_overlaps"
# What tests/pc/mod_overlaps/duelists-64 makes (tests/pc/mods_overlap_test.c too).
DUELISTS_64 = "heishin2's POW drops (B, C): C's \"replace\" clears what the earlier mods set"


class FixtureSource(overlaps.Source):
    """The cards and opponents tests/pc/mods_overlap_test.c's resolver knows."""

    def __init__(self, setup):
        self.cards = {int(k): v for k, v in setup["cards"].items()}
        self.types = {int(k): v for k, v in setup["types"].items()}
        self.duelists = setup["duelists"]

    def card_info(self, cid):
        if cid not in self.types:
            return None
        return cid, self.types[cid][0], self.types[cid][1]

    def card(self, text, number):
        for cid, name in self.cards.items():
            if text is None and number == cid:
                return cid
            if text is not None and (overlaps.letters(text) == overlaps.letters(name) or text == str(cid)):
                return cid
        return -1

    def card_name(self, cid):
        return self.cards.get(cid)

    def duelist(self, text):
        for name, did in self.duelists.items():
            if overlaps.letters(text) == overlaps.letters(name) or (overlaps.is_digits(text) and int(text) == did):
                return did
        return -1


def fixture_mods():
    setup = json.loads((FIXTURE / "fixture.json").read_text(encoding="utf-8"))
    mods = []
    for mid in setup["order"]:
        manifest = json.loads((FIXTURE / mid / "mod.json").read_text(encoding="utf-8"))
        mods.append(overlaps.Mod(mid, manifest["name"], manifest, FIXTURE / mid))
    return setup, mods


class SameAsTheGame(unittest.TestCase):
    def test_the_fixture_lines(self):
        # The lines and their texts, in the order the Mods window lists them.
        setup, mods = fixture_mods()
        found = overlaps.check(mods, FixtureSource(setup))
        expected = [row for row in (FIXTURE / "expected.txt").read_text(encoding="utf-8").splitlines() if row]
        self.assertEqual([f"{overlaps.line(o)}\t{o.text}" for o in found], expected)

    def test_involving_one_mod(self):
        # The editor's check works out only the overlaps of the mod it edits.
        setup, mods = fixture_mods()
        every = [o.text for o in overlaps.check(mods, FixtureSource(setup)) if "Gamma" in o.text.split(": ")[0]]
        only = [o.text for o in overlaps.check(mods, FixtureSource(setup), involving=2)]
        self.assertEqual(only, every)

    def test_the_texts(self):
        setup, mods = fixture_mods()
        texts = {o.label: o.text for o in overlaps.check(mods, FixtureSource(setup))}
        self.assertEqual(texts["Price of 'Mystical Elf'"],
                         "Price of 'Mystical Elf' (Alpha, Beta): Beta wins (later in load order, through its \"all\")")
        self.assertEqual(texts["menu.spacing"],
                         "menu.spacing (Beta, Gamma): Gamma wins (it loads after Beta on purpose: after/requires)")
        self.assertEqual(texts["Card 'Blue-eyes White Dragon'"],
                         "Card 'Blue-eyes White Dragon' (Alpha, Beta): Beta's description is used (cards are read in folder "
                         "order, not load order); "
                         "the rest combines")

    def test_wrong_types_are_nothing(self):
        # A list where an object belongs, a number where a list does: the game
        # notes them and reads on, so a player has such a mod installed, and
        # the check (which runs as any mod is opened) must read on too.
        wrong = [
            {"limits": [1], "title": [{}], "menu": [[1]], "terrain_bonus": [1], "decks": [{}],
             "drops": [{"pow": {}}], "passwords": [1], "trap_thresholds": [2], "audio": {"music": ["a"]}},
            {"cards": 5, "fusions": 5, "equips": 5, "rituals": 5, "data": 5, "textures": 5,
             "guardian_stars": {"stars": 5, "matchups": 5}, "menu": {"buttons": [[1], 5, {"id": 5}]}, "text": 5,
             "settings": 5, "after": 5},
            {"limits": {"life_points": {"duelists": [1]}}, "guardian_stars": {"stars": [{"id": 11, "beats": 5}]},
             "drops": {"all": [1]}, "decks": {"all": 5}, "terrain_bonus": {"Forest": [1]}}]
        for a in wrong:
            for b in wrong:
                mods = [overlaps.Mod("w0", "w0", dict(a, id="w0")), overlaps.Mod("w1", "w1", dict(b, id="w1"))]
                for found in overlaps.check(mods):
                    self.assertTrue(found.text)
                overlaps.load_order(mods)

    def test_cards_in_the_order_found(self):
        # The cards are read in the order the mods were found, not in load
        # order: "b" loads later but was found first, so "a" has the card.
        a = overlaps.Mod("a", "A", {"cards": [{"replace": 1, "attack": 100}]}, found=1)
        b = overlaps.Mod("b", "B", {"cards": [{"replace": 1, "attack": 200}]}, found=0)
        found = overlaps.check([a, b])
        self.assertEqual(found[0].text, "Card #1 (B, A): A's attack is used (cards are read in folder order, not load order); "
                                        "the rest combines")

    def test_duelists_64(self):
        # 64 duelists in one mod's folder, then one of its list without an
        # "id", then another mod's duelist whose pool file a third mod meets
        # (the C engine once lost or freed its list here).
        setup, _ = fixture_mods()
        folder = FIXTURE / "duelists-64"
        mods = [overlaps.Mod(m, m.upper(), overlaps._read_json(folder / m / "mod.json"), folder / m, found=i)
                for i, m in enumerate(("a", "b", "c"))]
        found = overlaps.check(mods, FixtureSource(setup))
        self.assertEqual([o.text for o in found], [DUELISTS_64])

    def test_one_mod_is_nothing(self):
        setup, mods = fixture_mods()
        self.assertEqual(overlaps.check(mods[:1], FixtureSource(setup)), [])

    def test_load_order(self):
        _, mods = fixture_mods()
        # Gamma names Beta in "after": however low its rank, it loads after it.
        order = overlaps.load_order(list(reversed(mods)), {"mod.gamma.order": -5})
        self.assertEqual([m.id for m in order], ["alpha", "beta", "gamma"])
        order = overlaps.load_order(mods, {"mod.alpha.order": 10})
        self.assertEqual([m.id for m in order], ["beta", "gamma", "alpha"])


class ConflictsTab(unittest.TestCase):
    """validate.cross_mod: the mod being edited against the installed ones."""

    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        for mid in ("alpha", "beta"):
            shutil.copytree(FIXTURE / mid, self.folder / mid)

    def tearDown(self):
        shutil.rmtree(self.folder, ignore_errors=True)

    def test_against_installed_mods(self):
        project = Project(fixture().game())
        project.info.id = "mine"
        project.info.name = "Mine"
        project.other["priority"] = 5
        project.other["limits"] = {"stats": 12000}
        (self.folder / "settings.txt").write_text("mod.alpha=1\nmod.beta=0\n", encoding="utf-8")
        issues, summary = validate.cross_mod(project, [self.folder], self.folder / "settings.txt")
        stats = [i for i in issues if i.where.startswith("Limit stats")]
        self.assertEqual(len(stats), 1)
        self.assertEqual(stats[0].level, "warning")
        self.assertIn("Mine wins (later in load order)", stats[0].message)
        self.assertIn("2 installed mods", summary)
        self.assertIn("beta is off in the game now", summary)

    def test_renamed_mod_is_itself(self):
        # Opened from alpha/ and given another id: the folder it came from is
        # still this mod, not another installed one meeting it everywhere.
        project, _ = manifest.open_mod(fixture().game(), self.folder / "alpha")
        project.info.id = "renamed"
        issues, summary = validate.cross_mod(project, [self.folder], False)
        self.assertIn("Checked against 1 installed mods", summary)
        self.assertFalse(any("renamed" in i.message and "Alpha" in i.message and "Beta" not in i.message
                             for i in issues))

    def test_cycle_is_left_out(self):
        a = overlaps.Mod("a", "A", {"after": ["b"]})
        b = overlaps.Mod("b", "B", {"after": ["a"]})
        c = overlaps.Mod("c", "C", {"requires": ["missing"]})
        d = overlaps.Mod("d", "D", {})
        self.assertEqual([m.id for m in overlaps.load_order([a, b, c, d])], ["d"])

    def test_applied(self):
        mod = overlaps.Mod("x-y", "X", {"legacy_setting": "old_x"})
        self.assertFalse(validate.applied(mod, {}))
        self.assertTrue(validate.applied(mod, {"old_x": 1}))
        self.assertFalse(validate.applied(mod, {"old_x": 1, "mod.x-y": 0}))
        os.environ["MEMORIES_MOD_X_Y"] = "1"
        try:
            self.assertTrue(validate.applied(mod, {"mod.x-y": 0}))
        finally:
            del os.environ["MEMORIES_MOD_X_Y"]

    def test_no_other_mods(self):
        project = Project(fixture().game())
        issues, summary = validate.cross_mod(project, [self.folder / "nothing"], None)
        self.assertEqual(issues, [])
        self.assertIn("no other installed mods", summary)


if __name__ == "__main__":
    unittest.main()
