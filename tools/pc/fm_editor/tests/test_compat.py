"""Which game a mod needs: "min_api" from the features its mod.json uses
(compat.py), and the editor's mod API against the game's.

    python -m unittest discover -s tools/pc/fm_editor/tests -t tools/pc
"""
import re
import json
import tempfile
import unittest
from pathlib import Path

from fm_editor import compat, gamedata as g, manifest, validate
from fm_editor.model import Project
from fm_editor.tests.fixtures import Fixture

ROOT = Path(__file__).resolve().parents[4]
MOD_TYPES = ROOT / "src/pc/mods/mod_types.h"
FIXTURE = None


def fixture() -> Fixture:
    global FIXTURE
    if FIXTURE is None:
        FIXTURE = Fixture()
    return FIXTURE


class HostApiTest(unittest.TestCase):
    @unittest.skipUnless(MOD_TYPES.exists(), "no source tree (the packaged editor)")
    def test_matches_the_game(self):
        """The editor's mod API is the game's (MEMORIES_MOD_API), so a mod
        the game takes is not called too new, nor one it refuses fine."""
        found = re.search(r"^#define\s+MEMORIES_MOD_API\s+(\d+)\s*$", MOD_TYPES.read_text(), re.M)
        self.assertIsNotNone(found, "MEMORIES_MOD_API is not in mod_types.h")
        self.assertEqual(compat.HOST_API, int(found.group(1)),
                         "fm_editor/compat.py HOST_API differs from src/pc/mods/mod_types.h MEMORIES_MOD_API")
        self.assertIs(validate.HOST_API, compat.HOST_API)

    def test_every_feature_is_within_the_host(self):
        self.assertLessEqual(max(compat.RELEASES), compat.HOST_API)

    def test_validate_takes_the_host_api(self):
        p = Project(fixture().game())
        p.info.id = "api"
        for api, error in ((9, False), (10, False), (compat.HOST_API, False), (compat.HOST_API + 1, True)):
            p.other["min_api"] = api
            issues = [i for i in validate.validate(p) if i.where == "min_api"]
            self.assertEqual(bool(issues), error, api)


