#!/usr/bin/env python3
"""Live card packs test (built game and user-supplied disc; notes/card-packs.md).

Makes a pack mod of its own (a PNG drawn here, no game data), opens the
Password screen of a fresh game, gives it starchips in a saved state, and
buys a pack with the triangle, BUY and a skip to the list of what came. It
checks that the starchips drop by the price, that the chest gains exactly
the cards the pack dealt and the cards last awarded are they, that a second
run deals the same (the same input, the same numbers), that a state saved
while the cards turn over, resumed in a new process, ends with the same
chest, that a pack whose every card the player holds "max_copies" of is
refused (ALL OWNED, nothing paid) unless it says "when_nothing_left":
"sell", that a full chest is never sold a card it would drop (the pack
deals only cards with room, a pack of none is refused, and so is one whose
fixed card has no room), and that without the mod the triangle does nothing. Artifacts stay
in tmp/pc/packs-test (or --out); no player saves are touched.

    python3 tools/pc/test_packs.py [--windows | --executable PATH] [--out DIR]
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import zlib

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "tmp/pc/packs-test"
EXECUTABLE = ROOT / "tmp/pc/game32/memories-pc"
WINDOWS_EXECUTABLE = ROOT / "tmp/pc/win32/memories-pc.exe"
WINE_PREFIX = ROOT / "tmp/pc/wine-prefix"

# The Password screen of a fresh game (MEMORIES_MODE_AT runs mode 10 once NEW
# GAME is chosen), up at SCREEN.
OPENING = "910:0008,916:0000,1000:0040,1006:0000,1020:0040,1026:0000,1040:0040,1046:0000,1060:0040,1066:0000," \
          "1100:4000,1106:0000"
SCREEN = 1400
TRIANGLE, CROSS, SQUARE, RIGHT = "1000", "4000", "8000", "0020"

STARCHIPS = 0x801D07E0          # SaveDataState.starchips
CHEST = 0x801D0250 - 1          # gLibrary_abCardChest, by card id
RECENT = 0x801D07BC             # the cards last awarded, newest first
PRICE, COUNT = 120, 5
CARDS = [2, 3, 4, 5, 6, 7, 8, 9]
OWNED, OWNED_SOLD, OWNED_PRICE = [10, 11], [12, 13], 50   # held once each: packs of "max_copies": 1
FIXED, FIXED_PRICE = 14, 30     # the fourth pack's one fixed card
FULL = 250                      # copies of a card the disc's chest keeps


def png(width, height):
    """An RGB PNG of our own: a diagonal gradient with a light frame."""
    rows = bytearray()
    for y in range(height):
        rows.append(0)
        for x in range(width):
            edge = x < 4 or y < 4 or x >= width - 4 or y >= height - 4
            rows += bytes((230, 230, 240) if edge else (40 + 150 * y // height, 30 + 120 * x // width, 150))
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(bytes(rows))) + chunk(b"IEND", b""))


def make_mod(mods):
    folder = mods / "packs-test"
    (folder / "packs").mkdir(parents=True, exist_ok=True)
    (folder / "packs" / "test.png").write_bytes(png(204, 192))
    manifest = {"id": "packs-test", "name": "Card packs test", "enabled": True,
                "packs": [{"id": "test", "name": "Test Pack", "image": "packs/test.png", "price": PRICE,
                           "count": COUNT, "tiers": {"common": {"odds": 9, "cards": CARDS[:6]},
                                                     "rare": {"odds": 1, "cards": CARDS[6:], "label": "RARE!"}},
                           "guarantee": {"rare": 1}},
                          {"id": "owned", "name": "Owned", "price": OWNED_PRICE, "count": 3, "max_copies": 1,
                           "tiers": {"common": {"cards": OWNED[:1]}, "rare": {"odds": 0, "cards": OWNED[1:]}},
                           "pity": {"rare": 2}, "stock": 3},
                          {"id": "owned-sold", "name": "Owned Sold", "price": OWNED_PRICE, "count": 3, "max_copies": 1,
                           "tiers": {"common": {"cards": OWNED_SOLD[:1]}, "rare": {"odds": 0, "cards": OWNED_SOLD[1:]}},
                           "pity": {"rare": 2}, "stock": 3, "when_nothing_left": "sell"},
                          {"id": "fixed", "name": "Fixed", "price": FIXED_PRICE, "count": 2,
                           "cards": CARDS[:1], "slots": [{"card": FIXED}, "cards"]}]}
    (folder / "mod.json").write_text(json.dumps(manifest, indent=4), encoding="utf-8")


def chunks(path):
    data = bytearray(path.read_bytes())
    at, found = 16, {}
    while at + 20 <= len(data):
        tag = data[at:at + 16].split(b"\0")[0].decode(errors="replace")
        size, = struct.unpack_from("<I", data, at + 16)
        found[tag] = at + 20
        at += 20 + size
    return data, found


def peek(path, address, form):
    data, found = chunks(path)
    return struct.unpack_from("<" + form, data, found["memory"] + address - 0x80000000)[0]


# What the save's progress says, in the state's pack-shop chunk: pack_shop.c
# Screen's own fields, then packs.h PacksProgress (starchips spent, packs
# opened, and a PackProgress a pack: bought, opened, pity[16], used). The
# purchase below checks the place against the counts it must have made.
PROGRESS_AT = 280
PACK_PROGRESS = 44


def progress(path, pack):
    """(starchips spent, packs opened, bought, opened, pity by tier) of a pack
    by its place in the list."""
    data, found = chunks(path)
    at = found["pack-shop"] + PROGRESS_AT
    spent, opened_all = struct.unpack_from("<II", data, at)
    mine = at + 8 + PACK_PROGRESS * pack
    bought, opened = struct.unpack_from("<II", data, mine)
    return spent, opened_all, bought, opened, list(struct.unpack_from("<16H", data, mine + 8))


def chest(path):
    data, found = chunks(path)
    base = found["memory"] + CHEST - 0x80000000
    return data[base + 1:base + 723]


def run(executable, label, frame, sequence, mods, state=None, mode_at=True, with_mod=True):
    folder = OUT / label
    shutil.rmtree(folder, ignore_errors=True)
    folder.mkdir(parents=True)
    settings = folder / "settings.txt"
    settings.write_text("mod.3d-monsters=0\nmod.hand-camera=0\nmod.ai-hard-mode=0\n" +
                        ("mod.packs-test=1\n" if with_mod else "mod.packs-test=0\n"))
    env = {key: value for key, value in os.environ.items() if not key.startswith("MEMORIES_")}
    env.update(MEMORIES_HEADLESS="1", MEMORIES_DETERMINISTIC="1", MEMORIES_NO_AUDIO="1", MEMORIES_NO_GAMEPAD="1",
               MEMORIES_NO_UPDATE_CHECK="1", MEMORIES_WATCHDOG="0", MEMORIES_SPEED="-1",
               MEMORIES_SETTINGS=str(settings), MEMORIES_USER_DIR=str(folder / "user"), MEMORIES_MODS_DIR=str(mods),
               MEMORIES_INPUT=sequence, MEMORIES_DUMP_FRAME=str(frame + 1), MEMORIES_DUMP_PATH=str(folder / "game.ppm"),
               MEMORIES_SAVE_STATE=f"{frame}:{folder / 'end.state'}")
    if mode_at:
        env["MEMORIES_MODE_AT"] = "1000:10"
    if "MEMORIES_DISC" in os.environ:
        env["MEMORIES_DISC"] = os.environ["MEMORIES_DISC"]
    if state:
        env["MEMORIES_LOAD_STATE"] = str(state)
    command = [str(executable)]
    if executable.suffix == ".exe" and sys.platform != "win32":
        command = ["wine", str(executable)]
        env.update(WINEPREFIX=str(WINE_PREFIX), WINEDLLOVERRIDES="mscoree,mshtml=", WINEDEBUG="-all")
    with (folder / "run.log").open("w") as log:
        subprocess.run(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=600)
    return folder / "end.state"


def presses(start, keys, gap=70):
    return ",".join(f"{start + gap * i}:{key},{start + gap * i + 6}:0000" for i, key in enumerate(keys))


def check(condition, message):
    if not condition:
        sys.exit(f"packs: FAILED: {message}")
    print(f"packs: ok: {message}")


def main():
    global OUT
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--windows", action="store_true", help="test the Windows build under Wine")
    parser.add_argument("--executable", type=Path, help="the game to test (default: the build for this host)")
    parser.add_argument("--out", type=Path, help=f"where the runs are kept (default: {OUT})")
    arguments = parser.parse_args()
    executable = WINDOWS_EXECUTABLE if arguments.windows else EXECUTABLE
    if arguments.executable:
        executable = arguments.executable.resolve()
    if arguments.out:
        OUT = arguments.out.resolve()
    mods = OUT / "mods"
    shutil.rmtree(mods, ignore_errors=True)
    make_mod(mods)

    # The Password screen of a fresh game, given starchips.
    screen = run(executable, "screen", SCREEN, OPENING, mods)
    data, found = chunks(screen)
    struct.pack_into("<I", data, found["memory"] + STARCHIPS - 0x80000000, 1000)
    for card in OWNED + OWNED_SOLD:
        data[found["memory"] + CHEST - 0x80000000 + card] = 1
    rich = OUT / "rich.state"
    rich.write_bytes(bytes(data))
    before = chest(rich)
    check("pack-shop" in found, "a state of the Password screen with a pack mod has its pack-shop chunk")

    # △, ✕ (BUY / QUIT), ✕ (BUY), then □ once the first card turns: the list.
    buying = presses(60, [TRIANGLE, CROSS, CROSS]) + "," + presses(400, [SQUARE])
    bought = run(executable, "buy", 520, buying, mods, state=rich, mode_at=False)
    after = chest(bought)
    gained = {card + 1: after[card] - before[card] for card in range(722) if after[card] != before[card]}
    check(peek(bought, STARCHIPS, "I") == 1000 - PRICE, f"the starchips drop by the price ({PRICE})")
    check(sum(gained.values()) == COUNT and set(gained) <= set(CARDS),
          f"the chest gains the {COUNT} cards of the pack: {gained}")
    data, found = chunks(bought)
    recent = list(struct.unpack_from(f"<{COUNT}H", data, found["memory"] + RECENT - 0x80000000))
    check(sorted(recent) == sorted(card for card, n in gained.items() for _ in range(n)),
          f"the cards last awarded are the pack's: {recent}")
    check(any(card in CARDS[6:] for card in recent), "the guarantee gives a rare")
    check(progress(bought, 0)[:4] == (PRICE, 1, 1, 1),
          f"the save's progress counts it: {PRICE} starchips spent, one pack opened, bought once")

    again = run(executable, "buy-again", 520, buying, mods, state=rich, mode_at=False)
    check(chest(again) == after, "the same input deals the same pack")

    # A state saved while the first card is up, resumed in a new process.
    turning = run(executable, "turning", 330, presses(60, [TRIANGLE, CROSS, CROSS]), mods, state=rich,
                  mode_at=False)
    resumed = run(executable, "resumed", 200, presses(60, [SQUARE]), mods, state=turning, mode_at=False)
    check(chest(resumed) == after, "a state saved mid-reveal keeps the cards, once, in a new process")
    check(peek(resumed, STARCHIPS, "I") == 1000 - PRICE, "and the starchips paid, once")

    # Every card held "max_copies" times: refused by default (the list, then
    # BUY / QUIT with BUY grey, ✕ taking QUIT), sold with "sell".
    refusing = presses(60, [TRIANGLE, RIGHT, CROSS, CROSS])
    run(executable, "owned-list", 60 + 70 + 150, refusing, mods, state=rich, mode_at=False)
    run(executable, "owned-question", 60 + 140 + 110, refusing, mods, state=rich, mode_at=False)
    refused = run(executable, "owned", 520, refusing, mods, state=rich, mode_at=False)
    check(peek(refused, STARCHIPS, "I") == 1000 and chest(refused) == before,
          "a pack with nothing left for the player is refused: no starchips, no cards")
    check(progress(refused, 1) == (0, 0, 0, 0, [0] * 16),
          "and its stock, its openings, the pity and the save's counts are untouched")
    sold = run(executable, "owned-sold", 520, presses(60, [TRIANGLE, RIGHT, RIGHT, CROSS, CROSS]), mods, state=rich,
               mode_at=False)
    check(peek(sold, STARCHIPS, "I") == 1000 - OWNED_PRICE and chest(sold) == before,
          "\"when_nothing_left\": \"sell\" sells it: the price paid, every slot empty")
    check(progress(sold, 2)[:4] == (OWNED_PRICE, 1, 1, 1) and progress(sold, 2)[4][1] == 1,
          "and counts it: a purchase of the stock, an opening, a pack without its rare for the pity")

    # A full chest: the commons at 250, the pack deals none of them; every
    # card at 250, it is refused; a fixed card at 250 refuses its pack.
    def chest_with(name, cards):
        data, found = chunks(rich)
        for card in cards:
            data[found["memory"] + CHEST - 0x80000000 + card] = FULL
        path = OUT / name
        path.write_bytes(bytes(data))
        return path
    commons_full = chest_with("commons-full.state", CARDS[:6])
    held = chest(commons_full)
    dealt = run(executable, "full-commons", 520, buying, mods, state=commons_full, mode_at=False)
    gained = {card + 1: chest(dealt)[card] - held[card] for card in range(722) if chest(dealt)[card] != held[card]}
    data, found = chunks(dealt)
    recent = list(struct.unpack_from(f"<{COUNT}H", data, found["memory"] + RECENT - 0x80000000))
    check(peek(dealt, STARCHIPS, "I") == 1000 - PRICE and gained and set(gained) <= set(CARDS[6:]) and
          not set(recent) & set(CARDS[:6]),
          f"a chest full of the commons is dealt none of them, only the rares (a common slot comes empty): {gained}")
    all_full = chest_with("all-full.state", CARDS)
    refused = run(executable, "full-all", 520, buying, mods, state=all_full, mode_at=False)
    check(peek(refused, STARCHIPS, "I") == 1000 and chest(refused) == chest(all_full),
          "a pack whose every card the chest is full of is refused: nothing paid")
    fixed_full = chest_with("fixed-full.state", [FIXED])
    fixed = presses(60, [TRIANGLE, RIGHT, RIGHT, RIGHT, CROSS, CROSS])
    refused = run(executable, "full-fixed", 600, fixed, mods, state=fixed_full, mode_at=False)
    check(peek(refused, STARCHIPS, "I") == 1000 and chest(refused) == chest(fixed_full),
          "a pack whose fixed card the chest has no room for is refused")
    sold = run(executable, "fixed", 600, fixed, mods, state=rich, mode_at=False)
    check(peek(sold, STARCHIPS, "I") == 1000 - FIXED_PRICE and chest(sold)[FIXED - 1] == 1,
          "and sold with room: the fixed card in the chest")

    # Without the mod, △ does nothing on the Password screen.
    plain = run(executable, "plain", SCREEN + 100, OPENING, mods, with_mod=False)
    pressed = run(executable, "plain-triangle", SCREEN + 100, OPENING + "," + presses(SCREEN + 20, [TRIANGLE]), mods,
                  with_mod=False)
    check((OUT / "plain" / "game.ppm").read_bytes() == (OUT / "plain-triangle" / "game.ppm").read_bytes(),
          "without a pack mod the triangle changes nothing on the screen")
    data, found = chunks(plain)
    check("pack-shop" not in found, "and a state has no pack-shop chunk")
    print("packs: all passed")


if __name__ == "__main__":
    main()
