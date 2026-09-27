"""Importing a .ygomods package into a port mod.

A .ygomods file is the package the old static recompilation's in-game
editor exported: a ZIP of INI and text files and PNGs. Its layout, as the
files describe themselves:

  manifest.ini              format = YGOFM-MOD-PACKAGE, version, game, counts
  cards/<id>/card.ini       key = value: name, description ("|" breaks a line),
                            attack, defense, level, type, attribute, star1,
                            star2, price, password, equips (the complete list of
                            monsters an equip card fits), ritual ("a, b, c -> r"),
                            and keys for colours and scripted effects
  cards/<id>/art.png, thumb.png, title.png
  drop_table_edits.ini      [duelist] then "<card> = <POW>, <BCD>, <TEC>": the
                            card's weight in each drop band, the rest of the
                            band sharing the remainder (the port's own rule);
                            "card =" / "when =" a scripted reward
  drop_missing_cards.ini    the same format, for the "drop missing cards" option
  cpu-duelists.ini          [duelist] then "name =", "ai = 9 bytes", and
                            "<card> = <weight>": the whole deck pool
  duelists/<n>/portrait.png the Free Duel portrait
  fusion-edits.txt          "a<TAB>b<TAB>result" (0 removes), "clear" empties
                            the table first
  dialogue.txt              the campaign's text, in the recomp's own numbering
  card_shop.ini, mod_settings.ini

What the port has a key for becomes that key; the rest (scripted effects,
colours, AI bytes, the shop, the recomp's own settings) is listed in the
report. No code of that project is used here, only its files' format.
"""
from __future__ import annotations

import json
import re
import struct
import zipfile

from . import gamedata as g
from .model import Project, duelist_named, type_named
from .pools import apply_edit, normalize

BAND_NAMES = ("pow", "bcd", "tec")
PASSWORDS = 0xFB9800            # WA_MRG.MRG: per card u32 cost, u32 BCD password
FREE_DUEL_PORTRAITS = 0xF55000  # WA_MRG.MRG: 40 records of 0x980 bytes
KNOWN_CARD_KEYS = {"name", "description", "attack", "defense", "level", "type", "attribute", "star1", "star2",
                   "price", "password", "equips", "ritual"}
MAX_ENTRY = 8 << 20


class PackageError(Exception):
    pass


def parse_ini(text: str) -> list:
    """[(section or None, key, value)] of an INI file; ";" and "#" start comments."""
    out, section = [], None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line[0] in ";#":
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip()
            continue
        if "=" in line:
            key, value = line.split("=", 1)
            out.append((section, key.strip(), value.strip()))
    return out


def _int(text, default=None):
    try:
        return int(str(text).strip(), 0)
    except ValueError:
        return default


def _choice(text, names):
    text = str(text).strip()
    for i, name in enumerate(names):
        if name and text.lower() == name.lower():
            return i
    return _int(text, -1)


class Package:
    def __init__(self, path):
        try:
            self.zip = zipfile.ZipFile(path)
        except (zipfile.BadZipFile, OSError) as problem:
            raise PackageError(f"{path} is not a .ygomods package ({problem})")
        self.names = {n.replace("\\", "/"): n for n in self.zip.namelist()}
        for info in self.zip.infolist():
            if info.file_size > MAX_ENTRY or ".." in info.filename.replace("\\", "/").split("/"):
                raise PackageError(f"{info.filename}: an entry this importer will not read")
        manifest = dict((k, v) for _, k, v in parse_ini(self.text("manifest.ini") or ""))
        if manifest.get("format") != "YGOFM-MOD-PACKAGE":
            raise PackageError("manifest.ini does not say format = YGOFM-MOD-PACKAGE")
        self.manifest = manifest

    def has(self, name):
        return name in self.names

    def data(self, name):
        return self.zip.read(self.names[name]) if name in self.names else None

    def text(self, name):
        blob = self.data(name)
        return blob.decode("utf-8-sig", "replace") if blob is not None else None


def import_package(retail: g.GameData, retail_wa: bytes, path, mod_id="ygomods-import", name=None):
    """(project, report) for a .ygomods package over retail."""
    package = Package(path)
    try:
        return _import(package, retail, retail_wa, mod_id, name)
    finally:
        package.zip.close()


