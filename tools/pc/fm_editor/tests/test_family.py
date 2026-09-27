"""The importer on synthetic mods made the way a community MIPS patch kit
makes them: the archive changed all
over, tables in other formats, and code whose shape says what the mod does.
No byte of the game is in here: the "code" is assembled from the fixture's
made-up values."""
import struct
import tempfile
import unittest
from pathlib import Path

from fm_editor import gamedata as g, importer, manifest
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


if __name__ == "__main__":
    unittest.main()
