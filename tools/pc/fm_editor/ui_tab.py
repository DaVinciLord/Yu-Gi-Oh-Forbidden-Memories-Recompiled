"""The UI tab: what a mod changes of the screens' look, on pictures of them
drawn from the user's own disc (ui_assets.py). Three pages: the title
screen ("title", notes/modding.md "The title screen"), its two menus
("menu", "The title's menus") and the duel's pictures ("ui", "The duel's
pictures"). Each page is a picture to drag things on and, beside it, what
the chosen thing has; the pages are in ui_title.py and ui_duel.py.

The three keys are the mod's own `other` keys (manifest.py keeps them as
written): a page changes only the members it shows, and a key left empty
is taken out, so a mod that changes nothing here writes nothing."""
from __future__ import annotations

import base64
import os
import tkinter as tk
from pathlib import Path
from tkinter import colorchooser, filedialog, messagebox, ttk

from . import pngio, theme, ui_assets
from .tabs import Tab
from .widgets import px

GAME_W, GAME_H = 320, 240
IMAGE_DIR = "ui"          # where the tab puts a PNG it is given, in the mod


# --- the mod's keys ---------------------------------------------------------------

def section(project, key: str) -> dict:
    value = project.other.get(key)
    return value if isinstance(value, dict) else {}


def ensure(project, *path) -> dict:
    """The object at project.other[path[0]][path[1]]..., made as needed."""
    at = project.other
    for key in path:
        if not isinstance(at.get(key), dict):
            at[key] = {}
        at = at[key]
    return at


def prune(project, key: str):
    """Empty objects under `key` taken out, then `key` itself if empty."""
    def tidy(value: dict):
        for k in list(value):
            if isinstance(value[k], dict):
                tidy(value[k])
                if not value[k]:
                    del value[k]
    value = project.other.get(key)
    if isinstance(value, dict):
        tidy(value)
        if not value:
            del project.other[key]


def set_member(target: dict, key: str, value, default=None):
    """target[key] = value, or the key taken out for its default."""
    if value is None or value == default:
        target.pop(key, None)
    else:
        target[key] = value


def colour_text(value: int) -> str:
    return f"#{value:06X}"


def as_int(value, default: int = 0) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else default


# --- the mod's pictures --------------------------------------------------------------

def image_bytes(project, name: str):
    """A PNG the mod names, from what the editor holds or the mod's folder."""
    if not isinstance(name, str) or not name:
        return None
    if name in project.files:
        return project.files[name]
    source = project.source_dir
    if source:
        path = Path(source) / name
        if path.is_file():
            try:
                return path.read_bytes()
            except OSError:
                return None
    return None


_decoded = {}


def mod_image(project, name: str):
    """The PNG as a pngio.Image, or None (decoded once per content)."""
    data = image_bytes(project, name)
    if data is None:
        return None
    key = hash(data)
    if key not in _decoded:
        try:
            _decoded[key] = pngio.decode(data)
        except (pngio.PngError, ValueError, Exception):
            _decoded[key] = None
    return _decoded[key]


_sized = {}


def sized(image: pngio.Image, width: int, height: int) -> pngio.Image:
    """The picture at width x height as the game's console resolution draws
    it (each texel the average of what is under it, art.c), kept."""
    key = (id(image), width, height)
    if key not in _sized:
        if image.width <= width * 3 and image.height <= height * 3:
            _sized[key] = pngio.scale_to(image, max(1, width), max(1, height))
        else:   # a big picture: a cheap step down first, then the average
            step = pngio.scale_to(image, max(1, width * 2), max(1, height * 2))
            _sized[key] = pngio.resample(step, max(1, width), max(1, height))
    return _sized[key]


