"""The editor's working copy: the retail tables with the user's edits on top.

A Project starts as a copy of the retail GameData. The GUI and the mod.json
reader change the copy; manifest.build() compares it with retail and writes
only the difference.
"""
from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field

from .gamedata import (CARD_COUNT, DECK_SIZE, DUELIST_COUNT, DUELIST_NAMES, POOLS, TYPE_NAMES, Card, GameData)

KEY_RE = re.compile(r"^[A-Za-z0-9_-]+$")


# --- naming cards the way the port does (src/pc/cards/cards.c) ----------------

def same_words(a: str, b: str) -> bool:
    return a.lower() == b.lower()


def letters(text: str) -> str:
    return "".join(c.lower() for c in text if c.isascii() and c.isalnum())


def same_letters(a: str, b: str) -> bool:
    return letters(a) == letters(b)


class RetailNames:
    """retail_by_name(): the exact name (any case) first, then letters and
    digits only; the first card wins."""

    PUNCTUATION = "!\"#$%&'()*+,-./:<>?"

    @classmethod
    def ascii_name(cls, name: str) -> str:
        """The name as the port's retail_name() spells it: what it cannot
        write in ASCII is a question mark."""
        return "".join(c if c == " " or (c.isascii() and c.isalnum()) or c in cls.PUNCTUATION else "?" for c in name)

    def __init__(self, cards: dict):
        self.names = {cid: self.ascii_name(cards[cid].name) for cid in range(1, CARD_COUNT + 1) if cid in cards}
        self.by_words, self.by_letters = {}, {}
        for cid, name in self.names.items():
            self.by_words.setdefault(name.lower(), cid)
            self.by_letters.setdefault(letters(name), cid)

    def find(self, text: str) -> int:
        return self.by_words.get(text.lower()) or (self.by_letters.get(letters(text)) if letters(text) else 0) or 0


def duelist_named(text) -> int:
    """Duelists_Named for the duelists the disc has: a number 0-39, or a name
    by its letters; -1. A mod's own duelists are not here -- which of them
    exists depends on the mods applied at run time, and the editor reads the
    game's files -- so an entry naming one is kept as it was written rather
    than resolved (manifest.read_pools)."""
    text = str(text)
    if text.isdigit():
        return int(text) if int(text) < DUELIST_COUNT else -1
    for d, name in enumerate(DUELIST_NAMES):
        if same_letters(text, name):
            return d
    return -1


def type_named(text: str) -> int:
    for t, name in enumerate(TYPE_NAMES):
        if same_letters(text, name):
            return t
    return -1


def card_matches(project, cid: int, text: str) -> bool:
    """The editor's card search: the card's number, or a part of its name in
    any case; no text finds every card."""
    if not text:
        return True
    text = text.lower().strip()
    card = project.cards.get(cid)
    if card is None:
        return False
    return text == str(cid) or text in card.name.lower()


@dataclass
class AddedCard:
    """A card the mod adds ("copy"): its stable key, its base, and the entry
    keys the editor does not show (art, count, fusions...), kept as written."""
    key: str
    base: int
    drops: bool = True
    opponents: bool = False
    extra: dict = field(default_factory=dict)


@dataclass
class StarterDeck:
    """A deck a new game may be dealt ("starter", notes/starter-deck.md): its
    own name, how often it is picked against the other offered decks, and its
    cards by their copies. `kept` holds a card the editor cannot place, under
    the name it was written with, so somebody else's deck is not thrown away;
    `extra` keeps the entry's other keys as written."""
    name: str = ""
    weight: int = 1
    cards: dict = field(default_factory=dict)   # card id -> copies
    kept: dict = field(default_factory=dict)    # name as written -> copies
    extra: dict = field(default_factory=dict)

    def total(self) -> int:
        return sum(self.cards.values()) + sum(self.kept.values())

    def complete(self) -> bool:
        """A deck the port will deal: the save holds exactly forty."""
        return self.total() == DECK_SIZE

    def copy(self) -> "StarterDeck":
        return StarterDeck(self.name, self.weight, dict(self.cards), dict(self.kept), copy.deepcopy(self.extra))


@dataclass
class ModInfo:
    id: str = "my-mod"
    name: str = "My mod"
    version: str = "1.0"
    author: str = ""
    description: str = ""
    settings: list = field(default_factory=list)


