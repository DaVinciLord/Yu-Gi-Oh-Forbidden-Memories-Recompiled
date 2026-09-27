"""The checks the port's loader makes, run before saving, so a problem shows
in the editor rather than as a line in the Mods window.

Errors are what the port would refuse (the mod, or that one rule); warnings
are what it would accept but likely not as meant.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .gamedata import (CARD_COUNT, DECK_POOL_MIN_CARDS, DUELIST_NAMES, POOLS, POOL_LABELS, POOL_TOTAL,
                       TYPE_MAGIC, TYPE_EQUIP, TYPE_RITUAL)
from .model import KEY_RE, Project

MOD_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,63}$")
SETTING_TYPES = ("int", "bool", "choice", "key")
MANIFEST_KEYS = ("id", "name", "version", "author", "description", "library", "enabled", "restart",
                 "legacy_setting", "data", "textures", "cards", "audio", "min_api", "game", "requires", "after",
                 "conflicts", "priority", "settings", "fusions", "equips", "rituals", "drops", "decks", "text", "font")
HOST_API = 4


@dataclass
class Issue:
    level: str          # "error" or "warning"
    area: str           # "Mod info", "Cards", "Fusions", "Equips", "Rituals", "Duelists"
    where: str
    message: str
    target: object = None   # what the GUI selects to show it (a card id, a pair, (duelist, pool)...)

    def __str__(self):
        return f"{self.level}: {self.area}: {self.where}: {self.message}"


def text_lines(text: str) -> int:
    """How many lines the port's card-text wrapping makes (cards.c
    encode_description): 20 letters a line, broken at spaces and at \\n."""
    lines, column = 1, 0
    for part in re.split(r"(\n)", text):
        if part == "\n":
            lines += 1
            column = 0
            continue
        for word in part.split(" "):
            if not word:
                continue
            if column and column + 1 + len(word) > 20:
                lines += 1
                column = 0
            elif column:
                column += 1
            column += len(word)
    return lines


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
    if not (0 <= card.star1 <= 10 and 0 <= card.star2 <= 10):
        add("error", "guardian stars are Mars to Venus")
    elif card.is_monster() and not (card.star1 and card.star2):
        add("warning", "a monster without two guardian stars")
    if not card.name.strip():
        add("warning", "the card has no name")
    elif len(card.name) > 32:
        add("warning", f"a long name ({len(card.name)} letters): its plate squeezes it")
    lines = text_lines(card.description)
    if lines > 8:
        add("warning", f"its text runs to {lines} lines; the card view shows 8")
    if any(ord(c) < 32 and c != "\n" for c in card.name + card.description):
        add("error", "a control character in its name or text")
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


def _check_tables(project: Project, out: list):
    valid = lambda cid: cid in project.cards
    for pair, result in project.fusions.items():
        if project.retail.fusions.get(pair) == result:
            continue
        where = f"{project.card_label(pair[0])} + {project.card_label(pair[1])}"
        if not (valid(pair[0]) and valid(pair[1]) and valid(result)):
            out.append(Issue("error", "Fusions", where, "names a card that does not exist", pair))
        elif not project.cards[result].is_monster():
            out.append(Issue("warning", "Fusions", where, "the result is not a monster", pair))
    retail_equips = {e: set(m) for e, m in project.retail.equips.items()}
    for equip, monsters in project.equips.items():
        if retail_equips.get(equip, set()) == monsters:
            continue
        where = project.card_label(equip)
        if not valid(equip) or project.cards[equip].type != TYPE_EQUIP:
            out.append(Issue("error", "Equips", where, "\"card\" is not an equip card", equip))
        for m in sorted(monsters - retail_equips.get(equip, set())):
            if not valid(m):
                out.append(Issue("error", "Equips", where, f"no card {m}", equip))
            elif not project.cards[m].is_monster():
                out.append(Issue("warning", "Equips", where, f"{project.card_label(m)} is not a monster", equip))
    for ritual, recipe in project.rituals.items():
        if project.retail.rituals.get(ritual) == recipe:
            continue
        where = project.card_label(ritual)
        if ritual > CARD_COUNT or not valid(ritual) or project.cards[ritual].type != TYPE_RITUAL:
            out.append(Issue("error", "Rituals", where, "\"card\" must be one of the disc's ritual cards", ritual))
        if len(recipe) != 4 or not all(valid(c) for c in recipe):
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


def validate(project: Project) -> list:
    out = []
    _check_info(project, out)
    for cid in sorted(project.cards):
        if project.card_changed(cid):
            _check_card(project, cid, out)
    _check_tables(project, out)
    return out


def validate_card(project: Project, cid: int) -> list:
    out = []
    _check_card(project, cid, out)
    return out


def errors(issues) -> list:
    return [i for i in issues if i.level == "error"]
