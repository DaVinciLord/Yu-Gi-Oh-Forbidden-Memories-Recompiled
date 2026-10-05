"""Monster effects (notes/more-cards.md, "Monster effects"): what a card's
"monster_effects" make a monster do on the field, as the game reads them
(src/pc/cards/monster_effects.c). The list lives in the card's mod.json
entry, so the editor keeps it there (card_extra, or an added card's extra)."""
from __future__ import annotations

from .gamedata import ATTRIBUTE_NAMES, TYPE_NAMES, TYPE_MAGIC

# The game's names, in the order of its enums, and the editor's for them.
WHEN = ("summon", "flip", "draw", "combat", "destroyed", "face_up")
WHEN_LABELS = ("On summon", "On flip", "On draw phase", "Before combat", "When destroyed", "While face up")
WHEN_HINTS = (
    "Put on the field, face up or face down (the CPU puts its monsters down face down): played, fused or a "
    "ritual's monster.",
    "Turned face up: it attacks or is attacked face down, or a reveal (Swords, Dark-piercing Light).",
    "At the start of its owner's every turn, while it is face up.",
    "It attacks or is attacked, before the damage (no trap sprang). Boosts last the battle.",
    "Destroyed by a battle or an effect (not when used for a fusion or a ritual).",
    "All the while it is face up on the field: a boost that goes when it does.",
)
DO = ("magic", "boost", "heal", "damage")
DO_LABELS = ("Magic card effect", "Boost ATK/DEF", "Heal its owner's LP", "Damage the opponent's LP")
TARGET = ("self", "own", "others", "opponent", "all", "battle")
TARGET_LABELS = ("This card", "Its owner's monsters", "Its owner's other monsters", "The opponent's monsters",
                 "Every monster", "The monster it battles")
# The disc's magic cards whose effect a monster may use: Magic cards whose
# effect group does something at play time and asks nothing (no ritual).
MAGIC = (320, 329, 330, 331, 332, 333, 334, 335, 336, 337, 338, 339, 340, 341, 342, 343, 344, 345, 346, 347, 348,
         349, 350, 653, 655, 656, 660, 661, 662, 663, 664, 669, 672)
AMOUNT_MAX = 9999
BOOST_MAX = 9999
MAX_EFFECTS = 8


def allowed(when: str, do: str, target: str | None = None) -> bool:
    """What the game takes (monster_effects.c MonsterEffect_Allowed)."""
    if when == "face_up":
        return do == "boost" and target != "battle"
    if when == "combat":
        return do in ("heal", "damage") or (do == "boost" and target in ("self", "battle"))
    if do != "boost":
        return True
    return target != "battle" and not (when == "destroyed" and target == "self")


def actions(when: str) -> list:
    return [do for do in DO if allowed(when, do, "self" if when != "destroyed" else "own")]


def targets(when: str) -> list:
    return [t for t in TARGET if allowed(when, "boost", t)]


def default_target(when: str) -> str:
    return "own" if when == "destroyed" else "self"


def _name(names, value) -> str | None:
    """A game name for `value` as the game reads it ("Face Up" is "face_up")."""
    if not isinstance(value, str):
        return None
    key = value.strip().lower().replace(" ", "_").replace("-", "_")
    return key if key in names else None


def normalize(effect: dict, resolve=None) -> dict | None:
    """The entry with its names in the game's spelling, or None when the
    game would leave it out. `resolve` turns a card reference into an id."""
    if not isinstance(effect, dict):
        return None
    when, do = _name(WHEN, effect.get("when")), _name(DO, effect.get("do"))
    target = _name(TARGET, effect.get("target")) if "target" in effect else (default_target(when) if when else None)
    if not when or not do or not target or not allowed(when, do, target):
        return None
    out = {"when": when, "do": do}
    if do == "magic":
        card = effect.get("card")
        card = resolve(card) if resolve and card is not None else card
        if card not in MAGIC:
            return None
        out["card"] = card
    elif do == "boost":
        out["target"] = target
        for key in ("attack", "defense"):
            value = effect.get(key, 0)
            if not isinstance(value, int) or isinstance(value, bool) or abs(value) > BOOST_MAX:
                return None
            if value:
                out[key] = value
        if "attack" not in out and "defense" not in out:
            return None
        if "type" in effect:
            t = effect["type"]
            t = TYPE_NAMES.index(t) if isinstance(t, str) and t in TYPE_NAMES else t
            if not isinstance(t, int) or not 0 <= t < TYPE_MAGIC:
                return None
            out["type"] = TYPE_NAMES[t]
        if "attribute" in effect:
            a = effect["attribute"]
            a = ATTRIBUTE_NAMES.index(a) if isinstance(a, str) and a in ATTRIBUTE_NAMES else a
            if not isinstance(a, int) or not 0 <= a < 6:
                return None
            out["attribute"] = ATTRIBUTE_NAMES[a]
    else:
        amount = effect.get("amount")
        if not isinstance(amount, int) or isinstance(amount, bool) or not 0 < amount <= AMOUNT_MAX:
            return None
        out["amount"] = amount
    return out


def problems(effects, resolve=None) -> list:
    """What the game would say of a card's "monster_effects"."""
    if effects is None:
        return []
    if not isinstance(effects, list):
        return ['"monster_effects" must be a list']
    out = []
    if len(effects) > MAX_EFFECTS:
        out.append(f"at most {MAX_EFFECTS} monster effects; the rest are left out")
    for n, effect in enumerate(effects[:MAX_EFFECTS]):
        if normalize(effect, resolve) is None:
            out.append(f"monster effect {n + 1} is not one the game takes ({describe_raw(effect)})")
    return out


def describe_raw(effect) -> str:
    return ", ".join(f"{k}: {v}" for k, v in effect.items()) if isinstance(effect, dict) else repr(effect)


def when_label(when: str) -> str:
    return WHEN_LABELS[WHEN.index(when)] if when in WHEN else str(when)


def describe(effect: dict, card_name=lambda cid: f"#{cid}") -> str:
    """What the effect does, in a line: "Raigeki", "Its owner's other
    Dragon monsters +500 ATK", "Heal its owner 800 LP"."""
    do = effect.get("do")
    if do == "magic":
        return f"{card_name(effect.get('card'))} (its effect)"
    if do == "heal":
        return f"Its owner gains {effect.get('amount')} LP"
    if do == "damage":
        return f"The opponent loses {effect.get('amount')} LP"
    target = effect.get("target", default_target(effect.get("when")))
    who = TARGET_LABELS[TARGET.index(target)] if target in TARGET else str(target)
    which = " ".join(str(effect[k]) for k in ("attribute", "type") if k in effect)
    if which:
        who += f" ({which} only)"
    stats = " ".join(f"{effect[k]:+d} {label}" for k, label in (("attack", "ATK"), ("defense", "DEF"))
                     if effect.get(k))
    lasting = " for the battle" if effect.get("when") == "combat" else ""
    return f"{who}: {stats}{lasting}"
