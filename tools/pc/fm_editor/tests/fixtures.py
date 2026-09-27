"""Synthetic game files for the tests: made-up cards and tables laid out at
the retail offsets. No byte of the game is in here."""
from __future__ import annotations

import random
import struct

from fm_editor import gamedata as g
from fm_editor.gamedata import Card

GLYPH_TABLE = 0x801D9000
NAME_TEXT = 0x801D9200          # after the glyph table
DESCRIPTION_TEXT = 0x801C0A00   # after the string table (dialog entries 0x400-0x4F9 included)

# Glyph codes 1.. for these characters, skipping the codes text_listing spells
# its own way; each is the full-width Shift-JIS form, as the retail table's.
CHARACTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-."
SPECIAL = {0x1B, 0x40, 0x27, 0x28, 0x30, 0x47}


def _sjis(ch: str) -> int:
    if ch == "-":
        return 0x817C
    if ch == ".":
        return 0x8144
    return int.from_bytes(chr(ord(ch) + 0xFEE0).encode("shift_jis"), "big")


def glyph_codes() -> dict:
    codes, code = {" ": 0}, 1
    for ch in CHARACTERS:
        while code in SPECIAL:
            code += 1
        codes[ch] = code
        code += 1
    return codes


def card_type(cid: int) -> int:
    if cid <= 600:
        return cid % 20
    if cid <= 650:
        return g.TYPE_MAGIC
    if cid <= 680:
        return g.TYPE_EQUIP
    if cid <= 700:
        return g.TYPE_RITUAL
    return g.TYPE_TRAP


def make_cards() -> dict:
    cards = {}
    for cid in range(1, g.CARD_COUNT + 1):
        monster = card_type(cid) < g.TYPE_MAGIC
        name = {1: "Blue Dragon", 2: "Mystic Elf", 3: "Kuriboh"}.get(cid, f"Card {cid}")
        cards[cid] = Card(
            id=cid, name=name, description=f"Text of card {cid}.\nSecond line." if cid % 3 else f"Card {cid} text.",
            attack=(cid * 10) % 3000 if monster else 0, defense=(cid * 70) % 2500 if monster else 0,
            type=card_type(cid), attribute=cid % 6 if monster else 6, level=cid % 12 + 1 if monster else 0,
            star1=cid % 10 + 1 if monster else 0, star2=(cid + 3) % 10 + 1 if monster else 0)
    return cards


def make_tables():
    rng = random.Random(1411)
    monsters = [cid for cid in range(1, 601)]
    fusions = {}
    while len(fusions) < 300:
        a, b = rng.choice(monsters), rng.choice(monsters)
        if a != b:
            fusions[(min(a, b), max(a, b))] = rng.choice(monsters)
    fusions[(1, 2)] = 3
    equips = {651: list(range(1, 31)), 652: [5, 6, 7], 653: [300, 400]}
    rituals = {681: (1, 2, 3, 500), 682: (10, 11, 12, 501)}
    pools = []
    for d in range(g.DUELIST_COUNT):
        record = {}
        for pool in g.POOLS:
            chosen = rng.sample(monsters, 20)
            weights = {cid: 100 for cid in chosen}
            weights[chosen[0]] += g.POOL_TOTAL - 2000
            record[pool] = weights
        pools.append(record)
    return fusions, equips, rituals, pools


def encode_text(text: str, codes: dict) -> bytes:
    out = bytearray()
    for ch in text:
        out.append(0xFE if ch == "\n" else codes[ch])
    return bytes(out) + b"\xFF"


def make_slus(cards: dict, other_names: dict = None) -> bytes:
    """The executable: glyphs, stats, names and texts; `other_names` are
    names-bank strings past the cards ({index: text}, a duelist's say)."""
    data = bytearray(0x1D0800)
    at = g.slus_offset
    codes = glyph_codes()
    for ch, code in codes.items():
        if code:
            struct.pack_into("<I", data, at(GLYPH_TABLE + code * 4), _sjis(ch))
    name_at, text_at = NAME_TEXT, DESCRIPTION_TEXT
    for cid, card in cards.items():
        struct.pack_into("<I", data, at(g.STATS_ADDRESS + (cid - 1) * 4), g.pack_stats(card))
        data[at(g.LEVEL_ATTR_ADDRESS + cid)] = card.level | (card.attribute << 4)
        name = encode_text(card.name, codes)
        struct.pack_into("<H", data, at(g.NAME_TABLE + cid * 2), name_at - g.NAME_BANK)
        data[at(name_at):at(name_at) + len(name)] = name
        name_at += len(name)
        text = encode_text(card.description, codes)
        struct.pack_into("<H", data, at(g.STRING_TABLE + (0x100 + cid) * 2), text_at - g.DESCRIPTION_BANK)
        data[at(text_at):at(text_at) + len(text)] = text
        text_at += len(text)
    for index, text in (other_names or {}).items():
        name = encode_text(text, codes)
        struct.pack_into("<H", data, at(g.NAME_TABLE + index * 2), name_at - g.NAME_BANK)
        data[at(name_at):at(name_at) + len(name)] = name
        name_at += len(name)
    assert name_at < 0x801E0000 and text_at < 0x801D0000
    return bytes(data)


