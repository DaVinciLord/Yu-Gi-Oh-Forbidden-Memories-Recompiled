"""A mod's "limits" (notes/gameplay-tables.md, "Limits"): the numbers the game
caps, which a mod may raise or lower. The port reads them in
src/pc/cards/tables.c (read_limits); the checks here are that file's, so a
problem shows in the editor rather than as a line in the Mods window.

The mod.json shape:

    "limits": {
        "stats": 30000, "attack": 30000, "defense": 30000,
        "life_points": 16000,                   or
        "life_points": {"start": 16000, "player": 8000, "opponent": 16000, "max": 30000,
                        "duelists": {"Heishin": 20000, "Seto": {"player": 8000, "opponent": 12000}}},
        "two_player": {"start": 8000, "max": 30000, "step": 500},
        "starchips": 999999, "chest": 250, "free_duel_record": 999, "two_player_record": 9999
    }

The editor keeps it in Project.other["limits"] as written; the Limits tab
turns it into a form (`flatten`) and back (`build`).
"""
from __future__ import annotations

from .model import duelist_named, same_letters

STAT_MAX = 32767            # s16 ATK/DEF in the duel's card records
LIFE_POINTS_MAX = 32767     # s16 LP in each side's record
CHEST_MAX = 255             # a byte a card in the chest
RECORD_MAX = 32767          # s16 Free Duel wins and losses
TWO_PLAYER_RECORD_MAX = 65535
STARCHIPS_MAX = 99999999    # eight digits on screen

# The simple fields and the advanced ones, in the form's order: key, label,
# the game's own value (what an empty field means), lowest, highest, and what
# keeping more than the highest would take.
FIELDS = (
    ("stats", "ATK and DEF cap", 9999, 0, STAT_MAX, "a 16-bit number in every card record"),
    ("life_points.start", "Starting LP (both sides)", 8000, 1, LIFE_POINTS_MAX, "a 16-bit number in each side's record"),
    ("life_points.max", "Most LP healing reaches", None, 1, LIFE_POINTS_MAX, "a 16-bit number in each side's record"),
)
ADVANCED = (
    ("attack", "ATK cap", 9999, 0, STAT_MAX, "a 16-bit number in every card record"),
    ("defense", "DEF cap", 9999, 0, STAT_MAX, "a 16-bit number in every card record"),
    ("life_points.player", "Player's starting LP", 8000, 1, LIFE_POINTS_MAX, "a 16-bit number in each side's record"),
    ("life_points.opponent", "Opponent's starting LP", 8000, 1, LIFE_POINTS_MAX,
     "a 16-bit number in each side's record"),
    ("two_player.start", "2P duel: LP it starts at", 8000, 1, LIFE_POINTS_MAX, "a 16-bit number in each side's record"),
    ("two_player.max", "2P duel: most LP to pick", 8000, 1, LIFE_POINTS_MAX, "a 16-bit number in each side's record"),
    ("two_player.step", "2P duel: LP a step", 500, 1, LIFE_POINTS_MAX, "a 16-bit number in each side's record"),
    ("starchips", "Most starchips", 999999, 0, STARCHIPS_MAX, "eight digits on screen"),
    ("chest", "Copies of a card in the chest", 250, 1, CHEST_MAX, "a byte a card in the memory card's save"),
    ("free_duel_record", "Free Duel wins/losses", 999, 1, RECORD_MAX, "a 16-bit number in the save"),
    ("two_player_record", "2P wins/losses", 9999, 1, TWO_PLAYER_RECORD_MAX, "a 16-bit number in the save"),
)
ALL_FIELDS = FIELDS + ADVANCED
TOP_KEYS = ("stats", "attack", "defense", "life_points", "two_player", "starchips", "chest", "free_duel_record",
            "two_player_record")
LIFE_KEYS = ("start", "player", "opponent", "max", "duelists")
TWO_PLAYER_KEYS = ("start", "max", "step")


def _get(limits: dict, path: str):
    """The value at "a.b" in limits; a number "life_points" is its "start"."""
    top, _, sub = path.partition(".")
    value = limits.get(top) if isinstance(limits, dict) else None
    if not sub:
        return value
    if top == "life_points" and isinstance(value, int) and not isinstance(value, bool):
        return value if sub == "start" else None
    return value.get(sub) if isinstance(value, dict) else None


def flatten(limits) -> dict:
    """The form's values: "path": number for each field the mod sets, and
    "duelists": {name: (player or None, opponent or None)}."""
    limits = limits if isinstance(limits, dict) else {}
    flat = {}
    for key, *_ in ALL_FIELDS:
        value = _get(limits, key)
        if isinstance(value, int) and not isinstance(value, bool):
            flat[key] = value
    life = limits.get("life_points")
    duelists = life.get("duelists") if isinstance(life, dict) else None
    flat["duelists"] = {}
    if isinstance(duelists, dict):
        for name, entry in duelists.items():
            if isinstance(entry, int) and not isinstance(entry, bool):
                flat["duelists"][name] = (None, entry)
            elif isinstance(entry, dict):
                flat["duelists"][name] = (entry.get("player"), entry.get("opponent"))
    return flat


