"""The checks the port's loader makes, run before saving, so a problem shows
in the editor rather than as a line in the Mods window.

Errors are what the port would refuse (the mod, or that one rule); warnings
are what it would accept but likely not as meant.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from pathlib import Path

from .gamedata import (CARD_COUNT, DECK_COPY_LIMIT, DECK_POOL_MIN_CARDS, DECK_SIZE, DUELIST_NAMES, POOLS,
                       POOL_LABELS, POOL_TOTAL, TYPE_MAGIC, TYPE_EQUIP, TYPE_RITUAL, exodia_piece)
from . import art, campaign_map, card_text, fixed_decks, guardian_stars, limits, packs as packmath
from . import starter_pools
from .model import KEY_RE, Project, duelist_named

MOD_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,63}$")
SETTING_TYPES = ("int", "bool", "choice", "key")
MANIFEST_KEYS = ("id", "name", "version", "author", "description", "library", "enabled", "restart",
                 "legacy_setting", "data", "textures", "cards", "audio", "min_api", "game", "requires", "after",
                 "conflicts", "priority", "settings", "fusions", "equips", "rituals", "drops", "decks", "text", "font",
                 "chest_overflow", "terrain_bonus", "trap_thresholds", "equip_bonus_default", "passwords",
                 "starter", "starter_pools", "limits", "guardian_stars", "packs", "pack_shop")
HOST_API = 8


@dataclass
class Issue:
    level: str          # "error" or "warning"
    area: str           # "Mod info", "Cards", "Art", "Fusions", "Equips", "Rituals", "Duelists"
    where: str
    message: str
    target: object = None   # what the GUI selects to show it (a card id, a pair, (duelist, pool)...)

    def __str__(self):
        return f"{self.level}: {self.area}: {self.where}: {self.message}"


def text_lines(text: str) -> int:
    """How many lines the port's card-text wrapping makes (cards.c
    encode_description): 20 letters a line, broken at spaces and at \\n;
    an icon code is one letter, a colour code none."""
    return 1 + card_text.encode(text).count("\n")


def _check_info(project: Project, out: list):
    info = project.info
    if not MOD_ID_RE.match(info.id or ""):
        out.append(Issue("error", "Mod info", "id", "id must be 1-63 letters, digits, hyphens or underscores"))
    if info.version and not re.match(r"^\d+(\.\d+)*$", info.version):
        out.append(Issue("warning", "Mod info", "version",
                         "a version is a dotted number (1.2.0), which \"requires\" bounds compare"))
    if not info.name:
        out.append(Issue("warning", "Mod info", "name", "the Mods window shows the id when there is no name"))
    seen = set()
    for i, setting in enumerate(info.settings):
        where = f"settings[{i}]"
        if not isinstance(setting, dict):
            out.append(Issue("error", "Mod info", where, "Invalid setting schema: not an object"))
            continue
        key = setting.get("key")
        if not isinstance(key, str) or not KEY_RE.match(key) or key == "order":
            out.append(Issue("error", "Mod info", where, f"Invalid setting schema: {key!r} is not a usable key"))
            continue
        if key in seen:
            out.append(Issue("error", "Mod info", where, f"Duplicate setting: {key}"))
        seen.add(key)
        kind = setting.get("type", "int")
        if kind not in SETTING_TYPES:
            out.append(Issue("error", "Mod info", where, f"Invalid setting schema: {key} (type is int, bool, choice or key)"))
        for number in ("default", "min", "max", "step"):
            if number in setting and (isinstance(setting[number], bool) or not isinstance(setting[number], int)):
                out.append(Issue("error", "Mod info", where, f"Invalid setting schema: {key} ({number} is a whole number)"))
        if kind == "choice":
            choices = setting.get("choices")
            if not isinstance(choices, list) or not choices or not all(isinstance(c, str) for c in choices):
                out.append(Issue("error", "Mod info", where, f"Invalid setting schema: {key} (a choice needs \"choices\")"))
        # manager.c Mods_CheckManifest and Mods_OptionValid: either refuses the whole mod.
        whole = lambda name, fallback: setting[name] if isinstance(setting.get(name), int) and \
            not isinstance(setting.get(name), bool) else fallback
        low, high, step, default = whole("min", 0), whole("max", 100), whole("step", 1), whole("default", 0)
        if low > high:
            out.append(Issue("error", "Mod info", where, f"Invalid setting schema: {key} (min is more than max)"))
        if step < 1:
            out.append(Issue("error", "Mod info", where, f"Invalid setting schema: {key} (step is at least 1)"))
        if kind == "bool":
            low, high = 0, 1
        elif kind == "choice":
            choices = setting.get("choices")
            low, high = 0, (len(choices) if isinstance(choices, list) else 0) - 1
        elif kind == "key":
            low, high = 0, 0xFFFF
        if not low <= default <= high:
            out.append(Issue("error", "Mod info", where,
                             f"Invalid setting schema: {key} (default {default} is outside {low} to {high})"))
        if len(f"mod.{info.id}.{key}") >= 256:
            out.append(Issue("error", "Mod info", where, f"Invalid setting schema: {key} (the key is too long)"))
    for key in project.other:
        if key not in MANIFEST_KEYS:
            out.append(Issue("warning", "Mod info", key, f"unknown key '{key}'"))
    game = project.other.get("game")
    if game is not None and game != "slus_01411":
        out.append(Issue("error", "Mod info", "game", "\"game\" must be \"slus_01411\""))
    api = project.other.get("min_api")
    if api is not None and (not isinstance(api, int) or api > HOST_API):
        out.append(Issue("error", "Mod info", "min_api", f"this game has mod API {HOST_API}"))
    for key in ("enabled", "restart"):
        if key in project.other and not isinstance(project.other[key], bool):
            out.append(Issue("warning", "Mod info", key, f"\"{key}\" should be true or false"))


def _check_card(project: Project, cid: int, out: list):
    card = project.cards[cid]
    where = project.card_label(cid)
    add = lambda level, message: out.append(Issue(level, "Cards", where, message, cid))
    for label, value in (("ATK", card.attack), ("DEF", card.defense)):
        if not isinstance(value, int) or not 0 <= value <= 5110:
            add("error", f"{label} is 0 to 5110")
        elif value % 10:
            add("error", f"{label} is stored in tens: {value} would become {value // 10 * 10}")
    if not 0 <= card.level <= 12:
        add("error", "level is 0 to 12")
    if not 0 <= card.type <= 23:
        add("error", "type is one of the 24 types")
    if not 0 <= card.attribute <= 15:
        add("error", "attribute is 0 to 15")
    count = guardian_stars.count(project.other.get("guardian_stars"))
    if not (0 <= card.star1 <= guardian_stars.MAX_STARS and 0 <= card.star2 <= guardian_stars.MAX_STARS):
        add("error", f"guardian stars are 1 to {guardian_stars.MAX_STARS}, or none (a card holds them in 4 bits)")
    elif card.star1 > count or card.star2 > count:
        add("warning", f"a guardian star past the {count} the mod has: declare it in the Guardian Stars tab")
    elif card.is_monster() and not card.star1 and card.star2:
        # stars.c Stars_Normalize: the game reads [none, X] as [X, none].
        name = guardian_stars.choices(project.other.get("guardian_stars"))[card.star2]
        add("warning", f"no first guardian star with a second: the game gives the card the one star {name}, "
                       "as if it were first (put it first, or both none for no star)")
    if not card.name.strip():
        add("warning", "the card has no name")
    elif len(card.name) > 32:
        add("warning", f"a long name ({len(card.name)} letters): its plate squeezes it")
    lines = text_lines(card.description)
    if lines > 8:
        add("warning", f"its text runs to {lines} lines; the card view shows 8")
    if any(ord(c) < 32 and c != "\n" for c in card.name + card.description):
        add("error", "a control character in its name or text")
    _check_password(project, cid, add)
    if cid in project.added:
        added = project.added[cid]
        base = project.cards.get(added.base)
        if not KEY_RE.match(added.key) or len(added.key) > 80:
            add("error", "invalid stable id: letters, digits, _ and - (at most 80)")
        if sum(1 for a in project.added.values() if a.key == added.key) > 1:
            add("error", f"duplicate card identity {added.key}")
        if base and base.is_monster() and not card.is_monster():
            add("error", "a copy of a monster stays a monster (it has its base's 3D model)")
        elif base and not base.is_monster() and card.type != base.type:
            add("error", "a copy of a magic, trap, ritual or equip card keeps its type (it has its base's effect)")
    elif cid in project.retail.cards:
        retail = project.retail.cards[cid]
        extra = project.card_extra.get(cid, {})
        if retail.is_monster() and not card.is_monster() and "effect" not in extra:
            add("warning", "a monster made a non-monster does nothing when played unless \"effect\" names a card")
        if not retail.is_monster() and card.is_monster() and "model" not in extra:
            add("warning", "a card made a monster fights without a 3D model unless \"model\" names one")


def _check_password(project: Project, cid: int, add):
    """A password the mod sets: 8 digits (tables.c read_shop_password), and
    no other card's. The Password screen gives the lower card number of two
    with the same password, and View > Card passwords would show both."""
    if not project.password_changed(cid):
        return
    value = project.passwords[cid]
    if not value:
        return
    if not re.fullmatch(r"\d{8}", value):
        add("error", "a password is up to 8 digits")
        return
    others = [other for other in sorted(project.cards) if other != cid and project.password(other) == value]
    if others:
        named = ", ".join(project.card_label(o) for o in others[:3]) + (" and more" if len(others) > 3 else "")
        add("error", f"password {value} is also {named}'s: the Password screen gives the lower card number")


def _check_tables(project: Project, out: list):
    valid = lambda cid: cid in project.cards
    for pair, result in project.fusions.items():
        if project.retail.fusions.get(pair) == result:
            continue
        where = f"{project.card_label(pair[0])} + {project.card_label(pair[1])}"
        if not (valid(pair[0]) and valid(pair[1]) and (result == 0 or valid(result))):
            out.append(Issue("error", "Fusions", where, "names a card that does not exist", pair))
        elif result and not project.cards[result].is_monster():
            out.append(Issue("warning", "Fusions", where, "the result is not a monster", pair))
    for equip, monsters in project.equips.items():
        baseline = project.equip_baseline(equip) if equip in project.cards else set()
        if baseline == monsters:
            continue
        where = project.card_label(equip)
        if not valid(equip) or project.cards[equip].type != TYPE_EQUIP:
            out.append(Issue("error", "Equips", where, "\"card\" is not an equip card", equip))
        for m in sorted(monsters - baseline):
            if not valid(m):
                out.append(Issue("error", "Equips", where, f"no card {m}", equip))
            elif not project.cards[m].is_monster():
                out.append(Issue("warning", "Equips", where, f"{project.card_label(m)} is not a monster", equip))
    for ritual, recipe in project.rituals.items():
        conditional = project.ritual_requirements.get(ritual)
        if project.retail.rituals.get(ritual) == recipe and not conditional:
            continue
        where = project.card_label(ritual)
        if not valid(ritual) or not project.is_ritual(ritual):
            out.append(Issue("error", "Rituals", where, "\"card\" must be a ritual card whose effect is a ritual's "
                             "(a copy of one, or \"effect\" naming one)", ritual))
        if len(recipe) != 4 or not valid(recipe[3]):
            out.append(Issue("error", "Rituals", where, "a valid result card is required", ritual))
            continue
        if conditional:
            if len(conditional) != 3 or any(not req for req in conditional):
                out.append(Issue("error", "Rituals", where, "three nonempty tribute requirements are required", ritual))
            for req in conditional:
                cid = req.get("card")
                if cid and not valid(cid):
                    out.append(Issue("error", "Rituals", where, f"no card {cid}", ritual))
                elif cid and not project.cards[cid].is_monster():
                    out.append(Issue("warning", "Rituals", where, f"{project.card_label(cid)} is not a monster", ritual))
            if not project.cards[recipe[3]].is_monster():
                out.append(Issue("warning", "Rituals", where, "the result should be a monster", ritual))
        elif not all(valid(c) for c in recipe):
            out.append(Issue("error", "Rituals", where, "three tributes and a result, all cards", ritual))
        elif not all(project.cards[c].is_monster() for c in recipe):
            out.append(Issue("warning", "Rituals", where, "tributes and result should be monsters", ritual))
    for d, pools in enumerate(project.pools):
        for pool in POOLS:
            weights = pools[pool]
            if weights == project.retail.pools[d][pool]:
                continue
            where = f"{DUELIST_NAMES[d]} {POOL_LABELS[pool]}"
            target = (d, pool)
            total = sum(weights.values())
            cards = sum(1 for w in weights.values() if w)
            if any(w < 0 or w > 0xFFFF for w in weights.values()):
                out.append(Issue("error", "Duelists", where, "a weight is a whole number, 0 to 65535", target))
            if any(not valid(c) for c in weights):
                out.append(Issue("error", "Duelists", where, "names a card that does not exist", target))
            if pool == "deck" and cards < DECK_POOL_MIN_CARDS:
                out.append(Issue("error", "Duelists", where,
                                 f"a deck is dealt from at least {DECK_POOL_MIN_CARDS} cards; it has {cards}", target))
            elif pool != "deck" and not cards:
                out.append(Issue("error", "Duelists", where, "no card would be left to win", target))
            if total != POOL_TOTAL:
                out.append(Issue("error", "Duelists", where,
                                 f"the weights add up to {total}, not {POOL_TOTAL} (Normalize fixes it)", target))


def _check_starter(project: Project, out: list):
    """The decks a new game may be dealt. The port deals a deck only when it
    is exactly DECK_SIZE cards, so anything else is an error here rather than
    a line in the Mods window after the fact."""
    decks = project.starter
    for i, deck in enumerate(decks):
        where = deck.name or f"deck {i + 1}"
        total = deck.total()
        if total != DECK_SIZE:
            out.append(Issue("error", "Starter decks", where,
                             f"a starter deck is {DECK_SIZE} cards, and this one has {total}", i))
        for name in deck.kept:
            out.append(Issue("error", "Starter decks", where, f"\"{name}\" is no card the editor knows", i))
        for cid, copies in sorted(deck.cards.items()):
            if cid not in project.cards:
                out.append(Issue("error", "Starter decks", where, f"no card {cid}", i))
            elif copies > DECK_COPY_LIMIT:
                out.append(Issue("warning", "Starter decks", where,
                                 f"{copies} copies of {project.card_label(cid)}: dealt as written, but Build Deck "
                                 f"takes back only {DECK_COPY_LIMIT}", i))
            elif exodia_piece(cid) and copies > 1:
                out.append(Issue("warning", "Starter decks", where,
                                 f"{copies} copies of {project.card_label(cid)}: Build Deck takes back only one "
                                 "of each Exodia piece", i))
    if decks and not any(deck.weight for deck in decks):
        out.append(Issue("warning", "Starter decks", "every deck",
                         "every deck weighs 0, so none is ever picked and the disc's own pools deal the deck", 0))


def pack_resolver(project: Project):
    """How the packs' cards are named for the checks and Simulate: as the
    game's Cards_Reference, the cards this project knows (a mod's own by its
    identity)."""
    def resolve(value):
        if isinstance(value, float) and value.is_integer():
            value = int(value)          # the game's JSON reads 5.0 as 5
        cid = project.resolve(value)
        return cid if cid else -1
    return resolve


def _check_packs(project: Project, out: list):
    """What the port's reader says of "packs" and "pack_shop" (packs.c), in
    its words: an error is a pack the game leaves out."""
    for level, message in packmath.check_rules(project.pack_shop):
        out.append(Issue(level, "Packs", "pack_shop", message, None))
    if project.packs_file is not None:
        return
    resolve = pack_resolver(project)
    ids, passwords = set(), {}
    card_passwords = {}
    for cid in project.cards:
        text = project.password(cid)
        if text:
            card_passwords.setdefault(int(text, 16) if text.isdigit() else None, cid)
    names = {packmath.pack_id(e) for e in project.packs}
    read, declared = [], 0
    for i, entry in enumerate(project.packs):
        # A pack without "order" is ordered by its place among those past
        # their id, as the game counts them (packs.read_packs).
        place = declared if packmath.entry_id(entry, ids) is not None else None
        declared += place is not None
        pack, notes = packmath.read_pack(entry, resolve, project.info.id, i, ids, place)
        where = packmath.pack_id(entry) if isinstance(entry, dict) else f"packs[{i}]"
        for level, message in notes:
            out.append(Issue(level, "Packs", where, message, i))
        if pack is None:
            continue
        ids.add(pack.id)
        read.append((pack, i))
        for level, message in packmath.shop_notes(pack, project.pack_shop):
            out.append(Issue(level, "Packs", where, message + " in this mod's \"pack_shop\" (another mod may add it)", i))
        image = entry.get("image")
        if isinstance(image, str) and image and image not in project.files and not (
                project.source_dir and (Path(project.source_dir) / image).is_file()):
            out.append(Issue("warning", "Packs", where, f"\"image\" {image} cannot be read; its cover is shown "
                                                         "instead", i))
        if pack.password is not None:
            if pack.password in card_passwords:
                out.append(Issue("warning", "Packs", where,
                                 f"its password is {project.card_label(card_passwords[pack.password])}'s: the card's "
                                 "comes first on the Password screen", i))
        unlock = entry.get("unlock") if isinstance(entry.get("unlock"), dict) else {}
        if "beat" in unlock and duelist_named(unlock["beat"]) < 0:
            out.append(Issue("warning", "Packs", where, f"\"unlock\" \"beat\" names no duelist of the disc "
                                                         f"(\"{unlock['beat']}\"); a mod's own, if it is not "
                                                         "applied, keeps the pack locked", i))
        if "card" in unlock and resolve(unlock["card"]) <= 0:
            out.append(Issue("warning", "Packs", where, f"\"unlock\" \"card\" names no card the editor knows "
                                                         f"(\"{unlock['card']}\"); the pack stays locked", i))
        opened = unlock.get("opened") if isinstance(unlock.get("opened"), dict) else {}
        for name in opened:
            if name not in names and name.split(":", 1)[-1] not in names:
                out.append(Issue("warning", "Packs", where, f"\"unlock\" \"opened\" names no pack of this mod "
                                                             f"(\"{name}\"); another mod's, if it is not applied, "
                                                             "keeps the pack locked", i))
    # Of two packs with one password the game sells the first in the list's
    # order ("order", then as declared), as packs.c Packs_Finish says.
    read.sort(key=lambda pair: pair[0].order)
    for pack, i in read:
        if pack.password is None:
            continue
        if pack.password in passwords:
            out.append(Issue("warning", "Packs", pack.id, f"its password is pack \"{passwords[pack.password]}\"'s "
                                                          "too; that one is sold", i))
        passwords.setdefault(pack.password, pack.id)
    if len(project.packs) > packmath.PACKS_MAX:
        out.append(Issue("error", "Packs", "packs", f"at most {packmath.PACKS_MAX} packs; the rest are left out",
                         packmath.PACKS_MAX))


def validate(project: Project) -> list:
    out = []
    _check_info(project, out)
    for cid in sorted(project.cards):
        if project.card_changed(cid):
            _check_card(project, cid, out)
    _check_tables(project, out)
    _check_starter(project, out)
    for level, where, message in limits.check(project.other.get("limits")):
        out.append(Issue(level, "Limits", where, message))
    stars = {}
    for card in project.cards.values():
        if card.is_monster():
            for star in (card.star1, card.star2):
                stars[star] = stars.get(star, 0) + 1
    # The ATK/DEF cap a bonus is measured against: the Limits tab's, else 9999.
    flat = limits.flatten(project.other.get("limits"))
    caps = [flat[key] for key in ("stats", "attack", "defense") if isinstance(flat.get(key), int)]
    cap = max(caps) if caps else guardian_stars.STAT_CAP
    for level, where, message in guardian_stars.check(project.other.get("guardian_stars"), stat_cap=cap,
                                                      card_stars=stars):
        out.append(Issue(level, "Guardian Stars", where, message))
    _check_packs(project, out)
    fixed_decks.check(project, out)
    art.check(project, out)
    campaign_map.check(project, out)
    starter_pools.check(project, out)
    return out


def validate_card(project: Project, cid: int) -> list:
    out = []
    _check_card(project, cid, out)
    return out


def errors(issues) -> list:
    return [i for i in issues if i.level == "error"]
