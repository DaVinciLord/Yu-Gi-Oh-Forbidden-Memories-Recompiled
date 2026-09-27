"""What a modified executable's code says about its tables and rules.

A family of community mods made with one patch kit changes the duel in
MIPS: it jumps from
the retail functions to code of its own and keeps its parameters in tables
there. The addresses of that code move from one mod to the next; the places
it hooks and the shape of the code do not. Each reader here starts at a
retail function, follows the mod's jump, and reads the values the code
uses, or answers None when the code is not that shape.

Nothing here runs the mod's code: it is read as data, a few instructions at
a time, with the registers' constants followed (lui, addiu, ori).
"""
from __future__ import annotations

import struct

from . import gamedata as g

HEADER_ADDRESS = 0x8000B070      # where the BIOS leaves the executable's header, which the kit fills with code
EXE_START = 0x80010000

# RAM windows the duel package is loaded into (Duel_CheckEquip, Duel_CheckRitual), and where they come from.
EQUIP_ADDRESS, EQUIP_WINDOW = 0x8017A1D8, 0x2100
RITUAL_ADDRESS = 0x801799D8

CHECK_EQUIP = 0x80019A08         # Duel_CheckEquip
EQUIP_RECORD = 94                # u16 equip id and a bitmap of 92 bytes, most significant bit first


# --- reading code ------------------------------------------------------------------------

class Memory:
    """The executable's RAM image, with the header's code and the duel
    package's tables where the game puts them."""

    def __init__(self, slus: bytes, wa: bytes = b""):
        self.slus, self.wa = slus, wa

    def bytes(self, address: int, count: int) -> bytes:
        if HEADER_ADDRESS <= address < HEADER_ADDRESS + 0x800:
            at = address - HEADER_ADDRESS
            return self.slus[at:at + count]
        if EQUIP_ADDRESS <= address < EQUIP_ADDRESS + EQUIP_WINDOW and self.wa:
            at = g.TERRAIN_BASE + g.EQUIP_OFFSET + address - EQUIP_ADDRESS
            return self.wa[at:at + count]
        at = g.slus_offset(address)
        return self.slus[at:at + count] if 0 <= at else b""

    def word(self, address: int):
        data = self.bytes(address, 4)
        return struct.unpack("<I", data)[0] if len(data) == 4 else None

    def u16(self, address: int):
        data = self.bytes(address, 2)
        return struct.unpack("<H", data)[0] if len(data) == 2 else None

    def s8(self, address: int):
        data = self.bytes(address, 1)
        return struct.unpack("<b", data)[0] if data else None


def s16(value: int) -> int:
    return value - 0x10000 if value & 0x8000 else value


def jump_target(word: int, address: int) -> int:
    return ((address + 4) & 0xF0000000) | ((word & 0x03FFFFFF) << 2)


class Ins:
    """One instruction's fields."""

    def __init__(self, word: int, address: int):
        self.word, self.address = word, address
        self.op, self.rs, self.rt = word >> 26, (word >> 21) & 31, (word >> 16) & 31
        self.rd, self.sa, self.fn = (word >> 11) & 31, (word >> 6) & 31, word & 63
        self.imm = s16(word & 0xFFFF)

    @property
    def is_jump(self):          # j
        return self.op == 2

    @property
    def is_call(self):          # jal
        return self.op == 3

    @property
    def target(self):
        return jump_target(self.word, self.address)

    def load(self, op):          # lb 32, lh 33, lw 35, lbu 36, lhu 37
        return self.op == op

    def is_addiu(self, rs=None, rt=None):
        return self.op == 9 and (rs is None or self.rs == rs) and (rt is None or self.rt == rt)

    def is_slti(self):
        return self.op == 10

    def is_sltiu(self):
        return self.op == 11

    def is_sra(self):
        return self.op == 0 and self.fn == 3

    def is_srl(self):
        return self.op == 0 and self.fn == 2

    def is_branch_or_return(self):
        return 1 <= self.op <= 7 or (self.op == 0 and self.fn in (8, 9))


def instructions(memory: Memory, address: int, count: int):
    out = []
    for i in range(count):
        word = memory.word(address + 4 * i)
        if word is None:
            break
        out.append(Ins(word, address + 4 * i))
    return out


class Constants:
    """Registers' values as lui, addiu and ori set them, followed through
    straight-line code; each load's address when its base is known."""

    def __init__(self):
        self.value = {0: 0}

    def step(self, ins: Ins):
        """The address a load or store uses, or None."""
        address = None
        if 32 <= ins.op <= 46 and ins.rs in self.value:
            address = (self.value[ins.rs] + ins.imm) & 0xFFFFFFFF
        if ins.op == 15:                                   # lui
            self.value[ins.rt] = (ins.word & 0xFFFF) << 16
        elif ins.op == 9:                                  # addiu
            if ins.rs in self.value:
                self.value[ins.rt] = (self.value[ins.rs] + ins.imm) & 0xFFFFFFFF
            else:
                self.value.pop(ins.rt, None)
        elif ins.op == 13 and ins.rs in self.value:        # ori
            self.value[ins.rt] = self.value[ins.rs] | (ins.word & 0xFFFF)
        elif ins.op in (32, 33, 35, 36, 37) or (ins.op == 0 and ins.fn not in (8, 9, 12, 13) and ins.word):
            target = ins.rt if ins.op else ins.rd
            if target:
                self.value.pop(target, None)
        self.value[0] = 0
        return address