def add_image_file(project, path, stem: str) -> str:
    """The PNG at `path` put in the mod as ui/<stem>.png (another name when
    that holds another picture); its name. ValueError when it is no PNG."""
    data = Path(path).read_bytes()
    try:
        pngio.decode(data)
    except (pngio.PngError, ValueError) as problem:
        raise ValueError(f"{Path(path).name} is not a PNG the editor can read: {problem}")
    name, n = f"{IMAGE_DIR}/{stem}.png", 2
    while (name in project.files and project.files[name] != data) or \
            (name not in project.files and image_bytes(project, name) not in (None, data)):
        name = f"{IMAGE_DIR}/{stem}-{n}.png"
        n += 1
    project.files[name] = data
    return name


def import_image(widget, project, stem: str):
    """A PNG the user chooses, put in the mod (add_image_file); its name or None."""
    path = filedialog.askopenfilename(parent=widget, title="Choose a PNG",
                                      filetypes=[("PNG pictures", "*.png"), ("All files", "*")])
    if not path:
        return None
    try:
        return add_image_file(project, path, stem)
    except (OSError, ValueError) as problem:
        messagebox.showerror("FM Editor", str(problem), parent=widget)
        return None


# --- widgets ---------------------------------------------------------------------------

class ColourButton(ttk.Frame):
    """A swatch and its #RRGGBB; a click picks another, the x puts it back."""

    def __init__(self, master, on_change, default=0xFFFFFF, allow_none=False):
        super().__init__(master)
        self.on_change, self.default, self.allow_none = on_change, default, allow_none
        self.value = default
        self.swatch = tk.Canvas(self, width=px(self, 34), height=px(self, 18), highlightthickness=1,
                                highlightbackground="#888", cursor="hand2")
        self.swatch.pack(side="left")
        self.swatch.bind("<Button-1>", lambda e: self.pick())
        self.text = ttk.Label(self, width=8)
        self.text.pack(side="left", padx=(4, 0))
        self.reset = ttk.Button(self, text="×", width=2, command=self.clear)
        self.reset.pack(side="left")
        self.set(default)

    def set(self, value):
        self.value = value
        self.swatch.delete("all")
        if value is None:
            self.swatch.create_line(0, px(self, 18), px(self, 34), 0, fill="#c01c28", width=2)
            self.text.configure(text="none")
        else:
            self.swatch.configure(background=colour_text(value))
            self.text.configure(text=colour_text(value))
        self.reset.state(["disabled"] if value == self.default else ["!disabled"])

    def pick(self):
        start = colour_text(self.value if self.value is not None else self.default)
        chosen = colorchooser.askcolor(color=start, parent=self, title="Choose a colour")
        if chosen and chosen[1]:
            self.set(int(chosen[1][1:], 16))
            self.on_change(self.value)

    def clear(self):
        self.set(None if self.allow_none else self.default)
        self.on_change(self.value)


