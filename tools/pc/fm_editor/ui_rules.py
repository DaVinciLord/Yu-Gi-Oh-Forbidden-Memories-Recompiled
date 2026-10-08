"""What the game accepts in a mod's "ui" key and the title's "images"
(src/pc/platform/ui_config.c, title_config.c), checked before saving as
the Mods window would note it."""
from __future__ import annotations

from pathlib import PurePosixPath

ELEMENTS = ("lp_opponent", "lp_player", "field", "card_bar", "hand_cursor", "field_cursor")
KEYS = ("x", "y", "scale", "tint", "hide", "image", "width", "height", "label", "digits")
# ui_config.c `takes`: which way each moves. The game slides the LP halves
# and the FIELD box off the screen sideways (for a battle, the duel's end,
# Exodia), so they move up and down only and slide with the game's; the
# card bar stays where the game has it, its size too; only the LP halves
# have digits and words.
MOVES = {"lp_opponent": "y", "lp_player": "y", "field": "y", "card_bar": "", "hand_cursor": "xy",
         "field_cursor": "xy"}
SIZED = ("lp_opponent", "lp_player", "field", "hand_cursor", "field_cursor")
LABELLED = ("lp_opponent", "lp_player")
SCALE_MIN, SCALE_MAX = 25, 400
RANGES = {"x": (-400, 400), "y": (-300, 300), "scale": (SCALE_MIN, SCALE_MAX), "width": (0, 320), "height": (0, 240)}
# ui_config.c `slide_reach`, `own_reach`, `own_size`: how far a sliding one may
# reach from its middle and still be off the screen where the game slides it
# (the panel's middle at 384, 64 right of the screen; the box's at -36), how
# far the game's own pieces reach (the panel's half 32 and 8 for a fifth LP
# digit; the box 28), and each one's size.
SLIDE_REACH = {"lp_opponent": 64, "lp_player": 64, "field": 36}
OWN_REACH = {"lp_opponent": 40, "lp_player": 40, "field": 28}
OWN_SIZE = {"lp_opponent": (64, 20), "lp_player": (64, 20), "field": (56, 24), "card_bar": (320, 72),
            "hand_cursor": (16, 16), "field_cursor": (64, 64)}


def _scaled(d: int, scale: int) -> int:
    t = d * scale
    return (t + 50) // 100 if t >= 0 else -((-t + 50) // 100)


def _int(value, default=0) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else default


