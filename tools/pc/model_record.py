#!/usr/bin/env python3
"""Model records for a mod's "models" (notes/model-replacement.md).

A card's 3D model is one MODEL.MRG record: 276 sectors (565,248 bytes) the
loader reads in seventeen phases -- model data (an HMD), textures, palettes,
the two stances' texture strips and palette rows, the battle's control
modules, the animation sequences, the voices and a metadata sector. A mod
ships a whole record per card; this tool gets one to start from and changes
what can be changed without a modeller:

    model_record.py extract CARD OUT.bin [--disc game/rpg-yfm.bin]
    model_record.py info RECORD.bin
    model_record.py recolor RECORD.bin OUT.bin [--hue DEG] [--saturation PCT]
                    [--brightness PCT]

CARD is a card id (1 to 722), the record of the model that card has. The
disc is a .bin of 2352-byte sectors or an .iso of 2048-byte ones; a
MODEL.MRG file on its own is read too.
"""
from __future__ import annotations

import argparse
import colorsys
import struct
import sys
from pathlib import Path

SECTOR = 2048
RECORD_SECTORS = 0x114
RECORD_BYTES = RECORD_SECTORS * SECTOR
CARD_COUNT = 722

# (name, sectors) in the order func_80056D7C reads them.
PHASES = [
    ("model data", 96), ("textures", 48), ("palettes", 2), ("stance 0 palette row", 1),
    ("stance 0 textures", 16), ("stance 1 palette row", 1), ("stance 1 textures", 16),
    ("stance 0 module, slot 0", 10), ("stance 0 module, slot 1", 10),
    ("stance 1 module, slot 0", 10), ("stance 1 module, slot 1", 10),
    ("primary module, slot 0", 2), ("primary module, slot 1", 2), ("sequence bank", 1),
    ("voices", 50), ("metadata", 1),
]
# The phases holding 16-bit colours: the palette block and the two rows.
PALETTE_PHASES = ("palettes", "stance 0 palette row", "stance 1 palette row")


def phase_offsets() -> dict[str, tuple[int, int]]:
    at, out = 0, {}
    for name, sectors in PHASES:
        out[name] = (at, sectors * SECTOR)
        at += sectors * SECTOR
    assert at == RECORD_BYTES
    return out


def record_index(card: int) -> int:
    """Model_LoadMonsterMerge's arithmetic (src/game/model.h): the model id is
    the card id less one, and three runs of ids have no record."""
    model = card - 1
    if (model < 0 or model >= 0x2D2 or 0x12C <= model < 0x15E or 0x28A <= model < 0x2BC
            or model == 0x2D0):
        raise SystemExit(f"card {card} has no 3D model on the disc")
    if model >= 0x2D1:
        model -= 1
    if model >= 0x2BC:
        model -= 50
    if model >= 0x15E:
        model -= 50
    return model