def _import(package, retail, retail_wa, mod_id, name):
    project = Project(retail)
    project.info.id = mod_id
    project.info.name = name or mod_id
    project.info.description = "Imported from a .ygomods package by the FM Editor."
    report = []
    unsupported = {}

    def unhandled(what, count=1):
        unsupported[what] = unsupported.get(what, 0) + count

    # --- cards ----------------------------------------------------------------
    card_ids = sorted({int(m.group(1)) for n in package.names for m in [re.match(r"cards/(\d+)/", n)] if m})
    patches = {}
    for cid in card_ids:
        if not 1 <= cid <= g.CARD_COUNT:
            unhandled(f"cards past 722 (card {cid})")
            continue
        card = project.cards[cid]
        values = {k: v for _, k, v in parse_ini(package.text(f"cards/{cid}/card.ini") or "")}
        if "name" in values and values["name"]:
            card.name = values["name"]
        if "description" in values:
            card.description = values["description"].replace("|", "\n")
        for key in ("attack", "defense", "level"):
            if _int(values.get(key)) is not None:
                setattr(card, key, _int(values[key]))
        if "type" in values:
            t = type_named(values["type"]) if not values["type"].isdigit() else int(values["type"])
            if t >= 0:
                card.type = t
        if "attribute" in values and _choice(values["attribute"], g.ATTRIBUTE_NAMES) >= 0:
            card.attribute = _choice(values["attribute"], g.ATTRIBUTE_NAMES)
        for key in ("star1", "star2"):
            if key in values and _choice(values[key], g.STAR_NAMES) >= 0:
                setattr(card, key, _choice(values[key], g.STAR_NAMES))
        if "equips" in values:
            monsters = {_int(x) for x in values["equips"].replace(";", ",").split(",") if _int(x)}
            project.equips[cid] = {m for m in monsters if m in project.cards}
        if "ritual" in values:
            match = re.match(r"\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*->\s*(\d+)", values["ritual"])
            if match:
                project.rituals[cid] = tuple(int(x) for x in match.groups())
            else:
                unhandled("ritual recipes it could not read")
        # Passwords and costs: a data patch of WA_MRG.MRG's table, when they change.
        if ("price" in values or "password" in values) and len(retail_wa or b"") >= PASSWORDS + 8 * (cid + 1):
            at = PASSWORDS + 8 * cid
            cost, code = struct.unpack_from("<II", retail_wa, at)
            new_cost = _int(values.get("price"), cost)
            password = values.get("password", "")
            new_code = int(password, 16) if re.fullmatch(r"\d{1,8}", password or "") else code
            if (new_cost, new_code) != (cost, code):
                patches[at] = struct.pack("<II", new_cost & 0xFFFFFFFF, new_code)
        for part, key in (("art.png", "art"), ("thumb.png", "thumbnail"), ("title.png", "title")):
            blob = package.data(f"cards/{cid}/{part}")
            if blob:
                path_in_mod = f"images/{cid:03d}-{part}"
                project.files[path_in_mod] = blob
                project.card_extra.setdefault(cid, {})[key] = path_in_mod
        for key in values:
            if key not in KNOWN_CARD_KEYS:
                unhandled(f"card key \"{key}\"")
    changed = sum(1 for cid in card_ids if cid in project.retail.cards and project.card_changed(cid))
    report.append(f"cards: {len(card_ids)} in the package, {changed} differ from retail")
    if patches:
        project.other.setdefault("data", []).append({"file": "\\DATA\\WA_MRG.MRG;1", "patch": [
            {"at": f"0x{at:X}", "bytes": blob.hex(" ").upper()} for at, blob in sorted(patches.items())]})
        report.append(f"cards: {len(patches)} passwords or starchip costs (\"price\") changed, as a data patch of "
                      "WA_MRG.MRG")

    # --- fusions ----------------------------------------------------------------
    text = package.text("fusion-edits.txt")
    if text is not None:
        count = 0
        for line in text.splitlines():
            line = line.split("#")[0].strip()
            if not line:
                continue
            if line.lower() == "clear":
                project.fusions = {}
                report.append("fusions: the package clears the disc's table first")
                continue
            parts = [_int(p) for p in re.split(r"[\t ,]+", line)]
            if len(parts) != 3 or None in parts:
                unhandled("fusion lines it could not read")
                continue
            a, b, result = parts
            if a in project.cards and b in project.cards and (result == 0 or result in project.cards):
                project.set_fusion(a, b, result or None)
                count += 1
        report.append(f"fusions: {count} edits read")

    # --- pools ------------------------------------------------------------------
    def drop_file(name, label):
        text = package.text(name)
        if text is None:
            return
        listed = {}
        for section, key, value in parse_ini(text):
            d = duelist_named(section or "")
            if section and section.lower().startswith("starchip reward"):
                unhandled("StarChip reward rules")
                continue
            if d < 0:
                unhandled(f"{label} sections naming no opponent")
                continue
            if key in ("card", "when"):
                unhandled("scripted rewards (card = / when =)")
                continue
            table = re.fullmatch(r"(pow|bcd|tec)_table", key)
            if table:
                pool = {}
                for item in value.split(","):
                    if ":" in item:
                        cid, weight = (_int(x) for x in item.split(":", 1))
                        if cid in project.cards and weight:
                            pool[cid] = weight
                if pool:
                    project.pools[d][table.group(1)] = normalize(pool)
                continue
            cid = _int(key)
            weights = [_int(x) for x in value.split(",")]
            if cid not in project.cards or len(weights) != 3 or None in weights:
                unhandled(f"{label} lines it could not read")
                continue
            for band, weight in zip(BAND_NAMES, weights):
                listed.setdefault((d, band), {})[cid] = weight
        refused = 0
        for (d, band), cards in listed.items():
            result = apply_edit(project.pools[d][band], cards)
            if result is None:
                refused += 1
            else:
                project.pools[d][band] = result
        report.append(f"drops: {label}: {len(listed)} pools edited" + (f", {refused} refused (no card left)" if refused else ""))

    settings = {k: v for _, k, v in parse_ini(package.text("mod_settings.ini") or "")}
    if package.has("drop_missing_cards.ini"):
        if settings.get("drop_missing_cards", "1") != "0":
            drop_file("drop_missing_cards.ini", "drop_missing_cards.ini")
        else:
            report.append("drops: drop_missing_cards.ini left out (its option is off in mod_settings.ini)")
    drop_file("drop_table_edits.ini", "drop_table_edits.ini")

    text = package.text("cpu-duelists.ini")
    if text is not None:
        decks, renamed = {}, {}
        for section, key, value in parse_ini(text):
            d = duelist_named(section or "")
            if d < 0:
                unhandled("cpu-duelists.ini sections naming no opponent")
                continue
            if key == "ai":
                if [x.strip() for x in value.split(",")]:
                    unhandled("AI profile bytes (ai =)")
                continue
            if key == "name":
                renamed[d] = value
                continue
            cid, weight = _int(key), _int(value)
            if cid in project.cards and weight is not None:
                decks.setdefault(d, {})[cid] = weight
        for d, pool in decks.items():
            result = apply_edit(project.pools[d]["deck"], {c: w for c, w in pool.items() if w}, replace=True, deck=True)
            if result is None:
                report.append(f"decks: {g.DUELIST_NAMES[d]}'s deck left as it was (fewer than 14 cards)")
            else:
                project.pools[d]["deck"] = result
        report.append(f"decks: {len(decks)} opponents' deck pools read")
        renamed = {d: n for d, n in renamed.items() if n != g.DUELIST_NAMES[d]}
        if renamed:
            listing = ["# Duelist names from a .ygomods package (notes/translation.md).", "", "@bank names", ""]
            for d, new in sorted(renamed.items()):
                listing += [f"[{0x8000 + 0x328 + d:04X}]", new.replace("{", "(").replace("}", ")") + "{end}", ""]
            project.files["text.txt"] = ("\n".join(listing) + "\n").encode("utf-8")
            project.other["text"] = "text.txt"
            report.append(f"text: {len(renamed)} opponents renamed, as a text listing (text.txt)")

    # --- portraits ---------------------------------------------------------------
    portraits = sorted(int(m.group(1)) for n in package.names
                       for m in [re.fullmatch(r"duelists/(\d+)/portrait\.png", n)] if m)
    if portraits:
        entries = []
        for d in portraits:
            if not 0 <= d < 40:
                continue
            record = FREE_DUEL_PORTRAITS + d * 0x980
            project.files[f"textures/portraits/freeduel-{d:02d}.png"] = package.data(f"duelists/{d}/portrait.png")
            entries.append({"file": f"portraits/freeduel-{d:02d}.png", "archive": "WA_MRG.MRG", "offset": record,
                            "words": 24, "rows": 48, "bpp": 8, "clut_offset": record + 0x900, "clut_entries": 64})
        project.files["textures/manifest.json"] = (json.dumps(entries, indent=2) + "\n").encode("utf-8")
        project.other["textures"] = "textures"
        report.append(f"portraits: {len(entries)} Free Duel portraits, as a texture pack (textures/)")

    # --- the rest -------------------------------------------------------------------
    if package.has("dialogue.txt"):
        unhandled("dialogue.txt (the recomp's own numbering of the game's codes; translate with "
                  "tools/pc/text_listing.py instead)")
    if package.has("card_shop.ini"):
        unhandled("card_shop.ini (the recomp's card shop)")
    if settings:
        unhandled("mod_settings.ini (the recomp's MODS and CHEATS rows)", len(settings))
    for what, count in sorted(unsupported.items()):
        report.append(f"not imported: {what}" + (f" ({count})" if count > 1 else ""))
    project.files["import-report.txt"] = ("\n".join(report) + "\n").encode("utf-8")
    return project, report