def make_wa(fusions, equips, rituals, pools) -> bytes:
    data = bytearray(0xED8000)
    for k in range(g.TERRAIN_COPIES):
        base = g.TERRAIN_BASE + k * g.TERRAIN_STRIDE
        for offset, blob in ((g.EQUIP_OFFSET, g.encode_equips(equips)), (g.FUSION_OFFSET, g.encode_fusions(fusions)),
                             (g.RITUAL_OFFSET, g.encode_rituals(rituals))):
            data[base + offset:base + offset + len(blob)] = blob
    for d, record in enumerate(pools):
        for pool, offset in g.POOL_OFFSETS.items():
            blob = g.encode_pool(record[pool])
            start = g.DUELIST_BASE + d * g.DUELIST_STRIDE + offset
            data[start:start + len(blob)] = blob
    return bytes(data)


class Fixture:
    """The synthetic retail game: its source values and its two files."""

    def __init__(self):
        self.cards = make_cards()
        self.fusions, self.equips, self.rituals, self.pools = make_tables()
        self.other_names = {0x330: "Heishin"}
        self.slus = make_slus(self.cards, self.other_names)
        self.wa = make_wa(self.fusions, self.equips, self.rituals, self.pools)

    def game(self) -> g.GameData:
        return g.read_game(self.slus, self.wa)


def make_iso(files: dict, raw: bool = True) -> bytes:
    """A small ISO 9660 image holding `files` ({"SLUS_014.11": bytes,
    "DATA/WA_MRG.MRG": bytes}), in 2352-byte MODE2 sectors or 2048-byte ones."""
    def record(name: bytes, lba: int, size: int, directory: bool) -> bytes:
        length = 33 + len(name) + (len(name) + 1) % 2
        out = bytearray(length)
        out[0] = length
        struct.pack_into("<I", out, 2, lba)
        struct.pack_into(">I", out, 6, lba)
        struct.pack_into("<I", out, 10, size)
        struct.pack_into(">I", out, 14, size)
        out[25] = 2 if directory else 0
        out[32] = len(name)
        out[33:33 + len(name)] = name
        return bytes(out)

    sectors = {}
    next_lba = 24
    placed = {}
    for path, blob in files.items():
        placed[path] = (next_lba, len(blob))
        for i in range(0, max(len(blob), 1), 2048):
            sectors[next_lba] = blob[i:i + 2048].ljust(2048, b"\0")
            next_lba += 1
    root_lba, data_lba = 20, 21
    data_dir = record(b"\0", data_lba, 2048, True) + record(b"\1", root_lba, 2048, True)
    root = record(b"\0", root_lba, 2048, True) + record(b"\1", root_lba, 2048, True)
    root += record(b"DATA", data_lba, 2048, True)
    for path, (lba, size) in placed.items():
        name = path.split("/")[-1].encode() + b";1"
        if path.startswith("DATA/"):
            data_dir += record(name, lba, size, False)
        else:
            root += record(name, lba, size, False)
    sectors[root_lba] = root.ljust(2048, b"\0")
    sectors[data_lba] = data_dir.ljust(2048, b"\0")
    pvd = bytearray(2048)
    pvd[0] = 1
    pvd[1:6] = b"CD001"
    pvd[156:156 + 34] = record(b"\0", root_lba, 2048, True)
    sectors[16] = bytes(pvd)
    out = bytearray()
    for lba in range(next_lba):
        user = sectors.get(lba, bytes(2048))
        if raw:
            out += bytes(24) + user + bytes(2352 - 24 - 2048)
        else:
            out += user
    return bytes(out)