class Stage(tk.Canvas):
    """The game's 320 x 240 at a whole zoom: pictures placed in the game's
    pixels, dragged with the mouse (the game's pixels again, on release),
    one chosen at a time with a dashed box round it. Pictures are pngio
    images, kept as Tk photos (zoomed by Tk) until they change."""

    def __init__(self, master, zoom: int = 2, on_select=None, on_move=None, on_wheel=None):
        super().__init__(master, width=GAME_W * zoom, height=GAME_H * zoom, highlightthickness=0,
                         background="#000", cursor="arrow")
        self.zoom = zoom
        self.on_select, self.on_move, self.on_wheel = on_select, on_move, on_wheel
        self.photos = {}          # (key, picture) -> (picture, zoom, photo): kept while their picture is
        self.shown = []           # the photos the canvas shows now (Tk forgets one nothing holds)
        self.items = {}           # key -> canvas items
        self.boxes = {}           # key -> (x, y, w, h) in the game's pixels
        self.draggable = set()
        self.chosen = None
        self.drag = None
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<B1-Motion>", self._motion)
        self.bind("<ButtonRelease-1>", self._release)
        self.bind("<MouseWheel>", self._wheel)
        self.bind("<Button-4>", lambda e: self._wheel(e, 120))
        self.bind("<Button-5>", lambda e: self._wheel(e, -120))
        self.bind("<Motion>", self._hover)

    def set_zoom(self, zoom: int):
        if zoom != self.zoom:
            self.zoom = zoom
            self.configure(width=GAME_W * zoom, height=GAME_H * zoom)
            self.photos.clear()

    def photo(self, key, image: pngio.Image):
        """The Tk photo of a picture at the zoom, made again only when the
        picture (its bytes) or the zoom changes."""
        signature = (key, image.width, image.height, hash(image.rgba))
        held = self.photos.get(signature)
        if held and held[1] == self.zoom:
            self.shown.append(held[2])
            return held[2]
        base = tk.PhotoImage(master=self, data=base64.b64encode(pngio.encode(image)), format="png")
        photo = base.zoom(self.zoom) if self.zoom > 1 else base
        if len(self.photos) > 400:
            self.photos.clear()
        self.photos[signature] = (image, self.zoom, photo)
        self.shown.append(photo)
        return photo

    def clear(self):
        self.delete("all")
        self.shown = []
        self.items.clear()
        self.boxes.clear()
        self.draggable.clear()

    def picture(self, key, image: pngio.Image, x: int, y: int, drag=True, box=None):
        """`image` with its top left at x, y; `box` (x, y, w, h) is what
        selects it (its own rectangle by default)."""
        z = self.zoom
        item = self.create_image(x * z, y * z, image=self.photo(key, image), anchor="nw")
        self.items.setdefault(key, []).append(item)
        if box is not None or key not in self.boxes:
            self.boxes[key] = box or (x, y, image.width, image.height)
        if drag:
            self.draggable.add(key)
        return item

    def rectangle(self, key, x, y, w, h, fill="", outline="", width=1, drag=False, dash=None):
        z = self.zoom
        item = self.create_rectangle(x * z, y * z, (x + w) * z, (y + h) * z, fill=fill, outline=outline,
                                     width=width, dash=dash)
        if key is not None:
            self.items.setdefault(key, []).append(item)
            self.boxes.setdefault(key, (x, y, w, h))
            if drag:
                self.draggable.add(key)
        return item

    def text(self, key, x, y, text, colour, size, anchor="w", font_family="TkDefaultFont", drag=True, shadow=True):
        z = self.zoom
        font = (font_family, -max(6, int(size * z)), "bold")
        items = []
        if shadow:
            items.append(self.create_text(x * z + z, y * z + z, text=text, fill="#000", font=font, anchor=anchor))
        items.append(self.create_text(x * z, y * z, text=text, fill=colour, font=font, anchor=anchor))
        if key is not None:
            self.items.setdefault(key, []).extend(items)
            x0, y0, x1, y1 = self.bbox(items[-1])
            self.boxes[key] = (x0 / z, y0 / z, (x1 - x0) / z, (y1 - y0) / z)
            if drag:
                self.draggable.add(key)
        return items

    def outline(self, key):
        """The chosen thing's dashed box, over everything."""
        self.delete("chosen")
        self.chosen = key
        if key not in self.boxes:
            return
        x, y, w, h = self.boxes[key]
        z = self.zoom
        accent = "#ffd34d"
        self.create_rectangle(x * z - 2, y * z - 2, (x + w) * z + 1, (y + h) * z + 1, outline="#000", width=3,
                              tags="chosen")
        self.create_rectangle(x * z - 2, y * z - 2, (x + w) * z + 1, (y + h) * z + 1, outline=accent, width=1,
                              dash=(4, 3), tags="chosen")

    def key_at(self, x, y):
        """The topmost draggable thing under the mouse (canvas pixels)."""
        gx, gy = x / self.zoom, y / self.zoom
        for item in reversed(self.find_overlapping(x, y, x, y)):
            for key, items in self.items.items():
                if item in items and key in self.draggable:
                    return key
        for key in reversed(list(self.boxes)):
            bx, by, bw, bh = self.boxes[key]
            if key in self.draggable and bx <= gx < bx + bw and by <= gy < by + bh:
                return key
        return None

    def _hover(self, event):
        self.configure(cursor="fleur" if self.key_at(event.x, event.y) is not None else "arrow")

    def _press(self, event):
        self.focus_set()
        key = self.key_at(event.x, event.y)
        self.drag = (key, event.x, event.y, 0, 0) if key is not None else None
        if self.on_select:
            self.on_select(key)

    def _motion(self, event):
        if not self.drag:
            return
        key, x0, y0, moved_x, moved_y = self.drag
        z = self.zoom
        dx, dy = round((event.x - x0) / z), round((event.y - y0) / z)
        if (dx, dy) != (moved_x, moved_y):
            for item in self.items.get(key, ()):
                self.move(item, (dx - moved_x) * z, (dy - moved_y) * z)
            self.move("chosen", (dx - moved_x) * z, (dy - moved_y) * z)
            self.drag = (key, x0, y0, dx, dy)

    def _release(self, event):
        if not self.drag:
            return
        key, _, _, dx, dy = self.drag
        self.drag = None
        if (dx or dy) and self.on_move:
            self.on_move(key, dx, dy)

    def _wheel(self, event, delta=None):
        delta = delta if delta is not None else event.delta
        key = self.key_at(event.x, event.y) or self.chosen
        if key is not None and self.on_wheel:
            self.on_wheel(key, 1 if delta > 0 else -1)


