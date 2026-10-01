"""What two or more mods change in common, and which of them the game uses:
the same check the Mods window makes (src/pc/mods/overlap.c), line for line,
so the editor can say where the mod being edited meets the other mods the
player has installed.

Every mod's manifest becomes claims, one for each thing it sets (a card, a
fusion pair, a pool, a limit, an image...): the thing's key, how the mod
sets it (it sets it, adds to it, defines it) and what it sets. Claims of two
or more mods on one key are an overlap, and the load order decides how it
comes out, the way the game's reader of that key decides it. "all" and
"replace" reach keys they do not name ("wide" claims).

tests/pc/mod_overlaps holds three mods and the lines both this module and
the C engine must find (tests/test_overlaps.py, tests/pc/mods_overlap_test.c).
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

KINDS = ["Disc data", "Sounds", "Texture images", "Cards", "Fusions", "Equips", "Rituals", "Drops and decks",
         "Starter decks", "Passwords", "Guardian Stars", "Limits", "Terrain bonuses", "Attack traps", "Duelists",
         "Text", "Fonts", "Title screen and menus", "Code hooks", "Game events"]
(DATA, AUDIO, TEXTURES, CARDS, FUSIONS, EQUIPS, RITUALS, POOLS, STARTER, PASSWORDS, STARS, LIMITS, TERRAIN,
 TRAPS, DUELISTS, TEXT, FONT, TITLE, HOOKS, EVENTS) = range(len(KINDS))
INFO, WARNING = 0, 1

SET, ADD, FIXED, BASE, CHAIN, EVENT, FIRST = range(7)
ALL = ("all",)
DEFAULT_EQUIP_BONUS = ("default",)
STAR_RETAIL = ["", "Mars", "Jupiter", "Saturn", "Uranus", "Pluto", "Neptune", "Mercury", "Sun", "Moon", "Venus"]
TERRAINS = ["", "Forest", "Wasteland", "Mountain", "Sogen", "Umi", "Yami"]
TERRAIN_ALIASES = {"meadow": 4, "sea": 5, "dark": 6}
POOL_WORDS = ["deck", "POW drops", "B/C/D drops", "TEC drops"]


def letters(text) -> str:
    """Letters and digits only, lowercased: how the readers compare names."""
    return "".join(c.lower() for c in str(text) if c.isalnum() and c.isascii())


def canonical(value) -> str:
    """What a value says, its own name aside (members' names and order count)."""
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)


def is_digits(text) -> bool:
    return isinstance(text, str) and text != "" and text.isascii() and text.isdigit()


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
    game has, and a mod's settings. The defaults match cards by number and
    letters only, as overlap.c does without the game."""

    def card(self, text, number) -> int:
        if text is None:
            return number
        return int(text) if is_digits(text) else 0

    def card_name(self, cid: int):
        return None

    def duelist(self, text) -> int:
        return -1

    def setting(self, mod: Mod, key: str):
        """The mod's setting `key`, or None when it declares none."""
        for spec in mod.manifest.get("settings") or []:
            if isinstance(spec, dict) and spec.get("key") == key:
                return spec.get("default", 0)
        return None


def _json_number(value, default):
    """json.c Json_Number: whole numbers, and strings holding one ("0x5D800")."""
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value, 16) if value[:2].lower() == "0x" else int(value, 10)
        except ValueError:
            return default
    return default


