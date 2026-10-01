"""The Map tab: the campaign map's sixteen places (campaign_map.py).

A place is what the game shows while the player stands there: its camera
over the map, its exits' arrows on the screen, and in the town the
Millennium Puzzle marker. The Screen view is that screen at 2x, arrows and
marker dragged where they go; the Overview shows every place and where its
exits lead, the world's sites where their cameras look and the town's where
the marker stands. The form edits every field of the selected place."""
from __future__ import annotations

import base64
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import campaign_map as cm
from . import map_art, pngio
from .tabs import Tab
from .widgets import px, scrolled_tree, ui_font

ZOOM = 2
CANVAS = (cm.SCREEN[0] * ZOOM, cm.SCREEN[1] * ZOOM)
CONFIRM_SCENE = "(enter the place's own scene)"
CONDITIONS = ("always", "while the flag is set", "while the flag is clear")
CONDITION_KINDS = ("always", "set", "clear")
EDGE_COLOURS = {"always": "#4fc36b", "set": "#f2c04c", "clear": "#6fb1ff"}
ARROW_GLYPHS = {"up": "▲", "down": "▼", "left": "◀", "right": "▶"}


def photo(master, image: pngio.Image, zoom: int = 1):
    """A Tk image keeping the picture's transparency (a PNG, Tk 8.6)."""
    image = pngio.scale_nearest(image, zoom)
    return tk.PhotoImage(master=master, data=base64.b64encode(pngio.encode(image)), format="png")