class UiTab(Tab):
    """Title screen, Menus and Duel: a row of three to choose from, the page
    under it (ui_title.TitlePage, ui_title.MenuPage, ui_duel.DuelPage)."""

    def __init__(self, notebook, app):
        super().__init__(notebook, app, "UI")
        from .ui_duel import DuelPage
        from .ui_title import MenuPage, TitlePage
        top = ttk.Frame(self)
        top.pack(fill="x")
        self.page_name = tk.StringVar(value="title")
        for value, text in (("title", "Title screen"), ("menu", "Menus"), ("duel", "Duel"), ("board", "Duel board")):
            ttk.Radiobutton(top, text=text, value=value, variable=self.page_name, style="Toolbutton",
                            command=self.show_page).pack(side="left", padx=(0, 2))
        self.hint = ttk.Label(top, style="Hint.TLabel")
        self.hint.pack(side="left", padx=(12, 0))
        self.body = ttk.Frame(self)
        self.body.pack(fill="both", expand=True, pady=(6, 0))
        from .ui_board import BoardPage
        self.pages = {"title": TitlePage(self.body, self), "menu": MenuPage(self.body, self),
                      "duel": DuelPage(self.body, self), "board": BoardPage(self.body, self)}
        self.assets = {}
        self.show_page()

    # The pictures off the disc, read once per game files.
    def title_art(self):
        files = getattr(self.app, "files", None)
        key = ("title", id(files))
        if key not in self.assets:
            self.assets[key] = ui_assets.TitleArt(ui_assets.read_su(files) if files else None)
        return self.assets[key]

    def duel_art(self, terrain: int = 0):
        files = getattr(self.app, "files", None)
        key = ("duel", id(files), terrain)
        if key not in self.assets:
            self.assets[key] = ui_assets.DuelArt(getattr(files, "wa", None), terrain)
        return self.assets[key]

    def show_page(self):
        name = self.page_name.get()
        for key, page in self.pages.items():
            if key == name:
                page.pack(fill="both", expand=True)
            else:
                page.pack_forget()
        self.hint.configure(text={"title": "Drag a picture to move it. Click the background for its colours.",
                                  "menu": "Drag a button to place it; the list sets the order.",
                                  "duel": "Drag to move, wheel to size. Each half of the life points is its own.",
                                  "board": "Click a part of the board or the list to choose it."}[name])
        if self.project is not None:
            self.pages[name].fill()

    def refresh(self):
        if self.project is None:
            return
        self.pages[self.page_name.get()].fill()

    def changed(self, key: str):
        """After an edit of project.other[key]: empty objects out, the window told."""
        prune(self.project, key)
        self.app.changed()
