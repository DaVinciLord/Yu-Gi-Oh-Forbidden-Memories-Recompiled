#!/usr/bin/env python3
"""Drive the native game through its control channel (MEMORIES_CONTROL,
notes/agent-control.md): launch it with folders of its own, step it, press
buttons, read its state as data, take pictures and save states, all in one
process.

    from yfm_control import Game
    with Game() as game:                       # boots; the game waits for it
        game.wait_until(lambda g: g.resident("main_menu"), 3000)   # the title
        game.press_until(lambda g: g.resident("password"), ["start", "cross"])  # NEW GAME
        game.shot("name-entry.png")
        print(game.state())

tools/pc/examples/control_first_duel.py goes on to the first duel.

The game runs only when told to (`step`); with MEMORIES_DETERMINISTIC=1,
which Game sets, the same calls give the same frames on every run. All the
game knowledge lives here; the C side only steps, presses and reads memory.

Run as a script for a quick look:  python3 tools/pc/yfm_control.py [--frames N]
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import sys
import tempfile
import time
from typing import Callable, Iterable
import weakref

sys.path.insert(0, str(Path(__file__).resolve().parent))
from smoke import launcher  # noqa: E402  (Wine for a Windows build off Windows)

ROOT = Path(__file__).resolve().parents[2]
EXECUTABLE = ROOT / "tmp/pc/game32" / ("memories-pc.exe" if sys.platform == "win32" else "memories-pc")
OUTPUT = ROOT / "tmp/pc/control"   # a run-XXXXXXXX folder each, as smoke.py does
ADDRESSES = ROOT / "config/pc/guest_addresses.txt"

# PS1 digital pad bits, active high (src/pc/platform/platform.h, Platform_Pad).
BUTTONS = {"select": 0x0001, "l3": 0x0002, "r3": 0x0004, "start": 0x0008, "up": 0x0010, "right": 0x0020,
           "down": 0x0040, "left": 0x0080, "l2": 0x0100, "r2": 0x0200, "l1": 0x0400, "r1": 0x0800,
           "triangle": 0x1000, "circle": 0x2000, "cross": 0x4000, "square": 0x8000}

# The low five bits of the mode byte (src/game/main_modes.h, MainMode).
MODE = {"debug": 0, "animated_battle": 1, "campaign": 2, "duel": 3, "library": 4, "campaign_map": 5,
        "free_duel": 6, "build_deck": 7, "menu": 8, "name_entry": 9, "password": 10, "options": 11,
        "game_over": 12, "unused_developer": 13, "trade": 14, "credits": 15, "two_player_setup": 16}
MODE_NAMES = {value: name for name, value in MODE.items()}
# Where each `jump` target lands (title_jump.h): the mode it runs.
JUMP_MODES = {"title": MODE["menu"], "debug": MODE["debug"], "duel": MODE["duel"], "free_duel": MODE["free_duel"],
              "build_deck": MODE["build_deck"], "library": MODE["library"], "password": MODE["password"],
              "map": MODE["campaign_map"], "credits": MODE["credits"], "options": MODE["options"]}

# Guest addresses by name. config/pc/guest_addresses.txt has every global the
# build pins to its retail address, and is read when present (a checkout);
# these are the fallbacks, from the headers named. The symbol table beside
# the executable (symbols/<build id>.txt, for carrying states between builds)
# holds only host addresses (functions and the game objects' own variables),
# none of these.
FALLBACK = {
    "D_8009B26C": 0x8009B26C,             # main_mode_state.h: the active mode and its flags
    "gDuel_bOpponentID": 0x8009B361,      # the duellist the next duel is against
    "D_800E9FF0": 0x800E9FF0,             # duel_side_state.h: DuelSideState[2], 0x20 each
    "D_801A7AD8": 0x801A7AD8,             # duel_card.h: DuelCardRecord[30], 0x1C each
    "gDuel_awPlayerDeck": 0x801D0200,     # save_data.h: the player's deck, u16[40] card ids
    "gLibrary_abCardChest": 0x801D0250,   # save_data.h: copies in the chest, u8 by card id - 1
    "gLibrary_dwStarchips": 0x801D07E0,   # save_data.h: SaveDataState.starchips, u32
    "gSaveData_aPlayerNameSjis": 0x801D060C,  # save_data.h: the player's name, Shift JIS
    "D_8009B26E": 0x8009B26E,             # a mode's step; 0x80 in a duel: the deck screen before it
}
# Overlay modules (tools/pc/build_game32.py, MODULES): the load address and
# the identifier word an image starts with while it is resident.
MODULES = {"main_menu": (0x80180000, 0x0F), "credits": (0x80180000, 0x10), "free_duel": (0x80168000, 0x13),
           "overworld": (0x80168000, 0x14), "password": (0x80168000, 0x15), "duel_effects": (0x80146000, 0x18)}
SIDE_SIZE, RECORD_SIZE, HAND_SIZE, DECK_SIZE, CARDS = 0x20, 0x1C, 5, 40, 722
# duel_field_layout.c: a side's card records are 15 in a row from 15 * side:
# five hand slots (D_800907CC), then the field (D_800907D8): five monster
# zones and five spell and trap zones.
HAND_RECORDS, MONSTER_RECORDS, SPELL_RECORDS = range(0, 5), range(5, 10), range(10, 15)


class ControlError(RuntimeError):
    """The game answered "err ..."."""


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def buttons(keys: str | Iterable[str] | int) -> int:
    """Pad bits from "cross", "up+cross", ["l1", "r1"] or the bits themselves."""
    if isinstance(keys, int):
        return keys
    if isinstance(keys, str):
        keys = keys.replace("+", " ").split()
    bits = 0
    for key in keys:
        if key.lower() not in BUTTONS:
            raise ValueError(f"no button {key!r}; buttons are {', '.join(BUTTONS)}")
        bits |= BUTTONS[key.lower()]
    return bits


def guest_addresses(path: Path = ADDRESSES) -> dict[str, int]:
    table = dict(FALLBACK)
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            parts = line.split()
            if len(parts) == 2 and not line.startswith("#"):
                table[parts[0]] = int(parts[1], 16)
    except OSError:
        pass
    return table


def _end(process: subprocess.Popen) -> None:
    if process.poll() is None:
        process.kill()
        process.wait()


class Game:
    """One game process and its control connection.

    executable  the game (default tmp/pc/game32/memories-pc[.exe])
    out         where its settings, user folder, log and pictures go
                (default a new tmp/pc/control/run-XXXXXXXX)
    settings    the player's settings by key ("mod.3d-monsters": 0, ...);
                everything else is the default
    env         more MEMORIES_* variables (MEMORIES_INPUT, MEMORIES_LOAD_STATE...)
    headless    no window (the default); a window shows each frame as it is stepped
    mods_dir    a mods folder of its own (MEMORIES_MODS_DIR); by default the
                mods shipped beside the executable, as smoke.py runs them
    """

    def __init__(self, executable: Path | str | None = None, out: Path | str | None = None,
                 settings: dict[str, object] | None = None, env: dict[str, str] | None = None,
                 headless: bool = True, mods_dir: Path | str | None = None, timeout: float = 60.0):
        self.executable = Path(executable or os.environ.get("YFM_EXECUTABLE") or EXECUTABLE).resolve()
        if not self.executable.is_file():
            raise FileNotFoundError(f"no game at {self.executable} (build it with tools/pc/build_game32.py)")
        if out is None:
            OUTPUT.mkdir(parents=True, exist_ok=True)
            out = tempfile.mkdtemp(prefix="run-", dir=OUTPUT)
        self.out = Path(out).resolve()
        self.out.mkdir(parents=True, exist_ok=True)
        self.symbols = guest_addresses()
        self.frame = self.vblank = 0
        self._buffer = b""
        settings_file = self.out / "settings.txt"
        settings_file.write_text("".join(f"{key}={value}\n" for key, value in (settings or {}).items()),
                                 encoding="utf-8")
        (self.out / "user").mkdir(exist_ok=True)
        environment = {key: value for key, value in os.environ.items() if not key.startswith("MEMORIES_")}
        if os.environ.get("MEMORIES_DISC"):
            environment["MEMORIES_DISC"] = os.environ["MEMORIES_DISC"]
        environment.update(MEMORIES_DETERMINISTIC="1", MEMORIES_NO_UPDATE_CHECK="1", MEMORIES_NO_GAMEPAD="1",
                           MEMORIES_SHOW_HUD="0", MEMORIES_WATCHDOG="0", MEMORIES_SETTINGS=str(settings_file),
                           MEMORIES_USER_DIR=str(self.out / "user"))
        if headless:
            environment.update(MEMORIES_HEADLESS="1", MEMORIES_NO_AUDIO="1")
        if mods_dir:
            environment["MEMORIES_MODS_DIR"] = str(Path(mods_dir).resolve())
        environment.update(env or {})
        command, extra = launcher(self.executable)
        environment.update(extra)
        self.log_path = self.out / "game.log"
        for attempt in range(3):   # a port taken between free_port() and the game's bind
            self.port = free_port()
            environment["MEMORIES_CONTROL"] = str(self.port)
            self._log = self.log_path.open("ab")
            self.process = subprocess.Popen(command, cwd=ROOT, env=environment, stdout=self._log,
                                            stderr=subprocess.STDOUT)
            # Ended with this object or this interpreter, whatever happens:
            # a game whose client has gone runs on by itself.
            self._finalizer = weakref.finalize(self, _end, self.process)
            self.connection = self._connect(timeout)
            if self.connection:
                break
            self.close()
        else:
            raise RuntimeError(f"the game never opened its control channel; see {self.log_path}")
        self.info()

    def _connect(self, timeout: float) -> socket.socket | None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline and self.process.poll() is None:
            try:
                connection = socket.create_connection(("127.0.0.1", self.port), timeout=5)
            except OSError:
                time.sleep(0.05)
                continue
            connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            connection.settimeout(None)
            return connection
        return None

    # The protocol: one line out, one line back.

    def command(self, line: str) -> str:
        """Send one command; its reply without "ok". ControlError on "err"."""
        self.connection.sendall(line.encode() + b"\n")
        while b"\n" not in self._buffer:
            chunk = self.connection.recv(1 << 20)
            if not chunk:
                raise ControlError(f"the game closed the channel after {line!r}; see {self.log_path}")
            self._buffer += chunk
        reply, self._buffer = self._buffer.split(b"\n", 1)
        text = reply.decode()
        if text.startswith("err"):
            raise ControlError(f"{line.split()[0]}: {text[4:]}")
        return text[3:] if text.startswith("ok ") else ""

    def _stopped(self, reply: str) -> dict[str, int]:
        fields = reply.split()
        values = {fields[i]: int(fields[i + 1], 16 if fields[i] == "build" else 10) for i in range(0, len(fields), 2)}
        self.frame, self.vblank = values["frame"], values["vblank"]
        return values

    # Primitives.

    def step(self, vblanks: int = 1) -> dict[str, int]:
        """Run `vblanks` VBlanks and stop at the next safe point (the end of
        the next VSync(0)): {"frame", "vblank"} where it stopped."""
        return self._stopped(self.command(f"step {int(vblanks)}"))

    def info(self) -> dict[str, int]:
        """{"frame", "vblank", "mode" (the raw byte), "build"}."""
        return self._stopped(self.command("info"))

    def mode(self) -> int:
        """The active main mode (MODE), without its flags."""
        return self.u8("D_8009B26C") & 0x1F

    def resident(self, module: str) -> bool:
        """Whether an overlay module (MODULES) is loaded now."""
        address, identifier = MODULES[module]
        return self.u32(address) == identifier

    def player_name(self) -> bytes:
        """The name entered at NEW GAME, as the save holds it (Shift JIS)."""
        return self.peek("gSaveData_aPlayerNameSjis", 16).split(b"\0")[0]

    def pad(self, keys: str | Iterable[str] | int = 0, port: int = 1) -> None:
        """Hold these buttons from now on (0 releases), on pad 1 or 2."""
        self.command(f"pad {port} {buttons(keys):04x}")

    def press(self, keys: str | Iterable[str] | int, hold: int = 6, after: int = 6, port: int = 1) -> None:
        """Press and release: held for `hold` VBlanks, then `after` more with
        nothing, so the next press is a press of its own."""
        self.pad(keys, port)
        self.step(hold)
        self.pad(0, port)
        if after:
            self.step(after)

    def presses(self, *keys: str, hold: int = 6, after: int = 6) -> None:
        for key in keys:
            self.press(key, hold, after)

    def wait_until(self, predicate: Callable[["Game"], object], timeout: int = 600, every: int = 1,
                   what: str = "") -> int:
        """Step `every` VBlanks at a time until predicate(game) holds; at most
        `timeout` VBlanks. The VBlanks it took; TimeoutError past it."""
        start = self.vblank
        while not predicate(self):
            if self.vblank - start >= timeout:
                raise TimeoutError(f"{what or 'condition'} not reached in {timeout} VBlanks "
                                   f"(frame {self.frame}, mode {self.mode()})")
            self.step(every)
        return self.vblank - start

    def press_until(self, predicate: Callable[["Game"], object], keys: str | list[str], every: int = 30,
                    timeout: int = 6000, what: str = "") -> int:
        """Until predicate(game) holds, press the keys in turn (a name, or a
        list of them cycled), one press every `every` VBlanks: dialogue,
        menus and screens that wait for a button, without counting frames.
        The presses it took; TimeoutError past `timeout` VBlanks."""
        keys = [keys] if isinstance(keys, str) else list(keys)
        start, count = self.vblank, 0
        while not predicate(self):
            if self.vblank - start >= timeout:
                raise TimeoutError(f"{what or 'condition'} not reached in {timeout} VBlanks "
                                   f"(frame {self.frame}, mode {self.mode()})")
            self.press(keys[count % len(keys)], hold=6, after=max(every - 6, 0))
            count += 1
        return count

    def wait_mode(self, mode: int | str, timeout: int = 3000) -> int:
        """Until the main mode is `mode` (MODE's names or numbers)."""
        wanted = MODE[mode] if isinstance(mode, str) else mode
        return self.wait_until(lambda game: game.mode() == wanted, timeout,
                               what=f"mode {MODE_NAMES.get(wanted, wanted)}")

    # Where the game is going: Debug > Jump to's path (title_jump.h).

    def goto(self, target: str, opponent: int | None = None, deck: str | Iterable[int] | None = None,
             timeout: int = 6000) -> dict[str, int]:
        """Jump to a screen the way Debug > Jump to does (the title, then the
        game's own debug menu and its entry), and step until it runs:
        "debug", "duel" (against `opponent`, with `deck`: ids or ranges as
        MEMORIES_DEBUG_DECK takes them, repeated to forty), "free_duel",
        "build_deck", "library", "password", "map", "credits", "options",
        "title". A duel stops at the deck screen the game shows before every
        duel (leave it with circle; duel_ready() waits for the hand)."""
        if deck is not None and not isinstance(deck, str):
            deck = ",".join(str(card) for card in deck)
        line = f"jump {target}"
        if opponent is not None or deck:
            line += f" {opponent or 0}" + (f" {deck}" if deck else "")
        self.command(line)
        wanted = JUMP_MODES[target]
        if target == "title":
            return {"vblanks": self.wait_until(lambda g: g.mode() == wanted and g.resident("main_menu"), timeout,
                                               what="the title")}
        if target == "debug":
            return {"vblanks": self.wait_until(lambda g: g.u8("D_8009B26C") == 0xC0, timeout, what="the debug menu")}
        return {"vblanks": self.wait_until(lambda g: g.u8("D_8009B26C") & 0x9F == 0x80 | wanted, timeout,
                                           what=target)}

    def duel_ready(self, timeout: int = 6000) -> int:
        """In a duel: past the deck screen before it (circle), until the
        player's five cards are dealt and the hand takes input."""
        self.press_until(lambda g: g.u8("D_8009B26E") != 0x80 and not g.resident("main_menu"), "circle", every=60,
                         timeout=timeout, what="the duel field")
        taken = self.wait_until(lambda g: all(g.duel()[0]["hand"]), timeout, every=10, what="the hand")
        self.step(200)   # the cards come up from the deck
        return taken + 200

    def shot(self, path: Path | str) -> Path:
        """The presented picture, as PNG (PPM for a .ppm path); relative
        paths go in the run's folder."""
        path = self.out / path
        path.parent.mkdir(parents=True, exist_ok=True)
        self.command(f"shot {path}")
        return path

    def hash(self) -> int:
        """FNV-1a of VRAM, as MEMORIES_FRAME_HASHES writes it."""
        return int(self.command("hash"), 16)

    def address(self, where: int | str) -> int:
        return self.symbols[where] if isinstance(where, str) else where

    def peek(self, where: int | str, length: int) -> bytes:
        """Guest memory (KSEG0, KSEG1 or physical; or a symbol's name)."""
        address, data = self.address(where), b""
        while len(data) < length:
            count = min(16384, length - len(data))
            data += bytes.fromhex(self.command(f"peek {address + len(data):08x} {count}"))
        return data

    def poke(self, where: int | str, data: bytes) -> None:
        address = self.address(where)
        for at in range(0, len(data), 16384):
            self.command(f"poke {address + at:08x} {data[at:at + 16384].hex()}")

    def u8(self, where: int | str, offset: int = 0) -> int:
        return self.peek(self.address(where) + offset, 1)[0]

    def u16(self, where: int | str, offset: int = 0) -> int:
        return struct.unpack("<H", self.peek(self.address(where) + offset, 2))[0]

    def u32(self, where: int | str, offset: int = 0) -> int:
        return struct.unpack("<I", self.peek(self.address(where) + offset, 4))[0]

    def save(self, path: Path | str) -> Path:
        """A save state, here (relative paths go in the run's folder)."""
        path = self.out / path
        path.parent.mkdir(parents=True, exist_ok=True)
        self.command(f"save {path}")
        return path

    def load(self, path: Path | str) -> dict[str, int]:
        """Resume a save state; the game stops again one frame into it."""
        return self._stopped(self.command(f"load {self.out / path}"))

    # The game's state, as data.

    def state(self) -> dict[str, object]:
        """What the game holds now: the mode, the opponent, the save's deck,
        chest and starchips, and in a duel both sides (duel_side_state.h):
        LP, the cards in hand and on the field (by card id; None empty)."""
        mode = self.u8("D_8009B26C")
        deck = struct.unpack(f"<{DECK_SIZE}H", self.peek("gDuel_awPlayerDeck", 2 * DECK_SIZE))
        chest = self.peek("gLibrary_abCardChest", CARDS)
        result: dict[str, object] = {
            "frame": self.frame, "vblank": self.vblank, "mode": mode & 0x1F,
            "mode_name": MODE_NAMES.get(mode & 0x1F, "?"), "mode_flags": mode & 0xE0,
            "opponent": self.u8("gDuel_bOpponentID"), "starchips": self.u32("gLibrary_dwStarchips"),
            "deck": list(deck), "chest": {card + 1: count for card, count in enumerate(chest) if count},
        }
        if mode & 0x1F in (MODE["duel"], MODE["campaign"]):
            result["duel"] = self.duel()
        return result

    def duel(self) -> list[dict[str, object]]:
        """Both sides of the duel: 0 the player, 1 the opponent. A hand slot
        whose byte at +0x1A is negative is empty (its card record keeps the
        card it held); a field zone is taken when its record has a card id.
        `flags` is the record's raw word (0x8000 set on every card dealt;
        0x1000 seen on a card just played). Checked against pictures of the
        first duel's opening hand and its first monster; a destroyed card's
        zone is not checked yet."""
        sides = self.peek("D_800E9FF0", 2 * SIDE_SIZE)
        records = self.peek("D_801A7AD8", 30 * RECORD_SIZE)

        def card(index: int) -> dict[str, int] | None:
            at = index * RECORD_SIZE
            card_id, attack, defense, _, _, flags = struct.unpack_from("<hhhhhH", records, at + 0x0C)
            if card_id <= 0:
                return None
            return {"id": card_id, "attack": attack, "defense": defense, "flags": flags}

        result = []
        for side in range(2):
            at = side * SIDE_SIZE
            displayed, life, maximum = struct.unpack_from("<hHh", sides, at + 0x12)
            base = 15 * side
            slots = list(struct.unpack_from("<5b", sides, at + 0x1A))
            result.append({
                "lp": life, "displayed_lp": displayed, "max_lp": maximum,
                "deck_cursor": struct.unpack_from("<b", sides, at + 0x18)[0],
                "hand_slots": slots,
                "hand": [card(base + i) if slots[i] >= 0 else None for i in HAND_RECORDS],
                "monsters": [card(base + i) for i in MONSTER_RECORDS],
                "spells": [card(base + i) for i in SPELL_RECORDS],
            })
        return result

    # The end.

    def quit(self) -> None:
        """Ask the game to end, and wait for it."""
        try:
            self.command("quit")
        except (ControlError, OSError):
            pass
        self.close()

    def close(self) -> None:
        """Close the connection; a game still running after a few seconds is
        ended (this process's own child only)."""
        connection = getattr(self, "connection", None)
        if connection:
            connection.close()
            self.connection = None
        if getattr(self, "process", None) and self.process.poll() is None:
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        if getattr(self, "_log", None):
            self._log.close()
            self._log = None

    def __enter__(self) -> "Game":
        return self

    def __exit__(self, *exception) -> None:
        if getattr(self, "connection", None) and exception[0] is None:
            self.quit()
        else:
            if getattr(self, "process", None) and self.process.poll() is None:
                self.process.kill()
            self.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--executable", type=Path)
    parser.add_argument("--frames", type=int, default=1200, help="VBlanks to run before looking")
    arguments = parser.parse_args()
    with Game(arguments.executable) as game:
        game.step(arguments.frames)
        print(json.dumps({key: value for key, value in game.state().items() if key != "chest"}, indent=1))
        print("picture:", game.shot("look.png"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
