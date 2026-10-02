"""What two or more mods change in common, and which of them the game uses:
the same check the Mods window makes (src/pc/mods/overlap.c), line for line
and in the same order, so the editor can say where the mod being edited
meets the other mods the player has installed.

Every mod's manifest becomes claims, one for each thing it sets (a card, a
fusion pair, a pool, a limit, an image...): the thing's key, how the mod
sets it (it sets it, adds to it, defines it) and what it sets. Claims of two
or more mods on one key are an overlap, and the load order decides how it
comes out, the way the game's reader of that key decides it. Some keys reach
keys they do not name ("wide" claims): "all", "stats", a life-point start,
"replace" and a new star's first declaration.

Every key is read as the type its reader takes, a list or an object, and
anything else as nothing, as the readers note it and leave it out; numbers,
booleans and strings as json.c reads them (Json_Number, Json_Bool).

tests/pc/mod_overlaps holds three mods and the lines both this module and
the C engine must find (tests/test_overlaps.py, tests/pc/mods_overlap_test.c).
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

KINDS = ["Disc data", "Sounds", "Texture images", "Cards", "Fusions", "Equips", "Rituals", "Drops and decks",
         "Starter decks", "Passwords", "Card packs", "Guardian Stars", "Limits", "Terrain bonuses", "Attack traps",
         "Duelists", "Text", "Fonts", "Title screen and menus", "Code hooks", "Game events"]
(DATA, AUDIO, TEXTURES, CARDS, FUSIONS, EQUIPS, RITUALS, POOLS, STARTER, PASSWORDS, PACKS, STARS, LIMITS, TERRAIN,
 TRAPS, DUELISTS, TEXT, FONT, TITLE, HOOKS, EVENTS) = range(len(KINDS))
INFO, WARNING = 0, 1

SET, ADD, FIXED, BASE, CHAIN, EVENT, FIRST = range(7)
CARD_COUNT = 722
ATTACK_TRAP_FIRST, ATTACK_TRAPS = 681, 6
ALL = ("all",)
DEFAULT_EQUIP_BONUS = ("default",)
STAR_RETAIL = ["", "Mars", "Jupiter", "Saturn", "Uranus", "Pluto", "Neptune", "Mercury", "Sun", "Moon", "Venus"]
TERRAINS = ["", "Forest", "Wasteland", "Mountain", "Sogen", "Umi", "Yami"]
TERRAIN_ALIASES = {"meadow": 4, "sea": 5, "dark": 6}
POOL_WORDS = ["deck", "POW drops", "B/C/D drops", "TEC drops"]
TYPE_NAMES = ["Dragon", "Spellcaster", "Zombie", "Warrior", "Beast-Warrior", "Beast", "Winged Beast", "Fiend",
              "Fairy", "Insect", "Dinosaur", "Reptile", "Fish", "Sea Serpent", "Machine", "Thunder", "Aqua", "Pyro",
              "Rock", "Plant", "Magic", "Trap", "Ritual", "Equip"]
ATTRIBUTE_NAMES = ["Light", "Dark", "Earth", "Water", "Fire", "Wind"]
CARD_RESET_KEYS = ("name", "description", "password", "art", "thumbnail", "title", "field_art", "fusion_groups")
ENTRY_NAMES = ["new_game", "load", "duel", "trade", "options", "campaign", "free_duel", "build_deck", "library",
               "password", "save"]
NO_BONUS = object()
C_SPACE = " \t\n\v\f\r"


def letters(text) -> str:
    """Letters and digits only, lowercased: how the readers compare names."""
    return "".join(c.lower() for c in str(text) if c.isascii() and c.isalnum())


def canonical(value) -> str:
    """What a value says, its own name aside (members' names and order count)."""
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)


def _list(value) -> list:
    """A list where the game's readers take only a list; anything else (they
    note it and leave it out) is nothing."""
    return value if isinstance(value, list) else []


def _obj(value) -> dict:
    """The same for an object."""
    return value if isinstance(value, dict) else {}


def _int(value) -> bool:
    """A JSON number (json.c: whole; a boolean is not one)."""
    return isinstance(value, int) and not isinstance(value, bool)


def is_digits(text) -> bool:
    return isinstance(text, str) and text != "" and text.isascii() and text.isdigit()


def _strtol(text: str, base: int):
    """C's strtol over `text`: (value, the rest unread); value 0 and all of
    `text` left when no digit is read. 32-bit longs, as the game's."""
    i, n = 0, len(text)
    while i < n and text[i] in C_SPACE:
        i += 1
    negative = False
    if i < n and text[i] in "+-":
        negative = text[i] == "-"
        i += 1
    digits = "0123456789abcdefABCDEF"[:10 if base == 10 else 22]
    if base == 16 and text[i:i + 2] in ("0x", "0X") and i + 2 < n and text[i + 2] in digits:
        i += 2
    start, value = i, 0
    while i < n and text[i] in digits:
        value = value * base + int(text[i], 16)
        i += 1
    if i == start:
        return 0, text
    value = -value if negative else value
    return max(-2 ** 31, min(2 ** 31 - 1, value)), text[i:]


def _json_number(value, default):
    """json.c Json_Number: a number, a boolean as 0 or 1, and a string that
    holds one, hexadecimal with its "0x" (spaces and a sign allowed)."""
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        stripped = value.lstrip(C_SPACE)
        digits = stripped[1:] if stripped[:1] in "+-" else stripped
        number, rest = _strtol(value, 16 if digits[:2] in ("0x", "0X") else 10)
        if rest != value and not rest.strip(C_SPACE) and -2 ** 31 < number < 2 ** 31 - 1:
            return number
    return default


def _json_bool(value, default=False) -> bool:
    """json.c Json_Bool: a boolean, or a number that is not 0."""
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    return default


def _json_string(value):
    return value if isinstance(value, str) else None


class _Refused(ValueError):
    pass


def _whole(text):
    """A JSON number json.c takes: whole ("1e3" is), within a 32-bit long."""
    number = float(text)
    if number != int(number):
        raise _Refused(text)
    return _in_long(int(number))


def _in_long(number):
    number = int(number)
    if not -2 ** 31 <= number <= 2 ** 31 - 1:
        raise _Refused(number)
    return number


def _depth(value, depth=0) -> int:
    if isinstance(value, (list, dict)):
        children = value.values() if isinstance(value, dict) else value
        return max([depth + 1] + [_depth(c, depth + 1) for c in children])
    return depth


def parse(text: str):
    """A manifest as json.c reads it, or None: whole numbers within a long,
    64 levels deep at most."""
    try:
        value = json.loads(text, parse_float=_whole, parse_int=_in_long)
    except (ValueError, RecursionError):
        return None
    return value if _depth(value) <= 64 else None


_cache = {}


def _read_json(path: Path):
    """A file as parse() reads it; kept by its size and time, as a check
    reads the same mods' files again on every refresh and changes none."""
    try:
        stat = os.stat(path)
    except OSError:
        return None
    key = (stat.st_mtime_ns, stat.st_size)
    held = _cache.get(str(path))
    if held is not None and held[0] == key:
        return held[1]
    try:
        value = parse(Path(path).read_bytes().decode("utf-8-sig"))
    except (OSError, UnicodeDecodeError):
        value = None
    _cache[str(path)] = (key, value)
    return value


