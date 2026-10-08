"""The UI tab's Duel board page: the textures of the duel's 3D board (the
floor's rows of zones and the platform's walls), field by field, drawn from
the user's own disc (board_art.py has where each is and what the mod
writes). On the left a sketch of the board as the duel's camera sees it at
the start of a turn, flat-shaded (the game's own light and camera
differ); clicking a part there or in the list chooses it. Beside them the
chosen texture: replace it with a PNG, export the game's to paint over,
tint the game's, or put it back."""
from __future__ import annotations

import base64
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import board_art as ba, pngio
from .pngio import Image
from .ui_tab import ColourButton
from .widgets import px, ui_font

FLOOR_ITEM = "floor"            # the whole floor, one picture
GROUPS = (("Floor", ba.FLOOR), ("Walls and trim", ba.WALLS))
SKETCH_W, SKETCH_H = 320, 240   # the sketch's own units, the game's screen
# The floor in perspective: depth z from 2.2 (far) to 1 (near); a row at depth
# z is at y = Y0 + YK / z and half as wide as HW / z.
Z_FAR, Z_NEAR, Y0, YK, HW = 2.2, 1.0, -35.8, 210.8, 128.0
# The board seen from above, far to near: (part, turned round, depth in texels).
# The centre strip twice, the near half turned round, as the game draws it,
# and the face of the step up to it between.
BOARD_ROWS = [("opponent_back", False, 52), ("opponent_front", False, 52), ("centre_step", False, 10),
              ("centre", False, 46), ("centre", True, 46), ("your_front", False, 52), ("your_back", False, 52)]
# The near wall below the floor (y from, to) and its pieces left to right.
TRIM_Y, WALL_Y, WALL_BOTTOM = 175, 179, 214
WALL_X0, WALL_X1 = 18, 302
WALL_PIECES = [("wall_corners", False), ("wall_left", False), ("wall_middle", False), ("wall_right", False),
               ("wall_corners", True)]
SIDE = 12                        # the long sides' width at the near end, beside the floor


def depth(s: float) -> float:
    return Z_FAR + (Z_NEAR - Z_FAR) * s


def floor_point(u: float, s: float):
    """The sketch's point of the floor's (u in -1..1 across, s 0 far .. 1 near)."""
    z = depth(s)
    return 160 + u * HW / z, Y0 + YK / z


def turned(image: Image) -> Image:
    """The picture turned half round."""
    px_ = [image.rgba[i:i + 4] for i in range(0, len(image.rgba), 4)]
    return Image(image.width, image.height, b"".join(reversed(px_)))


def mirrored(image: Image) -> Image:
    rows = []
    for y in range(image.height):
        line = image.rgba[y * image.width * 4:(y + 1) * image.width * 4]
        rows.append(b"".join(line[x * 4:x * 4 + 4] for x in range(image.width - 1, -1, -1)))
    return Image(image.width, image.height, b"".join(rows))