def model_mrg(path: Path) -> tuple[object, int, int]:
    """(file, byte offset of MODEL.MRG's first sector, sector size) inside a
    disc image, or the file itself when it is MODEL.MRG."""
    handle = path.open("rb")
    size = path.stat().st_size
    for sector_size, skip in ((2352, 24), (2352, 16), (2048, 0)):
        if size % sector_size:
            continue
        handle.seek(16 * sector_size + skip)
        if handle.read(6)[1:6] == b"CD001":
            break
    else:
        return handle, 0, SECTOR

    def sector(lba: int) -> bytes:
        handle.seek(lba * sector_size + skip)
        return handle.read(SECTOR)

    def directory(record: bytes) -> bytes:
        lba, length = struct.unpack_from("<I", record, 2)[0], struct.unpack_from("<I", record, 10)[0]
        return b"".join(sector(lba + i) for i in range((length + SECTOR - 1) // SECTOR))

    def find(listing: bytes, wanted: str) -> bytes:
        at = 0
        while at < len(listing):
            length = listing[at]
            if not length:
                at = (at // SECTOR + 1) * SECTOR
                continue
            name = listing[at + 33:at + 33 + listing[at + 32]].decode("ascii", "replace")
            if name.split(";")[0].upper() == wanted:
                return listing[at:at + length]
            at += length
        raise SystemExit(f"{path}: no {wanted} on the disc")

    root = sector(16)[156:156 + 34]
    entry = find(directory(find(directory(root), "DATA")), "MODEL.MRG")
    start = struct.unpack_from("<I", entry, 2)[0]
    if sector_size == SECTOR:
        return handle, start * SECTOR, SECTOR
    return handle, start * sector_size + skip, sector_size


def read_record(disc: Path, card: int) -> bytes:
    handle, base, sector_size = model_mrg(disc)
    first = record_index(card) * RECORD_SECTORS
    out = bytearray()
    for i in range(RECORD_SECTORS):
        handle.seek(base + (first + i) * sector_size)
        out += handle.read(SECTOR)
    if len(out) != RECORD_BYTES:
        raise SystemExit(f"{disc}: the record of card {card} is cut short")
    return bytes(out)


def load(path: Path) -> bytes:
    data = path.read_bytes()
    if len(data) != RECORD_BYTES:
        raise SystemExit(f"{path}: {len(data)} bytes; a model record is {RECORD_BYTES}")
    return data


def info(data: bytes) -> None:
    words = struct.unpack_from("<4I", data)
    print(f"model data: {words[0]} bytes, HMD with {words[3]} blocks")
    for name, (at, length) in phase_offsets().items():
        used = len(data[at:at + length].rstrip(b"\0"))
        print(f"  {name:26} at 0x{at:06X}, {length // SECTOR:3} sectors, {used:6} bytes used")


def recolor(data: bytes, hue: float, saturation: float, brightness: float) -> bytes:
    """Every 15-bit colour of the palette phases through an HSV change. The
    transparent word 0x0000 and each colour's semi-transparency bit stay, and
    a colour never becomes 0x0000 (which would make it transparent)."""
    out = bytearray(data)
    offsets = phase_offsets()
    for name in PALETTE_PHASES:
        at, length = offsets[name]
        for position in range(at, at + length, 2):
            word = out[position] | out[position + 1] << 8
            if word == 0:
                continue
            red, green, blue = (word & 31) / 31, (word >> 5 & 31) / 31, (word >> 10 & 31) / 31
            h, s, v = colorsys.rgb_to_hsv(red, green, blue)
            h = (h + hue / 360) % 1
            s = min(1.0, s * saturation)
            v = min(1.0, v * brightness)
            red, green, blue = (round(c * 31) for c in colorsys.hsv_to_rgb(h, s, v))
            new = (word & 0x8000) | blue << 10 | green << 5 | red
            if new == 0:
                new = 1
            out[position:position + 2] = struct.pack("<H", new)
    return bytes(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    extract = commands.add_parser("extract", help="write the record of a card's model")
    extract.add_argument("card", type=int)
    extract.add_argument("out", type=Path)
    extract.add_argument("--disc", type=Path, default=Path("game/rpg-yfm.bin"))
    show = commands.add_parser("info", help="describe a record")
    show.add_argument("record", type=Path)
    change = commands.add_parser("recolor", help="shift the colours of a record's palettes")
    change.add_argument("record", type=Path)
    change.add_argument("out", type=Path)
    change.add_argument("--hue", type=float, default=0.0, help="degrees round the colour wheel")
    change.add_argument("--saturation", type=float, default=100.0, help="percent")
    change.add_argument("--brightness", type=float, default=100.0, help="percent")
    arguments = parser.parse_args()

    if arguments.command == "extract":
        if not 1 <= arguments.card <= CARD_COUNT:
            raise SystemExit(f"card {arguments.card} is not one of the disc's")
        arguments.out.write_bytes(read_record(arguments.disc, arguments.card))
        print(f"{arguments.out}: the model of card {arguments.card}")
    elif arguments.command == "info":
        info(load(arguments.record))
    else:
        arguments.out.write_bytes(recolor(load(arguments.record), arguments.hue,
                                          arguments.saturation / 100, arguments.brightness / 100))
        print(f"{arguments.out}: recoloured")
    return 0


if __name__ == "__main__":
    sys.exit(main())