def _contained(relative) -> bool:
    """paths.c Paths_Contained: a path inside the mod."""
    if not isinstance(relative, str) or not relative or relative[0] in "/\\" or relative[1:2] == ":":
        return False
    if "\\" in relative:
        return False
    return all(part not in ("", ".", "..") for part in relative.split("/"))


@dataclass
class Mod:
    id: str
    name: str
    manifest: dict
    directory: Path | None = None


@dataclass
class Claim:
    kind: int
    mod: int
    key: object
    mode: int
    value: object
    src: object = None
    seq: int = 0
    label: str | None = None
    wide: object = None          # a match(key) for a wide claim
    via_wide: bool = False
    aimed: bool = False
    resets: bool = False
    via: str | None = None       # the wide key's own name, for the line
    lo: int = 0
    hi: int = 0


@dataclass
class Overlap:
    kind: int
    claims: list
    severity: int = WARNING
    outcome: str = "later"
    winner: int = -1
    other: int = -1
    label: str = ""
    text: str = ""
    mods: list = field(default_factory=list)


class Source:
    """What the check cannot know from manifests: the cards and opponents the
    game has, and a mod's settings. A method left None is unknown, as an
    empty member of overlap.c's ModsOverlapSource: cards are then matched by
    number and by letters, opponents by name."""
    card = None          # card(text, number) -> id, 0 or less for none (text None: by number)
    card_name = None     # card_name(id) -> name or None
    card_info = None     # card_info(id) -> (base, type, attribute) or None
    duelist = None       # duelist(text) -> id, -1 for none

    def setting(self, mod: Mod, key: str):
        """The mod's setting `key`, or None when it declares none."""
        for spec in _list(mod.manifest.get("settings")):
            if isinstance(spec, dict) and spec.get("key") == key:
                return _json_number(spec.get("default"), 0)
        return None


