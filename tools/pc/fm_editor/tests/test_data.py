"""The data layer on synthetic files: reading the tables, the diff to
mod.json, reading it back, and the port's pool arithmetic.

    python -m unittest discover -s tools/pc/fm_editor/tests -t tools/pc
"""
import json
import tempfile
import unittest
from pathlib import Path

from fm_editor import disc, gamedata as g, manifest, pools, validate
from fm_editor.model import Project
from fm_editor.tests.fixtures import Fixture, make_iso

FIXTURE = None


def fixture() -> Fixture:
    global FIXTURE
    if FIXTURE is None:
        FIXTURE = Fixture()
    return FIXTURE


def state(project: Project):
    """Everything a mod can change, for comparing two projects."""
    return ({cid: vars(card) for cid, card in project.cards.items()},
            {cid: (a.key, a.base, a.drops, a.opponents, a.extra) for cid, a in project.added.items()},
            project.fusions, {e: m for e, m in project.equips.items() if m or e in project.retail.equips},
            project.rituals, [{k: {c: w for c, w in v.items() if w} for k, v in d.items()} for d in project.pools],
            project.card_extra)


class ReadTest(unittest.TestCase):
    def test_cards(self):
        f = fixture()
        data = f.game()
        self.assertEqual(len(data.cards), g.CARD_COUNT)
        for cid in (1, 2, 3, 250, 600, 601, 651, 681, 722):
            self.assertTrue(data.cards[cid].same(f.cards[cid]), (data.cards[cid], f.cards[cid]))

    def test_tables(self):
        f = fixture()
        data = f.game()
        without_glitch = {p: r for p, r in data.fusions.items() if p not in data.glitch_fusions}
        self.assertEqual(without_glitch, f.fusions)
        self.assertEqual(data.equips, f.equips)
        self.assertEqual(data.rituals, f.rituals)
        self.assertEqual(data.pools, f.pools)
        self.assertEqual(data.notes, [])

    def test_fusion_counts_past_255(self):
        pairs = {(1, b): 700 for b in range(2, 300)}
        pairs[(2, 3)] = 4
        decoded, _ = g.decode_fusions(g.encode_fusions(pairs))
        self.assertEqual({p: r for p, r in decoded.items() if p in pairs}, pairs)

    def test_glitch_pair(self):
        # One pair under card 5: a three-byte group; the game compares a second
        # pair made of the next record's first two bytes.
        pairs = {(5, 6): 7, (8, 9): 10, (8, 11): 12}
        decoded, glitch = g.decode_fusions(g.encode_fusions(pairs))
        for pair, result in pairs.items():
            self.assertEqual(decoded[pair], result)
        self.assertTrue(all(p[0] == 5 for p in glitch))

    def test_disc_images(self):
        f = fixture()
        files = {"SLUS_014.11": f.slus, "DATA/WA_MRG.MRG": f.wa}
        with tempfile.TemporaryDirectory() as tmp:
            for raw, name in ((True, "game.bin"), (False, "game.iso")):
                path = Path(tmp) / name
                path.write_bytes(make_iso(files, raw))
                loaded = disc.load(path)
                self.assertEqual(loaded.slus, f.slus)
                self.assertEqual(loaded.wa, f.wa)
            folder = Path(tmp) / "extracted"
            (folder / "DATA").mkdir(parents=True)
            (folder / "SLUS_014.11").write_bytes(f.slus)
            (folder / "DATA" / "WA_MRG.MRG").write_bytes(f.wa)
            self.assertEqual(disc.load(folder).wa, f.wa)
            self.assertEqual(disc.load(folder / "SLUS_014.11").slus, f.slus)
            bad = Path(tmp) / "bad.bin"
            bad.write_bytes(bytes(2352 * 20))
            with self.assertRaises(disc.GameFilesError):
                disc.load(bad)


