"""The UI tab's Title screen and Menus pages (notes/modding.md "The title
screen", "The title's menus"): the title drawn as the game draws it, from
the disc's own pictures (ui_assets.TitleArt) and the mod's "title" and
"menu" over them, as title_config.c reads them and title_screen.c and
title_menu.c lay them out.

Title screen: the background (the game's wall, a colour, a picture of the
mod's own), the logo, the copyright line and PUSH START BUTTON (moved,
coloured, hidden, or a picture instead), pictures the mod adds and lines of
words. Menus: both menus' buttons in their order -- the game's entries and
the mod's own -- each with its words or picture, what it does and where it
stands, and the menus' own background."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from . import pngio, ui_assets as ua
from .ui_tab import (ColourButton, Stage, as_int, colour_text, ensure, import_image, mod_image, section, set_member,
                     sized)
from .widgets import px

LAYER_NAMES = ("logo", "copyright", "prompt")
LAYER_TITLES = {"logo": "Logo", "copyright": "Copyright line", "prompt": "PUSH START BUTTON"}
ENTRY_NAMES = ["new_game", "load", "duel", "trade", "options", "campaign", "free_duel", "build_deck", "library",
               "password", "save"]
ENTRY_TITLES = ["NEW GAME", "LOAD", "2P DUEL", "TRADE", "OPTION", "CAMPAIGN", "FREE DUEL", "BUILD DECK", "LIBRARY",
                "PASSWORD", "SAVE"]
ACTIONS = ENTRY_NAMES + ["back", "notice", "quit", "debug_menu", "event", "none"]
ACTION_TITLES = {"back": "Back", "notice": "Show a notice", "quit": "Quit the game", "debug_menu": "Debug menu",
                 "event": "Code mod event", "none": "Nothing (a buzz)"}
SHOW = ["always", "press_start", "menu"]
SHOW_TITLES = {"always": "Always", "press_start": "With PUSH START", "menu": "With a menu up"}
# title_config.c: the entries 32 apart around y 114 (first menu) and 122 (second),
# between y 16 and 204.
SPACING, MIDDLES, TOP, MOST = 32, (114, 122), 16, 188
MAX_PICTURES, MAX_LINES, MAX_BUTTONS = 8, 16, 16
LABEL_H, LABEL_PAD, LABEL_MIN, LABEL_MAX = 28, 14, 64, 240


def action_title(action: str) -> str:
    if action in ENTRY_NAMES:
        return ENTRY_TITLES[ENTRY_NAMES.index(action)].title()
    return ACTION_TITLES.get(action, action)


def allowed(action, menu: int) -> bool:
    """title_config.c allowed(): load, 2P duel and trade in the first menu,
    a loaded game's choices in the second, the rest in either."""
    if action is None or action in ACTION_TITLES or action in ("new_game", "options"):
        return True
    index = ENTRY_NAMES.index(action) if action in ENTRY_NAMES else -1
    return index < 5 if menu == 0 else index >= 5


def fit(width: int, height: int, max_w: int, max_h: int, want_w=0, want_h=0, guess_h=None):
    """title_images.c measure(): the size a picture is drawn at."""
    guess_h = guess_h or max_h
    if want_w and want_h:
        w, h = want_w, want_h
    elif want_w:
        w, h = want_w, height * want_w // max(1, width)
    elif want_h:
        w, h = width * want_h // max(1, height), want_h
    else:
        factor = 1
        while width // factor > max_w or height // factor > guess_h:
            factor += 1
        w, h = width // factor, height // factor
    if w > max_w:
        w, h = max_w, h * max_w // max(1, w)
    if h > max_h:
        w, h = w * max_h // max(1, h), max_h
    return max(2, (w + 1) & ~1), max(1, h)


class Scene:
    """What the mod's "title" and "menu" make of the title, as title_config.c
    reads them: the backgrounds, the pictures, the items and the menus'
    order and places."""

    def __init__(self, project):
        self.project = project
        self.title = section(project, "title")
        self.menu = section(project, "menu")
        self.mod_id = project.info.id or "mod"

    def background(self, menu_up: bool) -> dict:
        own = self.title.get("background") if isinstance(self.title.get("background"), dict) else {}
        out = {"picture": True, "shade": True, "tint": 0xFFFFFF, "color": None, "image": "", "dim": 128}
        for key, value in own.items():
            out[key] = value
        if menu_up:
            given = self.menu.get("background") if isinstance(self.menu.get("background"), dict) else {}
            for key, value in given.items():
                out[key] = value
        out["dim"] = max(0, min(128, as_int(out.get("dim"), 128)))
        return out

    def items(self) -> list:
        """Every item: the eleven entries, then the buttons, each a dict of
        its keys with "name", "own" (a button of this mod), "menu"."""
        entries = {}
        for source in (self.title.get("entries"), self.menu.get("entries")):
            if isinstance(source, dict):
                for name, value in source.items():
                    index = ENTRY_NAMES.index(name) if name in ENTRY_NAMES else \
                        int(name) if isinstance(name, str) and name.isdigit() and int(name) < 11 else -1
                    if index >= 0 and isinstance(value, dict):
                        entries.setdefault(index, {}).update(value)
        out = []
        for i, name in enumerate(ENTRY_NAMES):
            item = dict(entries.get(i, {}))
            item.update(name=name, index=i, menu=0 if i < 5 else 1, own=False, entry=True)
            out.append(item)
        buttons = self.menu.get("buttons")
        for button in buttons if isinstance(buttons, list) else []:
            if not isinstance(button, dict) or not isinstance(button.get("id"), str):
                continue
            item = dict(button)
            bid = button["id"]
            item.update(name=bid if ":" in bid else f"{self.mod_id}:{bid}", index=len(out), entry=False,
                        own=":" not in bid, menu=1 if button.get("menu") == "second" else 0)
            out.append(item)
        return out

    def order(self, menu: int) -> list:
        """The menu's items top to bottom (title_config.c arrange()), hidden
        ones included, as (item, shown)."""
        items = [i for i in self.items() if i["menu"] == menu]
        given = self.menu.get("order")
        names = given.get(("first", "second")[menu]) if isinstance(given, dict) else (given if menu == 0 else None)
        listed = []
        for name in names if isinstance(names, list) else []:
            if not isinstance(name, str):
                continue
            full = name if (name in ENTRY_NAMES or ":" in name) else f"{self.mod_id}:{name}"
            for item in items:
                if item["name"] == full and item not in listed:
                    listed.append(item)
        listed += [i for i in items if i not in listed]
        shown = [i for i in listed if i.get("hide") is not True]
        if not shown:
            shown = [i for i in listed if i["entry"]]
        return [(i, i in shown) for i in listed]

    def places(self, menu: int) -> dict:
        """Each shown item's middle (x, y), as stack() puts them."""
        shown = [i for i, on in self.order(menu) if on]
        spacing = as_int(self.menu.get("spacing"), as_int(self.title.get("spacing"), SPACING))
        count = len(shown)
        if count > 1 and (count - 1) * spacing > MOST:
            spacing = MOST // (count - 1)
        first = MIDDLES[menu] - (count - 1) * spacing // 2
        first = max(first, TOP)
        if first + (count - 1) * spacing > TOP + MOST:
            first = TOP + MOST - (count - 1) * spacing
        out = {}
        for row, item in enumerate(shown):
            y = as_int(item.get("y"), first + row * spacing) if "y" in item else first + row * spacing
            out[item["name"]] = (160 + as_int(item.get("x")), y)
        return out