class _Check:
    def __init__(self, mods, source):
        self.mods = mods
        self.source = source or Source()
        self.claims = []
        self.seq = 0
        self.memo = {}
        self.star_names = {}
        self.star_declared = set()
        self.defined = []
        self.declared = set()
        for w, mod in enumerate(mods):
            for key in ("after", "requires"):
                for v in _list(mod.manifest.get(key)):
                    target = v if isinstance(v, str) else _json_string(v.get("id")) or "" if isinstance(v, dict) else ""
                    for o, other in enumerate(mods):
                        if other.id == target:
                            self.declared.add((w, o))

    # --- tools ---------------------------------------------------------------

    def member(self, mod, key):
        return self.mods[mod].manifest.get(key)

    def having(self, key) -> int:
        return sum(1 for m in self.mods if key in m.manifest)

    def claim(self, kind, mod, key, mode, value, src=None, label=None) -> Claim:
        self.seq += 1
        c = Claim(kind, mod, key, mode, value, src, self.seq, label)
        self.claims.append(c)
        return c

    def mod_file(self, mod, relative):
        directory = self.mods[mod].directory
        if directory is None or not _contained(relative):
            return None
        return _read_json(Path(directory) / relative)

    def folder_names(self, mod, folder) -> list:
        directory = self.mods[mod].directory
        if directory is None:
            return []
        try:
            names = os.listdir(Path(directory) / folder)
        except OSError:
            return []
        return sorted((n[:-5] for n in names if n.endswith(".json") and len(n) > 5),
                      key=lambda n: n.encode("utf-8", "surrogateescape"))

    def setting(self, mod, key) -> int:
        value = self.source.setting(self.mods[mod], key) if self.source.setting else None
        return -1 if value is None else value

    def switched_on(self, mod, entry) -> bool:
        """mods.c entry_used: "setting" (and "value") of a text file, a
        fusion, equip or ritual entry."""
        key = _json_string(entry.get("setting")) if isinstance(entry, dict) else None
        if not key:
            return True
        value = self.setting(mod, key)
        if value < 0:
            return True
        if "value" in entry:
            return value == entry["value"] if _int(entry["value"]) else True
        return value != 0

    def card_text(self, text):
        name = letters(text)
        if not name:
            return None
        if name not in self.memo:
            if self.source.card:
                self.memo[name] = self.source.card(text, 0) or 0
            else:
                self.memo[name] = int(text) if is_digits(text) else 0
        cid = self.memo[name]
        return cid if cid > 0 else ("text", name)

    def card_key(self, value):
        if _int(value):
            cid = self.source.card(None, value) if self.source.card else value
            return cid if cid and cid > 0 else value if 0 < value < 2 ** 40 else None
        if isinstance(value, str):
            return self.card_text(value)
        return None

    def card_info(self, key):
        """(base, type, attribute) of a card key; -1 for what is unknown."""
        if not isinstance(key, int):
            return 0, -1, -1
        if self.source.card_info:
            info = self.source.card_info(key)
            if info:
                return info
        return key, -1, -1

    def card_words(self, value) -> str:
        number = value if _int(value) else 0
        text = _json_string(value)
        if self.source.card:
            cid = self.source.card(text, number)
        else:
            cid = number if number > 0 else 0
        name = self.source.card_name(cid) if cid and cid > 0 and self.source.card_name else None
        if name:
            return f"'{name}'"
        if text is not None:
            return f"'{text}'"
        return f"#{number}"

    def duelist_key(self, name):
        name = name if isinstance(name, str) else ""
        if letters(name) == "all":
            return ALL
        did = self.source.duelist(name) if self.source.duelist else -1
        if did < 0 and is_digits(name):
            did = int(name)
        return did if did >= 0 else ("text", letters(name))

    def known_duelist(self, who):
        """None when the game can say there is no such opponent."""
        if self.source.duelist and isinstance(who, tuple) and who != ALL:
            return None
        return who

    # --- the kinds -----------------------------------------------------------

    def read_data(self, mod):
        for entry in _list(self.member(mod, "data")):
            entry = _obj(entry)
            file, lba = _json_string(entry.get("file")), _json_number(entry.get("lba"), -1)
            replace = "replace" in entry
            if file:
                name = file.lstrip("\\").split(";")[0]
                self.claim(DATA, mod, ("file", name), SET if replace else ADD, ("own", mod), entry)
            elif lba >= 0:
                sectors = _json_number(entry.get("sectors"), 1)
                lo = hi = -1
                if replace:
                    lo, hi = lba, lba + (sectors if sectors > 0 else 1) - 1
                for p in _list(entry.get("patch")):
                    at, length = _json_number(_obj(p).get("at"), 0), _patch_length(p)
                    if at < 0:
                        continue
                    first, last = lba + at // 2048, lba + (at + (length or 1) - 1) // 2048
                    if lo < 0 or first < lo:
                        lo = first
                    if last > hi:
                        hi = last
                if lo < 0:
                    lo = hi = lba
                c = self.claim(DATA, mod, "raw", SET if replace else ADD, ("own", mod), entry)
                c.lo, c.hi = lo, hi

    def sector_runs(self):
        raw = sorted((c for c in self.claims if c.kind == DATA and c.key == "raw"), key=lambda c: (c.lo, c.seq))
        start = 0
        while start < len(raw):
            end, hi = start + 1, raw[start].hi
            while end < len(raw) and raw[end].lo <= hi:
                hi = max(hi, raw[end].hi)
                end += 1
            label = f"Sector {hi}" if raw[start].lo == hi else f"Sectors {raw[start].lo}-{hi}"
            for c in raw[start:end]:
                c.key, c.label = ("raw", raw[start].lo), label
            start = end

    def read_audio(self, mod):
        audio = _obj(self.member(mod, "audio"))
        for k, kind in enumerate(("music", "xa", "sfx")):
            for name, value in _obj(audio.get(kind)).items():
                number = _audio_id(name)
                if number >= 0:
                    self.claim(AUDIO, mod, (k, number), SET, ("own", mod), name)

    def read_textures(self, mod):
        folder = _json_string(self.member(mod, "textures"))
        if folder is None:
            return
        for entry in _list(self.mod_file(mod, f"{folder}/manifest.json")):
            entry = _obj(entry)
            archive, file = _json_string(entry.get("archive")), _json_string(entry.get("file"))
            offset, words = _json_number(entry.get("offset"), -1), _json_number(entry.get("words"), 0)
            rows, bpp = _json_number(entry.get("rows"), 0), _json_number(entry.get("bpp"), 0)
            stride, clut = _json_number(entry.get("stride"), words), _json_number(entry.get("clut_entries"), 0)
            if archive is None or file is None or not _contained(file) or offset < 0 or not 1 <= words <= 1024 \
                    or not 1 <= rows <= 512 or bpp not in (4, 8, 16) or stride < 1:
                continue
            setting = _json_string(entry.get("setting"))
            if "setting" in entry and setting and self.source.setting and self.setting(mod, setting) == 0:
                continue
            key = (archive, offset, words, rows, stride, bpp, _json_number(entry.get("clut_offset"), 0) if clut else 0)
            self.claim(TEXTURES, mod, key, SET, ("own", mod), entry)

    def read_cards(self, mod):
        for entry in _list(self.member(mod, "cards")):
            if not isinstance(entry, dict) or "replace" not in entry or _notes_only(entry):
                continue
            replaced = entry["replace"]
            text = _json_string(replaced)
            if text is not None and not (text[:1] and text[:1] in "0123456789"):
                if ":" in text:
                    continue   # an added card's identity: not the disc's
                key = self.card_text(text)
            else:
                number = _json_number(replaced, 0)
                key = number if 1 <= number <= CARD_COUNT else None
            if key is not None and (isinstance(key, tuple) or key <= CARD_COUNT):
                self.claim(CARDS, mod, key, SET, canonical(entry), entry)

    def read_fusions(self, mod):
        for rule in _list(self.member(mod, "fusions")):
            if not self.switched_on(mod, rule):
                continue
            rule = _obj(rule)
            if "remove" in rule:
                key = self.card_key(rule["remove"])
                if key is not None:
                    self.claim(FUSIONS, mod, ("remove", key), ADD, 0, rule)
                continue
            with_ = rule.get("with")
            pair = list(with_.values()) if isinstance(with_, dict) else with_ if isinstance(with_, list) else []
            if len(pair) != 2 or "result" not in rule:
                continue
            a, b = self.card_key(pair[0]), self.card_key(pair[1])
            if a is None or b is None:
                continue
            key = ("pair",) + tuple(sorted((a, b), key=repr))
            self.claim(FUSIONS, mod, key, SET, self.card_key(rule["result"]) or 0, rule)

    def read_equips(self, mod):
        for entry in _list(self.member(mod, "equips")):
            key = self.card_key(_obj(entry).get("card"))
            if key is not None and isinstance(entry, dict) and self.switched_on(mod, entry):
                self.claim(EQUIPS, mod, key, SET, canonical(entry), entry)
        if "equip_bonus_default" in self.mods[mod].manifest:
            bonus = self.member(mod, "equip_bonus_default")
            self.claim(EQUIPS, mod, DEFAULT_EQUIP_BONUS, SET, canonical(bonus), bonus)

    def read_rituals(self, mod):
        for entry in _list(self.member(mod, "rituals")):
            e = _obj(entry)
            key = self.card_key(e.get("card"))
            if key is not None and self.switched_on(mod, entry):
                value = (canonical(e["tributes"]) if "tributes" in e else "~",
                         canonical(e["result"]) if "result" in e else "~")
                self.claim(RITUALS, mod, key, SET, value, e)

    # duelists, then the pools that may name them

    def duelist_entry(self, mod, did, entry):
        if not isinstance(entry, dict):
            return
        copy = _json_string(entry.get("copy"))
        target = 0
        if "replace" in entry:
            who = _json_string(entry["replace"])
            if who is None:
                return
            number = int(who) if is_digits(who) else -1
            target = self.duelist_key(who)
            if target == ALL or number == 0 or number >= 40 or (isinstance(target, int) and (target == 0 or target >= 40)) \
                    or (self.source.duelist and isinstance(target, tuple)):
                return
            self.claim(DUELISTS, mod, ("replace", target), SET, ("own", mod), entry, f"Duelist '{who[:80]}' replaced")
        elif not copy:
            return
        if did:
            self.defined.append((mod, did, target))
        slot = entry.get("slot")
        if "slot" in entry and "replace" not in entry and _int(slot) and 40 <= slot < 128:
            self.claim(DUELISTS, mod, ("slot", slot), FIRST, ("own", mod), entry, f"Free Duel slot {slot}")

    def read_duelists(self, mod):
        for name in self.folder_names(mod, "duelists"):
            self.duelist_entry(mod, name, self.mod_file(mod, f"duelists/{name}.json"))
        listed = self.member(mod, "duelists")
        if isinstance(listed, str):
            listed = self.mod_file(mod, listed)
        for entry in _list(listed):
            self.duelist_entry(mod, _json_string(_obj(entry).get("id")), entry)

    def pool_claim(self, mod, duelist, who, pool, entry):
        e = _obj(entry)
        fixed_value = e.get("fixed") if pool == 0 else None
        if pool == 0 and "fixed" in e and not isinstance(fixed_value, (bool, int)):
            return
        fixed = _json_bool(fixed_value)
        if fixed and sum(v for k, v in e.items() if k != "fixed" and _int(v)) != 40:
            return
        mode = FIXED if fixed else SET if _json_bool(e.get("replace")) else ADD
        if who == ALL:
            label = f"Every opponent's {POOL_WORDS[pool]}"
        else:
            label = f"{duelist[:80]}'s {POOL_WORDS[pool]}"
        c = self.claim(POOLS, mod, (who, pool), mode, canonical(entry), entry, label)
        c.resets = mode == SET
        if who == ALL:
            c.wide, c.via = (lambda key, pool=pool: key[1] == pool), "all"

    def pool_table(self, mod, table, decks):
        for name, entry in _obj(table).items():
            who = self.known_duelist(self.duelist_key(name))
            if who is None:
                continue
            if decks:
                self.pool_claim(mod, name, who, 0, entry)
                continue
            for pool_name, pool in _obj(entry).items():
                which = _pool_named(pool_name)
                if which > 0:
                    self.pool_claim(mod, name, who, which, pool)

    def pool_file_duelist(self, mod, name):
        for owner, did, replaces in self.defined:
            if owner == mod and did == name:
                return replaces if replaces else ("own", f"{self.mods[mod].id}:{name}")
        return self.known_duelist(self.duelist_key(name))

    def read_pools(self, mod):
        for decks, key in ((0, "drops"), (1, "decks")):
            table = self.member(mod, key)
            if isinstance(table, str):
                table = self.mod_file(mod, table)
            self.pool_table(mod, table, decks)
            for name in self.folder_names(mod, key):
                who = self.pool_file_duelist(mod, name)
                if who is None:
                    continue
                root = self.mod_file(mod, f"{key}/{name}.json")
                if root is None:
                    continue
                if decks:
                    self.pool_claim(mod, name, who, 0, root)
                else:
                    for pool_name, pool in _obj(root).items():
                        if _pool_named(pool_name) > 0:
                            self.pool_claim(mod, name, who, _pool_named(pool_name), pool)

    def read_passwords(self, mod):
        for name, entry in _obj(self.member(mod, "passwords")).items():
            is_all = letters(name) == "all"
            card = ALL if is_all else self.card_text(name)
            if card is None or not isinstance(entry, dict) or (isinstance(card, int) and card > CARD_COUNT):
                continue
            for f, fields in enumerate((("password",), ("starchips", "starchips_percent"))):
                field_name = next((k for k in fields if k in entry), None)
                if field_name is None:
                    continue
                if is_all:
                    label = f"Every card's {'price' if f else 'password'}"
                else:
                    shown = self.source.card_name(card) if isinstance(card, int) and self.source.card_name else None
                    label = f"{'Price' if f else 'Password'} of '{shown[:100] if shown else name[:80]}'"
                c = self.claim(PASSWORDS, mod, (card, f + 1), SET, canonical([field_name, entry[field_name]]),
                               entry, label)
                if is_all:
                    c.wide, c.via = (lambda key, f=f: key[1] == f + 1), "all"

    def pack_rules(self, mod, rules):
        if not isinstance(rules, dict):
            return
        value = canonical([[k, v] for k, v in rules.items() if k != "shops"])
        self.claim(PACKS, mod, "rules", SET, value, rules, "The pack shop's rules")
        for shop in _list(rules.get("shops")):
            sid = _json_string(_obj(shop).get("id")) or ""
            if not isinstance(shop, dict) or not sid:
                continue
            self.claim(PACKS, mod, ("shop", sid), SET, canonical(shop), shop, f"Pack shop '{sid[:60]}'")

    def read_packs(self, mod):
        packs = self.member(mod, "packs")
        if isinstance(packs, str):
            found = self.mod_file(mod, packs)
            if isinstance(found, dict):
                self.pack_rules(mod, found.get("pack_shop"))
        self.pack_rules(mod, self.member(mod, "pack_shop"))

    def learn_star_names(self):
        for i in range(1, 11):
            self.star_names.setdefault(letters(STAR_RETAIL[i]), i)
        for mod in self.mods:
            for s in _list(_obj(mod.manifest.get("guardian_stars")).get("stars")):
                s = _obj(s)
                sid = _json_number(s.get("id"), -1)
                name = s.get("name")
                names = [name] if isinstance(name, str) else list(name.values()) if isinstance(name, dict) else []
                for n in names:
                    if letters(n if isinstance(n, str) else ""):
                        self.star_names.setdefault(letters(n), sid)

    def star_of(self, value) -> int:
        if _int(value):
            return value
        if not isinstance(value, str):
            return -1
        if is_digits(value):
            return int(value)
        return self.star_names.get(letters(value), -1)

    def star_pair(self, mod, a, d, bonus, src):
        if 0 <= a <= 15 and 0 <= d <= 15:
            self.claim(STARS, mod, ("pair", a, d), SET, bonus, src)

    def read_stars(self, mod):
        section = self.member(mod, "guardian_stars")
        if not isinstance(section, dict):
            return
        bonus = 500
        reset = _json_bool(section.get("replace"))
        if reset:
            c = self.claim(STARS, mod, ("reset",), SET, 0, section.get("replace"))
            c.wide, c.via, c.resets = (lambda key: key[0] == "pair"), "replace", True
        value = section.get("default_bonus")
        if _int(value):
            bonus = value
            for a in range(1, 11) if not reset else ():
                d = a % 6 + 1 if a <= 6 else (a - 7 + 1) % 4 + 7
                self.star_pair(mod, a, d, bonus, value)
                self.star_pair(mod, d, a, -bonus, value)
        if "choice" in section:
            choice = section["choice"]
            self.claim(STARS, mod, ("scalar", 2), SET, letters(choice) if isinstance(choice, str) else "", choice)
        for s in _list(section.get("stars")):
            sid = _json_number(_obj(s).get("id"), -1)
            if not isinstance(s, dict) or "id" not in s or not 1 <= sid <= 15:
                continue
            if sid > 10 and sid not in self.star_declared:
                c = self.claim(STARS, mod, ("declared", sid), SET, 0, s,
                               f"Star {sid} declared (every matchup of it at 0)")
                c.wide = lambda key, sid=sid: key[0] == "pair" and (key[1] == sid or key[2] == sid)
                c.via, c.resets = "stars", True
            self.star_declared.add(sid)
        for s in _list(section.get("stars")):
            sid = _json_number(_obj(s).get("id"), -1)
            if not isinstance(s, dict) or "id" not in s or not 1 <= sid <= 15:
                continue
            for f, name in enumerate(("name", "icon", "palette")):
                if name in s:
                    self.claim(STARS, mod, ("star", sid, f + 1), SET,
                               ("own", mod) if f == 1 else canonical(s[name]), s[name])
            for t in _list(s.get("beats")):
                other = self.star_of(t)
                self.star_pair(mod, sid, other, bonus, t)
                self.star_pair(mod, other, sid, -bonus, t)
        for m in _list(section.get("matchups")):
            if not isinstance(m, dict):
                continue
            a, d = self.star_of(m.get("attacker")), self.star_of(m.get("defender"))
            points = _json_number(m["bonus"], bonus) if "bonus" in m else bonus
            self.star_pair(mod, a, d, points, m)
            if _json_bool(m.get("mirror")):
                self.star_pair(mod, d, a, -points, m)

    def limit_claim(self, mod, path, key, value, src) -> Claim:
        return self.claim(LIMITS, mod, key if key is not None else path, SET, value, src, f"Limit {path}")

    def limit_both(self, mod, path, key, one, two, via, value):
        c = self.limit_claim(mod, path, key, canonical(value), value)
        c.wide, c.via = (lambda k, one=one, two=two: k == one or k == two), via

    def read_limits(self, mod):
        for name, m in _obj(self.member(mod, "limits")).items():
            if name == "stats":
                self.limit_both(mod, "stats", "stats", "attack", "defense", "stats", m)
            elif name == "life_points" and not isinstance(m, dict):
                self.limit_both(mod, "life_points", "life_points.start", "life_points.player",
                                "life_points.opponent", "life_points", m)
            elif name == "life_points":
                for k, v in m.items():
                    path = f"life_points.{k[:60]}"
                    if k == "start":
                        self.limit_both(mod, path, path, "life_points.player", "life_points.opponent",
                                        "life_points.start", v)
                    elif k == "duelists":
                        for d, dv in _obj(v).items():
                            who = self.duelist_key(d)
                            if who == ALL:
                                continue
                            key, label = ("lp", who), f"life_points.duelists.{d[:60]}"
                            if isinstance(dv, dict):
                                for s, sv in dv.items():
                                    if s in ("player", "opponent"):
                                        self.limit_claim(mod, f"{label}.{s}", key + (s,), canonical(sv), sv)
                            else:
                                self.limit_both(mod, label, key, key + ("player",), key + ("opponent",), d, dv)
                    elif isinstance(v, dict):
                        for s, sv in v.items():
                            self.limit_claim(mod, f"{path}.{s[:60]}", None, canonical(sv), sv)
                    else:
                        self.limit_claim(mod, path, None, canonical(v), v)
            elif isinstance(m, dict):
                for k, v in m.items():
                    self.limit_claim(mod, f"{name[:60]}.{k[:60]}", None, canonical(v), v)
            else:
                self.limit_claim(mod, name, None, canonical(m), m)
        overflow = self.member(mod, "chest_overflow")
        if isinstance(overflow, dict):
            limit, starchips = overflow.get("limit"), overflow.get("starchips")
            self.limit_claim(mod, "chest_overflow.limit" if "limit" in overflow else
                             "chest_overflow.limit (250, left out)", "chest",
                             canonical(limit) if "limit" in overflow else canonical(250), overflow)
            self.limit_claim(mod, "chest_overflow.starchips" if "starchips" in overflow else
                             "chest_overflow.starchips (0, left out)", "chest_overflow.starchips",
                             canonical(starchips) if "starchips" in overflow else canonical(0), overflow)

    def read_terrain(self, mod):
        table = self.member(mod, "terrain_bonus")
        if not isinstance(table, dict):
            return
        if _json_bool(table.get("replace")):
            c = self.claim(TERRAIN, mod, ("reset",), SET, 0, table.get("replace"), "Every terrain bonus (\"replace\")")
            c.wide, c.via, c.resets = (lambda key: key[0] == "t"), "replace", True
        for name, types in table.items():
            terrain = _terrain_named(name)
            if not 1 <= terrain <= 6:
                continue
            for type_name, value in _obj(types).items():
                self.claim(TERRAIN, mod, ("t", terrain, letters(type_name)), SET, canonical(value), value,
                           f"{TERRAINS[terrain]} bonus of {type_name[:60]}")

    def read_traps(self, mod):
        for name, value in _obj(self.member(mod, "trap_thresholds")).items():
            key = self.card_text(name)
            if key is None:
                continue
            base = self.card_info(key)[0]
            if isinstance(key, int) and not ATTACK_TRAP_FIRST <= base < ATTACK_TRAP_FIRST + ATTACK_TRAPS:
                continue
            self.claim(TRAPS, mod, base if isinstance(key, int) else key, SET, canonical(value), name)

    def text_file(self, mod, path):
        try:
            data = Path(path).read_bytes()
        except OSError:
            return
        opened, value = [], []
        for line in data.split(b"\n"):
            if line.endswith(b"\r"):
                line = line[:-1]
            if line[:1] == b"[" or line[:2] == b"{:":
                for c in opened:
                    c.value = tuple(value)
                opened, value = [], []
                close = line.find(b"]") if line[:1] == b"[" else -1
                word = line[1:close].decode("latin-1") if close > 0 else ""
                while word and len(opened) < 64:
                    number, rest = _strtoul16(word)
                    if rest == word:
                        break
                    word = rest.lstrip(" ")
                    if number > 0xFFFF:
                        continue
                    opened.append(self.claim(TEXT, mod, number, SET, ()))
            elif opened and line and line[:1] != b"#":
                value.append(line)
        for c in opened:
            c.value = tuple(value)

    def read_text(self, mod):
        text = self.member(mod, "text")
        directory = self.mods[mod].directory
        for one in text if isinstance(text, list) else [text] if text is not None else []:
            name = _json_string(one) if isinstance(one, str) else _json_string(_obj(one).get("file"))
            if name and directory is not None and _contained(name) and self.switched_on(mod, one):
                self.text_file(mod, Path(directory) / name)

    def title_tree(self, mod, path, key, value, mode, aimed=False):
        if not isinstance(value, dict):
            c = self.claim(TITLE, mod, key, mode, canonical(value), value, path)
            c.aimed = aimed
            return
        for name, inner in value.items():
            self.title_tree(mod, f"{path}.{name[:60]}", f"{key}.{name[:60]}", inner, mode, aimed)

    def title_entries(self, mod, path, entries):
        for name, value in _obj(entries).items():
            i = _entry_index(name)
            if i >= 0:
                self.title_tree(mod, f"{path}.{name[:60]}", f"entries.{i}", value, SET)

    def read_title(self, mod):
        own = self.mods[mod].id
        for name, value in _obj(self.member(mod, "title")).items():
            path = f"title.{name[:60]}"
            if name == "text":
                if isinstance(value, list):
                    self.claim(TITLE, mod, path, ADD, 0, value, "title.text (lines)")
            elif name == "entries":
                self.title_entries(mod, path, value)
            else:
                self.title_tree(mod, path, "spacing" if name == "spacing" else path, value, SET)
        for name, value in _obj(self.member(mod, "menu")).items():
            if name == "buttons":
                for button in _list(value):
                    bid = _json_string(_obj(button).get("id")) or ""
                    if not isinstance(button, dict) or _entry_index(bid) >= 0 or not bid:
                        continue
                    theirs = ":" in bid and not bid.startswith(own + ":")
                    path = f"menu.buttons.{bid[:100]}" if ":" in bid else f"menu.buttons.{own[:60]}:{bid[:60]}"
                    for k, v in button.items():
                        if k != "id":
                            leaf = f"{path}.{k[:60]}"
                            self.title_tree(mod, leaf, leaf, v, SET if theirs else BASE, theirs)
            elif name == "order":
                if isinstance(value, list):
                    self.title_tree(mod, "menu.order", "menu.order.first", value, SET)
                else:
                    for k, v in _obj(value).items():
                        if k in ("first", "second"):
                            self.title_tree(mod, f"menu.order.{k}", f"menu.order.{k}", v, SET)
            elif name == "entries":
                self.title_entries(mod, "menu.entries", value)
            else:
                path = f"menu.{name[:60]}"
                self.title_tree(mod, path, "spacing" if name == "spacing" else path, value, SET)

    # --- grouping ------------------------------------------------------------

    def run(self, involving=None) -> list:
        if len(self.mods) < 2:
            return []
        if self.having("guardian_stars") >= 2:
            self.learn_star_names()
        for mod in range(len(self.mods)):
            self.read_duelists(mod)
        for mod in range(len(self.mods)):
            if self.having("data") >= 2:
                self.read_data(mod)
            if self.having("audio") >= 2:
                self.read_audio(mod)
            if self.having("textures") >= 2:
                self.read_textures(mod)
            if self.having("cards") >= 2:
                self.read_cards(mod)
            if self.having("fusions") >= 2:
                self.read_fusions(mod)
            if self.having("equips") + self.having("equip_bonus_default") >= 2:
                self.read_equips(mod)
            if self.having("rituals") >= 2:
                self.read_rituals(mod)
            self.read_pools(mod)
            if self.having("starter") >= 2 and "starter" in self.mods[mod].manifest:
                self.claim(STARTER, mod, 0, ADD, 0)
            if self.having("passwords") >= 2:
                self.read_passwords(mod)
            if self.having("packs") + self.having("pack_shop") >= 2:
                self.read_packs(mod)
            if self.having("guardian_stars") >= 2:
                self.read_stars(mod)
            if self.having("limits") + self.having("chest_overflow") >= 2:
                self.read_limits(mod)
            if self.having("terrain_bonus") >= 2:
                self.read_terrain(mod)
            if self.having("trap_thresholds") >= 2:
                self.read_traps(mod)
            if self.having("text") >= 2:
                self.read_text(mod)
            if self.having("font") >= 2 and "font" in self.mods[mod].manifest:
                self.claim(FONT, mod, 0, ADD, 0)
            if self.having("title") + self.having("menu") >= 2:
                self.read_title(mod)
        self.sector_runs()
        self.widen()
        groups = {}
        for c in self.claims:
            groups.setdefault((c.kind, repr(c.key)), []).append(c)
        found = []
        for (kind, _), claims in groups.items():
            mods = {c.mod for c in claims}
            if len(mods) < 2 or (involving is not None and involving not in mods):
                continue
            claims.sort(key=lambda c: (c.mod, c.seq))
            overlap = Overlap(kind, claims)
            self.decide(overlap)
            overlap.label = self.label(overlap)
            overlap.mods = [self.mods[m].id for m in sorted(mods)]
            overlap.text = self.text(overlap)
            found.append(overlap)
        # Within a kind, the warnings first, then as the earliest mod's manifest
        # has them, and between the keys an "all" reaches, as the manifests name them.
        found.sort(key=lambda o: (o.kind, -o.severity, o.claims[0].seq,
                                  next((c.seq for c in o.claims if not c.via_wide), o.claims[0].seq)))
        return found

    def widen(self):
        wide = [c for c in self.claims if c.wide]
        if not wide:
            return
        named = {}
        for c in self.claims:
            if not c.wide and not c.via_wide:
                named.setdefault((c.kind, repr(c.key)), (c.key, set()))[1].add(c.mod)
        for w in wide:
            for (kind, _), (key, mods) in named.items():
                others = {m for m in mods if m != w.mod and (not w.resets or m < w.mod)}
                if kind == w.kind and others and w.wide(key):
                    copy = Claim(w.kind, w.mod, key, w.mode, w.value, w.src, w.seq, w.label, None, True, w.aimed,
                                 w.resets, w.via)
                    self.claims.append(copy)

    def decide(self, o: Overlap):
        c = o.claims
        o.severity = WARNING
        if o.kind == HOOKS:
            o.winner, o.outcome = c[-1].mod, "chain"
            return
        if o.kind == EVENTS:
            o.outcome, o.severity = "events", INFO
            return
        if o.kind == DATA:
            self.decide_data(o)
            return
        fixed = last = -1
        for i, x in enumerate(c):
            if x.mode == FIXED:
                fixed = i
            if x.mode in (SET, FIXED):
                last = i
        if o.kind == DUELISTS and c[0].mode == FIRST:
            o.winner, o.outcome = c[0].mod, "first"
            return
        if fixed >= 0:
            o.winner = c[fixed].mod
            agree = all(x.mod == o.winner or (x.mode == FIXED and x.value == c[fixed].value) for x in c)
            o.outcome, o.severity = ("agree", INFO) if agree else ("fixed", WARNING)
            return
        for i, x in enumerate(c):
            if x.mode == BASE:
                for y in c[:i]:
                    if y.aimed and y.mod < x.mod:
                        o.winner, o.other, o.outcome = y.mod, x.mod, "early"
                        return
        if last < 0:
            o.outcome, o.severity = "add", INFO
            return
        o.winner = c[last].mod
        losers, agree, all_declared = 0, True, True
        for x in c[:last]:
            if x.mod == o.winner:
                continue
            if x.mode == BASE:
                o.other = x.mod
                continue
            losers += 1
            o.other = x.mod
            if x.mode != SET or x.value != c[last].value:
                agree = False
            if (o.winner, x.mod) not in self.declared:
                all_declared = False
        if not losers:
            for x in c:
                if x.mode == BASE and x.mod != o.winner:
                    o.other = x.mod
            o.outcome, o.severity = ("aimed" if o.other >= 0 else "add"), INFO
            return
        if o.kind == CARDS:
            used, dropped, met = self.card_keys(o)
            if not used and not dropped:
                o.outcome, o.severity = ("agree" if met else "add"), INFO
                return
            o.outcome = "keys"
        elif o.kind == EQUIPS and c[last].key != DEFAULT_EQUIP_BONUS:
            differ = same = False
            for i in range(len(c)):
                for j in range(i + 1, len(c)):
                    if c[i].mod != c[j].mod:
                        d, s = self.equips_meet(c[i].src, c[j].src)
                        differ |= d
                        same |= s
            if not differ:
                o.outcome, o.severity = ("agree" if same else "add"), INFO
                return
            o.outcome = "reset" if _json_bool(_obj(c[last].src).get("replace")) else "later"
        elif agree:
            o.outcome, o.severity = "agree", INFO
            return
        else:
            o.outcome = "reset" if c[last].resets else "later"
        if all_declared:
            o.outcome, o.severity = "after", INFO

    def decide_data(self, o: Overlap):
        c = o.claims
        o.severity = WARNING
        for i in range(len(c) - 1, -1, -1):
            for j in range(i):
                if c[i].mode == SET and c[j].mode == SET and c[i].mod != c[j].mod and _sectors_meet(c[i], c[j]):
                    o.winner, o.other = c[i].mod, c[j].mod
                    after = (o.winner, o.other) in self.declared
                    o.outcome, o.severity = ("after", INFO) if after else ("later", WARNING)
                    return
        for i in range(len(c) - 1, -1, -1):
            for j in range(i):
                if c[i].mode == ADD and c[j].mode == ADD and c[i].mod != c[j].mod and _patches_meet(c[i], c[j]):
                    o.winner, o.other, o.outcome = c[i].mod, c[j].mod, "bytes"
                    return
        for i in range(len(c)):
            for j in range(len(c)):
                if c[i].mode == ADD and c[j].mode == SET and c[i].mod != c[j].mod and _sectors_meet(c[i], c[j]):
                    o.winner, o.other, o.outcome = c[i].mod, c[j].mod, "patched"
                    return
        o.outcome, o.severity = "add", INFO

    def card_keys(self, o: Overlap):
        """The keys a later mod's entry sets differently (used), the reset keys
        an earlier entry sets that a later one leaves out (dropped), and
        whether any key met at all."""
        c, used, dropped, met = o.claims, [], [], False
        for i in range(len(c)):
            for j in range(i + 1, len(c)):
                if c[j].mod == c[i].mod:
                    continue
                for name, value in c[i].src.items():
                    if name in ("replace", "notes", "id"):
                        continue
                    if name in c[j].src:
                        met = True
                        if canonical(c[j].src[name]) != canonical(value) and name not in used:
                            used.append(name)
                    elif name in CARD_RESET_KEYS and name not in dropped:
                        dropped.append(name)
        return used, dropped, met

    def equip_target(self, value):
        """A target of "add" or "remove": ("type", n), a card key, or None."""
        text = _json_string(value)
        t = _type_named(text) if text is not None else -1
        if t >= 0 and (not self.source.card or self.source.card(text, 0) <= 0):
            return ("type", t)
        return self.card_key(value)

    def equip_allows(self, entry, card, type_):
        best, rank = None, 0
        if _json_bool(entry.get("replace")):
            best, rank = False, 1
        for allow, key in ((True, "add"), (False, "remove")):
            for t in _list(entry.get(key)):
                target = self.equip_target(t)
                if target is None:
                    r = 0
                elif isinstance(target, tuple) and target[0] == "type":
                    r = 2 if type_ >= 0 and target[1] == type_ else 0
                else:
                    r = 3 if card is not None and target == card else 0
                if r and r >= rank:
                    best, rank = allow, r
        return best

    def equips_meet(self, early, late):
        cards, types, attributes = [], [-1], [-1]
        for entry in (early, late):
            for key in ("add", "remove"):
                for t in _list(entry.get(key)):
                    target = self.equip_target(t)
                    if target is None:
                        continue
                    if isinstance(target, tuple) and target[0] == "type":
                        if len(types) < 32:
                            types.append(target[1])
                    elif len(cards) < 64:
                        cards.append((target, self.card_info(target)[1]))
            for name, value in _obj(entry.get("bonus_if")).items():
                t, a = _type_named(name), _attribute_named(name)
                if 0 <= t < 20 and len(types) < 32:
                    types.append(t)
                elif a >= 0 and len(attributes) < 8:
                    attributes.append(a)
        differ = same = False
        for card, type_ in cards + [(None, t) for t in types]:
            a, b = self.equip_allows(early, card, type_), self.equip_allows(late, card, type_)
            if a is None or b is None:
                continue
            if a != b:
                differ = True
            else:
                same = True
        for t in types:
            for att in attributes:
                one, two = _equip_bonus(early, t, att), _equip_bonus(late, t, att)
                if one is NO_BONUS or two is NO_BONUS:
                    continue
                if one != two:
                    differ = True
                else:
                    same = True
        return differ, same

    # --- lines ---------------------------------------------------------------

    def star_words(self, star: int) -> str:
        if 1 <= star <= 10:
            return STAR_RETAIL[star]
        for mod in self.mods:
            for s in _list(_obj(mod.manifest.get("guardian_stars")).get("stars")):
                s = _obj(s)
                if _json_number(s.get("id"), -1) != star:
                    continue
                name = s.get("name")
                if isinstance(name, dict):
                    name = next(iter(name.values()), None)
                if isinstance(name, str):
                    return name
        return f"Star {star}"

    def label(self, o: Overlap) -> str:
        c = next((x for x in o.claims if not x.via_wide), o.claims[0])
        if c.label is not None:
            return c.label
        src, kind = c.src, o.kind
        if kind == DATA:
            return f"File {_json_string(src.get('file')) or '?'}"
        if kind == AUDIO:
            return f"{['Song', 'XA clip', 'Sound effect'][c.key[0]]} 0x{c.key[1]:X}"
        if kind == TEXTURES:
            name = _json_string(src.get("alias")) or _json_string(src.get("file")) or "?"
            return f"Image {name}, {_json_string(src.get('archive')) or '?'} at 0x{_json_number(src.get('offset'), 0):X}"
        if kind == CARDS:
            return f"Card {self.card_words(src.get('replace'))}"
        if kind == FUSIONS:
            if "remove" in src:
                return f"Disc recipes for {self.card_words(src['remove'])} removed"
            with_ = src["with"]
            pair = list(with_.values()) if isinstance(with_, dict) else with_
            return f"Fusion {self.card_words(pair[0])} + {self.card_words(pair[1])}"
        if kind == EQUIPS:
            return "The default equip bonus" if c.key == DEFAULT_EQUIP_BONUS else f"Equip {self.card_words(src.get('card'))}"
        if kind == RITUALS:
            return f"Ritual {self.card_words(src.get('card'))}"
        if kind == STARTER:
            return "Starter decks"
        if kind == STARS:
            key = c.key
            if key[0] == "pair":
                return f"Matchup {self.star_words(key[1])} attacking {self.star_words(key[2])}"
            if key[0] == "star":
                return f"The {['', 'name', 'icon', 'palette'][key[2]]} of star {key[1]}, {self.star_words(key[1])}"
            if key[0] == "scalar":
                return "How a summon chooses its star"
            return "Every matchup (\"replace\")"
        if kind == TRAPS:
            return f"Attack trap '{src}'"
        if kind == TEXT:
            return f"Text [{c.key:04X}]"
        if kind == FONT:
            return "Fonts"
        return "?"

    def text(self, o: Overlap) -> str:
        names = ", ".join(self.mods[m].name for m in sorted({c.mod for c in o.claims}))
        winner = self.mods[o.winner].name if o.winner >= 0 else ""
        other = self.mods[o.other].name if o.other >= 0 else ""
        via = next((c.via for c in o.claims if c.mod == o.winner and c.via_wide and c.via), None)
        head = f"{o.label} ({names}): "
        distinct = len({c.mod for c in o.claims})
        if o.outcome == "later":
            through = f', through its "{via[:80]}"' if via else ""
            return head + f"{winner} wins (later in load order{through})"
        if o.outcome == "after":
            return head + f"{winner} wins (it loads after {other} on purpose: after/requires)"
        if o.outcome == "agree":
            return head + ("where they set the same key they agree; the rest combines" if o.kind == CARDS
                           else "the same in each, so no difference")
        if o.outcome == "add":
            extra = {DATA: " (replacements first, then patches of different bytes)",
                     CARDS: " (they set different stats)",
                     POOLS: " (each edits the pool as the mods before left it)",
                     FONT: " (a letter comes from the first font that has it)"}.get(o.kind, "")
            return head + f"{'all' if distinct > 2 else 'both'} apply and add up{extra}"
        if o.outcome == "reset":
            word = via[:80] if via else "replace"
            return head + f"{winner}'s \"{word}\" clears what the earlier mods set"
        if o.outcome == "fixed":
            return head + f"{winner}'s fixed deck is dealt; the other edits of it are left out"
        if o.outcome == "keys":
            used, dropped, _ = self.card_keys(o)
            used_words = ", ".join(used)
            dropped_words = ", ".join(dropped)
            said = f"the later mod's {used_words} {'are' if ',' in used_words else 'is'} used" if used else ""
            if dropped:
                said += f"{'; ' if said else ''}the earlier's {dropped_words} " \
                        f"{'are' if ',' in dropped_words else 'is'} dropped (a later replace resets it)"
            return head + f"{said}; the rest combines"
        if o.outcome == "bytes":
            return head + f"{winner}'s bytes are read where they patch the same ones"
        if o.outcome == "patched":
            return head + f"{winner}'s patch is written into {other}'s replacement, at the disc's offsets"
        if o.outcome == "chain":
            return head + f"{winner}'s hook runs first (applied last); the others run only if it calls its original"
        if o.outcome == "events":
            return head + "each is called, higher priority first; a before-hook that handles it stops the rest"
        if o.outcome == "first":
            return head + f"{winner} keeps it, earlier in load order; the others take the next free slot"
        if o.outcome == "early":
            return head + f"{winner}'s change is left out: it loads before {other}, whose button it names"
        return head + f"{winner} changes {other}'s own on purpose"