def reach(name: str, scale: int, picture: bool = False, width: int = 0, height: int = 0) -> int:
    """UiConfig_Reach: how far the element at `scale` reaches from its middle."""
    if picture:
        w, h = OWN_SIZE[name]
        width = width or (w * height // h if height else w)
        return _scaled(width - width // 2, scale)
    return _scaled(OWN_REACH.get(name, 0), scale)


def scale_max(name: str, picture: bool = False, width: int = 0, height: int = 0) -> int:
    """UiConfig_ScaleMax: the most size at which it still leaves the screen
    with the game's (SCALE_MAX for one that does not slide, 100 for the card
    bar)."""
    if name not in SIZED:
        return 100
    if name not in SLIDE_REACH:
        return SCALE_MAX
    scale = SCALE_MAX
    while scale > SCALE_MIN and reach(name, scale, picture, width, height) > SLIDE_REACH[name]:
        scale -= 1
    return scale


def element_scale_max(name: str, element: dict) -> int:
    """scale_max for what the element has: a picture of its own and its size."""
    picture = isinstance(element.get("image"), str) and bool(element.get("image"))
    return scale_max(name, picture, _int(element.get("width")) if picture else 0,
                     _int(element.get("height")) if picture else 0)
LABEL_MAX = 15
PICTURES_MAX = 8


def _colour(value) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return 0 <= value <= 0xFFFFFF
    if isinstance(value, str):
        text = value[1:] if value.startswith("#") else value
        return len(text) == 6 and all(c in "0123456789abcdefABCDEF" for c in text)
    return False


def _contained(name: str) -> bool:
    """paths.c Paths_Contained: relative, inside the mod."""
    return bool(name) and not name.startswith("/") and ".." not in PurePosixPath(name).parts and "\\" not in name


def check(project, has_file) -> list:
    """(level, where, message) for each thing the game would note;
    has_file(name) says whether the mod holds a file."""
    out = []
    ui = project.other.get("ui")
    if ui is not None:
        if not isinstance(ui, dict):
            out.append(("warning", "ui", "\"ui\" is an object"))
            ui = {}
        for key in ui:
            if key != "duel":
                out.append(("warning", f"ui.{key}", "unknown key (the game reads \"duel\")"))
        duel = ui.get("duel", {})
        if not isinstance(duel, dict):
            out.append(("warning", "ui.duel", "\"duel\" is an object of pictures by name"))
            duel = {}
        for name, element in duel.items():
            where = f"ui.duel.{name}"
            if name not in ELEMENTS:
                out.append(("warning", where, f"no duel picture \"{name}\" ({', '.join(ELEMENTS)})"))
                continue
            if not isinstance(element, dict):
                out.append(("warning", where, "an object of keys"))
                continue
            for key, value in element.items():
                if key not in KEYS:
                    out.append(("warning", where, f"unknown key \"{key}\""))
                elif key in ("x", "y", "scale") and not MOVES[name]:
                    out.append(("warning", where, f"the card bar stays where the game has it; \"{key}\" is left out"))
                elif key == "x" and "x" not in MOVES[name]:
                    out.append(("warning", where, "the game slides it off the screen sideways, so it keeps its "
                                                  "place across; \"x\" is left out (\"y\" moves it)"))
                elif key in ("label", "digits") and name not in LABELLED:
                    out.append(("warning", where, f"has no \"{key}\""))
                elif key in RANGES and (isinstance(value, bool) or not isinstance(value, int) or
                                        not RANGES[key][0] <= value <= RANGES[key][1]):
                    out.append(("warning", where, f"\"{key}\" is a whole number from {RANGES[key][0]} to "
                                                  f"{RANGES[key][1]}"))
                elif key in ("tint", "digits") and not _colour(value):
                    out.append(("warning", where, f"\"{key}\" is a colour, \"#RRGGBB\""))
                elif key == "label" and (not isinstance(value, str) or len(value) > LABEL_MAX):
                    out.append(("warning", where, f"\"label\" is at most {LABEL_MAX} letters"))
                elif key == "hide" and not isinstance(value, bool):
                    out.append(("warning", where, "\"hide\" is true or false"))
                elif key == "image" and value:
                    if not isinstance(value, str) or not _contained(value):
                        out.append(("warning", where, "\"image\" is a PNG inside the mod"))
                    elif not has_file(value):
                        out.append(("warning", where, f"{value} is not in the mod"))
            scale = element.get("scale", 100)
            if name in SLIDE_REACH and isinstance(scale, int) and not isinstance(scale, bool) and \
                    SCALE_MIN <= scale <= SCALE_MAX:
                most = element_scale_max(name, element)
                picture = isinstance(element.get("image"), str) and bool(element.get("image"))
                if scale > most:
                    out.append(("warning", where, f"at {scale}% it would not leave the screen with the game's; "
                                                  f"drawn at {most}%"))
                elif picture and reach(name, scale, True, _int(element.get("width")),
                                       _int(element.get("height"))) > SLIDE_REACH[name]:
                    out.append(("warning", where, "\"image\" is too wide to leave the screen with the game's; "
                                                  "it is drawn narrower"))
    title = project.other.get("title")
    images = title.get("images") if isinstance(title, dict) else None
    if images is not None:
        if not isinstance(images, list):
            out.append(("warning", "title.images", "a list of pictures"))
            images = []
        if len(images) > PICTURES_MAX:
            out.append(("warning", "title.images", f"at most {PICTURES_MAX} pictures; the rest are left out"))
        for i, entry in enumerate(images):
            name = entry.get("image") if isinstance(entry, dict) else None
            if not isinstance(name, str) or not name:
                out.append(("warning", f"title.images[{i}]", "a picture without an \"image\""))
            elif not _contained(name):
                out.append(("warning", f"title.images[{i}]", "\"image\" is a PNG inside the mod"))
            elif not has_file(name):
                out.append(("warning", f"title.images[{i}]", f"{name} is not in the mod"))
    return out
