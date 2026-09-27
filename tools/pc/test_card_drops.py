#!/usr/bin/env python3
"""Live Game > Card drops test (built game and user-supplied disc).

Wins a real duel (the smoke test's opening, then the opponent's life points
set to zero in a saved state), and on RESULTS OF DUEL checks the page order,
the cards awarded on leaving, and that a state saved on the screen keeps the
added pages. With --smart it also checks Game > Smart drops: a chest
holding three of every card (the Cheats menu's "Give 3 of every card")
leaves the pool as it is, and a chest with a few of the pool's cards short
of three deals only those. Artifacts, settings, states and screenshots stay
in tmp/pc/card-drops-smoke (or --out); no player saves are touched.

    python3 tools/pc/test_card_drops.py [--windows | --executable PATH] [--smart] [--out DIR]
"""
import argparse
import json
import os
from pathlib import Path
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "tmp/pc/card-drops-smoke"
EXECUTABLE = ROOT / "tmp/pc/game32/memories-pc"
WINDOWS_EXECUTABLE = ROOT / "tmp/pc/win32/memories-pc.exe"
WINE_PREFIX = ROOT / "tmp/pc/wine-prefix"

HAND = 6560      # the duel's first hand (tests/pc/smoke/duel-hand-camera.json)
RESULTS = 8400   # RESULTS OF DUEL is up and the drops are dealt
# Fuse two hand cards, set the result, pick its guardian star and end the
# turn: the zeroed life points end the duel.
WIN = ("6570:0010,6576:0000,6590:0020,6596:0000,6610:0010,6616:0000,6640:8000,6646:0000,"
       "6700:4000,6706:0000,7600:4000,7606:0000,7800:0008,7806:0000")
RIGHT, LEFT, CROSS = "0020", "0080", "4000"   # the script's pad bits

OPPONENT_LP = 0x800EA024        # D_800E9FF0[1].life_points
OPPONENT_SHOWN_LP = 0x800EA022  # and the value drawn
RESULT_RECORD = 0x8009B1E8      # D_8009B1E8, DuelResultDisplayState *
PAGE_INDEX, DROPPED_CARD = 0x37, 0x3C
CHEST = 0x801D0250 - 1          # gLibrary_abCardChest, by card id
RECENT = 0x801D07BC             # the 16 cards last awarded, newest first
DECK = 0x801D0200               # the player's 40 cards, u16 ids
POOLS = 0x8017878C              # gDuel_awSaPowCardDrops: POW, BCD, TEC rows
POOL_STRIDE = 0x5B4             # 722 u16 weights and the padding
CARDS = 722


def chunks(path):
    data = bytearray(path.read_bytes())
    at, found = 16, {}
    while at + 20 <= len(data):
        tag = data[at:at + 16].split(b"\0")[0].decode()
        size, = struct.unpack_from("<I", data, at + 16)
        found[tag] = at + 20
        at += 20 + size
    return data, found["memory"]


def peek(path, address, form):
    data, memory = chunks(path)
    return struct.unpack_from("<" + form, data, memory + address - 0x80000000)[0]


def chest(path):
    data, memory = chunks(path)
    return data[memory + CHEST + 1 - 0x80000000:memory + CHEST + 723 - 0x80000000]


def deck(path):
    data, memory = chunks(path)
    return struct.unpack_from("<40H", data, memory + DECK - 0x80000000)


def pools(path):
    data, memory = chunks(path)
    return [struct.unpack_from(f"<{CARDS}H", data, memory + POOLS + POOL_STRIDE * i - 0x80000000) for i in range(3)]


def presses(frame, keys):
    return ",".join(f"{frame + 40 * i}:{key},{frame + 40 * i + 6}:0000" for i, key in enumerate(keys))