def _notes_only(entry: dict) -> bool:
    return all(k in ("replace", "notes", "id") for k in entry) and "notes" in entry


def _audio_id(text) -> int:
    """replace.c AudioReplace_ParseId: 0x-prefixed hexadecimal, else decimal, 0-0xFFFF."""
    if not isinstance(text, str) or not text or text[0] in "-+ ":
        return -1
    if text[:2] in ("0x", "0X"):
        if len(text) == 2:
            return -1
        value, rest = _strtol(text[2:], 16)
    else:
        value, rest = _strtol(text, 10)
    if rest or value < 0 or value > 0xFFFF:
        return -1
    return value


def _strtoul16(word: str):
    """strtoul(word, 16) as listing.c reads an item's ids: (value, the rest);
    the rest is `word` when nothing was read."""
    i, n = 0, len(word)
    while i < n and word[i] in C_SPACE:
        i += 1
    negative = False
    if i < n and word[i] in "+-":
        negative = word[i] == "-"
        i += 1
    hexdigits = "0123456789abcdefABCDEF"
    if word[i:i + 2] in ("0x", "0X") and i + 2 < n and word[i + 2] in hexdigits:
        i += 2
    start, value = i, 0
    while i < n and word[i] in hexdigits:
        value = value * 16 + int(word[i], 16)
        i += 1
    if i == start:
        return 0, word
    if negative and value:
        value = 2 ** 32 - value if value < 2 ** 32 else 2 ** 32
    return value, word[i:]