class MapTab(Tab):
    def __init__(self, notebook, app):
        super().__init__(notebook, app, "Map")
        self.index = 0
        self.filling = False
        self.photos = {}
        self.drag = None
        self.references = {}        # camera -> a picture the player chose (this session only)
        self.backgrounds = {}       # (package, camera, spotlight, size) -> map_view picture, or None

        left = ttk.Frame(self)
        left.pack(side="left", fill="y")
        frame, self.tree = scrolled_tree(left, [("id", "#"), ("name", "Place"), ("area", "Area")], [34, 170, 56], 18)
        frame.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", lambda e: self.picked())
        buttons = ttk.Frame(left)
        buttons.pack(fill="x", pady=(4, 0))
        ttk.Button(buttons, text="Reset place", command=self.reset_place).pack(side="left")
        ttk.Button(buttons, text="Reset all", command=self.reset_all).pack(side="left", padx=4)
        self.hint = ttk.Label(left, style="Hint.TLabel", wraplength=px(left, 270), justify="left")
        self.hint.pack(anchor="w", pady=(6, 0))

        middle = ttk.Frame(self, padding=(8, 0))
        middle.pack(side="left", fill="y")
        top = ttk.Frame(middle)
        top.pack(fill="x")
        self.view = tk.StringVar(value="screen")
        ttk.Radiobutton(top, text="Screen", value="screen", variable=self.view, command=self.draw).pack(side="left")
        ttk.Radiobutton(top, text="Overview", value="overview", variable=self.view,
                        command=self.draw).pack(side="left", padx=6)
        ttk.Button(top, text="Pictures...", command=self.show_pictures).pack(side="right", padx=(4, 0))
        ttk.Button(top, text="Reference picture...", command=self.choose_reference).pack(side="right")
        self.package = tk.StringVar(value=cm.PACKAGE_LABELS["before"])
        ttk.Combobox(top, textvariable=self.package, state="readonly", width=16,
                     values=[cm.PACKAGE_LABELS[name] for name, _ in cm.PACKAGES]).pack(side="right", padx=4)
        ttk.Label(top, text="Map").pack(side="right")
        self.package.trace_add("write", lambda *_: self.draw())
        self.canvas = tk.Canvas(middle, width=CANVAS[0], height=CANVAS[1], background="#000000",
                                highlightthickness=0)
        self.canvas.pack(pady=4)
        self.canvas.bind("<ButtonPress-1>", self.press)
        self.canvas.bind("<B1-Motion>", self.motion)
        self.canvas.bind("<ButtonRelease-1>", self.release)
        self.caption = ttk.Label(middle, style="Note.TLabel", wraplength=CANVAS[0], justify="left")
        self.caption.pack(anchor="w")
        self.problems = ttk.Label(middle, style="Warning.TLabel", wraplength=CANVAS[0], justify="left")
        self.problems.pack(anchor="w", pady=(4, 0))

        self.form_frame = ttk.Frame(self)
        self.form_frame.pack(side="left", fill="both", expand=True)
        self.build_form(self.form_frame)

    # --- the form ---------------------------------------------------------------------

    def spin(self, parent, var, low, high, width=6):
        box = ttk.Spinbox(parent, from_=low, to=high, textvariable=var, width=width, increment=1)
        return box

    def build_form(self, parent):
        self.vars = {}

        def var(key, kind=tk.IntVar):
            v = kind(self)
            v.trace_add("write", lambda *_: self.edited())
            self.vars[key] = v
            return v
        self.heading = ttk.Label(parent, font=ui_font(11))
        self.heading.pack(anchor="w")
        camera = ttk.LabelFrame(parent, text="Camera", padding=4)
        camera.pack(fill="x", pady=2)
        for column, (key, text, low, high) in enumerate((("distance", "Distance", -32768, 32767),
                                                         ("heading", "Heading", -32768, 32767),
                                                         ("pitch", "Pitch", -32768, 32767))):
            ttk.Label(camera, text=text).grid(row=0, column=column * 2, sticky="w")
            self.spin(camera, var(key), low, high).grid(row=0, column=column * 2 + 1, padx=(2, 8))
        for column, (key, text) in enumerate((("target_x", "Looks at x"), ("target_z", "z"))):
            ttk.Label(camera, text=text).grid(row=1, column=column * 2, sticky="w")
            self.spin(camera, var(key), -32768, 32767).grid(row=1, column=column * 2 + 1, padx=(2, 8), pady=2)
        marker = ttk.LabelFrame(parent, text="Millennium Puzzle marker (the town)", padding=4)
        marker.pack(fill="x", pady=2)
        ttk.Label(marker, text="x").grid(row=0, column=0)
        self.marker_x = self.spin(marker, var("marker_x"), -32768, 32767)
        self.marker_x.grid(row=0, column=1, padx=(2, 8))
        ttk.Label(marker, text="y").grid(row=0, column=2)
        self.marker_y = self.spin(marker, var("marker_y"), -32768, 32767)
        self.marker_y.grid(row=0, column=3, padx=2)
        self.marker_note = ttk.Label(marker, style="Hint.TLabel")
        self.marker_note.grid(row=1, column=0, columnspan=5, sticky="w")
        confirm = ttk.LabelFrame(parent, text="Confirm (Cross)", padding=4)
        confirm.pack(fill="x", pady=2)
        self.confirm = ttk.Combobox(confirm, textvariable=var("confirm", tk.StringVar), state="readonly", width=30)
        self.confirm.grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(confirm, text="only while exit 1's condition holds",
                        variable=var("gate", tk.BooleanVar)).grid(row=1, column=0, sticky="w")
        self.exit_vars = []
        self.exit_widgets = []
        self.exit_book = ttk.Notebook(parent)
        self.exit_book.pack(fill="x", pady=(4, 0))
        for n in range(cm.EXITS):
            box = ttk.Frame(self.exit_book, padding=6)
            self.exit_book.add(box, text=f"Exit {n + 1}")
            v = {}

            def evar(key, kind=tk.IntVar, n=n, v=v):
                x = kind(self)
                x.trace_add("write", lambda *_: self.edited())
                v[key] = x
                return x
            ttk.Checkbutton(box, text="Used", variable=evar("used", tk.BooleanVar)).grid(row=0, column=0, sticky="w")
            dest = ttk.Combobox(box, textvariable=evar("destination", tk.StringVar), state="readonly", width=20)
            dest.grid(row=0, column=1, columnspan=3, sticky="w")
            pad = ttk.Frame(box)
            pad.grid(row=1, column=0, rowspan=3, padx=(0, 6))
            for name, row, column in (("up", 0, 1), ("left", 1, 0), ("right", 1, 2), ("down", 2, 1)):
                ttk.Checkbutton(pad, text=ARROW_GLYPHS[name], style="Toolbutton", width=2,
                                variable=evar(name, tk.BooleanVar)).grid(row=row, column=column)
            ttk.Label(box, text="When").grid(row=1, column=1, sticky="w")
            ttk.Combobox(box, textvariable=evar("kind", tk.StringVar), values=CONDITIONS, state="readonly",
                         width=20).grid(row=1, column=2, columnspan=2, sticky="w")
            ttk.Label(box, text="Flag").grid(row=2, column=1, sticky="w")
            flag = self.spin(box, evar("flag"), 0, 0x7FFF)
            flag.grid(row=2, column=2, sticky="w")
            ttk.Label(box, text="Frames").grid(row=3, column=1, sticky="w")
            self.spin(box, evar("steps"), 0, 255, 4).grid(row=3, column=2, sticky="w")
            ttk.Label(box, text="Arrow").grid(row=4, column=0, sticky="w")
            ttk.Combobox(box, textvariable=evar("arrow", tk.StringVar),
                         values=[f"{i} {name}" for i, name in enumerate(cm.ARROWS)], state="readonly",
                         width=12).grid(row=4, column=1, columnspan=2, sticky="w")
            at = ttk.Frame(box)
            at.grid(row=5, column=0, columnspan=4, sticky="w")
            ttk.Label(at, text="at x").pack(side="left")
            self.spin(at, evar("x"), -32768, 32767, 5).pack(side="left", padx=2)
            ttk.Label(at, text="y").pack(side="left")
            self.spin(at, evar("y"), -32768, 32767, 5).pack(side="left", padx=2)
            self.exit_vars.append(v)
            self.exit_widgets.append((box, dest, flag))

    # --- the project ----------------------------------------------------------------------

    @property
    def map(self):
        return cm.state(self.project) if self.project is not None else None

    def refresh(self):
        self.backgrounds = {}
        if getattr(self, "pictures", None) is not None and self.pictures.winfo_exists():
            self.pictures.refresh()
        self.fill_list()
        state = "normal" if self.project is not None and cm.available(self.project) else "disabled"
        self.set_enabled(state == "normal")
        if state == "normal":
            names = [cm.label(self.project, i) for i in range(cm.COUNT)]
            self.confirm.configure(values=[CONFIRM_SCENE] + names[1:])
            for _, dest, _ in self.exit_widgets:
                dest.configure(values=names)
            self.select(min(self.index, cm.COUNT - 1))
        else:
            self.canvas.delete("all")
            self.heading.configure(text="")
            self.caption.configure(text="The game files hold no campaign map (the overworld packages of "
                                        "WA_MRG.MRG): choose the retail disc under File > Game files.")

    def set_enabled(self, on: bool):
        def walk(widget):
            for child in widget.winfo_children():
                try:
                    if isinstance(child, ttk.Combobox):
                        child.state(["!disabled", "readonly"] if on else ["disabled"])
                    elif isinstance(child, (ttk.Spinbox, ttk.Checkbutton, ttk.Button, ttk.Entry)):
                        child.state(["!disabled"] if on else ["disabled"])
                except tk.TclError:
                    pass
                walk(child)
        walk(self.form_frame)

    def fill_list(self):
        self.tree.delete(*self.tree.get_children())
        if self.project is None or not cm.available(self.project):
            return
        for i in range(cm.COUNT):
            tags = ("changed",) if cm.changed(self.project, i) else ()
            self.tree.insert("", "end", iid=str(i), values=(i, cm.name(self.project, i),
                                                           "Town" if i >= cm.TOWN_FIRST else "World"), tags=tags)
        self.hint.configure(text="Drag an arrow or the marker on the screen, or a place in the overview. "
                                 "Saving writes \"data\" patches of both overworld packages (before and after "
                                 "the coup); the game needs a restart to read them.")

    def update_row(self, index):
        if self.tree.exists(str(index)):
            self.tree.item(str(index), tags=("changed",) if cm.changed(self.project, index) else ())

    def picked(self):
        selection = self.tree.selection()
        if selection and int(selection[0]) != self.index:
            self.select(int(selection[0]))

    def select(self, index):
        self.index = index
        if self.tree.exists(str(index)) and self.tree.selection() != (str(index),):
            self.tree.selection_set(str(index))
            self.tree.see(str(index))
        self.fill_form()
        self.draw()

    def goto(self, index):
        if isinstance(index, int) and 0 <= index < cm.COUNT:
            self.select(index)

    # --- the form <-> the place ---------------------------------------------------------------

    def fill_form(self):
        loc = self.map.locations[self.index]
        self.filling = True
        try:
            self.heading.configure(text=cm.label(self.project, self.index) +
                                   ("  (town)" if self.index >= cm.TOWN_FIRST else "  (world map)"))
            for key in ("distance", "heading", "pitch", "target_x", "target_z", "marker_x", "marker_y"):
                self.vars[key].set(getattr(loc, key))
            self.vars["gate"].set(bool(loc.gate))
            self.vars["confirm"].set(self.confirm_text(loc.confirm))
            town = self.index >= cm.TOWN_FIRST
            for box in (self.marker_x, self.marker_y):
                box.state(["!disabled"] if town else ["disabled"])
            self.marker_note.configure(text="" if town else "The world map draws no marker: these are kept as "
                                                            "the disc has them.")
            for n, e in enumerate(loc.exits):
                v = self.exit_vars[n]
                v["used"].set(e.used)
                v["destination"].set(cm.label(self.project, e.destination) if e.destination < cm.COUNT
                                     else ("" if e.destination == cm.NO_EXIT else str(e.destination)))
                for name, bit in cm.DIRECTIONS:
                    v[name].set(bool(e.buttons & bit))
                kind, flag = cm.condition_parts(e.condition)
                v["kind"].set(CONDITIONS[CONDITION_KINDS.index(kind)])
                v["flag"].set(flag)
                v["steps"].set(e.steps)
                v["arrow"].set(f"{e.arrow} {cm.ARROWS[e.arrow]}" if e.arrow < len(cm.ARROWS) else str(e.arrow))
                v["x"].set(e.x)
                v["y"].set(e.y)
            self.exit_titles()
        finally:
            self.filling = False
        self.show_problems()

    def exit_titles(self):
        loc = self.map.locations[self.index]
        for n, e in enumerate(loc.exits):
            if e.used:
                where = cm.name(self.project, e.destination).split(" / ")[0] if e.destination < cm.COUNT else "?"
                glyphs = "".join(ARROW_GLYPHS[d] for d in cm.direction_names(e.buttons))
                text = f"{n + 1} {glyphs} {where}"
            else:
                text = f"{n + 1} (none)"
            self.exit_book.tab(n, text=text)

    def confirm_text(self, value):
        if value == 0:
            return CONFIRM_SCENE
        return cm.label(self.project, value) if value < cm.COUNT else str(value)

    @staticmethod
    def number(var, default=0):
        try:
            return int(var.get())
        except (tk.TclError, ValueError):
            return None

    @staticmethod
    def index_of(text):
        head = str(text).split(":", 1)[0].split(" ", 1)[0]
        return int(head) if head.isdigit() else None

    def edited(self):
        """A field changed: store the form in the place, when it reads."""
        if self.filling or self.project is None or not cm.available(self.project):
            return
        loc = self.map.locations[self.index].copy()
        for key in ("distance", "heading", "pitch", "target_x", "target_z", "marker_x", "marker_y"):
            value = self.number(self.vars[key])
            if value is None or not -32768 <= value <= 32767:
                return
            setattr(loc, key, value)
        gate = bool(self.vars["gate"].get())
        loc.gate = (loc.gate or 1) if gate else 0
        confirm = self.vars["confirm"].get()
        loc.confirm = 0 if confirm == CONFIRM_SCENE else (self.index_of(confirm) if self.index_of(confirm) is not None
                                                          else loc.confirm)
        refill = False
        for n, e in enumerate(loc.exits):
            v = self.exit_vars[n]
            was_used = e.used
            if not v["used"].get():
                e.destination = cm.NO_EXIT
                refill |= was_used
            else:
                picked = self.index_of(v["destination"].get())
                if picked is not None:
                    e.destination = picked
                elif not was_used:
                    e.destination = 0
                if not was_used:
                    refill = True
                    if not self.number(v["steps"]):
                        v["steps"].set(16)      # a new exit: the game's usual length
            buttons = e.buttons & ~cm.DIRECTION_BITS
            for name, bit in cm.DIRECTIONS:
                if v[name].get():
                    buttons |= bit
            e.buttons = buttons
            flag = self.number(v["flag"])
            if flag is None or not 0 <= flag <= 0x7FFF:
                return
            e.condition = cm.condition_value(CONDITION_KINDS[CONDITIONS.index(v["kind"].get())]
                                             if v["kind"].get() in CONDITIONS else "always", flag)
            for key in ("steps", "x", "y"):
                value = self.number(v[key])
                if value is None:
                    return
                setattr(e, key, value)
            if not 0 <= e.steps <= 255 or not -32768 <= e.x <= 32767 or not -32768 <= e.y <= 32767:
                return
            arrow = self.index_of(v["arrow"].get())
            if arrow is not None:
                e.arrow = arrow
        self.store(loc)
        if refill:
            self.after_idle(self.fill_form)

    def store(self, loc):
        if loc == self.map.locations[self.index]:
            return
        self.map.locations[self.index] = loc
        self.exit_titles()
        self.update_row(self.index)
        self.app.changed()
        self.draw()
        self.show_problems()

    def show_problems(self):
        issues = []
        cm.check(self.project, issues)
        mine = [i for i in issues if i.target == self.index]
        self.problems.configure(text="\n".join(f"{i.level}: {i.message}" for i in mine[:6]))

    def reset_place(self):
        if self.project is None or not cm.available(self.project):
            return
        if cm.changed(self.project, self.index):
            cm.reset(self.project, self.index)
            self.app.changed()
            self.update_row(self.index)
            self.fill_form()
            self.draw()

    def reset_all(self):
        if self.project is None or not cm.any_changed(self.project):
            return
        if not messagebox.askyesno("Map", "Put every place back as the disc has it?", parent=self):
            return
        cm.reset_all(self.project)
        self.app.changed()
        self.fill_list()
        self.select(self.index)

    # --- the pictures ---------------------------------------------------------------------------

    def image(self, key, make):
        """A Tk image, made once per key (the sprites) and kept alive."""
        if key not in self.photos:
            made = make()
            self.photos[key] = made
        return self.photos[key]

    def sprite(self, key, found):
        if found is None:
            return None
        image, left, top = found
        return self.image((key, self.version()), lambda: photo(self, image, ZOOM)), left, top

    def version(self):
        return map_art.state(self.project).version

    def strips(self):
        return {p: image for p in map_art.STRIP_PALETTES
                if (image := map_art.strip_override(self.project, p)) is not None}

    def package_name(self):
        return next(name for name, sector in cm.PACKAGES if sector == self.package_sector())

    def overrides(self):
        return map_art.texture_overrides(self.project, self.package_name())

    def camera(self, index):
        loc = self.map.locations[index]
        return loc.distance, loc.heading, loc.pitch, loc.target_x, loc.target_z

    def package_sector(self):
        for name, sector in cm.PACKAGES:
            if cm.PACKAGE_LABELS[name] == self.package.get():
                return sector
        return cm.PACKAGES[0][1]

    def picture(self, key, make):
        """A map_view picture, drawn once; None when the disc's model cannot
        be read (said in the caption)."""
        if key not in self.backgrounds:
            try:
                self.backgrounds[key] = make()
            except Exception as problem:     # a disc whose map the renderer cannot read
                self.backgrounds[key] = None
                self.drawing_problem = f"The map could not be drawn: {problem}"
        return self.backgrounds[key]

    def background(self, index):
        """(image, where it comes from) for the place's screen, or None."""
        from . import map_view
        camera = self.camera(index)
        if camera in self.references:
            return self.references[camera], "your reference picture"
        files = self.app.files
        if files is None:
            return None
        sector = self.package_sector()
        picture = self.picture(("view", sector, camera, index < cm.TOWN_FIRST, self.version()),
                               lambda: map_view.render(map_view.model(files.wa, sector), camera,
                                                       spotlight=index < cm.TOWN_FIRST, overrides=self.overrides()))
        if picture is None:
            return None
        return picture, f"drawn from the disc's map model, {self.package.get()}"

    def draw(self):
        self.canvas.delete("all")
        if self.project is not None and getattr(self, "drawn_version", None) != (id(self.project), self.version()):
            self.photos.clear()         # the pictures of another mod, or before an import
            self.drawn_version = (id(self.project), self.version())
        if self.project is None or not cm.available(self.project):
            return
        if self.view.get() == "overview":
            self.draw_overview()
        else:
            self.draw_screen()

    def draw_screen(self):
        data = self.map.retail
        loc = self.map.locations[self.index]
        found = self.background(self.index)
        if found is not None:
            picture, where = found
            key = ("bg", id(picture))
            self.canvas.create_image(0, 0, anchor="nw", image=self.image(key, lambda: photo(
                self, pngio.resample(picture, *cm.SCREEN) if picture.size != cm.SCREEN else picture, ZOOM)))
        else:
            where = getattr(self, "drawing_problem", "") or "no picture of the map"
            where += "; Reference picture... takes a screenshot of the game"
            for x in range(0, CANVAS[0], 40):
                self.canvas.create_line(x, 0, x, CANVAS[1], fill="#1c2430")
            for y in range(0, CANVAS[1], 40):
                self.canvas.create_line(0, y, CANVAS[0], y, fill="#1c2430")
        strips = self.strips()
        panel = self.sprite("panel", cm.sprite_image(data, *cm.PANEL, strips))
        if panel:
            self.canvas.create_image((cm.PANEL_AT[0] + panel[1]) * ZOOM, (cm.PANEL_AT[1] + panel[2]) * ZOOM,
                                     anchor="nw", image=panel[0])
        self.canvas.create_text(160 * ZOOM, 30 * ZOOM, text=cm.name(self.project, self.index).split(" / ")[0],
                                fill="#ffffff", font=ui_font(12))
        labels = {}
        for n, e in enumerate(loc.exits):
            if e.used:
                where_to = cm.name(self.project, e.destination).split(" / ")[0] if e.destination < cm.COUNT else "?"
                text = f"{n + 1}: {where_to}"
                if e.condition:
                    kind, flag = cm.condition_parts(e.condition)
                    text += f" ({'' if kind == 'set' else 'not '}{flag})"
                labels.setdefault((e.x, e.y), []).append((n, text))
        for n, e in enumerate(loc.exits):
            if not e.used:
                continue
            arrow = self.sprite(("arrow", e.arrow), cm.arrow_image(data, e.arrow, strips)) if e.arrow < 8 else None
            tag = ("exit", f"exit{n}", f"arrow{n}")
            if arrow:
                self.canvas.create_image((e.x + arrow[1]) * ZOOM, (e.y + arrow[2]) * ZOOM, anchor="nw",
                                         image=arrow[0], tags=tag)
            else:
                self.canvas.create_rectangle(e.x * ZOOM - 10, e.y * ZOOM - 10, e.x * ZOOM + 10, e.y * ZOOM + 10,
                                             outline="#ff5050", tags=tag)
            group = labels.get((e.x, e.y), [])
            if not group or group[0][0] != n:
                continue        # one label for the exits that share a place
            text = chr(10).join(t for _, t in group)
            tag = ("exit", "label", f"exit{n}") + tuple(f"exit{m}" for m, _ in group[1:])
            anchor = "e" if e.x > 200 else "w" if e.x < 120 else "n"
            dx = -16 if anchor == "e" else 16 if anchor == "w" else 0
            dy = 16 if anchor == "n" else 0
            self.canvas.create_text(e.x * ZOOM + dx, e.y * ZOOM + dy, text=text, anchor=anchor, fill="#ffffff",
                                    font=ui_font(9, "normal"), tags=tag)
        if self.index >= cm.TOWN_FIRST:
            marker = self.sprite("marker", cm.sprite_image(data, *cm.MARKER, strips))
            if marker:
                self.canvas.create_image((loc.marker_x + marker[1]) * ZOOM, (loc.marker_y + marker[2]) * ZOOM,
                                         anchor="nw", image=marker[0], tags=("marker",))
        self.canvas.tag_raise("label")      # the exits' names over the marker
        self.caption.configure(text=f"The screen at this place, 2x ({where}). Arrows are drawn with the exit's "
                                    "picture at its x, y; the conditions shown are the flags each needs.")

    # --- overview -------------------------------------------------------------------------------

    WORLD_BOX = (0, 40, 440, 480)       # canvas box for the world map, from above
    TOWN_BOX = (448, 40, 640, 184)      # canvas box for the town: its screen at 0.6
    WORLD_CENTRE = (0, 0)               # the terrain spans -1333..1333 on x and z
    WORLD_SPAN = 2800

    def world_frame(self):
        x0, y0, x1, y1 = self.WORLD_BOX
        scale = min(x1 - x0, y1 - y0) / self.WORLD_SPAN
        return self.WORLD_CENTRE[0], self.WORLD_CENTRE[1], scale, (x0 + x1) / 2, (y0 + y1) / 2

    def node(self, index):
        loc = self.map.locations[index]
        if index < cm.TOWN_FIRST:
            cx, cz, scale, ox, oy = self.world_frame()
            # Turned as the world's cameras mostly look (heading about half a
            # turn): -x up the picture, +z to the right.
            return ox + (loc.target_z - cz) * scale, oy + (loc.target_x - cx) * scale
        x0, y0, x1, y1 = self.TOWN_BOX
        return x0 + loc.marker_x * (x1 - x0) / cm.SCREEN[0], y0 + loc.marker_y * (y1 - y0) / cm.SCREEN[1]

    def draw_overview(self):
        from . import map_view
        c = self.canvas
        files = self.app.files
        sector = self.package_sector()
        x0, y0, x1, y1 = self.WORLD_BOX
        if files is not None:
            version = self.version()
            top = self.picture(("top", sector, version), lambda: map_view.render_top(
                map_view.model(files.wa, sector), self.WORLD_CENTRE, self.WORLD_SPAN, (x1 - x0, y1 - y0),
                overrides=self.overrides()))
            if top is not None:
                c.create_image(x0, y0, anchor="nw", image=self.image(("top", sector, version),
                                                                     lambda: photo(self, top)))
            town = self.map.locations[cm.TOWN_FIRST]
            if town:
                tx0, ty0, tx1, ty1 = self.TOWN_BOX
                camera = self.camera(cm.TOWN_FIRST)
                view = self.picture(("view", sector, camera, False, version), lambda: map_view.render(
                    map_view.model(files.wa, sector), camera, overrides=self.overrides()))
                if view is not None:
                    small = pngio.resample(view, tx1 - tx0, ty1 - ty0)
                    c.create_image(tx0, ty0, anchor="nw", image=self.image(("town", sector, camera, version),
                                                                            lambda: photo(self, small)))
        tx0, ty0, tx1, ty1 = self.TOWN_BOX
        c.create_rectangle(tx0, ty0, tx1, ty1, outline="#3b4b5e")
        c.create_text(tx0, ty0 - 4, text="The town (place 10's camera)", anchor="sw", fill="#c4c8cd",
                      font=ui_font(9, "normal"))
        c.create_text(x0 + 4, y0 - 4, anchor="sw", fill="#c4c8cd", font=ui_font(9, "normal"),
                      text="The world map from above: each site where its camera looks")
        legend = [("always", "always"), ("set", "while a flag is set"), ("clear", "while a flag is clear")]
        for k, (kind, text) in enumerate(legend):
            y = 204 + k * 16
            c.create_line(tx0, y, tx0 + 24, y, fill=EDGE_COLOURS[kind], width=2, arrow="last")
            c.create_text(tx0 + 30, y, text=text, anchor="w", fill="#c4c8cd", font=ui_font(9, "normal"))
        c.create_line(tx0, 204 + 48, tx0 + 24, 204 + 48, fill="#c4c8cd", width=2, arrow="last", dash=(4, 3))
        c.create_text(tx0 + 30, 204 + 48, text="Confirm", anchor="w", fill="#c4c8cd", font=ui_font(9, "normal"))
        locations = self.map.locations
        for index in range(cm.COUNT):
            ax, ay = self.node(index)
            for what, destination, condition in cm.edges(locations, index):
                if destination == index or what == "cancel":
                    continue
                bx, by = self.node(destination)
                kind = cm.condition_parts(condition)[0]
                width = 3 if self.index in (index, destination) else 1
                # A little to the side, so a way back does not cover the way there.
                dx, dy = by - ay, ax - bx
                length = max((dx * dx + dy * dy) ** 0.5, 1)
                sx, sy = dx / length * 3, dy / length * 3
                c.create_line(ax + sx, ay + sy, bx + sx, by + sy, fill=EDGE_COLOURS[kind], width=width,
                              arrow="last", arrowshape=(10, 12, 4), dash=() if what != "confirm" else (4, 3))
        for index in range(cm.COUNT):
            x, y = self.node(index)
            selected = index == self.index
            fill = "#f2c04c" if selected else ("#8ab4f8" if index >= cm.TOWN_FIRST else "#e8eaed")
            c.create_oval(x - 6, y - 6, x + 6, y + 6, fill=fill, outline="#000000", tags=("place", f"place{index}"))
            right = x > (tx0 + tx1) / 2 if index >= cm.TOWN_FIRST else x > (x0 + x1) / 2 + 60
            name = cm.name(self.project, index).split(" / ")[0] if index < cm.TOWN_FIRST else ""
            if index >= cm.TOWN_FIRST:
                c.create_text(tx0, 284 + (index - cm.TOWN_FIRST) * 15, anchor="w", fill="#c4c8cd",
                              font=ui_font(9, "bold" if selected else "normal"),
                              text=f"{index} {cm.name(self.project, index).split(' / ')[0]}")
            for ox, oy in ((1, 1), (-1, -1), (1, -1), (-1, 1)):
                c.create_text(x + (-9 if right else 9) + ox, y + oy, text=f"{index} {name}".strip(), fill="#000000",
                              anchor="e" if right else "w", font=ui_font(9, "bold" if selected else "normal"),
                              tags=("place", f"place{index}"))
            c.create_text(x + (-9 if right else 9), y, text=f"{index} {name}".strip(), anchor="e" if right else "w",
                          fill="#ffffff", font=ui_font(9, "bold" if selected else "normal"),
                          tags=("place", f"place{index}"))
        self.caption.configure(text="Every place and where its exits lead (thicker: to and from the selected one). "
                                    "Drag a world site to move where its camera looks, a town place to move its "
                                    "marker; click one to edit it. Cancel in the town, once the tournament is over, "
                                    "always leads back to Metropolis (not drawn).")

    # --- dragging ---------------------------------------------------------------------------------

    def hit(self, event):
        for item in reversed(self.canvas.find_overlapping(event.x - 2, event.y - 2, event.x + 2, event.y + 2)):
            for tag in self.canvas.gettags(item):
                if tag.startswith("exit") and tag[4:].isdigit():
                    return "exit", int(tag[4:])
                if tag == "marker":
                    return "marker", None
                if tag.startswith("place") and tag[5:].isdigit():
                    return "place", int(tag[5:])
        return None

    def press(self, event):
        if self.project is None or not cm.available(self.project):
            return
        found = self.hit(event)
        self.drag = (found, event.x, event.y, False) if found else None
        if found and found[0] == "place" and found[1] != self.index:
            self.select(found[1])
            self.drag = (found, event.x, event.y, False)

    def motion(self, event):
        if not self.drag:
            return
        found, x, y, _ = self.drag
        kind, n = found
        tags = {"exit": f"exit{n}", "marker": "marker", "place": f"place{n}"}[kind]
        self.canvas.move(tags, event.x - x, event.y - y)
        self.drag = (found, event.x, event.y, True)

    def release(self, event):
        if not self.drag:
            return
        found, x, y, moved = self.drag
        self.drag = None
        if not moved:
            return
        kind, n = found
        loc = self.map.locations[self.index].copy()
        if kind == "exit":
            items = self.canvas.find_withtag(f"arrow{n}")
            left, top = self.canvas.coords(items[0])[:2]
            arrow = cm.arrow_image(self.map.retail, loc.exits[n].arrow, self.strips()) \
                if loc.exits[n].arrow < 8 else None
            ox, oy = (arrow[1], arrow[2]) if arrow else (0, 0)
            if not arrow:
                left, top = left + 10, top + 10
            loc.exits[n].x = round(left / ZOOM) - ox
            loc.exits[n].y = round(top / ZOOM) - oy
        elif kind == "marker":
            left, top = self.canvas.coords(self.canvas.find_withtag("marker")[0])[:2]
            marker = cm.sprite_image(self.map.retail, *cm.MARKER, self.strips())
            loc.marker_x = round(left / ZOOM) - marker[1]
            loc.marker_y = round(top / ZOOM) - marker[2]
        elif kind == "place":
            ox, oy = self.node(n)
            items = self.canvas.find_withtag(f"place{n}")
            bx = self.canvas.coords(items[0])
            nx, ny = (bx[0] + bx[2]) / 2, (bx[1] + bx[3]) / 2
            if n < cm.TOWN_FIRST:
                _, _, scale, _, _ = self.world_frame()
                loc.target_z += round((nx - ox) / scale)
                loc.target_x += round((ny - oy) / scale)
            else:
                x0, y0, x1, y1 = self.TOWN_BOX
                loc.marker_x = round((nx - x0) * cm.SCREEN[0] / (x1 - x0))
                loc.marker_y = round((ny - y0) * cm.SCREEN[1] / (y1 - y0))
        self.store(loc)
        self.fill_form()

    # --- reference pictures ---------------------------------------------------------------------------

    def choose_reference(self):
        if self.project is None or not cm.available(self.project):
            return
        path = filedialog.askopenfilename(parent=self, title="A screenshot of this place in the game",
                                          filetypes=[("PNG", "*.png"), ("All files", "*.*")])
        if not path:
            return
        try:
            picture = pngio.read(path)
        except (OSError, pngio.PngError) as problem:
            messagebox.showerror("Map", f"Could not read {path}: {problem}", parent=self)
            return
        self.references[self.camera(self.index)] = picture
        self.draw()

    # --- the map's pictures (map_art) ------------------------------------------------------------

    def show_pictures(self):
        if self.project is None or not cm.available(self.project):
            return
        if getattr(self, "pictures", None) is None or not self.pictures.winfo_exists():
            self.pictures = MapPictures(self)
        else:
            self.pictures.refresh()
            self.pictures.lift()

    def art_changed(self):
        self.app.changed()
        self.draw()