def hook(retail: Memory, memory: Memory, start: int, end: int):
    """(address, target) of the first j the mod put in [start, end) where
    retail has other code, landing outside the retail executable's code
    (the header, or past it); else None."""
    for at in range(start, end, 4):
        word = memory.word(at)
        if word is None or word == retail.word(at) or word >> 26 != 2:
            continue
        return at, jump_target(word, at)
    return None


# --- equips as bitmaps (Duel_CheckEquip) ---------------------------------------------------

class EquipBitmaps:
    """The kit's equip table: records of an equip id and a bitmap of the
    monsters it equips; after `limit` of them (or at id 0), optional
    records of a monster and a bitmap of the equips it takes; and monsters
    no equip may equip."""

    def __init__(self):
        self.records = []           # [(equip id, {monster ids})], in the table's order
        self.limit = None           # how many records the game reads; None: up to id 0
        self.by_monster = []        # [(monster id, {equip ids})]
        self.blocked = set()        # monsters nothing equips
        self.where = ""

    def allowed(self, equip: int) -> set:
        """The monsters `equip` equips, as the mod's Duel_CheckEquip decides."""
        for key, monsters in self.records:
            if key == equip:
                return monsters - self.blocked
        return {m for m, equips in self.by_monster if equip in equips} - self.blocked


def _bitmap(data: bytes) -> set:
    return {m for m in range(1, g.CARD_COUNT + 1) if m >> 3 < len(data) and data[m >> 3] >> (7 - (m & 7)) & 1}


def _read_records(memory: Memory, address: int, limit):
    records = []
    most = limit if limit is not None else EQUIP_WINDOW // EQUIP_RECORD
    for k in range(most):
        at = address + k * EQUIP_RECORD
        key = memory.u16(at)
        if key is None or (limit is None and key == 0) or at + EQUIP_RECORD > EQUIP_ADDRESS + EQUIP_WINDOW:
            break
        if key == 0:
            break
        records.append((key, _bitmap(memory.bytes(at + 2, EQUIP_RECORD - 2))))
    return records


def equip_bitmaps(retail_slus: bytes, slus: bytes, wa: bytes):
    """The mod's equip table when its Duel_CheckEquip steps 94 bytes a
    record and tests one bit per monster (signature A6), else None."""
    retail, memory = Memory(retail_slus), Memory(slus, wa)
    if memory.bytes(CHECK_EQUIP, 0x58) == retail.bytes(CHECK_EQUIP, 0x58):
        return None
    body = instructions(memory, CHECK_EQUIP, 0x58 // 4)
    found = hook(retail, memory, CHECK_EQUIP, CHECK_EQUIP + 0x58)
    code = body
    if found:           # the hook's own instructions set registers the mod's code then uses
        at = (found[0] - CHECK_EQUIP) // 4
        code = body[:at + 2] + instructions(memory, found[1], 64)
    if not any(ins.is_addiu() and ins.rs == ins.rt and ins.imm == EQUIP_RECORD for ins in code):
        return None
    if not any(ins.op == 0 and ins.fn == 6 for ins in code):            # srlv: the bit of the monster
        return None
    table = EquipBitmaps()
    constants = Constants()
    tables, limits, blocked = [], [], []
    upper = set()                   # registers a lui just set: lui and addiu make a table's address
    for i, ins in enumerate(code):
        was_upper = ins.is_addiu() and ins.rs in upper
        address = constants.step(ins)
        upper.discard(ins.rt if ins.op else ins.rd)
        if ins.op == 15:
            upper.add(ins.rt)
        if was_upper and ins.rt in constants.value:
            value = constants.value[ins.rt]
            if EQUIP_ADDRESS <= value < EQUIP_ADDRESS + EQUIP_WINDOW and value not in tables:
                tables.append(value)
        if ins.is_slti() and ins.rs != ins.rt and ins.imm < 100:
            limits.append((len(tables), ins.imm))
        if ins.load(37) and address is not None and i + 1 < len(code) and code[i + 1].is_srl() \
                and code[i + 1].sa == 4 and not EQUIP_ADDRESS <= address < EQUIP_ADDRESS + EQUIP_WINDOW:
            blocked.append(address)                      # a list of id << 4 the code turns away
    if not tables:
        return None
    first = [n for count, n in limits if count <= 1]
    table.limit = first[0] if first else None
    table.records = _read_records(memory, tables[0], table.limit)
    if len(tables) > 1:
        second = [n for count, n in limits if count == 2]
        table.by_monster = _read_records(memory, tables[1], second[0] if second else None)
    for address in blocked:
        value = memory.u16(address)
        if value is not None and 1 <= value >> 4 <= g.CARD_COUNT:
            table.blocked.add(value >> 4)
    table.where = f"Duel_CheckEquip (0x{CHECK_EQUIP:08X})" + (f", and the mod's code at 0x{found[1]:08X}" if found else "")
    return table