def _entry_index(name: str) -> int:
    """title_config.c entry_index: an entry's name, or its number 0-10."""
    if name in ENTRY_NAMES:
        return ENTRY_NAMES.index(name)
    value, rest = _strtol(name, 10)
    return value if name and rest == "" and 0 <= value < 11 else -1


def _type_named(text) -> int:
    for i, name in enumerate(TYPE_NAMES):
        if letters(text) and letters(text) == letters(name):
            return i
    return -1


def _attribute_named(text) -> int:
    for i, name in enumerate(ATTRIBUTE_NAMES):
        if letters(text) and letters(text) == letters(name):
            return i
    return -1


def _equip_bonus(entry: dict, type_: int, attribute: int):
    for name, value in _obj(entry.get("bonus_if")).items():
        t = _type_named(name)
        a = _attribute_named(name) if t < 0 or t >= 20 else -1
        if not _int(value):
            continue
        if (0 <= t < 20 and t == type_) or (a >= 0 and a == attribute):
            return value
    return entry["bonus"] if _int(entry.get("bonus")) else NO_BONUS


def _pool_named(name) -> int:
    for i, names in enumerate((("pow", "sa-pow"), ("bcd", "b-c-d"), ("tec", "sa-tec"))):
        if any(letters(name) == letters(n) for n in names):
            return i + 1
    return -1