class FeatureTest(unittest.TestCase):
    """Each feature newer than v0.2.0 (API 9), alone, and the API it needs."""

    def needs(self, manifest_value: dict, project=None):
        return compat.required(manifest_value, project)[0]

    def test_nothing_new(self):
        old = {"id": "old", "cards": [{"replace": 1, "name": "X", "frame": "Purple", "notes": "n"}],
               "fusions": [{"with": [1, 2], "result": 3}, {"remove": [1, 2]}],
               "rituals": [{"card": 690, "tributes": [1, 2, 3], "result": 4}, {"card": 691, "result": None}],
               "equips": [{"card": 650, "bonus": 300}], "limits": {"attack": 30000, "life_points": 16000},
               "title": {"entries": {}}, "menu": {"entries": {}}, "starter_pools": [], "duelists": [{"copy": 1}],
               "packs": [{"name": "P"}], "trap_thresholds": {}}
        self.assertEqual(compat.required(old), (0, []))
        self.assertNotIn("min_api", compat.stamp(dict(old)))

    def test_api_10(self):
        for value in ({"card_text_colors": {}},
                      {"cards": [{"replace": 5, "monster_effects": []}]},
                      {"cards": [{"replace": 690, "trap_threshold": 1500}]},
                      {"cards": [{"copy": 5, "id": "c", "model": "Blue Dragon"}]},
                      {"cards": [{"copy": 610, "id": "c", "effect": "Card 611"}]},
                      {"equips": [{"card": 650, "bonus_attack": 300, "bonus_defense": 0}]},
                      {"packs": [{"name": "P", "image_style": "full"}]}):
            with self.subTest(value=value):
                self.assertEqual(self.needs(value), 10)

    def test_api_11(self):
        for value in ({"assets": "assets"}, {"ui": {"duel": {}}}, {"card_layout": {}}, {"palette_ramps": {"0": "#FF0000"}},
                      {"title": {"images": []}}, {"menu": {"scale": 120}},
                      {"menu": {"buttons": [{"id": "b", "scale": 80}]}},
                      {"title": {"entries": {"logo": {"scale": 50}}}},
                      {"cards": [{"replace": 1, "tags": ["dragon"]}]},
                      {"cards": [{"replace": 1, "frame": "Gold"}]}, {"cards": [{"replace": 1, "frame": "blue"}]},
                      {"cards": [{"replace": 1, "monster_effects": [
                          {"when": "face_up", "do": "boost", "attack": 300, "for_each": {"whose": "own"}}]}]},
                      {"fusions": [{"remove": "all"}]},
                      {"rituals": [{"card": 690, "tributes": [1, 2], "result": 4}]},
                      {"rituals": [{"card": 690, "tributes": [1, 2, 3, 4, 5], "result": 4}]},
                      {"rituals": [{"card": 690, "tributes": [1, 2, 3], "tributes_from": "hand", "result": 4}]},
                      {"limits": {"deck_copies": 5}}, {"limits": {"attack": 9999, "new_game_starchips": 10}}):
            with self.subTest(value=value):
                self.assertEqual(self.needs(value), 11)

    def test_reasons_are_the_highest_apis(self):
        api, reasons = compat.required({"card_text_colors": {}, "ui": {}, "limits": {"swords_turns": 5}})
        self.assertEqual(api, 11)
        self.assertEqual(len(reasons), 2)
        self.assertIn("swords_turns", reasons[1])

    def test_a_field_ritual_of_three_is_old(self):
        self.assertEqual(self.needs({"rituals": [{"card": 690, "tributes": [1, 2, 3], "tributes_from": "field",
                                                  "result": 4}]}), 0)

    def test_disc_frame_names_are_old(self):
        for frame in g.FRAME_NAMES + ["Type"]:
            self.assertEqual(self.needs({"cards": [{"replace": 1, "frame": frame}]}), 0, frame)

    def test_a_copy_of_another_kind(self):
        p = Project(fixture().game())
        monster, magic, equip = 5, 610, 660     # the fixture's types
        self.assertLess(p.cards[monster].type, g.TYPE_MAGIC)
        copy = lambda base, kind: {"cards": [{"copy": base, "id": "c", "type": kind}]}
        self.assertEqual(self.needs(copy(monster, "Dragon"), p), 0)        # a monster stays one
        self.assertEqual(self.needs(copy(monster, "Magic"), p), 10)
        self.assertEqual(self.needs(copy(magic, "Magic"), p), 0)
        self.assertEqual(self.needs(copy(magic, "Warrior"), p), 10)        # any card may become a monster
        self.assertEqual(self.needs(copy(equip, g.TYPE_MAGIC), p), 10)
        self.assertEqual(self.needs(copy(monster, "Magic")), 0)          # no project: the base is not known


class StampTest(unittest.TestCase):
    def setUp(self):
        self.p = Project(fixture().game())
        self.p.info.id = "stamp"

    def test_written_on_save_after_the_info(self):
        self.p.set_tags(1, ["dragon"])
        built = manifest.build(self.p)
        self.assertEqual(built["min_api"], 11)
        keys = list(built)
        self.assertTrue(set(keys[:keys.index("min_api")]) <= set(manifest.INFO_KEYS), keys)
        self.assertNotIn(keys[keys.index("min_api") + 1], manifest.INFO_KEYS)

    def test_retail_writes_none(self):
        self.assertNotIn("min_api", manifest.build(self.p))

    def test_never_lowered(self):
        self.p.equip_bonus[660] = (300, 100)
        self.p.other["min_api"] = 11
        self.assertEqual(manifest.build(self.p)["min_api"], 11)
        self.p.other["min_api"] = 4
        self.assertEqual(manifest.build(self.p)["min_api"], 10)
        self.assertEqual(self.p.other["min_api"], 4)    # what the author wrote stays theirs

    def test_not_a_number_is_left_to_validate(self):
        self.p.set_tags(1, ["dragon"])
        self.p.other["min_api"] = "11"
        self.assertEqual(manifest.build(self.p)["min_api"], "11")

    def test_round_trip(self):
        """Saved and opened again, the mod still says what it needs."""
        import tempfile
        self.p.set_tags(1, ["dragon"])
        with tempfile.TemporaryDirectory() as folder:
            manifest.save_mod(self.p, folder)
            data = manifest.read_json(Path(folder) / "mod.json")
            self.assertEqual(data["min_api"], 11)
            again = Project(fixture().game())
            manifest.apply(again, data)
            self.assertEqual(manifest.build(again)["min_api"], 11)

    def test_release_text(self):
        self.assertIn("v0.2.0", compat.release_text(9))
        self.assertIn("v0.2.1-preview.1 or newer", compat.release_text(10))
        self.assertIn("newer than v0.2.1-preview.1", compat.release_text(11))