def _read_json(path: Path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None


def _contained(relative) -> bool:
    if not isinstance(relative, str) or not relative or relative.startswith(("/", "\\")) or ":" in relative:
        return False
    return ".." not in re.split(r"[\\/]", relative)


class _Check:
    def __init__(self, mods, source):
        self.mods = mods
        self.source = source or Source()
        self.claims = []
        self.seq = 0
        self.memo = {}
        self.star_names = {}
        self.declared = set()
        for w, mod in enumerate(mods):
            for key in ("after", "requires"):
                for v in mod.manifest.get(key) or []:
                    target = v if isinstance(v, str) else v.get("id", "") if isinstance(v, dict) else ""
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
        return sorted(n[:-5] for n in names if n.endswith(".json") and len(n) > 5)

    def switched_on(self, mod, entry) -> bool:
        if not isinstance(entry, dict) or not isinstance(entry.get("setting"), str):
            return True
        value = self.source.setting(self.mods[mod], entry["setting"])
        if value is None:
            return True
        if "value" in entry:
            only = entry["value"]
            # Not a number: warned of, and used (mods.c entry_used).
            return value == only if isinstance(only, int) and not isinstance(only, bool) else True
        return value != 0

    def card_text(self, text):
        name = letters(text)
        if not name:
            return None
        if name not in self.memo:
            self.memo[name] = self.source.card(text, 0) or 0
        cid = self.memo[name]
        return cid if cid > 0 else ("text", name)

    def card_key(self, value):
        if isinstance(value, bool) or value is None:
            return None
        if isinstance(value, int):
            cid = self.source.card(None, value)
            return cid if cid and cid > 0 else value if value > 0 else None
        if isinstance(value, str):
            return self.card_text(value)
        return None

    def card_words(self, value) -> str:
        number = value if isinstance(value, int) and not isinstance(value, bool) else 0
        text = value if isinstance(value, str) else None
        cid = self.source.card(text, number) if (text is not None or number) else 0
        name = self.source.card_name(cid) if cid and cid > 0 else None
        if name:
            return f"'{name}'"
        if text is not None:
            return f"'{text}'"
        return f"#{number}"

    def duelist_key(self, name):
        if letters(name) == "all":
            return ALL
        did = self.source.duelist(name)
        if did < 0 and is_digits(name):
            did = int(name)
        return did if did >= 0 else ("text", letters(name))

    # --- the kinds -----------------------------------------------------------

    def read_data(self, mod):
        for entry in self.member(mod, "data") or []:
            if not isinstance(entry, dict):
                continue
            file, lba = entry.get("file"), _json_number(entry.get("lba"), -1)
            if isinstance(file, str) and file:
                name = file.split(";")[0].replace("/", "\\").lstrip("\\").upper()
                key = ("file", name)
            elif lba >= 0:
                key = lba
            else:
                continue
            self.claim(DATA, mod, key, SET if "replace" in entry else ADD, ("own", mod), entry)

    def read_audio(self, mod):
        audio = self.member(mod, "audio")
        for k, kind in enumerate(("music", "xa", "sfx")):
            for name, value in ((audio or {}).get(kind) or {}).items():
                try:
                    number = int(name[2:], 16) if name[:2].lower() == "0x" else int(name, 10)
                except ValueError:
                    continue
                if number >= 0:
                    self.claim(AUDIO, mod, (k, number), SET, canonical(value), name)

    def read_textures(self, mod):
        folder = self.member(mod, "textures")
        if not isinstance(folder, str):
            return
        for entry in self.mod_file(mod, f"{folder}/manifest.json") or []:
            if not isinstance(entry, dict) or not self.switched_on(mod, entry):
                continue
            clut = _json_number(entry.get("clut_entries"), 0)
            key = (str(entry.get("archive", "")).upper(), _json_number(entry.get("offset"), -1),
                   _json_number(entry.get("words"), 0), _json_number(entry.get("rows"), 0),
                   _json_number(entry.get("bpp"), 0), _json_number(entry.get("clut_offset"), 0) if clut else 0, clut)
            self.claim(TEXTURES, mod, key, SET, ("own", mod), entry)

    def any_identity_replace(self) -> bool:
        return any(isinstance(e, dict) and isinstance(e.get("replace"), str) and ":" in e["replace"]
                   for m in self.mods for e in (m.manifest.get("cards") or []))

    def read_cards(self, mod, identities):
        own = self.mods[mod].id
        for index, entry in enumerate(self.member(mod, "cards") or []):
            if not isinstance(entry, dict):
                continue
            if "replace" in entry:
                key = self.card_key(entry["replace"])
                if key is None:
                    continue
                c = self.claim(CARDS, mod, key, SET, canonical(entry), entry)
                text = entry["replace"]
                if isinstance(text, str) and ":" in text and not text.startswith(own):
                    c.aimed = True
            elif identities and "copy" in entry:
                count = _json_number(entry.get("count"), 1)
                entry_id = entry.get("id") if isinstance(entry.get("id"), str) else f"entry-{index}"
                for n in range(1, min(count, 4096) + 1):
                    identity = f"{own}:{entry_id}:{n}"
                    self.claim(CARDS, mod, self.card_text(identity), BASE, 0, entry, f"Card '{identity[:40]}'")

    def read_fusions(self, mod):
        for rule in self.member(mod, "fusions") or []:
            if not isinstance(rule, dict) or not self.switched_on(mod, rule):
                continue
            if "remove" in rule:
                key = self.card_key(rule["remove"])
                if key is not None:
                    self.claim(FUSIONS, mod, ("remove", key), ADD, 0, rule)
                continue
            with_ = rule.get("with")
            if not isinstance(with_, list) or len(with_) != 2 or "result" not in rule:
                continue
            a, b = self.card_key(with_[0]), self.card_key(with_[1])
            if a is None or b is None:
                continue
            pair = tuple(sorted((a, b), key=repr))
            self.claim(FUSIONS, mod, ("pair",) + pair, SET, self.card_key(rule["result"]) or 0, rule)

    def read_equips(self, mod):
        for entry in self.member(mod, "equips") or []:
            if not isinstance(entry, dict):
                continue
            key = self.card_key(entry.get("card"))
            if key is not None and self.switched_on(mod, entry):
                self.claim(EQUIPS, mod, key, SET, canonical(entry), entry)
        bonus = self.member(mod, "equip_bonus_default")
        if bonus is not None:
            self.claim(EQUIPS, mod, DEFAULT_EQUIP_BONUS, SET, canonical(bonus), bonus)

    def read_rituals(self, mod):
        for entry in self.member(mod, "rituals") or []:
            if not isinstance(entry, dict):
                continue
            key = self.card_key(entry.get("card"))
            if key is not None and self.switched_on(mod, entry):
                self.claim(RITUALS, mod, key, SET, (canonical(entry.get("tributes")), canonical(entry.get("result"))),
                           entry)

    def pool_claim(self, mod, duelist, pool, entry):
        who = self.duelist_key(duelist)
        fixed = pool == 0 and isinstance(entry, dict) and entry.get("fixed") is True
        replace = isinstance(entry, dict) and entry.get("replace") is True
        mode = FIXED if fixed else SET if replace else ADD
        label = f"Every opponent's {POOL_WORDS[pool]}" if who == ALL else f"{duelist[:80]}'s {POOL_WORDS[pool]}"
        c = self.claim(POOLS, mod, (who, pool), mode, canonical(entry), entry, label)
        c.resets = mode == SET
        if who == ALL:
            c.wide = lambda key, pool=pool: key[1] == pool

    def pool_table(self, mod, table, decks):
        if not isinstance(table, dict):
            return
        for name, entry in table.items():
            if decks:
                self.pool_claim(mod, name, 0, entry)
                continue
            if not isinstance(entry, dict):
                continue
            for pool_name, pool in entry.items():
                which = _pool_named(pool_name)
                if which > 0:
                    self.pool_claim(mod, name, which, pool)

    def read_pools(self, mod):
        for decks, key in ((0, "drops"), (1, "decks")):
            table = self.member(mod, key)
            if isinstance(table, str):
                table = self.mod_file(mod, table)
            self.pool_table(mod, table, decks)
            for name in self.folder_names(mod, key):
                root = self.mod_file(mod, f"{key}/{name}.json")
                if root is None:
                    continue
                if decks:
                    self.pool_claim(mod, name, 0, root)
                elif isinstance(root, dict):
                    for pool_name, pool in root.items():
                        if _pool_named(pool_name) > 0:
                            self.pool_claim(mod, name, _pool_named(pool_name), pool)

    def read_passwords(self, mod):
        table = self.member(mod, "passwords")
        if not isinstance(table, dict):
            return
        for name, entry in table.items():
            is_all = letters(name) == "all"
            card = ALL if is_all else self.card_text(name)
            if card is None or not isinstance(entry, dict):
                continue
            for f, fields in enumerate((("password",), ("starchips", "starchips_percent"))):
                value = next((entry[k] for k in fields if k in entry), None)
                if not any(k in entry for k in fields):
                    continue
                if is_all:
                    label = f"Every card's {'price' if f else 'password'}"
                else:
                    shown = self.source.card_name(card) if isinstance(card, int) else None
                    label = f"{'Price' if f else 'Password'} of '{(shown or name)[:100 if shown else 80]}'"
                c = self.claim(PASSWORDS, mod, (card, f + 1), SET, canonical(value), entry, label)
                if is_all:
                    c.wide = lambda key, f=f: key[1] == f + 1

    def learn_star_names(self):
        for i in range(1, 11):
            self.star_names.setdefault(letters(STAR_RETAIL[i]), i)
        for mod in self.mods:
            section = mod.manifest.get("guardian_stars")
            for s in (section.get("stars") or []) if isinstance(section, dict) else []:
                if not isinstance(s, dict):
                    continue
                sid = _json_number(s.get("id"), -1)
                name = s.get("name")
                names = [name] if isinstance(name, str) else list(name.values()) if isinstance(name, dict) else []
                for n in names:
                    if isinstance(n, str) and letters(n):
                        self.star_names.setdefault(letters(n), sid)

    def star_of(self, value) -> int:
        if isinstance(value, int) and not isinstance(value, bool):
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
        reset = section.get("replace") is True
        if reset:
            c = self.claim(STARS, mod, ("reset",), SET, 0, True)
            c.wide = lambda key: key[0] == "pair"
            c.resets = True
        value = section.get("default_bonus")
        if isinstance(value, int) and not isinstance(value, bool):
            bonus = value
            self.claim(STARS, mod, ("scalar", 1), SET, bonus, value)
            for a in range(1, 11) if not reset else ():
                d = a % 6 + 1 if a <= 6 else (a - 7 + 1) % 4 + 7
                self.star_pair(mod, a, d, bonus, value)
                self.star_pair(mod, d, a, -bonus, value)
        if "choice" in section:
            self.claim(STARS, mod, ("scalar", 2), SET, letters(section["choice"]) if isinstance(section["choice"], str)
                       else "", section["choice"])
        for s in section.get("stars") or []:
            if not isinstance(s, dict):
                continue
            sid = _json_number(s.get("id"), -1)
            if not 1 <= sid <= 15:
                continue
            for f, name in enumerate(("name", "icon", "palette")):
                if name in s:
                    self.claim(STARS, mod, ("star", sid, f + 1), SET,
                               ("own", mod) if f == 1 else canonical(s[name]), s[name])
            for t in s.get("beats") or []:
                other = self.star_of(t)
                self.star_pair(mod, sid, other, bonus, t)
                self.star_pair(mod, other, sid, -bonus, t)
        for m in section.get("matchups") or []:
            if not isinstance(m, dict):
                continue
            a, d = self.star_of(m.get("attacker")), self.star_of(m.get("defender"))
            points = _json_number(m["bonus"], bonus) if "bonus" in m else bonus
            self.star_pair(mod, a, d, points, m)
            if m.get("mirror") is True:
                self.star_pair(mod, d, a, -points, m)

    def limit_claim(self, mod, path, value, key=None):
        self.claim(LIMITS, mod, key or path, SET, canonical(value), value, f"Limit {path}")

    def limit_tree(self, mod, path, value):
        if not isinstance(value, dict):
            self.limit_claim(mod, path, value)
            return
        for name, inner in value.items():
            here = f"{path}.{name[:60]}"
            if path == "life_points.duelists":
                self.limit_claim(mod, here, inner, ("duelist LP", self.duelist_key(name)))
            else:
                self.limit_tree(mod, here, inner)

    def read_limits(self, mod):
        limits = self.member(mod, "limits")
        for name, value in (limits.items() if isinstance(limits, dict) else ()):
            if name == "life_points" and isinstance(value, int) and not isinstance(value, bool):
                self.limit_claim(mod, "life_points.start", value)
            else:
                self.limit_tree(mod, name, value)
        overflow = self.member(mod, "chest_overflow")
        if isinstance(overflow, dict):
            if "limit" in overflow:
                self.limit_claim(mod, "chest", overflow["limit"])
            if "starchips" in overflow:
                self.limit_claim(mod, "chest_overflow.starchips", overflow["starchips"])

    def read_terrain(self, mod):
        table = self.member(mod, "terrain_bonus")
        if not isinstance(table, dict):
            return
        if table.get("replace") is True:
            c = self.claim(TERRAIN, mod, ("reset",), SET, 0, True, "Every terrain bonus (\"replace\")")
            c.wide = lambda key: key[0] == "t"
            c.resets = True
        for name, types in table.items():
            terrain = _terrain_named(name)
            if not 1 <= terrain <= 6 or not isinstance(types, dict):
                continue
            for type_name, value in types.items():
                self.claim(TERRAIN, mod, ("t", terrain, letters(type_name)), SET, canonical(value), value,
                           f"{TERRAINS[terrain]} bonus of {type_name[:60]}")

    def read_traps(self, mod):
        table = self.member(mod, "trap_thresholds")
        for name, value in (table.items() if isinstance(table, dict) else ()):
            key = self.card_text(name)
            if key is not None:
                self.claim(TRAPS, mod, key, SET, canonical(value), name)

    def read_duelists(self, mod):
        for name in self.folder_names(mod, "duelists"):
            root = self.mod_file(mod, f"duelists/{name}.json")
            if not isinstance(root, dict):
                continue
            if "replace" in root:
                who = root["replace"]
                who = str(who) if isinstance(who, int) and not isinstance(who, bool) else who if isinstance(who, str) else ""
                self.claim(DUELISTS, mod, ("replace", self.duelist_key(who)), SET, ("own", mod), root,
                           f"Duelist '{who[:80]}' replaced")
            slot = root.get("slot")
            if isinstance(slot, int) and not isinstance(slot, bool):
                self.claim(DUELISTS, mod, ("slot", slot), FIRST, ("own", mod), root, f"Free Duel slot {slot}")

    def text_file(self, mod, path):
        try:
            lines = Path(path).read_bytes().decode("utf-8", "replace").splitlines()
        except OSError:
            return
        open_claim, value = None, []
        for line in lines:
            line = line.rstrip("\r\n")
            if line[:1] in ("[", "@"):
                if open_claim:
                    open_claim.value = tuple(value)
                open_claim = None
                if line[0] == "@":
                    continue
                m = re.match(r"\[([0-9A-Fa-f]+)\]", line)
                if not m:
                    continue
                value = []
                open_claim = self.claim(TEXT, mod, int(m.group(1), 16), SET, ())
            elif open_claim and line and line[0] != "#":
                value.append(line)
        if open_claim:
            open_claim.value = tuple(value)

    def read_text(self, mod):
        text = self.member(mod, "text")
        directory = self.mods[mod].directory
        for one in text if isinstance(text, list) else [text] if text is not None else []:
            name = one if isinstance(one, str) else one.get("file") if isinstance(one, dict) else None
            if isinstance(name, str) and directory is not None and _contained(name) and self.switched_on(mod, one):
                self.text_file(mod, Path(directory) / name)

    def title_tree(self, mod, path, value, mode, aimed=False):
        if not isinstance(value, dict):
            c = self.claim(TITLE, mod, path, mode, canonical(value), value, path)
            c.aimed = aimed
            return
        for name, inner in value.items():
            self.title_tree(mod, f"{path}.{name[:60]}", inner, mode, aimed)

    def read_title(self, mod):
        own = self.mods[mod].id
        title = self.member(mod, "title")
        for name, value in (title.items() if isinstance(title, dict) else ()):
            path = f"title.{name[:60]}"
            if name == "text":
                self.claim(TITLE, mod, path, ADD, 0, value, "title.text (lines)")
            else:
                self.title_tree(mod, path, value, SET)
        menu = self.member(mod, "menu")
        for name, value in (menu.items() if isinstance(menu, dict) else ()):
            if name == "buttons":
                for button in value if isinstance(value, list) else []:
                    if not isinstance(button, dict):
                        continue
                    bid = button.get("id") if isinstance(button.get("id"), str) else ""
                    theirs = ":" in bid and not bid.startswith(own + ":")
                    path = f"menu.buttons.{bid[:100]}" if ":" in bid else f"menu.buttons.{own[:60]}:{bid[:60]}"
                    for k, v in button.items():
                        if k != "id":
                            self.title_tree(mod, f"{path}.{k[:60]}", v, SET if theirs else BASE, theirs)
            elif name == "order" and isinstance(value, list):
                self.title_tree(mod, "menu.order.first", value, SET)
            else:
                self.title_tree(mod, f"menu.{name[:60]}", value, SET)

    # --- grouping ------------------------------------------------------------

    def run(self) -> list:
        if len(self.mods) < 2:
            return []
        identities = self.any_identity_replace()
        if self.having("guardian_stars") >= 2:
            self.learn_star_names()
        for mod in range(len(self.mods)):
            if self.having("data") >= 2:
                self.read_data(mod)
            if self.having("audio") >= 2:
                self.read_audio(mod)
            if self.having("textures") >= 2:
                self.read_textures(mod)
            if self.having("cards") >= 2:
                self.read_cards(mod, identities)
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
            if self.having("guardian_stars") >= 2:
                self.read_stars(mod)
            if self.having("limits") + self.having("chest_overflow") >= 2:
                self.read_limits(mod)
            if self.having("terrain_bonus") >= 2:
                self.read_terrain(mod)
            if self.having("trap_thresholds") >= 2:
                self.read_traps(mod)
            self.read_duelists(mod)
            if self.having("text") >= 2:
                self.read_text(mod)
            if self.having("font") >= 2 and "font" in self.mods[mod].manifest:
                self.claim(FONT, mod, 0, ADD, 0)
            if self.having("title") + self.having("menu") >= 2:
                self.read_title(mod)
        self.widen()
        groups = {}
        for c in self.claims:
            groups.setdefault((c.kind, repr(c.key)), []).append(c)
        found = []
        for (kind, _), claims in groups.items():
            claims.sort(key=lambda c: (c.mod, c.seq))
            if len({c.mod for c in claims}) < 2:
                continue
            overlap = Overlap(kind, claims)
            self.decide(overlap)
            overlap.label = self.label(overlap)
            overlap.mods = [self.mods[m].id for m in sorted({c.mod for c in claims})]
            overlap.text = self.text(overlap)
            found.append(overlap)
        # Within a kind, the warnings first, then as the earliest mod's manifest has them.
        found.sort(key=lambda o: (o.kind, -o.severity, o.claims[0].seq))
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
                if kind == w.kind and mods - {w.mod} and w.wide(key):
                    copy = Claim(w.kind, w.mod, key, w.mode, w.value, w.src, w.seq, w.label, None, True, w.aimed,
                                 w.resets)
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
            replaced, other = None, -1
            for x in c:
                if x.mode == SET:
                    if replaced is not None and replaced.mod != x.mod:
                        other = replaced.mod
                    replaced = x
            if other >= 0:
                o.winner, o.other = replaced.mod, other
                after = (o.winner, other) in self.declared
                o.outcome, o.severity = ("after", INFO) if after else ("later", WARNING)
                return
            for i in range(len(c) - 1, -1, -1):
                for j in range(i):
                    if c[i].mode == ADD and c[j].mode == ADD and c[i].mod != c[j].mod and _patches_meet(c[i], c[j]):
                        o.winner, o.other, o.outcome = c[i].mod, c[j].mod, "bytes"
                        return
            o.outcome, o.severity = "add", INFO
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
            conflicts, met = self.card_keys(o)
            if not conflicts:
                o.outcome, o.severity = ("agree" if met else "add"), INFO
                return
            o.outcome = "keys"
        elif o.kind == EQUIPS and c[last].key != DEFAULT_EQUIP_BONUS:
            if isinstance(c[last].src, dict) and c[last].src.get("replace") is True:
                o.outcome = "reset"
            else:
                meet, same = self.equips_meet(o)
                if meet:
                    o.outcome = "later"
                else:
                    o.outcome, o.severity = ("agree" if same else "add"), INFO
                    return
        elif agree:
            o.outcome, o.severity = "agree", INFO
            return
        else:
            o.outcome = "reset" if c[last].resets else "later"
        if all_declared:
            o.outcome, o.severity = "after", INFO

    def card_keys(self, o: Overlap):
        """The keys a later mod's entry sets differently from an earlier one's
        (the winner of each), and whether any key met at all."""
        c, keys, met = o.claims, [], False
        for i, x in enumerate(c):
            if x.mode != SET:
                continue
            for name, value in x.src.items():
                if name in ("replace", "notes", "id"):
                    continue
                differs = later = False
                for j, y in enumerate(c):
                    if y.mode != SET or y.mod == x.mod or name not in y.src:
                        continue
                    if j > i:
                        later = True
                    else:
                        met = True
                        differs |= canonical(y.src[name]) != canonical(value)
                if differs and not later:
                    keys.append(name)
        return keys, met

    def equips_meet(self, o: Overlap):
        c, same = o.claims, False
        lists = ("add", "remove", "bonus_if")
        for i in range(len(c)):
            for j in range(i + 1, len(c)):
                a, b = c[i].src, c[j].src
                if c[i].mod == c[j].mod:
                    continue
                if "bonus" in a and "bonus" in b:
                    if canonical(a["bonus"]) != canonical(b["bonus"]):
                        return True, same
                    same = True
                for p in range(3):
                    for q in range(3):
                        if (p == 2) != (q == 2):
                            continue
                        first, second = a.get(lists[p]), b.get(lists[q])
                        if p == 2:
                            pairs = [(s, t) for s in (first or {}) for t in (second or {})] \
                                if isinstance(first, dict) and isinstance(second, dict) else []
                        else:
                            pairs = [(s, t) for s in (first if isinstance(first, list) else [])
                                     for t in (second if isinstance(second, list) else [])]
                        for s, t in pairs:
                            if p == 2:
                                if letters(s) != letters(t):
                                    continue
                                if canonical(first[s]) != canonical(second[t]):
                                    return True, same
                            else:
                                if self.card_key(s) != self.card_key(t):
                                    continue
                                if p != q:
                                    return True, same
                            same = True
        return False, same

    # --- lines ---------------------------------------------------------------

    def star_words(self, star: int) -> str:
        if 1 <= star <= 10:
            return STAR_RETAIL[star]
        for mod in self.mods:
            section = mod.manifest.get("guardian_stars")
            for s in (section.get("stars") or []) if isinstance(section, dict) else []:
                if not isinstance(s, dict) or _json_number(s.get("id"), -1) != star:
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
            return f"File {src['file']}" if isinstance(src.get("file"), str) else f"Sector {_json_number(src.get('lba'), 0)}"
        if kind == AUDIO:
            return f"{['Song', 'XA clip', 'Sound effect'][c.key[0]]} 0x{c.key[1]:X}"
        if kind == TEXTURES:
            name = src.get("alias") if isinstance(src.get("alias"), str) else src.get("file", "?")
            return f"Image {name}, {src.get('archive', '?')} at 0x{_json_number(src.get('offset'), 0):X}"
        if kind == CARDS:
            return f"Card {self.card_words(src.get('replace'))}"
        if kind == FUSIONS:
            if "remove" in src:
                return f"Disc recipes for {self.card_words(src['remove'])} removed"
            return f"Fusion {self.card_words(src['with'][0])} + {self.card_words(src['with'][1])}"
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
                return "The default star bonus" if key[1] == 1 else "How a summon chooses its star"
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
        via = any(c.mod == o.winner and c.via_wide for c in o.claims)
        head = f"{o.label} ({names}): "
        distinct = len({c.mod for c in o.claims})
        if o.outcome == "later":
            return head + f"{winner} wins (later in load order{', through its \"all\"' if via else ''})"
        if o.outcome == "after":
            return head + f"{winner} wins (it loads after {other} on purpose: after/requires)"
        if o.outcome == "agree":
            return head + ("where they set the same key they agree; the rest combines" if o.kind == CARDS
                           else "the same in each, so no difference")
        if o.outcome == "add":
            extra = {DATA: " (replacements first, then patches of different bytes)",
                     CARDS: " (they set different keys)",
                     POOLS: " (each edits the pool as the mods before left it)",
                     FONT: " (a letter comes from the first font that has it)"}.get(o.kind, "")
            return head + f"{'all' if distinct > 2 else 'both'} apply and add up{extra}"
        if o.outcome == "reset":
            return head + f"{winner}'s \"replace\" clears what the earlier mods set"
        if o.outcome == "fixed":
            return head + f"{winner}'s fixed deck is dealt; the other edits of it are left out"
        if o.outcome == "keys":
            keys = ", ".join(self.card_keys(o)[0])
            return head + f"the later mod's {keys} {'are' if ',' in keys else 'is'} used; the rest combines"
        if o.outcome == "bytes":
            return head + f"{winner}'s bytes are read where they patch the same ones"
        if o.outcome == "chain":
            return head + f"{winner}'s hook runs first (applied last); the others run only if it calls its original"
        if o.outcome == "events":
            return head + "each is called, higher priority first; one that handles it stops the rest"
        if o.outcome == "first":
            return head + f"{winner} keeps it, earlier in load order; the others take the next free slot"
        return head + f"{winner} changes {other}'s own on purpose"


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


def _patch_runs(entry):
    for p in entry.get("patch") or []:
        if isinstance(p, dict):
            digits = sum(1 for ch in str(p.get("bytes", "")) if ch in "0123456789abcdefABCDEF")
            yield _json_number(p.get("at"), 0), digits // 2


def _patches_meet(a: Claim, b: Claim) -> bool:
    return any(pa < qa + ql and qa < pa + pl for pa, pl in _patch_runs(a.src) for qa, ql in _patch_runs(b.src))


def check(mods: list, source: Source = None) -> list:
    """The overlaps of `mods`, in load order (earliest first)."""
    return _Check(mods, source).run()


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
    game finds them: folder by folder, names sorted; the first of one id
    is kept within a folder, a later folder's copy replaces an earlier's."""
    found = {}
    for folder in folders:
        try:
            names = sorted(os.listdir(folder))
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


def load_order(mods: list, settings: dict = None) -> list:
    """manager.c Mods_Order: the lowest Load order first (the player's
    mod.<id>.order, else the manifest's priority), never before a mod it
    requires or names in "after"; equal ones in the order they were found."""
    settings = settings or {}
    ids = {m.id for m in mods}
    done, order = set(), []
    while len(order) < len(mods):
        best = None
        for i, m in enumerate(mods):
            if m.id in done:
                continue
            waits = [v if isinstance(v, str) else v.get("id") if isinstance(v, dict) else None
                     for k in ("requires", "after") for v in (m.manifest.get(k) or [])]
            if any(w in ids and w not in done for w in waits):
                continue
            rank = settings.get(f"mod.{m.id}.order", _json_number(m.manifest.get("priority"), 0))
            if best is None or rank < best[0]:
                best = (rank, i)
        if best is None:    # a cycle: the rest as found
            order += [m for m in mods if m.id not in done]
            break
        order.append(mods[best[1]])
        done.add(mods[best[1]].id)
    return order