class MapPictures(tk.Toplevel):
    """The map's sprites and terrain textures in the mod's texture pack."""

    def __init__(self, tab):
        super().__init__(tab)
        self.tab = tab
        self.title("Map pictures")
        self.photos = {}
        body = ttk.Frame(self, padding=8)
        body.pack(fill="both", expand=True)
        sprites = ttk.LabelFrame(body, text="Sprites (the map's strip: name panel, marker, arrows)", padding=6)
        sprites.pack(fill="x")
        self.previews = ttk.Frame(sprites)
        self.previews.pack(anchor="w")
        row = ttk.Frame(sprites)
        row.pack(anchor="w", pady=(6, 0))
        self.sprite = tk.StringVar(value=map_art.SPRITES[0][0])
        ttk.Combobox(row, textvariable=self.sprite, values=[s[0] for s in map_art.SPRITES], state="readonly",
                     width=30).pack(side="left")
        ttk.Button(row, text="Import picture...", command=self.import_sprite).pack(side="left", padx=4)
        row = ttk.Frame(sprites)
        row.pack(anchor="w", pady=(4, 0))
        ttk.Button(row, text="Export sprites...", command=self.export_sprites).pack(side="left")
        ttk.Button(row, text="Import sprites...", command=self.import_sprites).pack(side="left", padx=4)
        ttk.Button(row, text="Revert sprites", command=self.revert_sprites).pack(side="left")
        ttk.Label(sprites, style="Hint.TLabel", wraplength=px(self, 620), justify="left",
                  text="A picture of one sprite goes into every frame of its animation (the marker's 16, an "
                       "arrow's 10), so it keeps its motion; an arrow and its mirror share their cells. Export "
                       "sprites writes the strip through each palette (sprites-p0.png to p3.png, 256x256, or the "
                       "mod's at its size) to paint over; Import sprites takes those files back. Up to 4x: "
                       "Internal 2x and 4x draw the detail, the console's resolution averages it down.").pack(
            anchor="w", pady=(6, 0))
        terrain = ttk.LabelFrame(body, text="Terrain textures", padding=6)
        terrain.pack(fill="x", pady=(8, 0))
        row = ttk.Frame(terrain)
        row.pack(anchor="w")
        ttk.Label(row, text="Map").pack(side="left")
        self.package = tk.StringVar(value=cm.PACKAGE_LABELS["before"])
        box = ttk.Combobox(row, textvariable=self.package, state="readonly", width=16,
                           values=[cm.PACKAGE_LABELS[name] for name, _ in cm.PACKAGES])
        box.pack(side="left", padx=4)
        self.package.trace_add("write", lambda *_: self.refresh())
        self.count = ttk.Label(row)
        self.count.pack(side="left", padx=8)
        row = ttk.Frame(terrain)
        row.pack(anchor="w", pady=(4, 0))
        ttk.Button(row, text="Export textures...", command=self.export_textures).pack(side="left")
        ttk.Button(row, text="Import textures...", command=self.import_textures).pack(side="left", padx=4)
        ttk.Button(row, text="Revert textures", command=self.revert_textures).pack(side="left")
        ttk.Label(terrain, style="Hint.TLabel", wraplength=px(self, 620), justify="left",
                  text="The terrain is a 3D model with tiled textures (most are drawn in many places), so it is "
                       "repainted a texture at a time: Export writes each texture as the map draws it "
                       "(textureNN-PPPP.png, one per palette it is drawn with), Import takes the files of a "
                       "folder with those names. The map before the coup and the one after are two models with "
                       "textures of their own.").pack(anchor="w", pady=(6, 0))
        self.status = ttk.Label(body, style="Note.TLabel", wraplength=px(self, 620), justify="left")
        self.status.pack(anchor="w", pady=(8, 0))
        ttk.Button(body, text="Close", command=self.destroy).pack(anchor="e", pady=(8, 0))
        self.refresh()

    @property
    def project(self):
        return self.tab.project

    def package_name(self):
        return next(name for name, _ in cm.PACKAGES if cm.PACKAGE_LABELS[name] == self.package.get())

    def refresh(self):
        if self.project is None or not cm.available(self.project):
            self.destroy()
            return
        for child in self.previews.winfo_children():
            child.destroy()
        self.photos = {}
        data = cm.state(self.project).retail
        strips = {p: image for p in map_art.STRIP_PALETTES
                  if (image := map_art.strip_override(self.project, p)) is not None}
        shown = [("Marker", cm.MARKER), ("Name panel", cm.PANEL)] + \
            [(name, (2, i)) for i, name in enumerate(cm.ARROWS) if name in ("right", "down", "up", "up-right")]
        for column, (label, (animation, variant)) in enumerate(shown):
            found = cm.sprite_image(data, animation, variant, strips)
            if found is None:
                continue
            image = found[0]
            zoom = 1 if image.width > 64 else 2
            self.photos[label] = photo(self, image, zoom)
            ttk.Label(self.previews, text=label, style="Note.TLabel").grid(row=0, column=column, padx=4)
            ttk.Label(self.previews, image=self.photos[label]).grid(row=1, column=column, padx=4)
        st = map_art.state(self.project)
        package = self.package_name()
        total = len(map_art.package_textures(data, package))
        mine = sum(1 for t in st.textures if t.package == package)
        self.count.configure(text=f"{total} textures, {mine} replaced by the mod" if total else
                             "the disc's map model could not be read")

    def done(self, notes, what):
        self.tab.art_changed()
        self.refresh()
        self.status.configure(text=what + ("\n" + "\n".join(notes[:8]) if notes else ""))

    def import_sprite(self, path=None):
        label = self.sprite.get()
        _, animation, variant = next(s for s in map_art.SPRITES if s[0] == label)
        path = path or filedialog.askopenfilename(parent=self, title=f"A picture for the {label.lower()}",
                                                  filetypes=[("PNG", "*.png"), ("All files", "*.*")])
        if not path:
            return
        try:
            notes = map_art.set_sprite(self.project, animation, variant, pngio.read(path))
        except (OSError, pngio.PngError, ValueError) as problem:
            messagebox.showerror("Map pictures", f"Could not use {path}: {problem}", parent=self)
            return
        self.done(notes, f"{label}: {path}")

    def export_sprites(self, folder=None):
        folder = folder or filedialog.askdirectory(parent=self, title="A folder for the sprites")
        if folder:
            written = map_art.export_sprites(self.project, folder)
            self.status.configure(text=f"Wrote {len(written)} files to {folder}")

    def import_sprites(self, folder=None):
        folder = folder or filedialog.askdirectory(parent=self, title="The folder with sprites-p0.png to p3.png")
        if not folder:
            return
        try:
            notes = map_art.import_sprites(self.project, folder)
        except (OSError, pngio.PngError) as problem:
            messagebox.showerror("Map pictures", str(problem), parent=self)
            return
        self.done(notes, "Nothing named sprites-p0.png to p3.png there." if not notes else "Imported:")

    def revert_sprites(self):
        map_art.revert_sprites(self.project)
        self.done([], "The sprites are the disc's again.")

    def export_textures(self, folder=None):
        folder = folder or filedialog.askdirectory(parent=self, title="A folder for the textures")
        if folder:
            written = map_art.export_textures(self.project, self.package_name(), folder)
            self.status.configure(text=f"Wrote {len(written)} textures to {folder}")

    def import_textures(self, folder=None):
        folder = folder or filedialog.askdirectory(parent=self, title="The folder with the textures")
        if not folder:
            return
        try:
            notes = map_art.import_textures(self.project, self.package_name(), folder)
        except (OSError, pngio.PngError) as problem:
            messagebox.showerror("Map pictures", str(problem), parent=self)
            return
        self.done(notes, "No texture of this map is named there." if not notes else "Imported:")

    def revert_textures(self):
        map_art.revert_textures(self.project, self.package_name())
        self.done([], f"The textures of the map {self.package.get()} are the disc's again.")
