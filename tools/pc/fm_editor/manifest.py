"""mod.json out of a Project (only what differs from retail), and back.

The schema is the one the port reads (notes/modding.md, notes/more-cards.md,
notes/gameplay-tables.md; src/pc/mods/mods.c, src/pc/cards/cards.c and
tables.c): "cards" (replace and copy), "fusions", "equips", "rituals",
"drops" and "decks". Every other top-level key a mod has (data, text,
textures, audio, library, requires...) is kept as it was written.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from .gamedata import (ATTRIBUTE_NAMES, CARD_COUNT, DUELIST_NAMES, POOLS, STAR_NAMES, TYPE_NAMES, TYPE_MAGIC,
                       GameData)
from .model import AddedCard, ModInfo, Project, duelist_named, type_named, KEY_RE
from . import pools as poolmath

INFO_KEYS = ("id", "name", "version", "author", "description")
TABLE_KEYS = ("settings", "cards", "fusions", "equips", "rituals", "drops", "decks")
REPLACE_EXTRA = ("art", "thumbnail", "title", "model", "effect", "exodia")
POOL_ALIASES = {"deck": "deck", "pow": "pow", "sapow": "pow", "bcd": "bcd", "tec": "tec", "satec": "tec"}


# --- writing ----------------------------------------------------------------

def _type_value(t: int):
    return TYPE_NAMES[t] if 0 <= t < len(TYPE_NAMES) else t


def _attribute_value(a: int):
    return ATTRIBUTE_NAMES[a] if 0 <= a < len(ATTRIBUTE_NAMES) else a


def _star_value(s: int):
    return STAR_NAMES[s] if 1 <= s < len(STAR_NAMES) else s


def _card_fields(card, base, everything=False) -> dict:
    out = {}
    if everything or card.name != base.name:
        out["name"] = card.name
    if everything or card.description != base.description:
        out["description"] = card.description
    if everything or card.attack != base.attack:
        out["attack"] = card.attack
    if everything or card.defense != base.defense:
        out["defense"] = card.defense
    if everything or card.type != base.type:
        out["type"] = _type_value(card.type)
    if everything or card.attribute != base.attribute:
        out["attribute"] = _attribute_value(card.attribute)
    if everything or card.level != base.level:
        out["level"] = card.level
    if everything or (card.star1, card.star2) != (base.star1, base.star2):
        out["stars"] = [_star_value(card.star1), _star_value(card.star2)]
    return out


def build_cards(project: Project) -> list:
    entries = []
    for cid in sorted(project.retail.cards):
        card, retail = project.cards[cid], project.retail.cards[cid]
        fields = _card_fields(card, retail)
        extra = project.card_extra.get(cid, {})
        if fields or extra:
            entry = {"replace": cid}
            entry.update(fields)
            entry.update(extra)
            entries.append(entry)
    for cid in sorted(project.added):
        added = project.added[cid]
        card = project.cards[cid]
        base = project.cards[added.base]
        entry = {"copy": added.base, "id": added.key}
        fields = {"name": card.name}
        fields.update(_card_fields(card, base))     # what is left out is the base's, as the port has it
        if card.is_monster() != base.is_monster() or (not base.is_monster() and card.type != base.type):
            fields.pop("type", None)        # the port keeps the base's side; validation says so
        entry.update(fields)
        if not added.drops:
            entry["drops"] = False
        if added.opponents:
            entry["opponents"] = True
        entry.update(added.extra)
        entries.append(entry)
    return entries


def build_fusions(project: Project) -> list:
    rules = []
    retail = project.retail.fusions
    for pair in sorted(set(retail) | set(project.fusions)):
        now = project.fusions.get(pair)
        if retail.get(pair) == now:
            continue
        rules.append({"with": [project.ref(pair[0]), project.ref(pair[1])],
                      "result": project.ref(now) if now else None})
    return rules + project.kept["fusions"]


def build_equips(project: Project) -> list:
    entries = []
    retail = {e: set(m) for e, m in project.retail.equips.items()}
    for equip in sorted(set(retail) | set(project.equips)):
        before, after = retail.get(equip, set()), project.equips.get(equip, set())
        if before == after:
            continue
        add, remove = after - before, before - after
        entry = {"card": project.ref(equip)}
        if before and len(after) < len(add) + len(remove):
            entry["replace"] = True
            entry["add"] = [project.ref(m) for m in sorted(after)]
            entries.append(entry)
            continue
        # A whole monster type allowed (or taken away) is written as the type;
        # within an entry a named card still goes over its type.
        add_types, remove_types = [], []
        for t in range(TYPE_MAGIC):
            members = {cid for cid, card in project.cards.items() if card.type == t}
            if project.resolve(TYPE_NAMES[t]):
                continue        # a card of that name: the port would read the card
            if not members:
                continue
            if len(members & add) >= 3 and len(members - after) < len(members & add):
                add_types.append(TYPE_NAMES[t])
                add -= members
                remove |= members - after       # the type's cards it may not equip, named
            elif len(members & remove) >= 3 and len(members & after) < len(members & remove):
                remove_types.append(TYPE_NAMES[t])
                remove -= members
                add |= members & after
        if add or add_types:
            entry["add"] = add_types + [project.ref(m) for m in sorted(add)]
        if remove or remove_types:
            entry["remove"] = remove_types + [project.ref(m) for m in sorted(remove)]
        entries.append(entry)
    return entries + project.kept["equips"]


def build_rituals(project: Project) -> list:
    entries = []
    retail = project.retail.rituals
    for ritual in sorted(set(retail) | set(project.rituals)):
        now = project.rituals.get(ritual)
        if retail.get(ritual) == now:
            continue
        if now is None:
            entries.append({"card": project.ref(ritual), "result": None})
        else:
            entries.append({"card": project.ref(ritual), "tributes": [project.ref(t) for t in now[:3]],
                            "result": project.ref(now[3])})
    return entries + project.kept["rituals"]


def _duelist_key(d: int) -> str:
    return DUELIST_NAMES[d] if d else "0"


def _pool_body(project: Project, listed: dict, replace: bool, kept: dict) -> dict:
    body = {"replace": True} if replace else {}
    for cid, weight in sorted(listed.items(), key=lambda item: (-item[1], item[0])):
        body[str(project.ref(cid))] = weight
    body.update(kept)
    return body


def _pool_edits(project: Project, pool: str):
    """{duelist key: body} for one kind of pool. An edit that turns every
    opponent's pool into the edited one (say, one card taken out
    everywhere) is written once, as "all", before the opponents' own."""
    deck = pool == "deck"
    count = len(project.pools)
    retail = [project.retail.pools[d][pool] for d in range(count)]
    edited = [{c: w for c, w in project.pools[d][pool].items() if w} for d in range(count)]
    edits = [poolmath.edit_for(retail[d], edited[d], deck) for d in range(count)]
    out = {}
    bases = retail
    candidates = {}
    for edit in edits:
        if edit and not edit[1]:
            key = tuple(sorted(edit[0].items()))
            candidates[key] = candidates.get(key, 0) + 1
    for key, uses in sorted(candidates.items(), key=lambda item: -item[1]):
        if uses < 2:
            break
        listed = dict(key)
        after = [poolmath.apply_edit(retail[d], listed, False, deck) for d in range(count)]
        if any(a is None for a in after):
            continue
        later = [poolmath.edit_for(after[d], edited[d], deck) for d in range(count)]
        if sum(1 for e in later if e) + 1 < sum(1 for e in edits if e):
            out["all"] = _pool_body(project, listed, False, {})
            bases, edits = after, later
        break
    for d in range(count):
        kept = project.kept_pools.get((d, pool), {})
        if edits[d] is None and not kept:
            continue
        listed, replace = edits[d] if edits[d] else ({}, False)
        out[_duelist_key(d)] = _pool_body(project, listed, replace, kept)
    return out


