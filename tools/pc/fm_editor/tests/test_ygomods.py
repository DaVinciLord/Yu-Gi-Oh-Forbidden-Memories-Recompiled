"""The .ygomods importer on a package written here (synthetic cards)."""
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from fm_editor import manifest, validate, ygomods
from fm_editor.tests.test_data import fixture, state


def package(files: dict) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        for name, text in files.items():
            z.writestr(name, text)
    return out.getvalue()


FILES = {
    "manifest.ini": "; test\nformat = YGOFM-MOD-PACKAGE\nversion = 1\ngame = SLUS-01411\n",
    "cards/1/card.ini": "color = pink\nname = Big Dragon\nattack = 2070\nstar1 = Pluto\nstar2 = Uranus\n"
                        "price = 4100\npassword = 70022514\ndescription = Line one|line two\non_flip = raigeki\n",
    "cards/1/art.png": b"\x89PNG fake",
    "cards/651/card.ini": "equips = 1, 2, 3\n",
    "cards/681/card.ini": "ritual = 4, 5, 6 -> 7\n",
    "fusion-edits.txt": "# a b result\n1\t2\t9\n2\t1\t0\n5\t6\t7\n",
    "drop_table_edits.ini": "; weights\n[Simon Muran]\n5 = 100, 0, 3\ncard = 92\n[Starchip Reward 1]\nmode = x\n",
    "cpu-duelists.ini": "[Heishin]\nname = Heishin X\nai = 5, 20, 9, 1, 1, 0, 0, 25, 50\n" +
                        "".join(f"{c} = {10 + c}\n" for c in range(1, 16)),
    "duelists/10/portrait.png": b"\x89PNG portrait",
    "dialogue.txt": "[127A]\nhello\n",
    "mod_settings.ini": "card_drops = 15\n",
}


class YgomodsTest(unittest.TestCase):
    def setUp(self):
        self.f = fixture()
        self.retail = self.f.game()
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "test.ygomods"
        self.path.write_bytes(package(FILES))

    def tearDown(self):
        self.tmp.cleanup()

    def test_import(self):
        project, report = ygomods.import_package(self.retail, self.f.wa, self.path, "pkg")
        text = "\n".join(report)
        card = project.cards[1]
        self.assertEqual((card.name, card.attack, card.star1, card.star2), ("Big Dragon", 2070, 5, 4))
        self.assertEqual(card.description, "Line one\nline two")
        self.assertEqual(project.card_extra[1], {"art": "images/001-art.png"})
        self.assertEqual(project.equips[651], {1, 2, 3})
        self.assertEqual(project.rituals[681], (4, 5, 6, 7))
        self.assertEqual(project.fusions.get((1, 2)), None)          # the later line removes it
        self.assertEqual(project.fusions[(5, 6)], 7)
        self.assertEqual(project.pools[1]["pow"][5], 100)
        self.assertEqual(sum(project.pools[1]["pow"].values()), 2048)
        self.assertEqual(sorted(project.pools[8]["deck"]), list(range(1, 16)))
        self.assertIn(b"[8330]\nHeishin X{end}", project.files["text.txt"])
        entries = json.loads(project.files["textures/manifest.json"])
        self.assertEqual(entries[0]["offset"], 0xF55000 + 10 * 0x980)
        patch = project.other["data"][0]["patch"][0]
        self.assertEqual(patch["at"], f"0x{0xFB9800 + 8:X}")
        self.assertEqual(patch["bytes"], "04 10 00 00 14 25 02 70")
        for what in ("on_flip", "color", "AI profile", "dialogue.txt", "StarChip", "scripted rewards", "mod_settings"):
            self.assertIn(what, text)
        self.assertEqual(validate.errors(validate.validate(project)), [])
        with tempfile.TemporaryDirectory() as out:
            manifest.save_mod(project, out)
            self.assertTrue((Path(out) / "images" / "001-art.png").exists())
            self.assertTrue((Path(out) / "textures" / "portraits" / "freeduel-10.png").exists())
            opened, messages = manifest.open_mod(self.retail, out)
            self.assertEqual(messages, [])
            self.assertEqual(state(opened), state(project))

    def test_not_a_package(self):
        bad = Path(self.tmp.name) / "bad.ygomods"
        bad.write_bytes(package({"manifest.ini": "format = OTHER\n"}))
        with self.assertRaises(ygomods.PackageError):
            ygomods.import_package(self.retail, self.f.wa, bad)
        bad.write_bytes(b"not a zip")
        with self.assertRaises(ygomods.PackageError):
            ygomods.import_package(self.retail, self.f.wa, bad)


if __name__ == "__main__":
    unittest.main()