def run(executable, label, frame, sequence="", state=None, drops=1, smart=0, chest_cheat=None):
    folder = OUT / label
    folder.mkdir(parents=True, exist_ok=True)
    for old in folder.glob("*.bmp"):
        old.unlink()
    settings = folder / "settings.txt"
    settings.write_text(f"card_drops={drops}\nsmart_drops={smart}\nscale=2\nmod.3d-monsters=0\nmod.hand-camera=0\nmod.ai-hard-mode=0\n")
    env = {key: value for key, value in os.environ.items() if not key.startswith("MEMORIES_")}
    env.update(SDL_VIDEODRIVER=os.environ.get("SDL_VIDEODRIVER", "offscreen"),
               MEMORIES_DETERMINISTIC="1", MEMORIES_NO_AUDIO="1", MEMORIES_NO_GAMEPAD="1",
               MEMORIES_NO_UPDATE_CHECK="1", MEMORIES_WATCHDOG="0",
               MEMORIES_SPEED="-1", MEMORIES_SETTINGS=str(settings), MEMORIES_USER_DIR=str(folder / "user"),
               MEMORIES_INPUT=sequence, MEMORIES_WINDOW_SHOT=str(frame), MEMORIES_DUMP_FRAME=str(frame + 1),
               MEMORIES_SCREENSHOT_DIR=str(folder), MEMORIES_DUMP_PATH=str(folder / "game.ppm"),
               MEMORIES_SAVE_STATE=f"{frame}:{folder / 'end.state'}")
    if "MEMORIES_DISC" in os.environ:
        env["MEMORIES_DISC"] = os.environ["MEMORIES_DISC"]
    if state:
        env["MEMORIES_LOAD_STATE"] = str(state)
    if chest_cheat is not None:
        env["MEMORIES_DEBUG_CHEST"] = str(chest_cheat)   # Cheats_GiveAllCards, as the menu's
    command = [str(executable)]
    if executable.suffix == ".exe" and sys.platform != "win32":
        command = ["wine", str(executable)]
        env.update(WINEPREFIX=str(WINE_PREFIX), WINEDLLOVERRIDES="mscoree,mshtml=", WINEDEBUG="-all")
    with (folder / "run.log").open("w") as log:
        subprocess.run(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=300)
    return folder / "end.state"


def record(path):
    return peek(path, RESULT_RECORD, "I")


def page(path):
    return peek(path, record(path) + PAGE_INDEX, "B")


def owned(path):
    """Copies of each card (by id - 1) in the deck and the chest."""
    counts = list(chest(path))
    for card in deck(path):
        if card:
            counts[card - 1] += 1
    return counts


def exit_results(executable, label, ending, smart, chest_cheat=None, drops=5):
    """Win with `drops` cards, shoot SPOILS and the first added page, leave
    RESULTS OF DUEL, and return the cards gained, SPOILS' card and the
    copies owned before and after."""
    screen = run(executable, label + "-spoils", RESULTS + 120, WIN, ending, drops=drops, smart=smart,
                 chest_cheat=chest_cheat)
    run(executable, label + "-page", RESULTS + 120, presses(RESULTS + 20, [RIGHT]), screen, drops=drops, smart=smart)
    done = run(executable, label + "-exit", RESULTS + 900, presses(RESULTS + 20, [CROSS]), screen, drops=drops,
               smart=smart)
    before, after = owned(screen), owned(done)
    gained = []
    for index, (a, b) in enumerate(zip(after, before)):
        gained += [index + 1] * (a - b)
    first = peek(done, record(done) + DROPPED_CARD, "h")
    return gained, first, before, after


def smart_checks(executable, ending):
    # Three of every card (the cheat): nothing is left, and the pool stands
    # as the game has it, card for card the same as with the setting off.
    off, first_off, _, _ = exit_results(executable, "smart-full-off", ending, 0, chest_cheat=3)
    on, first_on, _, _ = exit_results(executable, "smart-full-on", ending, 1, chest_cheat=3)
    print(f"smart-full: off {off} (SPOILS {first_off}), on {on} (SPOILS {first_on})")
    assert len(on) == 5 and sorted(off) == sorted(on) and first_off == first_on, \
        "a full chest should leave the pool as it is"
    # The pool this duel draws from: the one holding every card just dealt.
    rows = [row for row in pools(ending) if all(row[card - 1] for card in on)]
    assert rows, "no drop pool holds the cards dealt"
    row = rows[0]
    # Three of every card but four of the pool's lightest ones (none in the
    # deck): the first of them at two, the others at none.
    counts = list(deck(ending))
    weighted = sorted((weight, card + 1) for card, weight in enumerate(row)
                      if weight and (card + 1) not in counts)
    open_cards = [card for _, card in weighted[:4]]
    data, memory = chunks(ending)
    for card in range(1, CARDS + 1):
        wanted = 3 - counts.count(card)
        if card == open_cards[0]:
            wanted = 2
        elif card in open_cards:
            wanted = 0
        data[memory + CHEST + card - 0x80000000] = max(wanted, 0)
    partial = OUT / "partial.state"
    partial.write_bytes(data)
    for smart in (0, 1):
        label = "smart-partial-" + ("on" if smart else "off")
        gained, first, before, after = exit_results(executable, label, partial, smart)
        print(f"{label}: open {open_cards} (weights {[row[c - 1] for c in open_cards]} of 2048), "
              f"SPOILS {first}, gained {gained}")
        assert len(gained) == 5, f"five cards should be awarded, not {gained}"
        if smart:
            assert all(card in open_cards for card in gained), "only the open cards should drop"
            assert all(after[card - 1] <= 3 for card in open_cards), "no card should pass three copies"
    print(f"smart drops: a full chest keeps the pool, a partial one deals only its open cards; {OUT}")