def build_pools(project: Project):
    decks = _pool_edits(project, "deck")
    drops = {}
    for pool in ("pow", "bcd", "tec"):
        for name, body in _pool_edits(project, pool).items():
            drops.setdefault(name, {})[pool] = body
    if "all" in drops:     # "all" first, so the opponents' own edits go over it
        drops = {"all": drops.pop("all"), **drops}
    return drops, decks


def build(project: Project) -> dict:
    """The mod.json object: the mod's own keys, then only what differs."""
    info = project.info
    manifest = {"id": info.id, "name": info.name}
    for key in ("version", "author", "description"):
        if getattr(info, key):
            manifest[key] = getattr(info, key)
    manifest.update(project.other)
    if info.settings:
        manifest["settings"] = info.settings
    cards = build_cards(project)
    if cards:
        manifest["cards"] = cards
    for key, builder in (("fusions", build_fusions), ("equips", build_equips), ("rituals", build_rituals)):
        rules = builder(project)
        if rules:
            manifest[key] = rules
    drops, decks = build_pools(project)
    if drops:
        manifest["drops"] = drops
    if decks:
        manifest["decks"] = decks
    return manifest


def _format(value, indent: int) -> str:
    one_line = json.dumps(value, ensure_ascii=False)
    if not isinstance(value, (dict, list)) or not value:
        return one_line
    pad = " " * (indent + 4)
    # A rule, a card entry or a list of names reads best on one line if it fits.
    if len(one_line) + indent <= 110 and (isinstance(value, list) or indent >= 8):
        return one_line
    if isinstance(value, list):
        items = [pad + _format(item, indent + 4) for item in value]
        return "[\n" + ",\n".join(items) + "\n" + " " * indent + "]"
    items = [pad + json.dumps(key, ensure_ascii=False) + ": " + _format(item, indent + 4) for key, item in value.items()]
    return "{\n" + ",\n".join(items) + "\n" + " " * indent + "}"