class ExternalPacksTest(unittest.TestCase):
    def test_external_list_and_wrapper_survive_save_as(self):
        pack = {"id": "p", "image_style": "full"}
        for value in ([pack], {"packs": [pack], "pack_shop": {"open": False}}):
            with self.subTest(value=value), tempfile.TemporaryDirectory() as temporary:
                source, target = Path(temporary) / "source", Path(temporary) / "target"
                source.mkdir()
                (source / "mod.json").write_text(json.dumps({"id": "external", "packs": "packs.json"}))
                contents = json.dumps(value).encode()
                (source / "packs.json").write_bytes(contents)
                p, _ = manifest.open_mod(fixture().game(), source)
                self.assertEqual(manifest.build(p)["min_api"], 10)
                manifest.save_mod(p, target)
                self.assertEqual((target / "packs.json").read_bytes(), contents)
                again, _ = manifest.open_mod(fixture().game(), target)
                self.assertEqual(manifest.build(again)["min_api"], 10)
                self.assertEqual(manifest.build(again)["packs"], "packs.json")

    def test_staged_file_wins_and_requirement_is_never_lowered(self):
        p = Project(fixture().game())
        p.packs_file = "packs.json"
        p.files["packs.json"] = b'[{"image_style":"full"}]'
        self.assertEqual(manifest.build(p)["min_api"], 10)
        p.other["min_api"] = 11
        self.assertEqual(manifest.build(p)["min_api"], 11)

    def test_unreadable_or_invalid_file_is_not_claimed_compatible(self):
        p = Project(fixture().game())
        p.packs_file = "missing.json"
        self.assertTrue(compat.problems(manifest.build(p), p))
        self.assertTrue(any(i.area == "Packs" and i.level == "error" for i in validate.validate(p)))
        for contents in (b'{', b'null', b'{"packs": "recursive.json"}'):
            p.files[p.packs_file] = contents
            self.assertTrue(compat.problems(manifest.build(p), p))
        # A syntax error is said as one, not as the wrong kind of value.
        p.files[p.packs_file] = b'[{"id": "p",]'
        self.assertEqual(compat.problems(manifest.build(p), p), ["packs file 'missing.json' is not valid JSON"])
        p.files[p.packs_file] = b'null'
        self.assertIn("must contain a pack list", compat.problems(manifest.build(p), p)[0])
        for name in ("../packs.json", "/packs.json", "C:\\packs.json", "..\\packs.json",
                     "packs\\list.json", "./packs.json", "packs//list.json", "packs/"):
            p.packs_file = name
            p.files[name] = b'[]'
            self.assertTrue(compat.problems(manifest.build(p), p))

    def test_game_json_syntax_and_old_packs(self):
        p = Project(fixture().game())
        p.packs_file = "packs.json"
        p.files[p.packs_file] = b'[{"image_style":"full",},]'
        self.assertEqual(manifest.build(p)["min_api"], 10)
        p.files[p.packs_file] = b'[{"id":"old"}]'
        self.assertNotIn("min_api", manifest.build(p))


if __name__ == "__main__":
    unittest.main()