def _terrain_named(name) -> int:
    for i in range(1, 7):
        if letters(name) == letters(TERRAINS[i]):
            return i
    if letters(name) in TERRAIN_ALIASES:
        return TERRAIN_ALIASES[letters(name)]
    return int(name) if is_digits(name) else -1


def _patch_length(patch) -> int:
    text = _json_string(_obj(patch).get("bytes")) or ""
    return sum(1 for ch in text if ch in "0123456789abcdefABCDEF") // 2


def _patches_meet(a: Claim, b: Claim) -> bool:
    if (a.key == "raw" or isinstance(a.key, tuple) and a.key[0] == "raw") != \
            (b.key == "raw" or isinstance(b.key, tuple) and b.key[0] == "raw"):
        return False

    def runs(c):
        base = _json_number(c.src.get("lba"), 0) * 2048 if isinstance(c.key, tuple) and c.key[0] == "raw" else 0
        for p in _list(c.src.get("patch")):
            yield base + _json_number(_obj(p).get("at"), 0), _patch_length(p)

    return any(pa < qa + ql and qa < pa + pl for pa, pl in runs(a) for qa, ql in runs(b))


def _sectors_meet(a: Claim, b: Claim) -> bool:
    return a.lo <= b.hi and b.lo <= a.hi


def check(mods: list, source: Source = None, involving: int = None) -> list:
    """The overlaps of `mods`, in load order (earliest first); with
    `involving`, only those of mods[involving] (the others are not worked
    out, which is what makes the editor's check quick)."""
    return _Check(mods, source).run(involving)


