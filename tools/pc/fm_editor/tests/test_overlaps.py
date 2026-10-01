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

from fm_editor import overlaps, validate
from fm_editor.model import Project
from fm_editor.tests.test_data import fixture

FIXTURE = Path(__file__).resolve().parents[4] / "tests" / "pc" / "mod_overlaps"


class FixtureSource(overlaps.Source):
    """The cards and opponents tests/pc/mods_overlap_test.c's resolver knows."""

    def __init__(self, setup):
        self.cards = {int(k): v for k, v in setup["cards"].items()}
        self.duelists = setup["duelists"]

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
        setup, mods = fixture_mods()
        found = overlaps.check(mods, FixtureSource(setup))
        expected = [row for row in (FIXTURE / "expected.txt").read_text(encoding="utf-8").splitlines() if row]
        self.assertEqual(sorted(overlaps.line(o) for o in found), expected)

    def test_the_texts(self):
        setup, mods = fixture_mods()
        texts = {o.label: o.text for o in overlaps.check(mods, FixtureSource(setup))}
        self.assertEqual(texts["Price of 'Mystical Elf'"],
                         "Price of 'Mystical Elf' (Alpha, Beta): Beta wins (later in load order, through its \"all\")")
        self.assertEqual(texts["menu.spacing"],
                         "menu.spacing (Beta, Gamma): Gamma wins (it loads after Beta on purpose: after/requires)")
        self.assertEqual(texts["Card 'Blue-eyes White Dragon'"],
                         "Card 'Blue-eyes White Dragon' (Alpha, Beta): the later mod's description is used; "
                         "the rest combines")

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

    def test_no_other_mods(self):
        project = Project(fixture().game())
        issues, summary = validate.cross_mod(project, [self.folder / "nothing"], None)
        self.assertEqual(issues, [])
        self.assertIn("no other installed mods", summary)


if __name__ == "__main__":
    unittest.main()