class Project:
    def __init__(self, retail: GameData):
        self.retail = retail
        self.names = RetailNames(retail.cards)
        self.cards = {cid: card.copy() for cid, card in retail.cards.items()}
        self.added = {}                 # editor id (723+) -> AddedCard
        self.card_extra = {}            # retail id -> keys of its "replace" entry the editor keeps as written
        self.fusions = dict(retail.fusions)
        self.equips = {e: set(m) for e, m in retail.equips.items()}
        self.rituals = dict(retail.rituals)
        # ritual id -> three requirement dictionaries. Empty means the traditional
        # three-specific-card recipe represented by self.rituals.
        self.ritual_requirements = {}
        self.pools = [{p: dict(retail.pools[d][p]) for p in POOLS} for d in range(len(retail.pools))]
        self.info = ModInfo()
        self.other = {}                 # top-level keys the editor keeps as written (data, text, audio...)
        self.kept = {"fusions": [], "equips": [], "rituals": []}   # rules naming cards it cannot place
        self.kept_pools = {}            # (duelist or "all", pool) -> {name: weight} it cannot place
        self.fixed = {}                 # key as written -> fixed_decks.FixedDeck ("fixed": true), in order
        self.starter = []               # StarterDeck: the decks a new game may be dealt
        self.starter_file = None        # "starter" naming a file of the mod's, kept as written
        self.kept_opponents = {}        # "decks"/"drops" -> {name: entry} naming a duelist it cannot place
        self.pool_files = {}            # "decks"/"drops" -> the file the mod names in place of the table
        self.source_dir = None
        self.files = {}                 # path in the mod folder -> bytes to write with it (an import's)
        self.text_cards = {}            # card id -> {field: value} its "text" file carries while unchanged
        # Passwords the mod sets, 8 digits or "" for none: a disc card's goes in
        # "passwords" (the Password screen's), an added card's is its entry's
        # "password" (View > Card passwords alone). password_keys: how
        # "passwords" named a disc card, so the entry is written back there.
        self.passwords = {}
        self.password_keys = {}
        # card id -> the card's "notes": the modder's own text, which the game
        # plays by none of; a code mod may read <tag: value> from it (API 7).
        self.notes = {}

    # --- cards -------------------------------------------------------------

    def next_id(self) -> int:
        return max([CARD_COUNT] + list(self.added)) + 1

    def base_of(self, cid: int) -> int:
        return self.added[cid].base if cid in self.added else cid

    def card_label(self, cid: int) -> str:
        card = self.cards.get(cid)
        return f"{cid} {card.name}" if card else str(cid)

    def password(self, cid: int) -> str:
        """The card's password as the mod leaves it: 8 digits, or "" for none
        (an added card has none of its own unless the mod gives it one)."""
        if cid in self.passwords:
            return self.passwords[cid]
        return self.retail.passwords.get(cid, "") if cid in self.retail.cards else ""

    def set_password(self, cid: int, value: str):
        """Set it; a disc card back at the disc's password, or an added card
        with none, sets nothing."""
        retail = self.retail.passwords.get(cid, "") if cid in self.retail.cards else ""
        if value == retail:
            self.passwords.pop(cid, None)
        else:
            self.passwords[cid] = value

    def password_changed(self, cid: int) -> bool:
        return cid in self.passwords

    def identity(self, cid: int) -> str:
        return f"{self.info.id}:{self.added[cid].key}:1"

    def ref(self, cid: int):
        """How a rule names a card: the retail name when that finds it again,
        its number otherwise, or the stable identity of an added card."""
        if cid in self.added:
            return self.identity(cid)
        name = self.names.names.get(cid, "")
        if name and ":" not in name and "?" not in name and not name.isdigit() and self.names.find(name) == cid:
            return name
        return cid

    def resolve(self, value, mod_id: str = None):
        """A card a rule names (tables.c card()): its id, or 0."""
        if value is None or isinstance(value, bool):
            return 0
        if isinstance(value, int):
            return value if 1 <= value <= CARD_COUNT or value in self.added else 0
        if not isinstance(value, str) or not value:
            return 0
        if ":" in value:
            parts = value.split(":")
            if len(parts) == 3 and parts[0] == (mod_id or self.info.id) and parts[2] == "1":
                for cid, added in self.added.items():
                    if added.key == parts[1]:
                        return cid
            return 0
        if value.isdigit():
            return self.resolve(int(value))
        return self.names.find(value)

    def add_card(self, base: int, key: str = None) -> int:
        cid = self.next_id()
        if not key:
            n = cid - CARD_COUNT
            keys = {a.key for a in self.added.values()}
            while f"card-{n}" in keys:
                n += 1
            key = f"card-{n}"
        source = self.cards[base]
        self.cards[cid] = source.copy(id=cid)
        self.added[cid] = AddedCard(key=key, base=base)
        # A copy equips and is equipped as its base (tables.c Tables_Equip).
        if base in self.equips:
            self.equips[cid] = set(self.equips[base])
        for monsters in self.equips.values():
            if base in monsters:
                monsters.add(cid)
        return cid

    def remove_card(self, cid: int):
        """Take an added card out, and every rule that names it."""
        if cid not in self.added:
            raise ValueError("only a card the mod adds can be removed")
        del self.added[cid]
        del self.cards[cid]
        self.passwords.pop(cid, None)
        self.notes.pop(cid, None)
        self.fusions = {p: r for p, r in self.fusions.items() if cid not in p and r != cid}
        self.equips.pop(cid, None)
        for monsters in self.equips.values():
            monsters.discard(cid)
        self.rituals = {r: rec for r, rec in self.rituals.items() if cid not in rec}
        self.ritual_requirements.pop(cid, None)
        for ritual, slots in list(self.ritual_requirements.items()):
            if ritual not in self.rituals or any(req.get("card") == cid for req in slots):
                self.ritual_requirements.pop(ritual, None)
        for pools in self.pools:
            for pool in pools.values():
                pool.pop(cid, None)

    def set_notes(self, cid: int, text: str):
        if text.strip():
            self.notes[cid] = text
        else:
            self.notes.pop(cid, None)

    def revert_card(self, cid: int):
        """Back to the disc's card, or an added card back to its base as the
        mod has it; its notes stay, as they are the modder's."""
        if cid in self.added:
            self.cards[cid] = self.cards[self.added[cid].base].copy(id=cid)
            self.passwords.pop(cid, None)
        elif cid in self.retail.cards:
            self.cards[cid] = self.retail.cards[cid].copy()
            self.card_extra.pop(cid, None)
            self.passwords.pop(cid, None)

    def card_changed(self, cid: int) -> bool:
        if cid in self.added:
            return True
        return (not self.cards[cid].same(self.retail.cards[cid]) or bool(self.card_extra.get(cid))
                or self.password_changed(cid))

    # --- tables ------------------------------------------------------------

    @staticmethod
    def pair(a: int, b: int):
        return (a, b) if a <= b else (b, a)

    def set_fusion(self, a: int, b: int, result):
        """A result, or none. A pair with an added card fuses as its bases
        when no rule names it, so taking its fusion away keeps a rule that
        forbids it (0), as {"result": null} does in the game."""
        pair = self.pair(a, b)
        if result:
            self.fusions[pair] = result
        elif a in self.added or b in self.added:
            self.fusions[pair] = 0
        else:
            self.fusions.pop(pair, None)

    def revert_fusion(self, pair):
        """Back to the disc's: an added card's pair to no rule at all."""
        retail = self.retail.fusions.get(pair)
        if retail:
            self.fusions[pair] = retail
        else:
            self.fusions.pop(pair, None)

    def fusion_status(self, pair) -> str:
        retail = self.retail.fusions.get(pair)
        now = self.fusions.get(pair)
        if retail == now:
            return "glitch" if pair in self.retail.glitch_fusions else ""
        if not now:
            return "removed"
        if retail is None:
            return "added"
        return "changed"

    def ritual_status(self, ritual: int) -> str:
        """The recipe against the disc's: "" the same, or "added", "removed" or
        "changed"."""
        now, retail = self.rituals.get(ritual), self.retail.rituals.get(ritual)
        if ritual in self.ritual_requirements:
            return "added" if retail is None else "changed"
        return "" if now == retail else "added" if retail is None else "removed" if now is None else "changed"

    def revert_ritual(self, ritual: int):
        self.ritual_requirements.pop(ritual, None)
        if ritual in self.retail.rituals:
            self.rituals[ritual] = self.retail.rituals[ritual]
        else:
            self.rituals.pop(ritual, None)

    def revert_pool(self, d: int, pool: str):
        """A duelist's pool ("deck", "pow", "bcd", "tec") back to the disc's
        weights (a fixed deck is fixed_decks.py's, and stays)."""
        self.pools[d][pool] = dict(self.retail.pools[d][pool])

    def monsters(self):
        return [cid for cid, card in self.cards.items() if card.is_monster()]

    def equip_retail(self, equip: int, monster: int) -> bool:
        """What the disc's table says, by the base ids (duel_card_checks.c)."""
        return self.base_of(monster) in self.retail.equips.get(self.base_of(equip), ())

    def equip_baseline(self, equip: int) -> set:
        """What the equip fits with no mod: the disc's list, copies as their
        bases."""
        return {m for m in self.cards if self.equip_retail(equip, m)}

    def equip_cards(self):
        return sorted(cid for cid, card in self.cards.items() if card.type == 23)

    def ritual_cards(self):
        return sorted(cid for cid, card in self.cards.items() if cid <= CARD_COUNT and card.type == 22)

    def clone(self) -> "Project":
        return copy.deepcopy(self)