def line(overlap: Overlap) -> str:
    """kind|severity|outcome|mods|label, as tests/pc/mod_overlaps/expected.txt has them."""
    return "|".join((KINDS[overlap.kind], "warning" if overlap.severity else "info", overlap.outcome,
                     ", ".join(overlap.mods), overlap.label))


# --- the installed mods and their order ------------------------------------------

def read_settings(path: Path) -> dict:
    """The port's settings file (src/pc/platform/settings.c): key=value lines."""
    values = {}
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return values
    for row in text.splitlines():
        key, sep, value = row.partition("=")
        if sep:
            try:
                values[key.strip()] = int(value.strip())
            except ValueError:
                pass
    return values


def installed(folders) -> list:
    """Every mod (a folder with a mod.json) in `folders`, in the order the
    game finds them (mods.c scan): folder by folder, names sorted; the first
    of one id is kept within a folder, a later folder's copy replaces an
    earlier's in its place."""
    found = {}
    for folder in folders:
        try:
            names = sorted(os.listdir(folder), key=lambda n: n.encode("utf-8", "surrogateescape"))
        except OSError:
            continue
        here = set()
        for name in names:
            if name.startswith("."):
                continue
            manifest = _read_json(Path(folder) / name / "mod.json")
            if not isinstance(manifest, dict):
                continue
            mid = manifest.get("id") if isinstance(manifest.get("id"), str) else name
            if mid in here:
                continue
            here.add(mid)
            found[mid] = Mod(mid, manifest.get("name") if isinstance(manifest.get("name"), str) else mid, manifest,
                             Path(folder) / name)
    return list(found.values())