def build(flat: dict, kept=None):
    """"limits" from the form's values; None when nothing is set. What the
    form does not show (a key the editor does not know) is kept from `kept`,
    the mod's own "limits" as it was read."""
    kept = kept if isinstance(kept, dict) else {}
    out = {key: value for key, value in kept.items() if key not in TOP_KEYS}
    for key, *_ in ALL_FIELDS:
        value = flat.get(key)
        if value is None:
            continue
        top, _, sub = key.partition(".")
        if sub:
            out.setdefault(top, {})[sub] = value
        else:
            out[top] = value
    duelists = {}
    for name, (player, opponent) in (flat.get("duelists") or {}).items():
        if player is None and opponent is None:
            continue
        duelists[name] = opponent if player is None else {k: v for k, v in (("player", player),
                                                                            ("opponent", opponent)) if v is not None}
    if duelists:
        out.setdefault("life_points", {})["duelists"] = duelists
    life = out.get("life_points")
    if isinstance(life, dict) and set(life) == {"start"}:
        out["life_points"] = life["start"]      # the short form, as a person would write it
    return out or None


def check(limits) -> list:
    """(level, where, message) for what read_limits would note: "error" where
    it leaves a value out, "warning" where it holds one at the most the game
    keeps."""
    out = []
    if limits is None:
        return out
    if not isinstance(limits, dict):
        return [("error", "limits", "\"limits\" is an object: {\"stats\": 30000, \"life_points\": 16000, ...}")]
    for key in limits:
        if key not in TOP_KEYS:
            out.append(("error", key, f"no limit \"{key}\" ({', '.join(TOP_KEYS)})"))
    life = limits.get("life_points")
    if life is not None and (isinstance(life, bool) or not isinstance(life, (int, dict))):
        out.append(("error", "life_points", "a number (both sides' start) or an object of start, player, opponent, "
                                           "max and duelists"))
    two = limits.get("two_player")
    if two is not None and not isinstance(two, dict):
        out.append(("error", "two_player", "an object: {\"start\": 8000, \"max\": 8000, \"step\": 500}"))
    for key, label, retail, low, high, storage in ALL_FIELDS:
        value = _get(limits, key)
        if value is None:
            continue
        out += _number(key, value, low, high, storage)
    if isinstance(life, dict):
        for key in life:
            if key not in LIFE_KEYS:
                out.append(("error", f"life_points.{key}", f"no \"{key}\" ({', '.join(LIFE_KEYS)})"))
        duelists = life.get("duelists")
        if duelists is not None and not isinstance(duelists, dict):
            out.append(("error", "life_points.duelists", "an object of duelists and their LP"))
        for name, entry in (duelists.items() if isinstance(duelists, dict) else ()):
            where = f"life_points.duelists \"{name}\""
            if name.lower() != "all" and duelist_named(name) < 0:
                out.append(("warning", where, "not one of the disc's forty duelists: the game looks for it among "
                                              "the mods' added duelists"))
            if isinstance(entry, dict):
                for side in ("player", "opponent"):
                    if side in entry:
                        out += _number(f"{where} {side}", entry[side], 1, LIFE_POINTS_MAX,
                                       "a 16-bit number in each side's record")
            else:
                out += _number(where, entry, 1, LIFE_POINTS_MAX, "a 16-bit number in each side's record")
    if isinstance(two, dict):
        for key in two:
            if key not in TWO_PLAYER_KEYS:
                out.append(("error", f"two_player.{key}", f"no \"{key}\" (start, max, step)"))
        start, top, step = two.get("start", 8000), two.get("max", 8000), two.get("step", 500)
        if isinstance(start, int) and isinstance(top, int) and start > top:
            out.append(("warning", "two_player.start", f"past the most to pick ({top}): the choice starts at {top}"))
        if isinstance(step, int) and isinstance(top, int) and step > top:
            out.append(("warning", "two_player.step", f"past the most to pick ({top}): a step is {top}"))
    return out


def _number(where, value, low, high, storage) -> list:
    if not isinstance(value, int) or isinstance(value, bool):
        return [("error", where, f"a whole number, {low} to {high}, without quotes; left out")]
    if value < low:
        return [("error", where, f"at least {low}; left out")]
    if value > high:
        return [("warning", where, f"{value} is past the {high} the game keeps ({storage}); {high} is used")]
    return []