class PoolMathTest(unittest.TestCase):
    def test_scale_largest_remainder(self):
        weights = {1: 1, 2: 1, 3: 1}
        self.assertTrue(pools.scale(weights, [1, 2, 3], 2048))
        self.assertEqual(weights, {1: 683, 2: 683, 3: 682})   # lower id first between equals

    def test_replace_in_proportion(self):
        self.assertEqual(pools.apply_edit({5: 2048}, {1: 1, 2: 3}, replace=True), {1: 512, 2: 1536})

    def test_listed_keep_their_weight(self):
        result = pools.apply_edit({1: 1024, 2: 1024}, {3: 48})
        self.assertEqual(result, {1: 1000, 2: 1000, 3: 48})
        self.assertEqual(pools.apply_edit({1: 1024, 2: 1024}, {1: 0}), {2: 2048})

    def test_refusals(self):
        self.assertIsNone(pools.apply_edit({1: 2048}, {1: 0}))
        deck = {cid: 128 for cid in range(1, 17)}
        self.assertIsNone(pools.apply_edit(deck, {1: 0, 2: 0, 3: 0}, deck=True))
        self.assertIsNotNone(pools.apply_edit(deck, {1: 0, 2: 0}, deck=True))

    def test_edit_for_is_exact(self):
        retail = fixture().pools[3]["pow"]
        edited = dict(retail)
        moved = next(iter(edited))
        edited[moved] -= 40
        edited[599] = edited.get(599, 0) + 40
        listed, replace = pools.edit_for(retail, edited)
        self.assertFalse(replace)
        self.assertEqual(set(listed), {moved, 599})
        self.assertEqual(pools.apply_edit(retail, listed, replace), {c: w for c, w in edited.items() if w})
        self.assertIsNone(pools.edit_for(retail, dict(retail)))

    def test_normalize(self):
        self.assertEqual(sum(pools.normalize({1: 7, 2: 9, 3: 1}).values()), 2048)