def label_button(text: str, selected: bool) -> pngio.Image:
    """menu_label.c's frame for a label, at the console's size, the words
    left to the canvas (drawn over it in Times): (picture, width)."""
    import tkinter.font as tkfont
    try:
        font = tkfont.Font(family="Times", size=-17, weight="bold")
        words = font.measure(text)
    except tk.TclError:
        words = 8 * len(text)
    w = max(LABEL_MIN, min(LABEL_MAX, words + 2 * LABEL_PAD))
    w = (w + 1) & ~1
    h = LABEL_H
    rgba = bytearray(w * h * 4)

    def fill(x0, y0, x1, y1, colour):
        for y in range(y0, y1):
            for x in range(x0, x1):
                rgba[(y * w + x) * 4:(y * w + x) * 4 + 4] = bytes(colour + (255,))
    if selected:
        fill(0, 0, w, h, (168, 16, 16))
        fill(1, 1, w - 1, h - 1, (232, 136, 0))
        fill(2, 2, w - 2, h - 2, (168, 16, 16))
        fill(3, 3, w - 3, h - 3, (40, 24, 24))
        for y, colour in ((4, (104, 96, 200)), (5, (224, 224, 248)), (6, (48, 64, 184)), (h - 7, (104, 96, 200)),
                          (h - 6, (224, 224, 248)), (h - 5, (48, 64, 184))):
            fill(5, y, w - 5, y + 1, colour)
    else:
        fill(0, 0, w, h, (16, 8, 16))
        fill(1, 1, w - 1, h - 1, (96, 96, 8))
        fill(2, 2, w - 2, h - 2, (40, 32, 32))
        fill(6, 5, w - 6, 6, (128, 120, 120))
        fill(6, h - 6, w - 6, h - 5, (128, 120, 120))
    return pngio.Image(w, h, bytes(rgba))