def checker(w: int, h: int, cell: int = 6) -> Image:
    out = bytearray(w * h * 4)
    for y in range(h):
        for x in range(w):
            v = 0x6a if (x // cell + y // cell) & 1 else 0x50
            out[(y * w + x) * 4:(y * w + x) * 4 + 4] = bytes((v, v, v, 255))
    return Image(w, h, bytes(out))


def over(base: Image, piece: Image) -> Image:
    """`piece` (as large as `base`) over it, alpha-mixed."""
    out = bytearray(base.rgba)
    src = piece.rgba
    for i in range(0, len(src), 4):
        a = src[i + 3]
        if a == 255:
            out[i:i + 3] = src[i:i + 3]
        elif a:
            for c in range(3):
                out[i + c] = (src[i + c] * a + out[i + c] * (255 - a)) // 255
    return Image(base.width, base.height, bytes(out))


class Sketch:
    """The board drawn at a size: the picture and, for each part, the
    outline it takes (the sketch's units) to choose it by."""

    def __init__(self, width: int, height: int):
        self.width, self.height = width, height
        self.k = width / SKETCH_W
        self.out = bytearray(bytes((5, 6, 10, 255)) * (width * height))
        self.shapes = []            # (part key, [(x, y), ...]) last drawn on top

    def _put(self, x: int, y: int, rgba, light: float = 1.0):
        if rgba[3] < 128:
            return
        at = (y * self.width + x) * 4
        self.out[at:at + 4] = bytes((min(255, int(rgba[0] * light)), min(255, int(rgba[1] * light)),
                                     min(255, int(rgba[2] * light)), 255))

    def floor(self, rows: dict):
        """rows: part key -> its picture (any scale)."""
        pictures = [(key, turned(rows[key]) if flip else rows[key]) for key, flip, _ in BOARD_ROWS]
        heights = [h for _, _, h in BOARD_ROWS]
        total = sum(heights)
        starts, at = [], 0
        for h in heights:
            starts.append(at)
            at += h
        k = self.k
        top, bottom = int(floor_point(0, 0)[1] * k), int(floor_point(0, 1)[1] * k)
        for sy in range(max(0, top), min(self.height, bottom)):
            z = YK / ((sy + 0.5) / k - Y0)
            s = (Z_FAR - z) / (Z_FAR - Z_NEAR)
            if not 0 <= s < 1:
                continue
            v = s * total
            index = max(i for i, start in enumerate(starts) if start <= v)
            key, image = pictures[index]
            ty = min(image.height - 1, int((v - starts[index]) / heights[index] * image.height))
            half = HW / z * k
            light = 0.55 + 0.45 * s
            row = ty * image.width * 4
            for sx in range(max(0, int(160 * k - half)), min(self.width, int(160 * k + half) + 1)):
                u = (sx + 0.5 - 160 * k) / half
                if not -1 <= u < 1:
                    continue
                tx = min(image.width - 1, int((u + 1) / 2 * image.width))
                self._put(sx, sy, image.rgba[row + tx * 4:row + tx * 4 + 4], light)
        for (key, _, _), start, h in zip(BOARD_ROWS, starts, heights):
            s0, s1 = start / total, (start + h) / total
            self.shapes.append((key, [floor_point(-1, s0), floor_point(1, s0), floor_point(1, s1),
                                      floor_point(-1, s1)]))

    def rect(self, key: str, image: Image, x0: float, y0: float, x1: float, y1: float, tile: int = 1,
             light: float = 1.0):
        """`image` stretched over a rectangle (`tile` times across)."""
        k = self.k
        for sy in range(max(0, int(y0 * k)), min(self.height, int(y1 * k))):
            ty = max(0, min(image.height - 1, int((sy + 0.5 - y0 * k) / ((y1 - y0) * k) * image.height)))
            row = ty * image.width * 4
            for sx in range(max(0, int(x0 * k)), min(self.width, int(x1 * k))):
                f = max(0.0, (sx + 0.5 - x0 * k) / ((x1 - x0) * k)) * tile % 1
                tx = min(image.width - 1, int(f * image.width))
                self._put(sx, sy, image.rgba[row + tx * 4:row + tx * 4 + 4], light)
        self.shapes.append((key, [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]))

    def side(self, key: str, image: Image, left: bool):
        """A long side: a band beside the floor's edge, the wall's picture
        along it (its length across the picture, far to near)."""
        k = self.k
        sign = -1 if left else 1
        top, bottom = floor_point(0, 0)[1], floor_point(0, 1)[1]
        for sy in range(max(0, int(top * k)), min(self.height, int(bottom * k))):
            z = YK / ((sy + 0.5) / k - Y0)
            s = (Z_FAR - z) / (Z_FAR - Z_NEAR)
            if not 0 <= s < 1:
                continue
            edge = 160 + sign * HW / z
            width = SIDE * Z_NEAR / z
            tx = min(image.width - 1, int(s * image.width))
            for sx in range(int(min(edge, edge + sign * width) * k), int(max(edge, edge + sign * width) * k)):
                if 0 <= sx < self.width:
                    f = abs(sx / k - edge) / width
                    ty = min(image.height - 1, int(f * image.height))
                    self._put(sx, sy, image.rgba[(ty * image.width + tx) * 4:(ty * image.width + tx) * 4 + 4],
                              0.45 + 0.4 * s)
        x_far, y_far = floor_point(sign, 0)
        x_near, y_near = floor_point(sign, 1)
        self.shapes.append((key, [(x_far, y_far), (x_far + sign * SIDE * Z_NEAR / Z_FAR, y_far),
                                  (x_near + sign * SIDE, y_near), (x_near, y_near)]))

    def image(self) -> Image:
        return Image(self.width, self.height, bytes(self.out))

    def part_at(self, x: float, y: float):
        """The part whose outline holds the point (the sketch's units)."""
        for key, points in reversed(self.shapes):
            inside = False
            j = len(points) - 1
            for i, (xi, yi) in enumerate(points):
                xj, yj = points[j]
                if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
                    inside = not inside
                j = i
            if inside:
                return key
        return None


def draw_board(pieces: dict, width: int, height: int) -> Sketch:
    """The sketch of a field with `pieces` (part key -> picture)."""
    sketch = Sketch(width, height)
    sketch.side("wall_left", pieces["wall_left"], True)
    sketch.side("wall_right", pieces["wall_right"], False)
    sketch.floor(pieces)
    near_left, near_right = floor_point(-1, 1)[0], floor_point(1, 1)[0]
    sketch.rect("trim", pieces["trim"], near_left - SIDE, TRIM_Y, near_right + SIDE, WALL_Y, tile=2)
    total = sum(ba.BY_KEY[key].w for key, _ in WALL_PIECES)
    x = WALL_X0
    for key, flip in WALL_PIECES:
        w = (WALL_X1 - WALL_X0) * ba.BY_KEY[key].w / total
        image = mirrored(pieces[key]) if flip else pieces[key]
        sketch.rect(key, image, x, WALL_Y, x + w, WALL_BOTTOM, light=0.8)
        x += w
    return sketch


class BoardPage(ttk.Frame):
    def __init__(self, master, tab):
        super().__init__(master)
        self.tab = tab
        self.terrain = ba.TERRAINS[0]
        self.chosen = FLOOR_ITEM
        self.loading = False
        self.sketch = None
        self.offset = (0, 0)
        self.photos = []
        self._job = None
        self._drawn = None

        top = ttk.Frame(self)
        top.pack(fill="x", pady=(0, 6))
        ttk.Label(top, text="Field").pack(side="left", padx=(0, 6))
        self.field = tk.StringVar(value=self.terrain)
        self.field_buttons = {}
        for terrain in ba.TERRAINS:
            button = ttk.Radiobutton(top, text=ba.TERRAIN_LABELS[terrain], value=terrain, variable=self.field,
                                     style="Toolbutton", command=self.choose_field)
            button.pack(side="left", padx=(0, 2))
            self.field_buttons[terrain] = button
        # The tab's own Revert to retail (top right) puts the board back too.
        self.revert_page = ttk.Button(top, text="Revert page", command=self.revert_all)
        self.revert_page.pack(side="right")

        body = ttk.Frame(self)
        body.pack(fill="both", expand=True)
        # The sketch takes the room the list and the texture leave.
        left = ttk.Frame(body)
        middle = ttk.Frame(body, padding=(10, 0, 0, 0))
        side = ttk.Frame(body, padding=(12, 0, 0, 0), width=px(self, 330))
        side.pack(side="right", fill="y")
        side.pack_propagate(False)
        middle.pack(side="right", fill="y")
        left.pack(side="left", fill="both", expand=True)
        ttk.Label(left, text="A sketch: the game's camera and light differ.", style="Hint.TLabel").pack(
            side="bottom", anchor="w", pady=(4, 0))
        self.canvas = tk.Canvas(left, width=px(self, 480), height=px(self, 360), highlightthickness=0,
                                background="#05060a", cursor="hand2")
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Button-1>", self.clicked)

        self.tree = ttk.Treeview(middle, columns=("state",), show="tree", selectmode="browse",
                                 height=len(ba.PARTS) + 3)
        self.tree.column("#0", width=px(self, 180), stretch=False)
        self.tree.column("state", width=px(self, 64), stretch=False)
        self.tree.pack(fill="y", expand=True)
        for title, parts in GROUPS:
            group = self.tree.insert("", "end", iid=FLOOR_ITEM if parts is ba.FLOOR else "walls", text=title,
                                     open=True)
            for part in parts:
                self.tree.insert(group, "end", iid=part.key, text=part.label)
        self.tree.bind("<<TreeviewSelect>>", self.tree_selected)

        self.title = ttk.Label(side, font=("TkDefaultFont", 12, "bold"))
        self.title.pack(anchor="w")
        self.what = ttk.Label(side, style="Hint.TLabel", wraplength=px(self, 300), justify="left")
        self.what.pack(anchor="w", pady=(0, 6))
        self.preview = tk.Canvas(side, width=px(self, 300), height=px(self, 150), highlightthickness=0,
                                 background="#05060a")
        self.preview.pack(anchor="w")
        self.size = ttk.Label(side, style="Hint.TLabel", wraplength=px(self, 300), justify="left")
        self.size.pack(anchor="w", pady=(4, 6))
        buttons = ttk.Frame(side)
        buttons.pack(anchor="w")
        ttk.Button(buttons, text="Replace...", command=self.replace).pack(side="left")
        ttk.Button(buttons, text="Export game's...", command=self.export).pack(side="left", padx=(4, 0))
        self.revert_button = ttk.Button(buttons, text="Revert", command=self.revert)
        self.revert_button.pack(side="left", padx=(4, 0))
        tints = ttk.Frame(side)
        tints.pack(anchor="w", pady=(8, 0))
        ttk.Label(tints, text="Tint").pack(side="left", padx=(0, 8))
        self.tint = ColourButton(tints, self.set_tint)
        self.tint.pack(side="left")
        self.all_fields = tk.BooleanVar(value=False)
        ttk.Checkbutton(side, text="All seven fields", variable=self.all_fields).pack(anchor="w", pady=(8, 0))
        self.warnings = ttk.Label(side, style="Warning.TLabel", wraplength=px(self, 300), justify="left")
        self.warnings.pack(anchor="w", pady=(8, 0))
        self.status = ttk.Label(side, style="Hint.TLabel", wraplength=px(self, 300), justify="left")
        self.status.pack(anchor="w", pady=(6, 0))
        self.canvas.bind("<Configure>", lambda e: self.draw_later())

    # --- the mod ---------------------------------------------------------------------

    @property
    def project(self):
        return self.tab.project

    def parts(self) -> list:
        return ba.FLOOR if self.chosen == FLOOR_ITEM else [ba.BY_KEY[self.chosen]]

    def terrains(self) -> list:
        return list(ba.TERRAINS) if self.all_fields.get() else [self.terrain]

    def edited(self, notes=()):
        self.status.configure(text="\n".join(notes))
        self.tab.app.changed()
        self.fill()
        self.tab.mark_reverts()

    # --- drawing -------------------------------------------------------------------------

    def fill(self):
        if self.project is None:
            return
        self.mark()
        self.fill_form()
        self.draw()

    def mark(self):
        """A dot on each field and part the mod changes."""
        for terrain, button in self.field_buttons.items():
            button.configure(text=ba.TERRAIN_LABELS[terrain] + (" •" if ba.changed(self.project, terrain) else ""))
        st = ba.state(self.project)
        for part in ba.PARTS:
            key = (self.terrain, part.key)
            state = "replaced" if key in st.pictures else "tinted" if key in st.tints else ""
            self.tree.set(part.key, "state", state)
        if self.tree.selection() != (self.chosen,):
            self.loading = True
            self.tree.selection_set(self.chosen)
            self.tree.see(self.chosen)
            self.loading = False

    def draw_later(self):
        if self._job is not None:
            self.after_cancel(self._job)
        self._job = self.after(120, self.draw)

    def draw(self):
        self._job = None
        canvas = self.canvas
        if self.project is None:
            return
        data = ba.disc(self.project)
        width = max(160, canvas.winfo_width() if canvas.winfo_width() > 1 else int(canvas["width"]))
        height = max(120, canvas.winfo_height() if canvas.winfo_height() > 1 else int(canvas["height"]))
        k = min(width / SKETCH_W, height / SKETCH_H)
        size = (int(SKETCH_W * k), int(SKETCH_H * k))
        canvas.delete("all")
        self.photos = []
        if not data.ok:
            self.sketch = None
            canvas.create_text(width // 2, height // 2, fill="#ccc", width=width - 40,
                               text="The board's textures come from the game files (File > Game files...).")
            return
        # The tab's "Hold: the game's": the board without the mod's pictures and tints.
        comparing = getattr(self.tab, "comparing", False)
        held = self.project.board_art if comparing else None
        if comparing:
            self.project.board_art = ba.BoardArt()
        try:
            signature = (self.terrain, size, comparing, ba.state(self.project).version, ba.digest(self.project))
            if self._drawn is None or self._drawn[0] != signature:
                pieces = {part.key: ba.shown(self.project, self.terrain, part) for part in ba.PARTS}
                sketch = draw_board(pieces, *size)
                self._drawn = (signature, sketch, self.photo(sketch.image()))
        finally:
            if comparing:
                self.project.board_art = held
        _, self.sketch, photo = self._drawn
        self.photos.append(photo)
        self.offset = ((width - size[0]) // 2, (height - size[1]) // 2)
        canvas.create_image(*self.offset, image=photo, anchor="nw")
        if comparing:
            canvas.create_rectangle(0, 0, px(canvas, 96), px(canvas, 22), fill="#000", outline="#ffd34d")
            canvas.create_text(px(canvas, 48), px(canvas, 11), text="The game's", fill="#ffd34d", font=ui_font(10))
        else:
            self.outline()

    def outline(self):
        """The chosen parts' outlines, dashed, over the sketch."""
        self.canvas.delete("chosen")
        if self.sketch is None:
            return
        keys = {p.key for p in self.parts()}
        k = self.sketch.k
        ox, oy = self.offset
        for key, points in self.sketch.shapes:
            if key in keys:
                flat = [c for x, y in points for c in (ox + x * k, oy + y * k)]
                self.canvas.create_polygon(*flat, fill="", outline="#000", width=3, tags="chosen")
                self.canvas.create_polygon(*flat, fill="", outline="#ffd34d", width=1, dash=(4, 3), tags="chosen")

    def photo(self, image: Image):
        return tk.PhotoImage(master=self, data=base64.b64encode(pngio.encode(image)), format="png")

    def current_image(self):
        if self.chosen == FLOOR_ITEM:
            return ba.floor_image(self.project, self.terrain)
        return ba.shown(self.project, self.terrain, ba.BY_KEY[self.chosen])

    def fill_form(self):
        self.loading = True
        parts = self.parts()
        st = ba.state(self.project)
        keys = [(self.terrain, p.key) for p in parts]
        replaced = [k for k in keys if k in st.pictures]
        if self.chosen == FLOOR_ITEM:
            self.title.configure(text="Floor")
            self.what.configure(text="All five rows as one picture, far to near: the opponent's back row at the top, "
                                     "the centre strip once, your back row at the bottom.")
            w, h = ba.FLOOR_W, ba.FLOOR_H
            warnings = [ba.BY_KEY["centre"].warnings[0]]
        else:
            part = parts[0]
            self.title.configure(text=part.label)
            self.what.configure(text=part.what)
            w, h = part.w, part.h
            warnings = list(part.warnings)
        self.size.configure(text=f"{w}x{h} texels, or 2x {w * 2}x{h * 2}, 4x {w * 4}x{h * 4} for Internal 2x and 4x. "
                                 "Other sizes are stretched to fit; at 1x a picture is averaged down.")
        image = self.current_image()
        self.preview.delete("all")
        if image is not None:
            box_w, box_h = px(self, 300), px(self, 160)
            scale = min(box_w / image.width, box_h / image.height)
            shown = pngio.scale_to(image, max(1, int(image.width * scale)), max(1, int(image.height * scale)))
            shown = over(checker(*shown.size), shown)
            self.preview.configure(width=shown.width, height=shown.height)
            photo = self.photo(shown)
            self.preview_photo = photo
            self.preview.create_image(0, 0, image=photo, anchor="nw")
        tint = ba.common_tint(self.project, self.terrain, parts)
        self.tint.set(ba.WHITE if tint is None else tint)
        if replaced:
            self.tint.text.configure(text="off")
        if tint is None:
            warnings.append("The rows have different tints: a new one sets them all.")
        for widget in (self.tint.swatch,):
            widget.configure(cursor="arrow" if replaced else "hand2")
        self.tint.reset.state(["disabled"] if replaced or self.tint.value == ba.WHITE else ["!disabled"])
        if replaced:
            warnings.append("Replaced: the picture has its own colours, so the tint is off.")
        self.revert_button.state(["!disabled"] if replaced or any(k in st.tints for k in keys) else ["disabled"])
        self.warnings.configure(text="\n".join("⚠ " + w for w in warnings))
        self.loading = False

    # --- choosing ---------------------------------------------------------------------------

    def choose_field(self):
        self.terrain = self.field.get()
        self.status.configure(text="")
        self.fill()

    def select(self, key):
        if key is None or key == "walls":
            return
        self.chosen = key
        self.status.configure(text="")
        self.mark()
        self.fill_form()
        self.outline()

    def tree_selected(self, event=None):
        if self.loading:
            return
        chosen = self.tree.selection()
        if chosen:
            self.select(chosen[0])

    def clicked(self, event):
        if self.sketch is None:
            return
        ox, oy = self.offset
        key = self.sketch.part_at((event.x - ox) / self.sketch.k, (event.y - oy) / self.sketch.k)
        if key is not None:
            self.select(key)

    # --- edits --------------------------------------------------------------------------------

    def replace(self, path=None):
        if self.project is None:
            return
        path = path or filedialog.askopenfilename(parent=self, title="Choose a PNG",
                                                  filetypes=[("PNG pictures", "*.png"), ("All files", "*")])
        if not path:
            return
        try:
            image = pngio.read(path)
        except (OSError, pngio.PngError) as problem:
            messagebox.showerror("FM Editor", f"That PNG cannot be read: {problem}", parent=self)
            return
        if self.chosen == FLOOR_ITEM:
            notes = ba.set_floor(self.project, self.terrains(), image)
        else:
            notes = ba.set_piece(self.project, self.terrains(), ba.BY_KEY[self.chosen], image)
        self.edited(notes)

    def export(self, path=None):
        if self.project is None or not ba.disc(self.project).ok:
            return
        name = f"{self.terrain}-{self.chosen}.png"
        path = path or filedialog.asksaveasfilename(parent=self, title="Export the game's texture",
                                                    initialfile=name, defaultextension=".png",
                                                    filetypes=[("PNG pictures", "*.png")])
        if not path:
            return
        data = ba.disc(self.project)
        if self.chosen == FLOOR_ITEM:
            image = ba.floor_image(self.project, self.terrain, retail=True)
        else:
            image = ba.piece_image(data, self.terrain, ba.BY_KEY[self.chosen])
        pngio.write(path, image)
        self.status.configure(text=f"Wrote {path} ({image.width}x{image.height}).")

    def set_tint(self, value):
        if self.loading or self.project is None:
            return
        st = ba.state(self.project)
        if any((t, p.key) in st.pictures for t in self.terrains() for p in self.parts()):
            self.tint.set(ba.WHITE)
            self.status.configure(text="Revert the picture to tint the game's.")
            return
        ba.set_tint(self.project, self.terrains(), self.parts(), ba.WHITE if value is None else value)
        self.edited()

    def revert(self):
        if self.project is None:
            return
        ba.revert(self.project, self.terrains(), self.parts())
        self.edited()

    def revert_all(self):
        """Every field's board back as the game has it, asked first as the
        tab's other pages' Revert page is, and an undo step of its own."""
        if self.project is None or not ba.changed(self.project):
            return
        if not messagebox.askyesno("Revert page", "Put every field's duel board back as the game has it?\n\n"
                                   "Lost: the board's pictures and tints.\n\nEdit > Undo brings them back.",
                                   parent=self):
            return
        self.tab.app.flush_history()
        ba.revert_all(self.project)
        self.edited(["Every field's board is the game's again."])

    def reset_choice(self):
        """After the tab's Revert to retail: the board's floor, as it opens."""
        self.chosen = FLOOR_ITEM
