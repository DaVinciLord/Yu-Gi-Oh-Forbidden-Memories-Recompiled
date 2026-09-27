"""The importer on synthetic mods made the way a community MIPS patch kit
makes them: the archive changed all
over, tables in other formats, and code whose shape says what the mod does.
No byte of the game is in here: the "code" is assembled from the fixture's
made-up values."""
import struct
import tempfile
import unittest
from pathlib import Path

from fm_editor import gamedata as g, importer, kit, manifest
from fm_editor.disc import GameFiles
from fm_editor.tests import fixtures
from fm_editor.tests.test_data import fixture


def imported(f, slus=None, wa=None):
    result = importer.import_modded(GameFiles(f.slus, f.wa, "retail"),
                                    GameFiles(slus or f.slus, wa or f.wa, "modded", 9173), "family")
    return result, "\n".join(result.report)


class ArchiveTest(unittest.TestCase):
    def test_many_changes_replace_the_whole_file(self):
        f = fixture()
        wa = bytearray(f.wa)
        for k in range(importer.WA_PATCHES_MOST + 1):             # small changes all over the pictures
            wa[0x169000 + 0x1000 * k] ^= 0x5A
        equip = g.TERRAIN_BASE + g.EQUIP_OFFSET
        wa[equip:equip + 8] = b"\x99" * 8                          # a table in a format mod.json carries otherwise
        starters = bytearray(g.STARTER_LENGTH)                     # starter decks as counts of 40
        for k in range(7):
            struct.pack_into("<H", starters, k * (g.STARTER_LENGTH // 7) + 2 + 2 * 4, 40)
        wa[g.STARTER_BASE:g.STARTER_BASE + g.STARTER_LENGTH] = starters
        result, report = imported(f, wa=bytes(wa))
        built = manifest.build(result.project)
        self.assertEqual(built["data"], [{"file": importer.WA_FILE, "replace": "WA_MRG.MRG"}])
        whole = result.project.files["WA_MRG.MRG"]
        self.assertEqual(len(whole), len(f.wa))
        self.assertEqual(whole[0x169000], wa[0x169000])            # the mod's bytes
        self.assertEqual(whole[equip:equip + 8], f.wa[equip:equip + 8])      # the table as retail's
        self.assertEqual(whole[g.STARTER_BASE:g.STARTER_BASE + g.STARTER_LENGTH],
                         f.wa[g.STARTER_BASE:g.STARTER_BASE + g.STARTER_LENGTH])
        self.assertIn("the whole file is replaced", report)
        self.assertIn("the starter decks are counts of cards", report)

    def test_a_larger_archive_keeps_the_tables_retail(self):
        f = fixture()
        wa = bytearray(f.wa) + bytes(4096)
        pool = g.DUELIST_BASE + 3 * g.DUELIST_STRIDE
        wa[pool:pool + 4] = b"\x01\x00\x02\x00"
        result, report = imported(f, wa=bytes(wa))
        whole = result.project.files["WA_MRG.MRG"]
        self.assertEqual(len(whole), len(wa))
        self.assertEqual(whole[pool:pool + 4], f.wa[pool:pool + 4])
        self.assertIn("its size differs", report)

    def test_few_changes_stay_patches_at_retail_sectors(self):
        f = fixture()
        wa = bytearray(f.wa)
        wa[0x200] = 1
        wa[0x169000:0x169000 + 5000] = bytes([7]) * 5000
        wa[0x169000 + 6000:0x169000 + 11000] = bytes([8]) * 5000   # the same or the next sectors: one region
        result, report = imported(f, wa=bytes(wa))
        data = manifest.build(result.project)["data"]
        self.assertEqual(data[0]["patch"], [{"at": "0x200", "bytes": "01"}])
        self.assertEqual(data[1:], [{"lba": 10102 + 0x169000 // 2048, "sectors": 6, "replace": "data/wa_002D2.bin"}])


def bitmap_record(key: int, ids) -> bytes:
    bits = bytearray(92)
    for m in ids:
        bits[m >> 3] |= 0x80 >> (m & 7)
    bits[91] = 0xFF                          # past the last card: the kit's padding, ignored
    return struct.pack("<H", key) + bytes(bits)


def with_equip_table(f, records: bytes) -> bytearray:
    wa = bytearray(f.wa)
    for k in range(g.TERRAIN_COPIES):
        at = g.TERRAIN_BASE + k * g.TERRAIN_STRIDE + g.EQUIP_OFFSET
        wa[at:at + g.EQUIP_LENGTH] = records.ljust(g.EQUIP_LENGTH, b"\0")
    return wa


EQUIP_LO = kit.EQUIP_ADDRESS - 0x80180000     # the low half, as addiu adds it to lui 0x8018


class EquipTest(unittest.TestCase):
    def test_bitmaps_read_up_to_id_0(self):
        """One shape: Duel_CheckEquip itself steps 94 bytes."""
        f = fixture()
        slus = bytearray(f.slus)
        fixtures.put(slus, kit.CHECK_EQUIP, fixtures.asm(kit.CHECK_EQUIP, [
            ("lui", "v0", 0x8018), ("addiu", "v0", "v0", EQUIP_LO), ("lhu", "v1", 0, "v0"),
            ("bne", "v1", "zero", kit.CHECK_EQUIP + 0x1C), ("addiu", "a2", "v0", 2), ("jr", "ra"), ("nop",),
            ("bne", "v1", "a0", kit.CHECK_EQUIP + 8), ("addiu", "v0", "v0", 94), ("srl", "v1", "a1", 3),
            ("addu", "v1", "v1", "a2"), ("lbu", "v1", 0, "v1"), ("srlv", "v1", "v1", "v0"), ("jr", "ra"), ("nop",)]))
        wa = with_equip_table(f, bitmap_record(651, [1, 2, 3]) + bitmap_record(652, [9]) +
                              bitmap_record(10, [7]) + bitmap_record(0, []) + bitmap_record(653, [4]))
        result, report = imported(f, bytes(slus), bytes(wa))
        equips = result.project.equips
        self.assertEqual(equips[651], {1, 2, 3})
        self.assertEqual(equips[652], {9})
        self.assertEqual(equips[653], set())              # past id 0: the game never reads it
        self.assertNotIn(10, equips)
        self.assertIn("reads its table as bitmaps of 94 bytes", report)
        self.assertIn("1 records are for cards that are not equip cards (10 Card 10)", report)
        built = manifest.build(result.project)["equips"]
        self.assertIn({"card": "Card 653", "replace": True, "add": []}, built)
        # The archive's table itself stays retail's: the rules say it all.
        self.assertNotIn("data", manifest.build(result.project))

    def test_bitmaps_with_monster_records_and_blocked_monsters(self):
        """Another shape: a jump to the mod's code, a count of
        records, records per monster after them and a list of monsters no
        equip takes."""
        f = fixture()
        slus = bytearray(f.slus)
        code = 0x8000B200
        fixtures.put(slus, kit.CHECK_EQUIP, fixtures.asm(kit.CHECK_EQUIP, [
            ("lui", "v0", 0x8018), ("addiu", "v0", "v0", EQUIP_LO), ("li", "a2", 0), ("j", code), ("lui", "a3", 0x801D)]))
        second = EQUIP_LO + 3 * 94
        fixtures.put(slus, code, fixtures.asm(code, [
            ("lhu", "a3", 0x197C, "a3"), ("srl", "a3", "a3", 4), ("beq", "a3", "a1", code + 0x60),
            ("lui", "a3", 0x801D), ("lhu", "a3", 0x197E, "a3"), ("srl", "a3", "a3", 4),
            ("lhu", "v1", 0, "v0"), ("beq", "v1", "a0", code + 0x70), ("addiu", "a2", "a2", 1),
            ("slti", "a3", "a2", 3), ("bne", "a3", "zero", code + 0x18), ("addiu", "v0", "v0", 94),
            ("lui", "v0", 0x8018), ("addiu", "v0", "v0", second), ("lhu", "v1", 0, "v0"), ("li", "a2", 0),
            ("addiu", "a2", "a2", 1), ("slti", "a3", "a2", 2), ("addiu", "v0", "v0", 94),
            ("srlv", "v1", "v1", "a3"), ("jr", "ra"), ("nop",)]))
        fixtures.put(slus, 0x801D197C, struct.pack("<HH", (2 << 4) | 1, 723 << 4))
        wa = with_equip_table(f, bitmap_record(651, [1, 2, 3]) + bitmap_record(652, [5]) + bitmap_record(10, [7]) +
                              bitmap_record(20, [653, 651]) + bitmap_record(21, [654]))
        result, report = imported(f, bytes(slus), bytes(wa))
        equips = result.project.equips
        self.assertEqual(equips[651], {1, 3})             # 2 is turned away; 20's record is not asked for 651
        self.assertEqual(equips[652], {5})
        self.assertEqual(equips[653], {20})               # in no record of its own: the monsters' records
        self.assertEqual(equips[654], {21})
        self.assertIn("2 records name a monster and the equips it takes", report)
        self.assertIn("no equip equips 2 Mystic Elf", report)

    def test_rituals_that_are_code_are_removed(self):
        f = fixture()
        wa = bytearray(f.wa)
        for k in range(g.TERRAIN_COPIES):
            at = g.TERRAIN_BASE + k * g.TERRAIN_STRIDE + g.RITUAL_OFFSET
            wa[at:at + 20] = struct.pack("<10H", 0x2402, 0x27BD, 0xFFE8, 0xAFBF, 0x0010, 0x0C00, 0x1234, 0, 0, 0)
        result, report = imported(f, wa=bytes(wa))
        self.assertEqual(result.project.rituals, {})
        self.assertIn({"card": "Card 681", "result": None}, manifest.build(result.project)["rituals"])
        self.assertIn("the rituals were imported as removed", report)


def put_text(slus: bytearray, table_entry: int, bank: int, address: int, data: bytes):
    """A string's bytes at `address`, and the u16 offset entry pointing at it."""
    fixtures.put(slus, address, data)
    struct.pack_into("<H", slus, g.slus_offset(table_entry), address - bank)


class TextTest(unittest.TestCase):
    def test_coloured_names_and_empty_texts_go_to_the_text_file(self):
        f = fixture()
        codes = fixtures.glyph_codes()
        slus = bytearray(f.slus)
        put_text(slus, g.NAME_TABLE + 6 * 2, g.NAME_BANK, 0x801DF000,
                 b"\xF8\x0A\x05" + fixtures.encode_text("Dark Card", codes))           # a coloured name
        put_text(slus, g.NAME_TABLE + 9 * 2, g.NAME_BANK, 0x801DF100, fixtures.encode_text("Plain New", codes))
        put_text(slus, g.STRING_TABLE + (0x100 + 7) * 2, g.DESCRIPTION_BANK, 0x801CF000, b"\xFF")   # empty
        put_text(slus, g.STRING_TABLE + (0x100 + 8) * 2, g.DESCRIPTION_BANK, 0x801CF010,
                 b"\xF8\x0A\x05" + fixtures.encode_text("Effect", codes)[:-1] + b"\xF8\x0A\x00\xFE" +
                 fixtures.encode_text("Burns", codes))
        result, report = imported(f, slus=bytes(slus))
        project = result.project
        self.assertEqual(project.cards[6].name, "Dark Card")
        self.assertEqual(project.cards[7].description, "")
        self.assertEqual(project.cards[8].description, "{f8 0A 05}Effect{f8 0A 00}\nBurns")
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "family"
            importer.save(result, folder)
            built = manifest.read_json(folder / "mod.json")
            entries = {e["replace"]: e for e in built["cards"]}
            self.assertNotIn(6, entries)                                  # the text file has it, colour and all
            self.assertEqual(entries[9], {"replace": 9, "name": "Plain New"})
            self.assertNotIn(7, entries)
            self.assertNotIn(8, entries)
            text = (folder / "text.txt").read_text(encoding="utf-8")
            self.assertIn("[8006]\n{f8 0A 05}Dark Card{end}", text)
            self.assertIn("[D107]", text)
            self.assertIn("{f8 0A 05}Effect{f8 0A 00}", text)
            self.assertNotIn("Plain New", text)
            # Opened again, the editor shows them and writes the same mod.json.
            opened, messages = manifest.open_mod(f.game(), folder)
            self.assertEqual(opened.cards[6].name, "Dark Card")
            self.assertEqual(opened.cards[8].description, project.cards[8].description)
            self.assertEqual(manifest.build(opened)["cards"], built["cards"])
            opened.cards[6].name = "Darker Card"                          # an edit goes to cards[] again
            self.assertIn({"replace": 6, "name": "Darker Card"}, manifest.build(opened)["cards"])
        self.assertIn("carry colour or icon codes or are empty on purpose (1 empty)", report)

    def test_the_name_entry_strings_stay_retail(self):
        f = fixture()
        codes = fixtures.glyph_codes()
        slus = bytearray(f.slus)
        dialog = 0x801B0000
        put_text(slus, g.STRING_TABLE + 0x10 * 2, dialog, dialog + 0x100, fixtures.encode_text("Hello", codes))
        put_text(slus, g.STRING_TABLE + 0xF5 * 2, dialog, dialog + 0x200, fixtures.encode_text("Pick a deck", codes))
        result, report = imported(f, slus=bytes(slus))
        text = result.project.files["text.txt"].decode("utf-8")
        self.assertIn("[0010]\nHello{end}", text)
        self.assertNotIn("Pick a deck", text)
        self.assertIn("the name entry's strings [00F5] stay retail's", report)

    def test_texts_kept_in_the_archive(self):
        """Texts kept in the archive: the string table points descriptions 1-8
        at slots of 0x100 and the texts are past the archive's retail end."""
        f = fixture()
        codes = fixtures.glyph_codes()
        slus = bytearray(f.slus)
        for k in range(8):
            struct.pack_into("<H", slus, g.slus_offset(g.STRING_TABLE + (0x101 + k) * 2), 0xA00 + 0x100 * k)
        fixtures.put(slus, 0x801C0A00, bytes(range(0x20, 0x40)) * 8)   # what the mod keeps there instead: code
        wa = bytearray(f.wa).ljust(g.WA_TEXT_BASE, b"\0")
        for cid in range(1, g.CARD_COUNT + 1):
            text = fixtures.encode_text(f"Kept {cid}", codes) if cid != 9 else \
                b"\xF8\x0A\x05" + fixtures.encode_text("Union", codes)
            wa += text.ljust(g.WA_TEXT_SLOT, b"\0")
        result, report = imported(f, bytes(slus), bytes(wa))
        project = result.project
        self.assertEqual(project.cards[5].description, "Kept 5")
        self.assertEqual(project.cards[9].description, "{f8 0A 05}Union")
        self.assertIn("the card texts are in WA_MRG.MRG", report)
        self.assertEqual(result.project.text_cards[9], {"description": "{f8 0A 05}Union"})
        self.assertIn("[D109]", result.project.files["text.txt"].decode("utf-8"))


class DeckAndDropTest(unittest.TestCase):
    def test_decks_dealt_by_count_are_fixed(self):
        f = fixture()
        slus = bytearray(f.slus)
        start = kit.SHUFFLE_DECK[0]
        fixtures.put(slus, start, fixtures.asm(start, [
            ("lhu", "v0", 0, "v1"), ("beq", "v0", "zero", start + 0x68), ("addiu", "s3", "s3", 1),
            ("slti", "v0", "s3", 40), ("bne", "v0", "zero", start + 8), ("nop",)]))
        pools = [{p: dict(v) for p, v in d.items()} for d in f.pools]
        pools[3]["deck"] = {5: 30, 6: 10}
        pools[5]["deck"] = {7: 2}                                  # too few: the shuffle would never end
        wa = fixtures.make_wa(f.fusions, f.equips, f.rituals, pools)
        result, report = imported(f, bytes(slus), wa)
        project = result.project
        decks = manifest.build(project)["decks"]
        self.assertEqual(decks["Jono"], {"fixed": True, "Card 5": 30, "Card 6": 10})
        first = sorted(f.pools[4]["deck"])                         # 2048 weights: the first cards up to 40
        self.assertEqual(decks["Villager 1"], {"fixed": True, str(project.ref(first[0])): 40})   # weights of 100+
        self.assertNotIn("Villager 2", decks)
        self.assertEqual(project.pools[3]["deck"], f.pools[3]["deck"])
        self.assertNotIn("scaled", report)
        self.assertIn("pools hold fewer than 40 cards (Villager 2)", report)
        from fm_editor.model import Project
        again = Project(f.game())                                  # read back, kept as written
        manifest.apply(again, manifest.build(project))
        self.assertEqual(manifest.build(again)["decks"], decks)

    def test_extra_draws_decoding_the_weights(self):
        from fm_editor.tests.test_importer import encoded_mod
        f, files, pools = encoded_mod(2512, 3, code=False)
        slus = bytearray(files.slus)
        loop, decode = 0x8000B300, 0x8000B380
        fixtures.put(slus, kit.RESULT_DRAW, fixtures.asm(kit.RESULT_DRAW, [("j", loop)]))
        fixtures.put(slus, loop, fixtures.asm(loop, [
            ("lui", "sp", 0x8001), ("lbu", "s6", -0x4C00, "sp"), ("lbu", "s7", -0x4BFF, "sp"),
            ("jal", decode), ("nop",), ("jr", "ra")]))
        fixtures.put(slus, decode, fixtures.asm(decode, [("addiu", "v0", "v0", -2512), ("sra", "v0", "v0", 3),
                                                         ("jr", "ra")]))
        fixtures.put(slus, 0x8000B400, bytes([0, 6]))
        result, report = imported(f, bytes(slus), files.wa)
        self.assertEqual(result.project.pools, pools)
        self.assertIn("the prize draw at 0x80021C6C jumps to the mod's code at 0x8000B300, which calls 0x8000B380", report)
        self.assertEqual(kit.extra_draws(f.slus, bytes(slus)).count, 5)


if __name__ == "__main__":
    unittest.main()
