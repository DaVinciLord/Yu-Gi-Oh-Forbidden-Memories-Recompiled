"""The UI tab's Duel page: the duel's pictures ("ui"."duel", notes/modding.md
"The duel's pictures") on a duel drawn from the disc's own pieces -- the
life-point panel's two halves and their digits, the FIELD box, the card
bar, the hand's and the field's cursors -- over a sketch of the field and
the hand (the 3D field is not drawn here). Drag a picture to move it, the
mouse wheel sizes it about its middle, and the side has the rest: its
colours, its words (the life-point halves), a picture of the mod's own,
hidden, back to the game's."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from . import art, pngio, ui_assets as ua
from .ui_tab import (ColourButton, Stage, as_int, colour_text, ensure, import_image, mod_image, section, set_member,
                     sized)
from .widgets import px

ELEMENTS = ["lp_opponent", "lp_player", "field", "card_bar", "hand_cursor", "field_cursor"]
NAMES = {"lp_opponent": "Opponent's LP", "lp_player": "Your LP", "field": "FIELD box", "card_bar": "Card bar",
         "hand_cursor": "Hand cursor", "field_cursor": "Field cursor"}
# What ui_config.c lets each take (its `takes`).
PLACED = {"lp_opponent", "lp_player", "field", "hand_cursor", "field_cursor"}
LABELLED = {"lp_opponent", "lp_player"}
SCALE_MIN, SCALE_MAX = 25, 400
# The hand the sketch holds: the five cards the first duel deals (deck 1-40, as the
# runtime tests play).
HAND = [9, 20, 27, 31, 28]
# The words' boxes in a half (hd_text.c name_boxes): their rows from the half's
# top, and where they meet the panel.
LABEL_TOP = {"lp_opponent": 9, "lp_player": 1}
LABEL_JOIN = 25
LABEL_COLOUR = {"lp_opponent": ("#2c3c98", "#b0b8ff"), "lp_player": ("#b81818", "#ffd8d8")}


def place(rect, element: dict):
    """(dx, dy, scale) of an element and the function that moves a point."""
    x, y, w, h = rect
    px_, py_ = x + w // 2, y + h // 2
    dx, dy = as_int(element.get("x")), as_int(element.get("y"))
    scale = as_int(element.get("scale"), 100) if as_int(element.get("scale"), 100) >= SCALE_MIN else 100

    def at(gx, gy):
        def one(v, p, d):
            t = (v - p) * scale
            return p + d + ((t + 50) // 100 if t >= 0 else -((-t + 50) // 100))
        return one(gx, px_, dx), one(gy, py_, dy)
    return at


class DuelPage(ttk.Frame):
    def __init__(self, master, tab):
        super().__init__(master)
        self.tab = tab
        self.chosen = "lp_player"
        self.loading = False
        left = ttk.Frame(self)
        left.pack(side="left", fill="y")
        self.stage = Stage(left, zoom=2, on_select=self.select, on_move=self.moved, on_wheel=self.wheel)
        self.stage.pack(anchor="nw")
        chips = ttk.Frame(left)
        chips.pack(fill="x", pady=(6, 0))
        self.chip = tk.StringVar(value=self.chosen)
        self.chips = {}
        for name in ELEMENTS:
            self.chips[name] = ttk.Radiobutton(chips, text=NAMES[name], value=name, variable=self.chip,
                                               style="Toolbutton", command=lambda: self.select(self.chip.get()))
            self.chips[name].pack(side="left", padx=(0, 2))
        views = ttk.Frame(left)
        views.pack(fill="x", pady=(4, 0))
        self.opponent_turn = tk.BooleanVar(value=False)
        ttk.Checkbutton(views, text="Opponent's turn", variable=self.opponent_turn,
                        command=self.draw).pack(side="left")

        side = ttk.Frame(self, padding=(12, 0, 0, 0))
        side.pack(side="left", fill="both", expand=True)
        self.title = ttk.Label(side, font=("TkDefaultFont", 12, "bold"))
        self.title.pack(anchor="w")
        self.what = ttk.Label(side, style="Hint.TLabel", wraplength=px(self, 330), justify="left")
        self.what.pack(anchor="w", pady=(0, 8))
        form = ttk.Frame(side)
        form.pack(anchor="w", fill="x")
        self.vars = {key: tk.StringVar() for key in ("x", "y", "scale", "label", "width", "height")}
        row = 0

        def line(text, widget):
            nonlocal row
            ttk.Label(form, text=text).grid(row=row, column=0, sticky="w", pady=2, padx=(0, 8))
            widget.grid(row=row, column=1, sticky="w", pady=2)
            row += 1
            return widget

        places = ttk.Frame(form)
        self.x_box = ttk.Spinbox(places, from_=-400, to=400, width=5, textvariable=self.vars["x"],
                                 command=lambda: self.typed("x"))
        self.x_box.pack(side="left")
        ttk.Label(places, text="  y").pack(side="left")
        self.y_box = ttk.Spinbox(places, from_=-300, to=300, width=5, textvariable=self.vars["y"],
                                 command=lambda: self.typed("y"))
        self.y_box.pack(side="left", padx=(4, 0))
        self.place_row = line("Moved by  x", places)
        sizes = ttk.Frame(form)
        self.scale_slider = ttk.Scale(sizes, from_=SCALE_MIN, to=SCALE_MAX, length=px(self, 150),
                                      command=self.slid)
        self.scale_slider.pack(side="left")
        self.scale_box = ttk.Spinbox(sizes, from_=SCALE_MIN, to=SCALE_MAX, increment=5, width=4,
                                     textvariable=self.vars["scale"], command=lambda: self.typed("scale"))
        self.scale_box.pack(side="left", padx=(6, 0))
        ttk.Label(sizes, text="%").pack(side="left")
        self.size_row = line("Size", sizes)
        self.tint = line("Colour", ColourButton(form, lambda v: self.set_colour("tint", v)))
        self.digits = line("Digits", ColourButton(form, lambda v: self.set_colour("digits", v)))
        self.digits_label = form.grid_slaves(row=row - 1, column=0)[0]
        self.label_entry = line("Words", ttk.Entry(form, textvariable=self.vars["label"], width=16))
        self.label_caption = form.grid_slaves(row=row - 1, column=0)[0]
        for key in ("x", "y", "scale", "label", "width", "height"):
            entry = {"x": self.x_box, "y": self.y_box, "scale": self.scale_box, "label": self.label_entry}.get(key)
            if entry is not None:
                entry.bind("<Return>", lambda e, k=key: self.typed(k))
                entry.bind("<FocusOut>", lambda e, k=key: self.typed(k))
        pictures = ttk.Frame(form)
        ttk.Button(pictures, text="Choose PNG...", command=self.choose_image).pack(side="left")
        self.remove_image = ttk.Button(pictures, text="Game's", command=self.clear_image)
        self.remove_image.pack(side="left", padx=(4, 0))
        line("Picture", pictures)
        self.image_name = ttk.Label(form, style="Hint.TLabel")
        self.image_name.grid(row=row, column=1, sticky="w")
        row += 1
        self.hidden = tk.BooleanVar()
        hide = ttk.Checkbutton(form, text="Hidden", variable=self.hidden, command=self.set_hidden)
        hide.grid(row=row, column=1, sticky="w", pady=(6, 0))
        row += 1
        buttons = ttk.Frame(side)
        buttons.pack(anchor="w", pady=(12, 0))
        ttk.Button(buttons, text="Back to the game's", command=self.reset).pack(side="left")
        ttk.Button(buttons, text="Reset every picture", command=self.reset_all).pack(side="left", padx=(6, 0))
        self.status = ttk.Label(side, style="Hint.TLabel", wraplength=px(self, 330), justify="left")
        self.status.pack(anchor="w", pady=(10, 0))

    # --- the mod -------------------------------------------------------------------

    @property
    def project(self):
        return self.tab.project

    def element(self, name: str) -> dict:
        value = section(self.project, "ui").get("duel", {})
        value = value.get(name) if isinstance(value, dict) else None
        return value if isinstance(value, dict) else {}

    def edit(self, name: str) -> dict:
        return ensure(self.project, "ui", "duel", name)

    def done(self):
        self.tab.changed("ui")
        self.draw()
        self.fill_form()

    # --- the picture -------------------------------------------------------------------

    def fill(self):
        self.draw()
        self.fill_form()

    def sketch(self, stage: Stage):
        """The field and the hand, roughly: the 3D field is the game's."""
        z = stage.zoom
        stage.create_rectangle(0, 0, 320 * z, 240 * z, fill="#05060a", outline="")
        rows = [(70, 104), (104, 146), (146, 174)]
        top_w, bottom_w = 200, 320
        for i, (y0, y1) in enumerate(rows):
            def width(y):
                return top_w + (bottom_w - top_w) * (y - 60) / 120
            w0, w1 = width(y0), width(y1)
            shade = ("#7a5a18", "#a07a24", "#c89a34")[i]
            stage.create_polygon((160 - w0 / 2) * z, y0 * z, (160 + w0 / 2) * z, y0 * z, (160 + w1 / 2) * z,
                                 y1 * z, (160 - w1 / 2) * z, y1 * z, fill=shade, outline="#3c2a08")
            for c in range(1, 5):
                stage.create_line((160 - w0 / 2 + w0 * c / 5) * z, y0 * z, (160 - w1 / 2 + w1 * c / 5) * z, y1 * z,
                                  fill="#3c2a08")

    def hand(self, stage: Stage):
        wa = getattr(getattr(self.tab.app, "files", None), "wa", None)
        z = stage.zoom
        for i, (x, y) in enumerate(ua.HAND_AT):
            stage.create_rectangle(x * z, y * z, (x + 40) * z, (y + 56) * z, fill="#b08a2c", outline="#3c2a08")
            if wa:
                picture = self.tab.assets.get(("thumb", HAND[i]))
                if picture is None:
                    try:
                        picture = art.disc_image(wa, HAND[i], "thumbnail")
                    except Exception:
                        picture = False
                    self.tab.assets[("thumb", HAND[i])] = picture
                if picture:
                    stage.picture(("hand", i), sized(picture, 36, 29), x + 2, y + 2, drag=False)

    def mark_chips(self):
        """A dot on each picture the mod changes."""
        for name, chip in self.chips.items():
            chip.configure(text=NAMES[name] + (" \u2022" if self.element(name) else ""))

    def draw(self):
        stage = self.stage
        stage.clear()
        if self.project is not None:
            self.mark_chips()
        duel = self.tab.duel_art()
        self.sketch(stage)
        if not duel.ok:
            stage.create_text(160 * stage.zoom, 120 * stage.zoom, fill="#ccc",
                              text="The duel's pictures come from the game files (File > Game files...).")
            return
        turn = self.opponent_turn.get()
        pieces = {"card_bar": duel.card_bar(), "field": duel.field(), "hand_cursor": duel.hand_cursor(),
                  "field_cursor": duel.field_cursor(), "lp_opponent": duel.panel_half(0, turn),
                  "lp_player": duel.panel_half(1, turn)}
        for name in ("card_bar", "field_cursor", "field", "lp_opponent", "lp_player"):
            self.draw_element(stage, name, pieces[name], duel, turn)
        self.hand(stage)
        self.draw_element(stage, "hand_cursor", pieces["hand_cursor"], duel, turn)
        stage.outline(self.chosen)

    def draw_element(self, stage, name, piece, duel, turn):
        rect = ua.DUEL_RECTS[name]
        element = self.element(name)
        at = place(rect, element)
        x0, y0 = at(rect[0], rect[1])
        x1, y1 = at(rect[0] + rect[2], rect[1] + rect[3])
        w, h = max(1, x1 - x0), max(1, y1 - y0)
        if element.get("hide") is True:
            stage.rectangle(name, x0, y0, w, h, outline="#9a9a9a", width=1, drag=True, dash=(3, 3))
            return
        tint = ua.parse_colour(element.get("tint"))
        picture = mod_image(self.project, element.get("image")) if element.get("image") else None
        if picture is not None:
            iw, ih = as_int(element.get("width")), as_int(element.get("height"))
            if iw or ih:
                iw = iw or rect[2] * ih // rect[3]
                ih = ih or rect[3] * iw // rect[2]
                mx, my = rect[0] + rect[2] // 2, rect[1] + rect[3] // 2
                x0, y0 = at(mx - iw // 2, my - ih // 2)
                x1, y1 = at(mx - iw // 2 + iw, my - ih // 2 + ih)
                w, h = max(1, x1 - x0), max(1, y1 - y0)
            image = ua.tint(sized(picture, w, h), tint)
            stage.picture(name, image, x0, y0)
        else:
            image = piece if (w, h) == (piece.width, piece.height) else pngio.scale_to(piece, w, h)
            stage.picture(name, ua.tint(image, tint), x0, y0)
        if name in LABELLED:
            self.draw_digits(stage, name, element, at, duel, turn)
            label = element.get("label")
            if isinstance(label, str) and label and picture is None:
                self.draw_label(stage, name, label, rect, at, tint)

    def draw_digits(self, stage, name, element, at, duel, turn):
        tint = ua.parse_colour(element.get("digits"))
        # The side whose turn it is lit, the other dimmed (0x80 and 0x40, Duel_DrawLifePointsAndDeckCounts).
        lit = (name == "lp_opponent") == turn
        values = {"lp_opponent": ("8000", "40"), "lp_player": ("8000", "35")}[name]
        for (x, y, count), text in zip(ua.LP_DIGITS[name], values):
            text = text.rjust(count)
            for i, ch in enumerate(text):
                if ch == " ":
                    continue
                gx0, gy0 = at(x + 8 * i, y)
                gx1, gy1 = at(x + 8 * i + 8, y + 8)
                digit = duel.digit(int(ch))
                if (gx1 - gx0, gy1 - gy0) != (8, 8):
                    digit = pngio.scale_to(digit, max(1, gx1 - gx0), max(1, gy1 - gy0))
                stage.picture((name, "digit"), ua.tint(digit, tint, 255 if lit else 128), gx0, gy0, drag=False)

    def draw_label(self, stage, name, label, rect, at, tint):
        """The words in the COM or YOU box, coloured as the panel is (the
        game draws them through its palette and colour)."""
        top = rect[1] + LABEL_TOP[name]

        def tinted(colour):
            value = int(colour[1:], 16)
            parts = [(value >> s & 255) * (tint >> s & 255) // 255 for s in (16, 8, 0)]
            return "#%02x%02x%02x" % tuple(parts)
        fill, ink = (tinted(c) for c in LABEL_COLOUR[name])
        z = stage.zoom
        x1, y0 = at(rect[0] + LABEL_JOIN, top)
        _, y1 = at(rect[0] + LABEL_JOIN, top + 10)
        size = max(4, (y1 - y0) - 2)
        text = stage.create_text(0, 0, text=label, font=("Times", -max(6, size * z), "bold"), anchor="e")
        bx0, _, bx1, _ = stage.bbox(text)
        stage.delete(text)
        width = (bx1 - bx0) / z + 4
        stage.create_rectangle((x1 - width) * z, y0 * z, x1 * z, y1 * z, fill=fill, outline=tinted("#ffffff"))
        stage.create_text((x1 - 2) * z, (y0 + y1) / 2 * z, text=label, fill=ink,
                          font=("Times", -max(6, size * z), "bold"), anchor="e")

    # --- choosing and moving ------------------------------------------------------------

    def select(self, key):
        if isinstance(key, tuple) or key is None:
            return
        self.chosen = key
        self.chip.set(key)
        self.stage.outline(key)
        self.fill_form()

    def moved(self, key, dx, dy):
        if key not in PLACED:
            self.status.configure(text=f"The {NAMES.get(key, key).lower()} stays where the game has it: its words "
                                       "and cards follow it. Its colours and picture are yours.")
            self.draw()
            return
        element = self.edit(key)
        set_member(element, "x", max(-400, min(400, as_int(element.get("x")) + dx)), 0)
        set_member(element, "y", max(-300, min(300, as_int(element.get("y")) + dy)), 0)
        self.select(key)
        self.done()

    def wheel(self, key, step):
        if key not in PLACED:
            return
        self.select(key)
        element = self.edit(key)
        scale = as_int(element.get("scale"), 100) + 10 * step
        set_member(element, "scale", max(SCALE_MIN, min(SCALE_MAX, scale)), 100)
        self.done()

    # --- the form ------------------------------------------------------------------

    def fill_form(self):
        if self.project is None:
            return
        self.loading = True
        name = self.chosen
        element = self.element(name)
        self.title.configure(text=NAMES[name])
        self.what.configure(text={
            "lp_opponent": "The panel's top half: the opponent's LP, COM and their deck count.",
            "lp_player": "The panel's bottom half: YOU, your LP and your deck count.",
            "field": "The terrain's name, top left.",
            "card_bar": "The strip under the hand. It stays put: its words, the cards and the stars move with it.",
            "hand_cursor": "The arrow under the card you are on.",
            "field_cursor": "The frame on the zone you are choosing."}[name])
        self.vars["x"].set(str(as_int(element.get("x"))))
        self.vars["y"].set(str(as_int(element.get("y"))))
        scale = as_int(element.get("scale"), 100)
        self.vars["scale"].set(str(scale))
        self.scale_slider.set(scale)
        self.tint.set(ua.parse_colour(element.get("tint")))
        self.digits.set(ua.parse_colour(element.get("digits")))
        label = element.get("label")
        self.vars["label"].set(label if isinstance(label, str) else "")
        image = element.get("image")
        self.image_name.configure(text=image if isinstance(image, str) and image else "the game's own")
        self.remove_image.state(["!disabled"] if image else ["disabled"])
        self.hidden.set(element.get("hide") is True)
        placed = name in PLACED
        for widget in (self.x_box, self.y_box, self.scale_box):
            widget.state(["!disabled"] if placed else ["disabled"])
        self.scale_slider.state(["!disabled"] if placed else ["disabled"])
        labelled = name in LABELLED
        for widget in (self.digits, self.digits_label, self.label_entry, self.label_caption):
            if labelled:
                widget.grid()
            else:
                widget.grid_remove()
        self.status.configure(text="")
        self.loading = False

    def typed(self, key):
        if self.loading or self.project is None:
            return
        name = self.chosen
        text = self.vars[key].get().strip()
        element = self.edit(name)
        if key == "label":
            if len(text) > 15:
                self.status.configure(text="At most 15 letters.")
                text = text[:15]
            set_member(element, "label", text or None)
        else:
            try:
                value = int(text or 0)
            except ValueError:
                self.status.configure(text="A whole number.")
                return
            low, high, default = {"x": (-400, 400, 0), "y": (-300, 300, 0), "scale": (SCALE_MIN, SCALE_MAX, 100)}[key]
            set_member(element, key, max(low, min(high, value)), default)
        self.done()

    def slid(self, value):
        if self.loading or self.project is None or self.chosen not in PLACED:
            return
        scale = int(round(float(value) / 5) * 5)
        if scale == as_int(self.element(self.chosen).get("scale"), 100):
            return
        set_member(self.edit(self.chosen), "scale", scale, 100)
        self.vars["scale"].set(str(scale))
        self.tab.changed("ui")
        self.draw()

    def set_colour(self, key, value):
        if self.loading or self.project is None:
            return
        set_member(self.edit(self.chosen), key, colour_text(value) if value is not None else None, "#FFFFFF")
        self.done()

    def choose_image(self):
        if self.project is None:
            return
        name = import_image(self, self.project, f"duel-{self.chosen.replace('_', '-')}")
        if name:
            self.edit(self.chosen)["image"] = name
            self.done()

    def clear_image(self):
        element = self.edit(self.chosen)
        for key in ("image", "width", "height"):
            element.pop(key, None)
        self.done()

    def set_hidden(self):
        if self.loading:
            return
        set_member(self.edit(self.chosen), "hide", True if self.hidden.get() else None)
        self.done()

    def reset(self):
        duel = ensure(self.project, "ui", "duel")
        duel.pop(self.chosen, None)
        self.done()

    def reset_all(self):
        ui = section(self.project, "ui")
        if isinstance(ui.get("duel"), dict):
            ui.pop("duel")
        self.done()