def main():
    global OUT
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--windows", action="store_true", help="test the Windows build under Wine")
    parser.add_argument("--executable", type=Path, help="the game to test (default: the build for this host)")
    parser.add_argument("--out", type=Path, help=f"where the runs are kept (default: {OUT})")
    parser.add_argument("--smart", action="store_true", help="also check Game > Smart drops")
    arguments = parser.parse_args()
    executable = WINDOWS_EXECUTABLE if arguments.windows else EXECUTABLE
    if arguments.executable:
        executable = arguments.executable.resolve()
    if arguments.out:
        OUT = arguments.out.resolve()
    opening = json.loads((ROOT / "tests/pc/smoke/duel-hand-camera.json").read_text())["input"]
    hand = run(executable, "hand", HAND, opening)
    data, memory = chunks(hand)
    for address in (OPPONENT_LP, OPPONENT_SHOWN_LP):
        struct.pack_into("<h", data, memory + address - 0x80000000, 0)
    ending = OUT / "ending.state"
    ending.write_bytes(data)
    before = chest(ending)

    # One card: the console's three pages and one award.
    one = run(executable, "one-right", RESULTS + 120, WIN + "," + presses(RESULTS + 20, [RIGHT]), ending)
    assert page(one) == 1, "Right from SPOILS should reach the statistics with one card"
    one = run(executable, "one-exit", RESULTS + 900, WIN + "," + presses(RESULTS + 20, [CROSS]), ending)
    first = peek(one, record(one) + DROPPED_CARD, "h")
    gained = [a - b for a, b in zip(chest(one), before)]
    assert sum(gained) == 1 and gained[first - 1] == 1, "one card should award SPOILS' card alone"

    # Twenty: the added pages sit between SPOILS and the statistics.
    many = run(executable, "many", RESULTS, WIN, ending, drops=20)
    right = run(executable, "many-right", RESULTS + 120, presses(RESULTS + 20, [RIGHT]), many, drops=20)
    assert page(right) == 3, "Right from SPOILS should open the first added page"
    left = run(executable, "many-left", RESULTS + 120, presses(RESULTS + 20, [LEFT]), many, drops=20)
    assert page(left) == 2, "Left from SPOILS should still reach SPECIAL ARTS"
    back = run(executable, "many-back", RESULTS + 200, presses(RESULTS + 20, [LEFT, LEFT, LEFT]), many, drops=20)
    assert page(back) >= 3, "Left from the statistics should reach the last added page"
    # Leaving with the setting back at one: the duel's own deal is awarded,
    # from a state saved on the screen, the first card last.
    done = run(executable, "many-exit", RESULTS + 900, presses(RESULTS + 20, [CROSS]), many)
    first = peek(done, record(done) + DROPPED_CARD, "h")
    gained = [a - b for a, b in zip(chest(done), before)]
    assert sum(gained) == 20, f"twenty cards should be awarded, not {sum(gained)}"
    assert peek(done, RECENT, "H") == first, "SPOILS' card should be the last awarded"
    print(f"card drops: page order, awards and saved states passed; {OUT}")
    if arguments.smart:
        smart_checks(executable, ending)


if __name__ == "__main__":
    main()