def _needs(manifest: dict, key: str) -> list:
    return [v if isinstance(v, str) else _json_string(v.get("id")) if isinstance(v, dict) else None
            for v in _list(manifest.get(key))]


def load_order(mods: list, settings: dict = None) -> list:
    """manager.c Mods_Order: the lowest Load order first (the player's
    mod.<id>.order, else the manifest's priority), never before a mod it
    requires or names in "after"; equal ones in the order they were found.
    A mod whose requirement is not there, and the mods of a cycle (and those
    waiting on them), are left out, as the game leaves them out."""
    settings = settings or {}
    ids = {m.id for m in mods}
    mods = [m for m in mods if all(r in ids for r in _needs(m.manifest, "requires") if r)]
    ids = {m.id for m in mods}
    done, order = set(), []
    while len(order) < len(mods):
        best = None
        for i, m in enumerate(mods):
            if m.id in done:
                continue
            waits = _needs(m.manifest, "requires") + _needs(m.manifest, "after")
            if any(w in ids and w not in done for w in waits):
                continue
            rank = settings.get(f"mod.{m.id}.order", _json_number(m.manifest.get("priority"), 0))
            if best is None or rank < best[0]:
                best = (rank, i)
        if best is None:    # a cycle: the rest are not loaded
            break
        order.append(mods[best[1]])
        done.add(mods[best[1]].id)
    return order