class ManifestTest(unittest.TestCase):
    def setUp(self):
        self.retail = fixture().game()

    def test_retail_is_an_empty_mod(self):
        built = manifest.build(Project(self.retail))
        self.assertEqual(set(built), {"id", "name", "version"})

    def edited(self) -> Project:
        p = Project(self.retail)
        p.info.id = "test-mod"
        p.info.author = "Tester"
        # cards
        p.cards[1].name = "Bulbasaur"
        p.cards[1].attack = 1180
        p.cards[2].star1, p.cards[2].star2 = 8, 9
        p.cards[2].type = 19
        p.cards[3].description = "A round fellow.\nAlways late."
        p.card_extra[4] = {"art": "images/four.png"}
        new = p.add_card(3, "dingus")
        p.cards[new].name = "Dingus Shmingus"
        p.cards[new].attack = 2500
        p.added[new].opponents = True
        # fusions: change, forbid, add, and one with the new card
        pairs = sorted(self.retail.fusions)
        p.set_fusion(*pairs[0], 3)
        p.set_fusion(*pairs[1], None)
        p.set_fusion(597, 598, 599)
        p.set_fusion(new, 1, 2)
        # equips
        p.equips[651].discard(1)
        p.equips[651].add(new)
        p.equips[653] = {1}
        p.equips[652] |= {c for c in range(20, 601, 20) if c != 40}   # the Dragons (type 0) but one
        # rituals
        p.rituals[681] = (4, 5, 6, new)
        del p.rituals[682]
        # pools
        deck = p.pools[8]["deck"]
        first = next(iter(deck))
        deck[first] -= 100
        deck[new] = 100
        drop = p.pools[1]["pow"]
        gone = sorted(drop)[0]
        drop[sorted(drop)[1]] += drop.pop(gone)
        return p

    def test_round_trip(self):
        p = self.edited()
        self.assertEqual(validate.errors(validate.validate(p)), [])
        text = manifest.dumps(manifest.build(p))
        data = json.loads(text)
        self.assertEqual(data["cards"][0], {"replace": 1, "name": "Bulbasaur", "attack": 1180})
        self.assertEqual(data["cards"][1]["stars"], ["Sun", "Moon"])
        self.assertEqual(data["cards"][1]["type"], "Plant")
        self.assertEqual(data["cards"][-1]["copy"], 3)
        self.assertIn({"card": "Card 682", "result": None}, data["rituals"])
        self.assertEqual(set(data["decks"]), {"Heishin"})
        equip = next(e for e in data["equips"] if e["card"] == "Card 652")
        self.assertEqual((equip["add"], equip["remove"]), (["Dragon"], ["Card 40"]))
        self.assertEqual(set(data["drops"]), {"Simon Muran"})
        again = Project(self.retail)
        messages = manifest.apply(again, data)
        self.assertEqual(messages, [])
        self.assertEqual(state(again), state(p))
        self.assertEqual(manifest.build(again), manifest.build(p))

    def test_mod_folder(self):
        p = self.edited()
        p.other = {"text": "text.txt", "data": [{"file": "\\DATA\\WA_MRG.MRG;1", "patch": [{"at": "0x10", "bytes": "01"}]}],
                   "requires": ["other-mod"]}
        with tempfile.TemporaryDirectory() as tmp:
            first = Path(tmp) / "first"
            manifest.save_mod(p, first)
            (first / "text.txt").write_text("@bank names\n", encoding="utf-8")
            (first / "images").mkdir()
            (first / "images" / "four.png").write_bytes(b"png")
            opened, messages = manifest.open_mod(self.retail, first)
            self.assertEqual(messages, [])
            self.assertEqual(state(opened), state(p))
            self.assertEqual(opened.other, p.other)
            second = Path(tmp) / "second"
            manifest.save_mod(opened, second)
            self.assertTrue((second / "images" / "four.png").exists())
            self.assertEqual(manifest.read_json(second / "mod.json"), manifest.read_json(first / "mod.json"))
            game = Path(tmp) / "game"
            game.mkdir()
            (game / "SLUS_014.11").write_bytes(b"x")
            with self.assertRaises(ValueError):
                manifest.save_mod(opened, game)

    def test_reads_what_people_write(self):
        p = Project(self.retail)
        data = {
            "id": "hand", "cards": [{"replace": "blue dragon", "attack": "1500", "stars": ["mars", "venus"]},
                                    {"copy": "Kuriboh", "id": "k2", "name": "Kuriboh 2", "type": "Dragon"}],
            "fusions": [{"with": ["Blue-Dragon", "mystic elf"], "result": 0},
                        {"remove": 3}, {"with": ["hand:k2:1", 1], "result": 2},
                        {"with": ["other:x:1", 1], "result": 2}],
            "equips": [{"card": 652, "add": ["Dragon"], "remove": ["Card 20"]}],
            "drops": {"all": {"sa-tec": {"Card 5": 0}}, "Seto": {"POW": {"replace": True, "Kuriboh": 1, "Mystic Elf": 3}}},
            "decks": {"8": {"replace": True, "Kuriboh": 1, "Mystic Elf": 3}},
        }
        messages = manifest.apply(p, data)
        self.assertEqual(p.cards[1].attack, 1500)
        self.assertEqual((p.cards[1].star1, p.cards[1].star2), (1, 10))
        self.assertNotIn((1, 2), p.fusions)
        self.assertFalse([pair for pair, r in p.fusions.items() if r == 3 and self.retail.fusions.get(pair) == 3])
        copy = max(p.added)
        self.assertEqual(p.fusions[(1, copy)], 2)
        self.assertEqual(p.cards[copy].type, 0)   # Dragon: still a monster, so allowed
        self.assertIn(20, [c for c in range(1, 601) if self.retail.cards[c].type == 0])
        self.assertNotIn(20, p.equips[652])
        self.assertIn(40, p.equips[652])
        self.assertEqual(p.pools[7]["pow"], {3: 512, 2: 1536})
        self.assertEqual(p.pools[8]["deck"], self.retail.pools[8]["deck"])   # two cards: the port refuses
        self.assertTrue(any("left as it was" in m for m in messages))
        self.assertEqual(len(p.kept["fusions"]), 1)
        self.assertTrue(any("cannot place" in m for m in messages))
        built = manifest.build(p)
        self.assertIn({"with": ["other:x:1", 1], "result": 2}, built["fusions"])


class ValidateTest(unittest.TestCase):
    def test_problems(self):
        p = Project(fixture().game())
        p.info.id = "bad id!"
        p.cards[1].attack = 1234
        p.cards[2].level = 13
        new = p.add_card(1, "x")
        p.cards[new].type = g.TYPE_MAGIC
        p.pools[1]["deck"] = {1: 2000}
        p.equips[1] = {2}
        found = [(i.area, i.message) for i in validate.validate(p) if i.level == "error"]
        text = "\n".join(m for _, m in found)
        self.assertIn("id must be 1-63", text)
        self.assertIn("stored in tens", text)
        self.assertIn("level is 0 to 12", text)
        self.assertIn("stays a monster", text)
        self.assertIn("at least 14 cards", text)
        self.assertIn("add up to 2000", text)
        self.assertIn("not an equip card", text)

    def test_text_lines(self):
        self.assertEqual(validate.text_lines("a b"), 1)
        self.assertEqual(validate.text_lines("x" * 20 + " y"), 2)
        self.assertEqual(validate.text_lines("a\nb\nc"), 3)


if __name__ == "__main__":
    unittest.main()
