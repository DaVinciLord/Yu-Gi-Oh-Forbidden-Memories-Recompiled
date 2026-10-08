"""What the game accepts in a mod's "ui" key and the title's "images"
(src/pc/platform/ui_config.c, title_config.c), checked before saving as
the Mods window would note it."""
from __future__ import annotations

from pathlib import PurePosixPath

ELEMENTS = ("lp_opponent", "lp_player", "field", "card_bar", "hand_cursor", "field_cursor")
KEYS = ("x", "y", "scale", "tint", "hide", "image", "width", "height", "label", "digits")
# ui_config.c `takes`: the card bar stays where the game has it; only the LP
# halves have digits and words.
PLACED = ("lp_opponent", "lp_player", "field", "hand_cursor", "field_cursor")
LABELLED = ("lp_opponent", "lp_player")
RANGES = {"x": (-400, 400), "y": (-300, 300), "scale": (25, 400), "width": (0, 320), "height": (0, 240)}
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
                elif key in ("x", "y", "scale") and name not in PLACED:
                    out.append(("warning", where, f"the card bar stays where the game has it; \"{key}\" is left out"))
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