class TitleCanvas:
    """Draws a Scene on a Stage: the title, or a menu up with an item
    chosen. Keys: "background", a layer's name, ("picture", i),
    ("text", i), ("item", name)."""

    def __init__(self, tab, stage: Stage):
        self.tab, self.stage = tab, stage

    def draw(self, scene: Scene, menu=None, cursor=None, chosen=None):
        stage = self.stage
        stage.clear()
        title_art = self.tab.title_art()
        project = scene.project
        background = scene.background(menu is not None)
        dim = background["dim"] if menu is not None else 0
        base = ua.blank(320, 240, (0, 0, 0, 255))
        colour = background.get("color")
        if colour is not None:
            c = ua.parse_colour(colour, -1)
            if c >= 0:
                base = ua.blank(320, 240, (c >> 16, c >> 8 & 255, c & 255, 255))
        image = mod_image(project, background.get("image")) if background.get("image") else None
        if background.get("picture") is not False:
            if image is not None:
                base = ua.paste(base, ua.tint(sized(image, 320, 240), ua.parse_colour(background.get("tint"))), 0, 0)
            elif title_art.ok:
                base = ua.paste(base, ua.tint(title_art.wall(), ua.parse_colour(background.get("tint"))), 0, 0)
        if background.get("shade") is not False:
            rows = []
            for y in range(240):
                level = y * 255 // 239
                table = bytes(max(0, v - level) for v in range(256))
                line = bytearray(base.rgba[y * 1280:(y + 1) * 1280].translate(table))
                line[3::4] = b"\xff" * 320
                rows.append(bytes(line))
            base = pngio.Image(320, 240, b"".join(rows))
        if not title_art.ok and image is None and colour is None:
            stage.create_text(160 * stage.zoom, 228 * stage.zoom, fill="#999",
                              text="The game's title pictures come from DATA/SU.MRG beside the game files.")
        # The layers and the pictures under the menu's dimming: drawn into the background's picture
        # only where they are not to be dragged; here each its own, dimmed alike.
        stage.picture("background", ua.subtract(base, dim), 0, 0, drag=False)
        stage.boxes["background"] = (0, 0, 320, 240)
        layers = self.tab_layers(scene, title_art, menu)
        for key, picture, x, y in layers:
            stage.picture(key, ua.subtract(picture, dim) if key != "prompt" else picture, x, y)
        # A hidden one as a dashed box where it would be, to choose it again.
        for name in LAYER_NAMES:
            layer = scene.title.get(name) if isinstance(scene.title.get(name), dict) else {}
            if layer.get("hide") is True and title_art.ok:
                picture, x, y = title_art.layer(name)
                stage.rectangle(name, x + as_int(layer.get("x")), y + as_int(layer.get("y")), picture.width,
                                picture.height, outline="#9a9a9a", drag=True, dash=(3, 3))
        for i, (picture, x, y) in enumerate(self.pictures(scene, menu)):
            if picture is not None:
                stage.picture(("picture", i), ua.subtract(picture, dim), x, y)
        if menu is not None:
            self.draw_menu(scene, menu, cursor, title_art)
        self.draw_text(scene, menu)
        stage.outline(chosen)

    def tab_layers(self, scene: Scene, title_art, menu):
        out = []
        for name in LAYER_NAMES:
            layer = scene.title.get(name) if isinstance(scene.title.get(name), dict) else {}
            if layer.get("hide") is True:
                continue
            if name == "prompt" and (menu is not None or scene.title.get("press_start") is False):
                continue
            show = layer.get("show", "always")
            if show == "menu" and menu is None or show == "press_start" and menu is not None:
                continue
            dx, dy = as_int(layer.get("x")), as_int(layer.get("y"))
            tint = ua.parse_colour(layer.get("tint"))
            level = 0x58 * 255 // 0x80 if name == "prompt" else 255     # PUSH START's pulse, at its middle
            own = mod_image(scene.project, layer.get("image")) if layer.get("image") else None
            if own is not None:
                w, h = fit(own.width, own.height, 320, 240 if name == "logo" else 120, as_int(layer.get("width")),
                           as_int(layer.get("height")))
                mx, my = ua.LAYER_MIDDLES[name]
                out.append((name, ua.tint(sized(own, w, h), tint, level), mx + dx - w // 2, my + dy - h // 2))
            elif title_art.ok:
                picture, x, y = title_art.layer(name)
                out.append((name, ua.tint(picture, tint, level), x + dx, y + dy))
        return out

    def pictures(self, scene: Scene, menu):
        out = []
        images = scene.title.get("images")
        for entry in images if isinstance(images, list) else []:
            if not isinstance(entry, dict):
                out.append((None, 0, 0))
                continue
            show = entry.get("show", "always")
            own = mod_image(scene.project, entry.get("image"))
            if own is None or (show == "menu" and menu is None) or (show == "press_start" and menu is not None):
                out.append((None, 0, 0))
                continue
            w, h = fit(own.width, own.height, 320, 240, as_int(entry.get("width")), as_int(entry.get("height")))
            x, y = as_int(entry.get("x"), 160), as_int(entry.get("y"), 120)
            out.append((ua.tint(sized(own, w, h), ua.parse_colour(entry.get("tint"))), x - w // 2, y - h // 2))
        return out

    def draw_menu(self, scene: Scene, menu: int, cursor, title_art):
        stage = self.stage
        places = scene.places(menu)
        for item, shown in scene.order(menu):
            if not shown:
                continue
            x, y = places[item["name"]]
            selected = item["name"] == cursor
            tint = ua.parse_colour(item.get("tint"))
            key = ("item", item["name"])
            image = mod_image(scene.project, item.get("selected_image" if selected else "image")) \
                if item.get("selected_image" if selected else "image") else None
            if selected and image is None and item.get("image"):
                image = mod_image(scene.project, item.get("image"))
                level = 255
            else:
                level = 255 if selected or item.get("selected_image") or not item.get("image") else 0x60 * 255 // 0x80
            if image is not None:
                w, h = fit(image.width, image.height, 256, 64, as_int(item.get("width")), as_int(item.get("height")),
                           guess_h=32)
                stage.picture(key, ua.tint(sized(image, w, h), tint, level), x - w // 2, y - h // 2)
            elif isinstance(item.get("label"), str) and item["label"] or not item["entry"]:
                text = item.get("label") or item["name"].split(":", 1)[-1]
                frame = label_button(text, selected)
                level = 255 if selected else 0x60 * 255 // 0x80
                stage.picture(key, ua.tint(frame, tint, level), x - frame.width // 2, y - frame.height // 2)
                ink = "#e0f8d8" if selected else "#b0b0b0"
                stage.text(None, x, y, text, ink, 17, anchor="center", font_family="Times", drag=False,
                           shadow=not selected)
            elif title_art.ok:
                picture, dx, dy = title_art.entry(item["index"], selected)
                stage.picture(key, ua.tint(picture, tint), x + dx, y + dy)
            else:
                stage.rectangle(key, x - 48, y - 14, 96, 28, fill="#28201f", outline="#606008", drag=True)
                stage.text(None, x, y, ENTRY_TITLES[item["index"]], "#ddd", 12, anchor="center", drag=False)

    def draw_text(self, scene: Scene, menu):
        lines = scene.title.get("text")
        for i, line in enumerate(lines if isinstance(lines, list) else []):
            if not isinstance(line, dict) or not isinstance(line.get("text"), str):
                continue
            show = line.get("show", "always")
            if (show == "menu" and menu is None) or (show == "press_start" and menu is not None):
                continue
            size = max(1, min(8, as_int(line.get("size"), 1)))
            align = {"left": "w", "right": "e"}.get(line.get("align"), "center")
            colour = colour_text(ua.parse_colour(line.get("color")))
            self.stage.text(("text", i), as_int(line.get("x"), 160), as_int(line.get("y"), 220), line["text"],
                            colour, 12 * size, anchor=align)


# --- the pages -------------------------------------------------------------------------

class BackgroundForm(ttk.Frame):
    """A "background" object's keys: the game's wall or a picture, its
    colour, the shade, a colour under it, the menu's dimming."""

    def __init__(self, master, page, menu: bool):
        super().__init__(master)
        self.page, self.menu = page, menu
        self.loading = False
        self.picture = tk.BooleanVar()
        self.shade = tk.BooleanVar()
        ttk.Checkbutton(self, text="The game's wall", variable=self.picture,
                        command=lambda: self.set("picture", self.picture.get(), True)).grid(row=0, column=0,
                                                                                         sticky="w")
        ttk.Checkbutton(self, text="Dark-to-light shade", variable=self.shade,
                        command=lambda: self.set("shade", self.shade.get(), True)).grid(row=0, column=1, sticky="w")
        ttk.Label(self, text="Wall colour").grid(row=1, column=0, sticky="w", pady=2)
        self.tint = ColourButton(self, lambda v: self.set("tint", colour_text(v) if v is not None else None, "#FFFFFF"))
        self.tint.grid(row=1, column=1, sticky="w")
        ttk.Label(self, text="Colour under it").grid(row=2, column=0, sticky="w", pady=2)
        self.colour = ColourButton(self, lambda v: self.set("color", colour_text(v) if v is not None else None),
                                   default=None, allow_none=True)
        self.colour.grid(row=2, column=1, sticky="w")
        ttk.Label(self, text="Picture").grid(row=3, column=0, sticky="w", pady=2)
        buttons = ttk.Frame(self)
        buttons.grid(row=3, column=1, sticky="w")
        ttk.Button(buttons, text="Choose PNG...", command=self.choose).pack(side="left")
        ttk.Button(buttons, text="None", command=lambda: self.set("image", None)).pack(side="left", padx=(4, 0))
        self.image = ttk.Label(self, style="Hint.TLabel")
        self.image.grid(row=4, column=1, sticky="w")
        ttk.Label(self, text="Menu dimming").grid(row=5, column=0, sticky="w", pady=2)
        self.dim = ttk.Scale(self, from_=0, to=128, length=px(self, 150), command=self.dimmed)
        self.dim.grid(row=5, column=1, sticky="w")

    def target(self) -> dict:
        return ensure(self.page.project, "menu" if self.menu else "title", "background")

    def current(self) -> dict:
        owner = section(self.page.project, "menu" if self.menu else "title")
        value = owner.get("background")
        return value if isinstance(value, dict) else {}

    def fill(self):
        self.loading = True
        bg = self.current()
        self.picture.set(bg.get("picture") is not False)
        self.shade.set(bg.get("shade") is not False)
        self.tint.set(ua.parse_colour(bg.get("tint")))
        colour = bg.get("color")
        self.colour.set(ua.parse_colour(colour, 0) if colour is not None else None)
        self.image.configure(text=bg.get("image") or ("the title's" if self.menu else "none"))
        self.dim.set(as_int(bg.get("dim"), 128))
        self.loading = False

    def set(self, key, value, default=None):
        if self.loading:
            return
        set_member(self.target(), key, value, default)
        self.page.edited()

    def choose(self):
        name = import_image(self, self.page.project, "menu-background" if self.menu else "title-background")
        if name:
            self.set("image", name)

    def dimmed(self, value):
        if self.loading:
            return
        value = int(float(value))
        if value != as_int(self.current().get("dim"), 128):
            set_member(self.target(), "dim", value, 128)
            self.page.edited(redraw_form=False)


class TitlePage(ttk.Frame):
    def __init__(self, master, tab):
        super().__init__(master)
        self.tab = tab
        self.chosen = "background"
        self.loading = False
        left = ttk.Frame(self)
        left.pack(side="left", fill="y")
        self.stage = Stage(left, zoom=2, on_select=self.select, on_move=self.moved)
        self.stage.pack(anchor="nw")
        self.canvas = TitleCanvas(tab, self.stage)
        tools = ttk.Frame(left)
        tools.pack(fill="x", pady=(6, 0))
        ttk.Button(tools, text="+ Picture", command=self.add_picture).pack(side="left")
        ttk.Button(tools, text="+ Words", command=self.add_text).pack(side="left", padx=(4, 0))
        self.menu_up = tk.BooleanVar(value=False)
        ttk.Checkbutton(tools, text="With the menu up", variable=self.menu_up, command=self.draw).pack(side="left",
                                                                                                    padx=(12, 0))
        # Everything on the title, to choose what the picture hides.
        self.chips = ttk.Frame(left)
        self.chips.pack(fill="x", pady=(6, 0))
        self.chip = tk.StringVar(value="background")
        self.side = ttk.Frame(self, padding=(12, 0, 0, 0))
        self.side.pack(side="left", fill="both", expand=True)
        self.heading = ttk.Label(self.side, font=("TkDefaultFont", 12, "bold"))
        self.heading.pack(anchor="w")
        self.forms = {}
        self.forms["background"] = self.background_form()
        self.forms["layer"] = self.layer_form()
        self.forms["picture"] = self.picture_form()
        self.forms["text"] = self.text_form()
        self.status = ttk.Label(self.side, style="Hint.TLabel", wraplength=px(self, 330), justify="left")
        self.status.pack(side="bottom", anchor="w")

    @property
    def project(self):
        return self.tab.project

    def title(self) -> dict:
        return ensure(self.project, "title")

    def edited(self, redraw_form=True):
        self.tab.changed("title")
        self.draw()
        if redraw_form:
            self.fill_form()

    # --- the forms ----------------------------------------------------------------

    def background_form(self):
        frame = ttk.Frame(self.side)
        self.background = BackgroundForm(frame, self, menu=False)
        self.background.pack(anchor="w", fill="x")
        screen = ttk.LabelFrame(frame, text="The screen", padding=6)
        screen.pack(anchor="w", fill="x", pady=(10, 0))
        self.skip = tk.BooleanVar()
        self.press = tk.BooleanVar()
        ttk.Checkbutton(screen, text="Skip the intro movie", variable=self.skip,
                        command=lambda: self.set_title("skip_intro", True if self.skip.get() else None)).grid(
            row=0, column=0, columnspan=2, sticky="w")
        ttk.Checkbutton(screen, text="PUSH START BUTTON first", variable=self.press,
                        command=lambda: self.set_title("press_start", None if self.press.get() else False)).grid(
            row=1, column=0, columnspan=2, sticky="w")
        self.music = tk.StringVar()
        self.idle = tk.StringVar()
        ttk.Label(screen, text="Song (0x000)").grid(row=2, column=0, sticky="w", pady=2)
        music = ttk.Entry(screen, textvariable=self.music, width=8)
        music.grid(row=2, column=1, sticky="w")
        ttk.Label(screen, text="Intro again after (s, 0 never)").grid(row=3, column=0, sticky="w", pady=2)
        idle = ttk.Entry(screen, textvariable=self.idle, width=8)
        idle.grid(row=3, column=1, sticky="w")
        for entry in (music, idle):
            entry.bind("<Return>", lambda e: self.screen_typed())
            entry.bind("<FocusOut>", lambda e: self.screen_typed())
        return frame

    def layer_form(self):
        frame = ttk.Frame(self.side)
        self.layer_vars = {"x": tk.StringVar(), "y": tk.StringVar(), "show": tk.StringVar()}
        ttk.Label(frame, text="Moved by  x").grid(row=0, column=0, sticky="w", pady=2)
        places = ttk.Frame(frame)
        places.grid(row=0, column=1, sticky="w")
        for key in ("x", "y"):
            if key == "y":
                ttk.Label(places, text="  y").pack(side="left")
            box = ttk.Spinbox(places, from_=-320, to=320, width=5, textvariable=self.layer_vars[key],
                              command=lambda k=key: self.layer_typed(k))
            box.pack(side="left", padx=(4, 0))
            box.bind("<Return>", lambda e, k=key: self.layer_typed(k))
            box.bind("<FocusOut>", lambda e, k=key: self.layer_typed(k))
        ttk.Label(frame, text="Colour").grid(row=1, column=0, sticky="w", pady=2)
        self.layer_tint = ColourButton(frame, lambda v: self.set_layer("tint", colour_text(v) if v is not None else None,
                                                                       "#FFFFFF"))
        self.layer_tint.grid(row=1, column=1, sticky="w")
        ttk.Label(frame, text="Shown").grid(row=2, column=0, sticky="w", pady=2)
        self.show_box = ttk.Combobox(frame, state="readonly", width=18, values=[SHOW_TITLES[s] for s in SHOW])
        self.show_box.grid(row=2, column=1, sticky="w")
        self.show_box.bind("<<ComboboxSelected>>", lambda e: self.set_layer(
            "show", SHOW[self.show_box.current()], "always"))
        ttk.Label(frame, text="Picture").grid(row=3, column=0, sticky="w", pady=2)
        buttons = ttk.Frame(frame)
        buttons.grid(row=3, column=1, sticky="w")
        ttk.Button(buttons, text="Choose PNG...", command=self.layer_image).pack(side="left")
        ttk.Button(buttons, text="Game's", command=lambda: self.set_layer("image", None)).pack(side="left", padx=(4, 0))
        self.layer_image_name = ttk.Label(frame, style="Hint.TLabel")
        self.layer_image_name.grid(row=4, column=1, sticky="w")
        self.layer_hidden = tk.BooleanVar()
        ttk.Checkbutton(frame, text="Hidden", variable=self.layer_hidden,
                        command=lambda: self.set_layer("hide", True if self.layer_hidden.get() else None)).grid(
            row=5, column=1, sticky="w", pady=(6, 0))
        ttk.Button(frame, text="Back to the game's", command=self.reset_layer).grid(row=6, column=1, sticky="w",
                                                                                 pady=(10, 0))
        return frame

    def picture_form(self):
        frame = ttk.Frame(self.side)
        self.picture_vars = {"width": tk.StringVar(), "height": tk.StringVar()}
        ttk.Label(frame, text="Colour").grid(row=0, column=0, sticky="w", pady=2)
        self.picture_tint = ColourButton(frame, lambda v: self.set_picture(
            "tint", colour_text(v) if v is not None else None, "#FFFFFF"))
        self.picture_tint.grid(row=0, column=1, sticky="w")
        ttk.Label(frame, text="Size").grid(row=1, column=0, sticky="w", pady=2)
        sizes = ttk.Frame(frame)
        sizes.grid(row=1, column=1, sticky="w")
        for key in ("width", "height"):
            if key == "height":
                ttk.Label(sizes, text=" x ").pack(side="left")
            box = ttk.Spinbox(sizes, from_=0, to=320, width=5, textvariable=self.picture_vars[key],
                              command=lambda k=key: self.picture_typed(k))
            box.pack(side="left")
            box.bind("<Return>", lambda e, k=key: self.picture_typed(k))
            box.bind("<FocusOut>", lambda e, k=key: self.picture_typed(k))
        ttk.Label(frame, text="0 its own", style="Hint.TLabel").grid(row=2, column=1, sticky="w")
        ttk.Label(frame, text="Shown").grid(row=3, column=0, sticky="w", pady=2)
        self.picture_show = ttk.Combobox(frame, state="readonly", width=18, values=[SHOW_TITLES[s] for s in SHOW])
        self.picture_show.grid(row=3, column=1, sticky="w")
        self.picture_show.bind("<<ComboboxSelected>>", lambda e: self.set_picture(
            "show", SHOW[self.picture_show.current()], "always"))
        buttons = ttk.Frame(frame)
        buttons.grid(row=4, column=1, sticky="w", pady=(10, 0))
        ttk.Button(buttons, text="Another PNG...", command=self.replace_picture).pack(side="left")
        ttk.Button(buttons, text="Remove", command=self.remove_picture).pack(side="left", padx=(4, 0))
        return frame

    def text_form(self):
        frame = ttk.Frame(self.side)
        self.text_vars = {"text": tk.StringVar(), "size": tk.StringVar()}
        ttk.Label(frame, text="Words").grid(row=0, column=0, sticky="w", pady=2)
        words = ttk.Entry(frame, textvariable=self.text_vars["text"], width=30)
        words.grid(row=0, column=1, sticky="w")
        ttk.Label(frame, text="Colour").grid(row=1, column=0, sticky="w", pady=2)
        self.text_colour = ColourButton(frame, lambda v: self.set_text(
            "color", colour_text(v) if v is not None else None, "#FFFFFF"))
        self.text_colour.grid(row=1, column=1, sticky="w")
        ttk.Label(frame, text="Size").grid(row=2, column=0, sticky="w", pady=2)
        size = ttk.Spinbox(frame, from_=1, to=8, width=4, textvariable=self.text_vars["size"],
                           command=lambda: self.text_typed("size"))
        size.grid(row=2, column=1, sticky="w")
        ttk.Label(frame, text="Lined up").grid(row=3, column=0, sticky="w", pady=2)
        self.align_box = ttk.Combobox(frame, state="readonly", width=10, values=["left", "center", "right"])
        self.align_box.grid(row=3, column=1, sticky="w")
        self.align_box.bind("<<ComboboxSelected>>", lambda e: self.set_text("align", self.align_box.get(), "center"))
        ttk.Label(frame, text="Shown").grid(row=4, column=0, sticky="w", pady=2)
        self.text_show = ttk.Combobox(frame, state="readonly", width=18, values=[SHOW_TITLES[s] for s in SHOW])
        self.text_show.grid(row=4, column=1, sticky="w")
        self.text_show.bind("<<ComboboxSelected>>", lambda e: self.set_text(
            "show", SHOW[self.text_show.current()], "always"))
        ttk.Button(frame, text="Remove", command=self.remove_text).grid(row=5, column=1, sticky="w", pady=(10, 0))
        for widget, key in ((words, "text"), (size, "size")):
            widget.bind("<Return>", lambda e, k=key: self.text_typed(k))
            widget.bind("<FocusOut>", lambda e, k=key: self.text_typed(k))
        return frame

    # --- drawing and choosing ---------------------------------------------------------

    def fill(self):
        self.draw()
        self.fill_form()

    def draw(self):
        if self.project is None:
            return
        scene = Scene(self.project)
        self.canvas.draw(scene, menu=0 if self.menu_up.get() else None, cursor="new_game",
                         chosen=self.chosen)
        self.fill_chips(scene)

    @staticmethod
    def chip_key(key) -> str:
        return key if isinstance(key, str) else f"{key[0]}:{key[1]}"

    def fill_chips(self, scene):
        """A chip for each thing on the title, a dot on those the mod changes."""
        for child in self.chips.winfo_children():
            child.destroy()
        title = scene.title
        entries = [("background", "Background", bool(title.get("background")))]
        entries += [(name, LAYER_TITLES[name], bool(title.get(name))) for name in LAYER_NAMES]
        images = title.get("images") if isinstance(title.get("images"), list) else []
        entries += [(("picture", i), f"Picture {i + 1}", True) for i in range(len(images))]
        lines = title.get("text") if isinstance(title.get("text"), list) else []
        entries += [(("text", i), f"Words {i + 1}", True) for i in range(len(lines))]
        self.chip.set(self.chip_key(self.chosen))
        for i, (key, text, changed) in enumerate(entries):
            ttk.Radiobutton(self.chips, text=text + (" \u2022" if changed else ""), value=self.chip_key(key),
                            variable=self.chip, style="Toolbutton",
                            command=lambda k=key: self.select(k)).grid(row=i // 6, column=i % 6, sticky="w",
                                                                       padx=(0, 2), pady=(0, 2))

    def select(self, key):
        if key is None:
            key = "background"
        if isinstance(key, tuple) and key[0] == "item":
            return
        self.chosen = key
        self.stage.outline(key if key != "background" else None)
        self.fill_form()

    def kind(self):
        if self.chosen == "background":
            return "background"
        if self.chosen in LAYER_NAMES:
            return "layer"
        return self.chosen[0]

    def fill_form(self):
        if self.project is None:
            return
        self.loading = True
        kind = self.kind()
        for name, form in self.forms.items():
            if name == kind:
                form.pack(anchor="w", fill="x", pady=(6, 0))
            else:
                form.pack_forget()
        title = section(self.project, "title")
        if kind == "background":
            self.heading.configure(text="Background")
            self.background.fill()
            self.skip.set(title.get("skip_intro") is True)
            self.press.set(title.get("press_start") is not False)
            music = title.get("music")
            self.music.set(music if isinstance(music, str) else f"0x{music:03X}" if isinstance(music, int) else "")
            idle = title.get("idle_seconds")
            self.idle.set(str(idle) if isinstance(idle, int) else "")
        elif kind == "layer":
            self.heading.configure(text=LAYER_TITLES[self.chosen])
            layer = title.get(self.chosen) if isinstance(title.get(self.chosen), dict) else {}
            self.layer_vars["x"].set(str(as_int(layer.get("x"))))
            self.layer_vars["y"].set(str(as_int(layer.get("y"))))
            self.layer_tint.set(ua.parse_colour(layer.get("tint")))
            show = layer.get("show", "always")
            self.show_box.configure(values=[SHOW_TITLES[s] for s in SHOW if self.chosen != "prompt" or s != "menu"])
            self.show_box.current(SHOW.index(show) if show in SHOW else 0)
            self.layer_image_name.configure(text=layer.get("image") or "the game's own")
            self.layer_hidden.set(layer.get("hide") is True)
        elif kind == "picture":
            entry = self.picture_entry()
            self.heading.configure(text=f"Picture {self.chosen[1] + 1}: {entry.get('image', '')}")
            self.picture_tint.set(ua.parse_colour(entry.get("tint")))
            self.picture_vars["width"].set(str(as_int(entry.get("width"))))
            self.picture_vars["height"].set(str(as_int(entry.get("height"))))
            show = entry.get("show", "always")
            self.picture_show.current(SHOW.index(show) if show in SHOW else 0)
        elif kind == "text":
            line = self.text_entry()
            self.heading.configure(text="Words")
            self.text_vars["text"].set(line.get("text", ""))
            self.text_vars["size"].set(str(as_int(line.get("size"), 1)))
            self.text_colour.set(ua.parse_colour(line.get("color")))
            self.align_box.set(line.get("align", "center"))
            show = line.get("show", "always")
            self.text_show.current(SHOW.index(show) if show in SHOW else 0)
        self.status.configure(text="")
        self.loading = False

    def moved(self, key, dx, dy):
        if key in LAYER_NAMES:
            layer = ensure(self.project, "title", key)
            set_member(layer, "x", as_int(layer.get("x")) + dx, 0)
            set_member(layer, "y", as_int(layer.get("y")) + dy, 0)
        elif isinstance(key, tuple) and key[0] == "picture":
            entry = self.picture_entry(key[1])
            entry["x"] = as_int(entry.get("x"), 160) + dx
            entry["y"] = as_int(entry.get("y"), 120) + dy
        elif isinstance(key, tuple) and key[0] == "text":
            line = self.text_entry(key[1])
            line["x"] = as_int(line.get("x"), 160) + dx
            line["y"] = as_int(line.get("y"), 220) + dy
        else:
            return
        self.chosen = key
        self.edited()

    # --- the title's own keys ------------------------------------------------------------

    def set_title(self, key, value):
        if self.loading:
            return
        set_member(self.title(), key, value)
        self.edited()

    def screen_typed(self):
        if self.loading or self.project is None:
            return
        title = self.title()
        music, idle = self.music.get().strip(), self.idle.get().strip()
        try:
            if music:
                number = int(music, 0)
                if not 0 <= number <= 0xFFF:
                    raise ValueError
                title["music"] = f"0x{number:03X}"
            else:
                title.pop("music", None)
            if idle:
                seconds = int(idle)
                if seconds < 0:
                    raise ValueError
                title["idle_seconds"] = seconds
            else:
                title.pop("idle_seconds", None)
        except ValueError:
            self.status.configure(text="The song is a number from 0x000 to 0xFFF; the seconds 0 or more.")
            return
        self.edited(redraw_form=False)

    # --- the three pictures ------------------------------------------------------------

    def set_layer(self, key, value, default=None):
        if self.kind() != "layer":
            return
        if self.loading:
            return
        set_member(ensure(self.project, "title", self.chosen), key, value, default)
        self.edited()

    def layer_typed(self, key):
        if self.kind() != "layer":
            return
        if self.loading:
            return
        try:
            value = int(self.layer_vars[key].get().strip() or 0)
        except ValueError:
            self.status.configure(text="A whole number.")
            return
        self.set_layer(key, value, 0)

    def layer_image(self):
        if self.kind() != "layer":
            return
        name = import_image(self, self.project, f"title-{self.chosen}")
        if name:
            self.set_layer("image", name)

    def reset_layer(self):
        if self.kind() != "layer":
            return
        title = self.title()
        title.pop(self.chosen, None)
        self.edited()

    # --- added pictures ------------------------------------------------------------------

    def pictures_list(self) -> list:
        title = self.title()
        if not isinstance(title.get("images"), list):
            title["images"] = []
        return title["images"]

    def picture_entry(self, index=None) -> dict:
        images = self.pictures_list()
        index = self.chosen[1] if index is None else index
        if not isinstance(images[index], dict):
            images[index] = {}
        return images[index]

    def add_picture(self):
        if self.project is None:
            return
        if len(self.pictures_list()) >= MAX_PICTURES:
            self.status.configure(text=f"At most {MAX_PICTURES} pictures.")
            return
        name = import_image(self, self.project, "title-picture")
        if not name:
            if not self.pictures_list():
                self.title().pop("images", None)
            return
        self.pictures_list().append({"image": name, "x": 160, "y": 120})
        self.chosen = ("picture", len(self.pictures_list()) - 1)
        self.edited()

    def replace_picture(self):
        if self.kind() != "picture":
            return
        name = import_image(self, self.project, "title-picture")
        if name:
            self.picture_entry()["image"] = name
            self.edited()

    def remove_picture(self):
        if self.kind() != "picture":
            return
        images = self.pictures_list()
        del images[self.chosen[1]]
        if not images:
            self.title().pop("images")
        self.chosen = "background"
        self.edited()

    def set_picture(self, key, value, default=None):
        if self.kind() != "picture":
            return
        if self.loading:
            return
        set_member(self.picture_entry(), key, value, default)
        self.edited()

    def picture_typed(self, key):
        if self.kind() != "picture":
            return
        if self.loading:
            return
        try:
            value = max(0, min(320 if key == "width" else 240, int(self.picture_vars[key].get().strip() or 0)))
        except ValueError:
            self.status.configure(text="A whole number.")
            return
        self.set_picture(key, value or None)

    # --- lines of words ----------------------------------------------------------------

    def lines(self) -> list:
        title = self.title()
        if not isinstance(title.get("text"), list):
            title["text"] = []
        return title["text"]

    def text_entry(self, index=None) -> dict:
        lines = self.lines()
        index = self.chosen[1] if index is None else index
        if not isinstance(lines[index], dict):
            lines[index] = {"text": ""}
        return lines[index]

    def add_text(self):
        if self.project is None:
            return
        if len(self.lines()) >= MAX_LINES:
            self.status.configure(text=f"At most {MAX_LINES} lines.")
            return
        self.lines().append({"text": self.project.info.name or "My mod", "x": 160, "y": 228})
        self.chosen = ("text", len(self.lines()) - 1)
        self.edited()

    def remove_text(self):
        if self.kind() != "text":
            return
        lines = self.lines()
        del lines[self.chosen[1]]
        if not lines:
            self.title().pop("text")
        self.chosen = "background"
        self.edited()

    def set_text(self, key, value, default=None):
        if self.kind() != "text":
            return
        if self.loading:
            return
        set_member(self.text_entry(), key, value, default)
        self.edited()

    def text_typed(self, key):
        if self.kind() != "text":
            return
        if self.loading:
            return
        if key == "text":
            text = self.text_vars["text"].get()
            if len(text.encode("utf-8")) > 95:
                self.status.configure(text="At most 95 letters.")
                return
            self.text_entry()["text"] = text
            self.edited()
            return
        try:
            value = max(1, min(8, int(self.text_vars["size"].get().strip() or 1)))
        except ValueError:
            self.status.configure(text="A size from 1 to 8.")
            return
        self.set_text("size", value, 1)


class MenuPage(ttk.Frame):
    def __init__(self, master, tab):
        super().__init__(master)
        self.tab = tab
        self.menu = tk.IntVar(value=0)
        self.chosen = "new_game"
        self.loading = False
        left = ttk.Frame(self)
        left.pack(side="left", fill="y")
        self.stage = Stage(left, zoom=2, on_select=self.select_stage, on_move=self.moved)
        self.stage.pack(anchor="nw")
        self.canvas = TitleCanvas(tab, self.stage)
        tools = ttk.Frame(left)
        tools.pack(fill="x", pady=(6, 0))
        for value, text in ((0, "First menu"), (1, "Second menu (a game loaded)")):
            ttk.Radiobutton(tools, text=text, value=value, variable=self.menu, style="Toolbutton",
                            command=self.switch_menu).pack(side="left", padx=(0, 2))
        ttk.Label(tools, text="Spacing").pack(side="left", padx=(12, 4))
        self.spacing = tk.StringVar()
        spacing = ttk.Spinbox(tools, from_=8, to=64, width=4, textvariable=self.spacing, command=self.spaced)
        spacing.pack(side="left")
        spacing.bind("<Return>", lambda e: self.spaced())
        side = ttk.Frame(self, padding=(12, 0, 0, 0))
        side.pack(side="left", fill="both", expand=True)
        listing = ttk.Frame(side)
        listing.pack(fill="x")
        self.tree = ttk.Treeview(listing, columns=("does",), height=9, selectmode="browse", show="tree headings")
        self.tree.heading("#0", text="Button")
        self.tree.heading("does", text="Does")
        self.tree.column("#0", width=px(self, 170))
        self.tree.column("does", width=px(self, 150))
        self.tree.pack(side="left", fill="x", expand=True)
        self.tree.bind("<<TreeviewSelect>>", lambda e: self.picked())
        order = ttk.Frame(listing)
        order.pack(side="left", fill="y", padx=(4, 0))
        ttk.Button(order, text="▲", width=3, command=lambda: self.move(-1)).pack()
        ttk.Button(order, text="▼", width=3, command=lambda: self.move(1)).pack(pady=(2, 0))
        actions = ttk.Frame(side)
        actions.pack(fill="x", pady=(4, 0))
        ttk.Button(actions, text="+ Button", command=self.add_button).pack(side="left")
        self.hide_button = ttk.Button(actions, text="Hide", command=self.toggle_hidden)
        self.hide_button.pack(side="left", padx=(4, 0))
        self.remove_button = ttk.Button(actions, text="Remove", command=self.remove)
        self.remove_button.pack(side="left", padx=(4, 0))
        ttk.Button(actions, text="Menu background", command=self.background_chosen).pack(side="left", padx=(4, 0))
        self.heading = ttk.Label(side, font=("TkDefaultFont", 12, "bold"))
        self.heading.pack(anchor="w", pady=(8, 0))
        self.item_form = self.make_item_form(side)
        self.background = BackgroundForm(side, self, menu=True)
        self.status = ttk.Label(side, style="Hint.TLabel", wraplength=px(self, 360), justify="left")
        self.status.pack(side="bottom", anchor="w")

    @property
    def project(self):
        return self.tab.project

    def edited(self, redraw_form=True):
        self.tab.changed("menu")
        self.draw()
        if redraw_form:
            self.fill_list()
            self.fill_form()

    def make_item_form(self, parent):
        frame = ttk.Frame(parent)
        self.item_vars = {key: tk.StringVar() for key in ("label", "notice_title", "notice", "value", "x", "y")}
        row = 0

        def line(text, widget):
            nonlocal row
            ttk.Label(frame, text=text).grid(row=row, column=0, sticky="w", pady=2, padx=(0, 8))
            widget.grid(row=row, column=1, sticky="w", pady=2)
            row += 1
            return widget
        label = line("Words", ttk.Entry(frame, textvariable=self.item_vars["label"], width=24))
        self.action_box = line("Does", ttk.Combobox(frame, state="readonly", width=22))
        self.action_box.bind("<<ComboboxSelected>>", lambda e: self.set_action())
        notice = ttk.Frame(frame)
        ttk.Entry(notice, textvariable=self.item_vars["notice_title"], width=10).pack(side="left")
        ttk.Entry(notice, textvariable=self.item_vars["notice"], width=22).pack(side="left", padx=(4, 0))
        self.notice_row = line("Notice", notice)
        self.notice_caption = frame.grid_slaves(row=row - 1, column=0)[0]
        self.value_box = line("Event value", ttk.Entry(frame, textvariable=self.item_vars["value"], width=8))
        self.value_caption = frame.grid_slaves(row=row - 1, column=0)[0]
        self.item_tint = line("Colour", ColourButton(frame, lambda v: self.set_item(
            "tint", colour_text(v) if v is not None else None, "#FFFFFF")))
        pictures = ttk.Frame(frame)
        ttk.Button(pictures, text="PNG...", command=lambda: self.item_image("image")).pack(side="left")
        ttk.Button(pictures, text="With cursor...", command=lambda: self.item_image("selected_image")).pack(
            side="left", padx=(4, 0))
        ttk.Button(pictures, text="None", command=self.clear_images).pack(side="left", padx=(4, 0))
        line("Picture", pictures)
        self.item_image_name = ttk.Label(frame, style="Hint.TLabel")
        self.item_image_name.grid(row=row, column=1, sticky="w")
        row += 1
        places = ttk.Frame(frame)
        x = ttk.Spinbox(places, from_=-214, to=214, width=5, textvariable=self.item_vars["x"],
                        command=lambda: self.item_typed("x"))
        x.pack(side="left")
        ttk.Label(places, text="  y").pack(side="left")
        y = ttk.Spinbox(places, from_=-40, to=280, width=5, textvariable=self.item_vars["y"],
                        command=lambda: self.item_typed("y"))
        y.pack(side="left", padx=(4, 0))
        ttk.Button(places, text="In line", command=self.in_line).pack(side="left", padx=(6, 0))
        line("Place  x", places)
        for widget, key in ((label, "label"), (x, "x"), (y, "y"), (self.value_box, "value")):
            widget.bind("<Return>", lambda e, k=key: self.item_typed(k))
            widget.bind("<FocusOut>", lambda e, k=key: self.item_typed(k))
        for child in notice.winfo_children():
            child.bind("<Return>", lambda e: self.item_typed("notice"))
            child.bind("<FocusOut>", lambda e: self.item_typed("notice"))
        ttk.Button(frame, text="Back to the game's", command=self.reset_item).grid(row=row, column=1, sticky="w",
                                                                                pady=(8, 0))
        return frame

    # --- the menu's items -----------------------------------------------------------------

    def scene(self):
        return Scene(self.project)

    def item(self, name=None):
        name = name or self.chosen
        for item in self.scene().items():
            if item["name"] == name:
                return item
        return None

    def target(self, name=None) -> dict:
        """The object the mod keeps an item's keys in: an entry's under
        "menu"."entries", a button its own in "buttons"."""
        name = name or self.chosen
        if name in ENTRY_NAMES:
            return ensure(self.project, "menu", "entries", name)
        menu = ensure(self.project, "menu")
        buttons = menu.setdefault("buttons", [])
        own = self.project.info.id or "mod"
        for button in buttons:
            if isinstance(button, dict) and (button.get("id") == name or f"{own}:{button.get('id')}" == name):
                return button
        button = {"id": name}
        buttons.append(button)
        return button

    def short(self, name: str) -> str:
        own = (self.project.info.id or "mod") + ":"
        return name[len(own):] if name.startswith(own) else name

    def fill(self):
        self.draw()
        self.fill_list()
        self.fill_form()

    def switch_menu(self):
        order = self.scene().order(self.menu.get())
        if order and (self.item() is None or self.item()["menu"] != self.menu.get()):
            self.chosen = order[0][0]["name"]
        self.fill()

    def draw(self):
        if self.project is None:
            return
        scene = self.scene()
        chosen = ("item", self.chosen) if self.chosen != "background" else None
        self.canvas.draw(scene, menu=self.menu.get(), cursor=self.chosen, chosen=chosen)
        spacing = as_int(scene.menu.get("spacing"), as_int(scene.title.get("spacing"), SPACING))
        self.spacing.set(str(spacing))

    def fill_list(self):
        if self.project is None:
            return
        self.tree.delete(*self.tree.get_children())
        for item, shown in self.scene().order(self.menu.get()):
            text = item.get("label") or (ENTRY_TITLES[item["index"]] if item["entry"] else self.short(item["name"]))
            action = item.get("action") or (item["name"] if item["entry"] else
                                            ("notice" if item.get("notice") else "none"))
            does = action_title(action) + ("" if allowed(action, self.menu.get()) else " (not here)")
            self.tree.insert("", "end", iid=item["name"], text=("" if shown else "◌ ") + text,
                             values=(does,), tags=() if shown else ("hidden",))
        self.tree.tag_configure("hidden", foreground="#888")
        if self.tree.exists(self.chosen):
            self.loading = True
            self.tree.selection_set(self.chosen)
            self.tree.see(self.chosen)
            self.loading = False

    def picked(self):
        if self.loading:
            return
        selection = self.tree.selection()
        if selection:
            self.chosen = selection[0]
            self.draw()
            self.fill_form()

    def select_stage(self, key):
        if isinstance(key, tuple) and key[0] == "item":
            self.chosen = key[1]
            self.draw()
            self.fill_list()
            self.fill_form()

    def background_chosen(self):
        self.chosen = "background"
        self.tree.selection_remove(*self.tree.selection())
        self.draw()
        self.fill_form()

    def fill_form(self):
        if self.project is None:
            return
        self.loading = True
        if self.chosen == "background":
            self.item_form.pack_forget()
            self.background.pack(anchor="w", fill="x", pady=(6, 0))
            self.heading.configure(text="Menu background (what it leaves out is the title's)")
            self.background.fill()
            self.loading = False
            return
        self.background.pack_forget()
        self.item_form.pack(anchor="w", fill="x", pady=(6, 0))
        item = self.item() or {"name": self.chosen, "entry": False, "menu": 0}
        self.heading.configure(text=ENTRY_TITLES[item["index"]] if item.get("entry") else
                               f"Button {self.short(item['name'])}")
        self.item_vars["label"].set(item.get("label") or "")
        menu = item["menu"]
        choices = [a for a in ACTIONS if allowed(a, menu)]
        self.action_choices = (["(its own)"] if item.get("entry") else []) + choices
        self.action_box.configure(values=[c if c == "(its own)" else action_title(c) for c in self.action_choices])
        action = item.get("action")
        if action in self.action_choices:
            self.action_box.current(self.action_choices.index(action))
        elif item.get("entry"):
            self.action_box.current(0)
        else:
            self.action_box.current(self.action_choices.index("notice" if item.get("notice") else "none"))
        notice = item.get("notice")
        self.item_vars["notice_title"].set(notice.get("title", "") if isinstance(notice, dict) else "")
        self.item_vars["notice"].set(notice.get("text", "") if isinstance(notice, dict) else
                                     notice if isinstance(notice, str) else "")
        self.item_vars["value"].set(str(as_int(item.get("value"))))
        shown_action = self.action_choices[self.action_box.current()]
        for widget in (self.notice_row, self.notice_caption):
            widget.grid() if shown_action == "notice" else widget.grid_remove()
        for widget in (self.value_box, self.value_caption):
            widget.grid() if shown_action == "event" else widget.grid_remove()
        self.item_tint.set(ua.parse_colour(item.get("tint")))
        pictures = [item.get("image"), item.get("selected_image")]
        self.item_image_name.configure(text=" / ".join(p for p in pictures if p) or "the game's own" if item.get(
            "entry") else " / ".join(p for p in pictures if p) or "words on a frame")
        place = self.scene().places(menu).get(item["name"])
        self.item_vars["x"].set(str(as_int(item.get("x"))))
        self.item_vars["y"].set(str(as_int(item.get("y"))) if "y" in item else str(place[1]) if place else "")
        self.hide_button.configure(text="Show" if item.get("hide") is True else "Hide")
        self.remove_button.state(["disabled"] if item.get("entry") or not item.get("own", True) else ["!disabled"])
        self.status.configure(text="")
        self.loading = False

    # --- edits ------------------------------------------------------------------------

    def set_item(self, key, value, default=None):
        if self.loading or self.chosen == "background":
            return
        set_member(self.target(), key, value, default)
        self.edited()

    def item_typed(self, key):
        if self.loading or self.chosen == "background":
            return
        target = self.target()
        if key == "label":
            text = self.item_vars["label"].get().strip()
            if len(text) > 31:
                self.status.configure(text="At most 31 letters.")
                return
            set_member(target, "label", text or None)
        elif key == "notice":
            title, text = self.item_vars["notice_title"].get(), self.item_vars["notice"].get()
            set_member(target, "notice", {"title": title, "text": text} if title else (text or None))
        else:
            try:
                value = int(self.item_vars[key].get().strip() or 0)
            except ValueError:
                self.status.configure(text="A whole number.")
                return
            if key == "y":
                target["y"] = value
            else:
                set_member(target, key, value, 0)
        self.edited()

    def set_action(self):
        if self.chosen == "background" or self.project is None:
            return
        if self.loading:
            return
        choice = self.action_choices[self.action_box.current()]
        target = self.target()
        if choice == "(its own)":
            target.pop("action", None)
        else:
            target["action"] = choice
            if choice == "notice" and not target.get("notice"):
                target["notice"] = {"title": target.get("label") or "", "text": "..."}
        self.edited()

    def in_line(self):
        if self.chosen == "background" or self.project is None:
            return
        target = self.target()
        target.pop("y", None)
        target.pop("x", None)
        self.edited()

    def item_image(self, key):
        if self.chosen == "background" or self.project is None:
            return
        name = import_image(self, self.project, f"menu-{self.short(self.chosen).replace(':', '-')}"
                            + ("-on" if key == "selected_image" else ""))
        if name:
            self.set_item(key, name)

    def clear_images(self):
        if self.chosen == "background" or self.project is None:
            return
        target = self.target()
        for key in ("image", "selected_image", "width", "height"):
            target.pop(key, None)
        self.edited()

    def moved(self, key, dx, dy):
        if not (isinstance(key, tuple) and key[0] == "item"):
            return
        self.chosen = key[1]
        place = self.scene().places(self.menu.get()).get(self.chosen)
        target = self.target()
        set_member(target, "x", as_int(target.get("x")) + dx, 0)
        if dy and place:
            target["y"] = place[1] + dy
        self.edited()

    def spaced(self):
        if self.loading or self.project is None:
            return
        try:
            value = max(8, min(64, int(self.spacing.get())))
        except ValueError:
            return
        set_member(ensure(self.project, "menu"), "spacing", value, SPACING)
        self.edited(redraw_form=False)

    def order_names(self) -> list:
        """The shown menu's order as the mod writes it."""
        return [self.short(item["name"]) for item, _ in self.scene().order(self.menu.get())]

    def write_order(self, names: list):
        menu = ensure(self.project, "menu")
        order = menu.get("order")
        if not isinstance(order, dict):
            order = {"first": order} if isinstance(order, list) else {}
            menu["order"] = order
        order[("first", "second")[self.menu.get()]] = names

    def move(self, step: int):
        if self.chosen == "background":
            return
        names = self.order_names()
        name = self.short(self.chosen)
        if name not in names:
            return
        at = names.index(name)
        to = at + step
        if not 0 <= to < len(names):
            return
        names[at], names[to] = names[to], names[at]
        self.write_order(names)
        self.edited()

    def toggle_hidden(self):
        if self.chosen == "background":
            return
        item = self.item()
        set_member(self.target(), "hide", None if item and item.get("hide") is True else True)
        self.edited()

    def add_button(self):
        if self.project is None:
            return
        buttons = ensure(self.project, "menu").setdefault("buttons", [])
        if len([b for b in self.scene().items() if not b["entry"]]) >= MAX_BUTTONS:
            self.status.configure(text=f"At most {MAX_BUTTONS} buttons.")
            return
        taken = {b.get("id") for b in buttons if isinstance(b, dict)}
        n = 1
        while f"button{n}" in taken:
            n += 1
        button = {"id": f"button{n}", "label": f"BUTTON {n}", "action": "notice",
                  "notice": {"title": f"Button {n}", "text": "Words of your own."}}
        if self.menu.get() == 1:
            button["menu"] = "second"
        buttons.append(button)
        self.chosen = f"{self.project.info.id or 'mod'}:button{n}"
        self.edited()

    def remove(self):
        if self.chosen == "background" or self.project is None:
            return
        item = self.item()
        if not item or item.get("entry") or not item.get("own"):
            return
        menu = ensure(self.project, "menu")
        menu["buttons"] = [b for b in menu.get("buttons", []) if not (isinstance(b, dict) and b.get("id") ==
                                                                        self.short(self.chosen))]
        if not menu["buttons"]:
            menu.pop("buttons")
        order = menu.get("order")
        for names in (order.values() if isinstance(order, dict) else [order] if isinstance(order, list) else []):
            if isinstance(names, list) and self.short(self.chosen) in names:
                names.remove(self.short(self.chosen))
        self.chosen = self.scene().order(self.menu.get())[0][0]["name"]
        self.edited()

    def reset_item(self):
        if self.chosen == "background" or self.project is None:
            return
        if self.chosen in ENTRY_NAMES:
            entries = ensure(self.project, "menu", "entries")
            entries.pop(self.chosen, None)
            title_entries = section(self.project, "title").get("entries")
            if isinstance(title_entries, dict):
                title_entries.pop(self.chosen, None)
        else:
            target = self.target()
            keep = {k: target[k] for k in ("id", "menu") if k in target}
            target.clear()
            target.update(keep)
            target["label"] = self.short(self.chosen).upper()
        self.edited()