def dumps(manifest: dict) -> str:
    """JSON laid out as the example mods are: four spaces, and each rule or
    card entry on a line of its own when it fits."""
    return _format(manifest, 0) + "\n"


# --- reading ----------------------------------------------------------------

def _choice(value, names):
    """cards.c choice(): a number, or one of the names in any case; -1."""
    if isinstance(value, bool):
        return -1
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        for i, name in enumerate(names):
            if name and value.lower() == name.lower():
                return i
        if value.strip().lstrip("-").isdigit():
            return int(value)
    return -1


def _number(value, default=-1):
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        try:
            return int(text, 16) if text.startswith("0x") else int(text)
        except ValueError:
            return default
    return default


def _clamp(value, low, high):
    return max(low, min(high, value))


def _apply_fields(card, entry: dict, is_replace: bool, messages: list, where: str):
    name = entry.get("name")
    if isinstance(name, str) and name:
        card.name = name
    text = entry.get("description")
    if isinstance(text, str) and text:
        card.description = text
    value = _number(entry.get("attack"))
    if value >= 0:
        card.attack = _clamp(value // 10, 0, 0x1FF) * 10
    value = _number(entry.get("defense"))
    if value >= 0:
        card.defense = _clamp(value // 10, 0, 0x1FF) * 10
    if "type" in entry:
        value = _choice(entry["type"], TYPE_NAMES)
        if value >= 0:
            value = _clamp(value, 0, 23)
            monster = card.type < TYPE_MAGIC
            if not is_replace and (value >= TYPE_MAGIC if monster else value != card.type):
                messages.append(f"{where}: a copy keeps its base's side (monster or not); \"type\" left out")
            else:
                card.type = value
    stars = entry.get("stars")
    if isinstance(stars, list) and len(stars) == 2:
        first, second = _choice(stars[0], STAR_NAMES), _choice(stars[1], STAR_NAMES)
        if first >= 0:
            card.star1 = _clamp(first, 0, 10)
        if second >= 0:
            card.star2 = _clamp(second, 0, 10)
    value = _number(entry.get("level"))
    if value >= 0:
        card.level = _clamp(value, 0, 12)
    if "attribute" in entry:
        value = _choice(entry["attribute"], ATTRIBUTE_NAMES)
        if value >= 0:
            card.attribute = _clamp(value, 0, 15)


def _base_id(project: Project, value) -> int:
    if isinstance(value, str) and value and not value[0].isdigit():
        return project.names.find(value)
    return _number(value, 0)


def read_cards(project: Project, entries, messages: list):
    if entries is None:
        return
    if not isinstance(entries, list):
        messages.append("\"cards\" is not an array; left out")
        return
    for index, entry in enumerate(entries):
        where = f"cards[{index}]"
        if not isinstance(entry, dict):
            messages.append(f"{where} is not an object; left out")
            continue
        is_replace = "replace" in entry
        base = _base_id(project, entry.get("replace") if is_replace else entry.get("copy"))
        if not 1 <= base <= CARD_COUNT:
            messages.append(f"{where}: \"{'replace' if is_replace else 'copy'}\" must name a card of the disc, 1 to 722")
            continue
        if is_replace:
            _apply_fields(project.cards[base], entry, True, messages, where)
            extra = {k: entry[k] for k in REPLACE_EXTRA if k in entry}
            unknown = [k for k in entry if k not in extra and k not in (
                "replace", "name", "description", "attack", "defense", "type", "attribute", "level", "stars")]
            if unknown:
                messages.append(f"{where}: keys a replace does not use, dropped: {', '.join(unknown)}")
            if extra:
                project.card_extra.setdefault(base, {}).update(extra)
            continue
        key = entry.get("id")
        if not isinstance(key, str) or not key:
            key = f"entry-{index}"
        if len(key) > 80 or not KEY_RE.match(key):
            messages.append(f"{where}: invalid stable id; left out")
            continue
        if any(a.key == key for a in project.added.values()):
            messages.append(f"{where}: duplicate card identity {key}; left out")
            continue
        cid = project.add_card(base, key)
        _apply_fields(project.cards[cid], entry, False, messages, where)
        added = project.added[cid]
        added.drops = bool(entry.get("drops", True))
        added.opponents = bool(entry.get("opponents", False))
        added.extra = {k: v for k, v in entry.items() if k not in (
            "copy", "id", "name", "description", "attack", "defense", "type", "attribute", "level", "stars",
            "drops", "opponents")}
        if _number(entry.get("count"), 1) != 1 or entry.get("count_setting"):
            messages.append(f"{where}: adds several cards (\"count\"); the editor shows the first and keeps the count")


def read_fusions(project: Project, rules, messages: list):
    if rules is None:
        return
    if not isinstance(rules, list):
        messages.append("\"fusions\" is not an array; left out")
        return
    set_rules, removed = {}, set()
    for i, rule in enumerate(rules):
        where = f"fusions[{i}]"
        if not isinstance(rule, dict):
            messages.append(f"{where} is not an object; left out")
            continue
        if "remove" in rule:
            cid = project.resolve(rule["remove"])
            if cid:
                removed.add(cid)
            else:
                messages.append(f"{where}: no card {rule['remove']!r}; kept as written")
                project.kept["fusions"].append(rule)
            continue
        with_ = rule.get("with")
        if not isinstance(with_, list) or len(with_) != 2:
            messages.append(f"{where}: \"with\" names two cards; left out")
            continue
        a, b = project.resolve(with_[0]), project.resolve(with_[1])
        result = rule.get("result", "missing")
        if result == "missing":
            messages.append(f"{where}: \"result\" is a card, or null to forbid the fusion; left out")
            continue
        made = 0 if result is None or result == 0 else project.resolve(result)
        if not a or not b or (result not in (None, 0) and not made):
            messages.append(f"{where}: names a card the editor cannot place; kept as written")
            project.kept["fusions"].append(rule)
            continue
        set_rules[Project.pair(a, b)] = made
    if removed:
        for pair, result in list(project.fusions.items()):
            if result in removed and project.retail.fusions.get(pair) == result:
                del project.fusions[pair]
    for pair, made in set_rules.items():
        project.set_fusion(pair[0], pair[1], made)


def _expand_target(project: Project, value):
    """A card, or every monster of a type; (ids, is_type)."""
    if isinstance(value, str) and type_named(value) >= 0 and project.resolve(value) <= 0:
        t = type_named(value)
        return {cid for cid, card in project.cards.items() if card.type == t}, True
    cid = project.resolve(value)
    return ({cid} if cid else set()), False


def read_equips(project: Project, entries, messages: list):
    if entries is None:
        return
    if not isinstance(entries, list):
        messages.append("\"equips\" is not an array; left out")
        return
    for i, entry in enumerate(entries):
        where = f"equips[{i}]"
        if not isinstance(entry, dict):
            messages.append(f"{where} is not an object; left out")
            continue
        equip = project.resolve(entry.get("card"))
        if not equip:
            messages.append(f"{where}: no card {entry.get('card')!r}; kept as written")
            project.kept["equips"].append(entry)
            continue
        if project.cards[equip].type != 23:
            messages.append(f"{where}: \"card\" is not an equip card; left out")
            continue
        now = set(project.equips.get(equip, set()))
        if entry.get("replace") is True:
            now = set()
        unplaced = False
        # Within one entry a card is surer than a type: types first, then cards.
        for is_type_pass in (True, False):
            for allow, key in ((True, "add"), (False, "remove")):
                for target in entry.get(key, []) or []:
                    ids, is_type = _expand_target(project, target)
                    if is_type != is_type_pass:
                        continue
                    if not ids and not is_type:
                        unplaced = True
                        continue
                    now = now | ids if allow else now - ids
        if unplaced:
            messages.append(f"{where}: names cards the editor cannot place; those are left out")
        if entry.get("replace") is True or now != project.equips.get(equip, set()):
            project.equips[equip] = now


def read_rituals(project: Project, entries, messages: list):
    if entries is None:
        return
    if not isinstance(entries, list):
        messages.append("\"rituals\" is not an array; left out")
        return
    for i, entry in enumerate(entries):
        where = f"rituals[{i}]"
        if not isinstance(entry, dict):
            continue
        ritual = project.resolve(entry.get("card"))
        if not ritual or ritual > CARD_COUNT or project.cards[ritual].type != 22:
            messages.append(f"{where}: \"card\" must be one of the disc's ritual cards; left out")
            continue
        if "result" in entry and entry["result"] is None:
            project.rituals.pop(ritual, None)
            continue
        tributes = entry.get("tributes")
        if not isinstance(tributes, list) or len(tributes) != 3:
            messages.append(f"{where}: \"tributes\" names three monsters; left out")
            continue
        ids = [project.resolve(t) for t in tributes] + [project.resolve(entry.get("result"))]
        if not all(ids):
            messages.append(f"{where}: names a card the editor cannot place; kept as written")
            project.kept["rituals"].append(entry)
            continue
        project.rituals[ritual] = tuple(ids)


def _read_pool(project: Project, where, duelists, pool, body, messages):
    if not isinstance(body, dict):
        messages.append(f"{where}: a pool is an object of cards and their weights; left out")
        return
    listed, kept = {}, {}
    for name, weight in body.items():
        if name == "replace":
            continue
        if isinstance(weight, bool) or not isinstance(weight, int) or weight < 0:
            messages.append(f"{where} \"{name}\": a weight is a whole number, 0 or more; left out")
            continue
        cid = project.resolve(name)
        if not cid:
            messages.append(f"{where} \"{name}\": no such card; kept as written")
            kept[name] = weight
            continue
        listed[cid] = min(weight, 0xFFFF)
    replace = body.get("replace") is True
    for d in duelists:
        if kept:
            project.kept_pools.setdefault((d, pool), {}).update(kept)
        if not listed and not replace:
            continue
        result = poolmath.apply_edit(project.pools[d][pool], listed, replace, pool == "deck")
        if result is None:
            messages.append(f"{where}: {DUELIST_NAMES[d]}'s {pool} left as it was (the port refuses this edit)")
        else:
            project.pools[d][pool] = result


def read_pools(project: Project, table, decks: bool, messages: list):
    if table is None:
        return
    label = "decks" if decks else "drops"
    if not isinstance(table, dict):
        messages.append(f"\"{label}\" is an object of opponents; left out")
        return
    for name, entry in table.items():
        if same_all(name):
            duelists = list(range(len(project.pools)))
        else:
            d = duelist_named(name)
            if d < 0:
                messages.append(f"{label}: no opponent \"{name}\"; left out")
                continue
            duelists = [d]
        if decks:
            _read_pool(project, f"decks \"{name}\"", duelists, "deck", entry, messages)
            continue
        if not isinstance(entry, dict):
            messages.append(f"drops \"{name}\": an object of pools (pow, bcd, tec); left out")
            continue
        for pool_name, body in entry.items():
            pool = POOL_ALIASES.get("".join(c for c in pool_name.lower() if c.isalnum()))
            if pool in (None, "deck"):
                messages.append(f"drops \"{name}\" \"{pool_name}\": the pools are pow, bcd and tec; left out")
                continue
            _read_pool(project, f"drops \"{name}\" \"{pool_name}\"", duelists, pool, body, messages)


def same_all(name: str) -> bool:
    return "".join(c for c in name.lower() if c.isalnum()) == "all"


def apply(project: Project, manifest: dict, messages: list = None, default_id: str = None) -> list:
    """Lay a mod.json over the project (which should be retail): what the
    editor understands becomes edits, the rest is kept as written. A mod
    with no "id" is named after its folder, as the port does."""
    messages = [] if messages is None else messages
    if not isinstance(manifest, dict):
        raise ValueError("mod.json is not a JSON object")
    info = ModInfo(id=default_id or ModInfo.id)
    for key in INFO_KEYS:
        value = manifest.get(key)
        if isinstance(value, str):
            setattr(info, key, value)
    settings = manifest.get("settings")
    info.settings = settings if isinstance(settings, list) else []
    project.info = info
    project.other = {k: v for k, v in manifest.items() if k not in INFO_KEYS and k not in TABLE_KEYS}
    read_cards(project, manifest.get("cards"), messages)
    read_fusions(project, manifest.get("fusions"), messages)
    read_equips(project, manifest.get("equips"), messages)
    read_rituals(project, manifest.get("rituals"), messages)
    read_pools(project, manifest.get("drops"), False, messages)
    read_pools(project, manifest.get("decks"), True, messages)
    return messages


# --- folders ------------------------------------------------------------------

def read_json(path: Path):
    text = Path(path).read_text(encoding="utf-8-sig")
    return json.loads(text)


def open_mod(retail: GameData, folder) -> tuple:
    """(project, messages): retail with the mod folder's mod.json on top."""
    folder = Path(folder)
    project = Project(retail)
    messages = apply(project, read_json(folder / "mod.json"), default_id=folder.name)
    project.source_dir = folder
    return project, messages


def is_game_folder(folder: Path) -> bool:
    folder = Path(folder)
    return (folder / "SLUS_014.11").exists() or (folder / "DATA" / "WA_MRG.MRG").exists() or \
        any(p.suffix.lower() in (".bin", ".cue") and p.stat().st_size > 100_000_000
            for p in folder.glob("*") if p.is_file())


def save_mod(project: Project, folder, manifest: dict = None) -> Path:
    """Write the mod folder: mod.json, and when it is a new place, the files
    of the folder the mod was opened from (art, text, textures...)."""
    folder = Path(folder)
    if folder.exists() and is_game_folder(folder):
        raise ValueError(f"{folder} holds game files; the editor writes mod folders only")
    folder.mkdir(parents=True, exist_ok=True)
    source = project.source_dir
    if source and Path(source).resolve() != folder.resolve() and Path(source).is_dir():
        for item in Path(source).rglob("*"):
            if item.is_file() and item.name != "mod.json":
                target = folder / item.relative_to(source)
                if not target.exists():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(item, target)
    manifest = build(project) if manifest is None else manifest
    path = folder / "mod.json"
    temporary = folder / "mod.json.tmp"
    temporary.write_text(dumps(manifest), encoding="utf-8", newline="\n")
    temporary.replace(path)
    project.source_dir = folder
    return path
