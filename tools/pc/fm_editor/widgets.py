"""Small Tkinter pieces the editor's tabs share: a card field with a picker,
a scrolled tree, and dialogs."""
from __future__ import annotations

import sys
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

from . import theme
from .gamedata import TYPE_NAMES
from .model import card_matches  # noqa: F401 (model.py's; tabs.py and art_tab.py import it from here)


def ui_scale(widget) -> float:
    """How much bigger than at 96 dpi the default font is drawn: a desktop
    set to 144 dpi (Xft.dpi) enlarges the text but not Tk's pixel sizes, so
    widths, wrap lengths and row heights given in pixels grow by this.
    On Windows the program is dpi aware (theme.dpi_awareness): Tk's scaling
    (pixels a point) is the dpi's, 4/3 at 100%, and the fonts in points
    follow it, so the pixel sizes do too."""
    if sys.platform == "win32":
        return max(1.0, float(widget.tk.call("tk", "scaling")) * 72 / 96)
    return max(1.0, tkfont.nametofont("TkDefaultFont", root=widget).metrics("linespace") / 19)


def px(widget, pixels: int) -> int:
    """`pixels` at 96 dpi, at the desktop's size (ui_scale)."""
    return round(pixels * ui_scale(widget))


def ui_font(size: int, weight: str = "bold"):
    """The default font's face at another size (a heading): ("TkDefaultFont",
    size, weight) names no face, which X11 matches to its default sans but
    Windows to Arial, so there the face is TkDefaultFont's own."""
    if sys.platform == "win32":
        return (tkfont.nametofont("TkDefaultFont").actual("family"), size, weight)
    return ("TkDefaultFont", size, weight)


def scrolled_tree(parent, columns, widths, height=20, selectmode="browse"):
    """A Treeview with a vertical scrollbar, in a frame of its own."""
    frame = ttk.Frame(parent)
    tree = ttk.Treeview(frame, columns=[c for c, _ in columns], show="headings", height=height, selectmode=selectmode)
    # The widths as made: a theme change (theme.py) asks the tree's size
    # again from its columns, which stretching has widened by then.
    tree.widths = {key: px(frame, width) for (key, _), width in zip(columns, widths)}
    for (key, label), width in zip(columns, widths):
        tree.heading(key, text=label)
        tree.column(key, width=tree.widths[key], stretch=width > 120, anchor="w")
    bar = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=bar.set)
    tree.grid(row=0, column=0, sticky="nsew")
    bar.grid(row=0, column=1, sticky="ns")
    frame.rowconfigure(0, weight=1)
    frame.columnconfigure(0, weight=1)
    for tag in theme.TAGS:
        tree.tag_configure(tag, foreground=theme.tag_color(tree, tag))
    return frame, tree


class CardPicker(tk.Toplevel):
    """A dialog to choose a card by searching its name or number."""

    def __init__(self, master, project, title="Choose a card", only=None, initial=""):
        super().__init__(master)
        self.title(title)
        self.transient(master)
        self.resizable(True, True)
        self.project = project
        self.only = only
        self.result = None
        self.search = tk.StringVar(value=initial)
        entry = ttk.Entry(self, textvariable=self.search, width=40)
        entry.pack(fill="x", padx=8, pady=(8, 4))
        frame, self.tree = scrolled_tree(self, [("id", "#"), ("name", "Name"), ("type", "Type")], [50, 240, 110], 16)
        frame.pack(fill="both", expand=True, padx=8)
        buttons = ttk.Frame(self)
        buttons.pack(fill="x", padx=8, pady=8)
        ttk.Button(buttons, text="OK", command=self.ok).pack(side="right")
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="right", padx=4)
        self.search.trace_add("write", lambda *_: self.fill())
        self.tree.bind("<Double-1>", lambda e: self.ok())
        entry.bind("<Return>", lambda e: self.ok())
        entry.bind("<Down>", lambda e: (self.tree.focus_set(), self._select_first()))
        self.bind("<Escape>", lambda e: self.destroy())
        self.fill()
        entry.focus_set()
        grab(self)

    def _select_first(self):
        children = self.tree.get_children()
        if children:
            self.tree.selection_set(children[0])
            self.tree.focus(children[0])

    def fill(self):
        self.tree.delete(*self.tree.get_children())
        text = self.search.get()
        shown = 0
        for cid in sorted(self.project.cards):
            if self.only and not self.only(cid):
                continue
            if not card_matches(self.project, cid, text):
                continue
            card = self.project.cards[cid]
            kind = TYPE_NAMES[card.type] if 0 <= card.type < len(TYPE_NAMES) else str(card.type)
            self.tree.insert("", "end", iid=str(cid), values=(cid, card.name, kind))
            shown += 1
            if shown >= 800:
                break
        self._select_first()

    def ok(self):
        selection = self.tree.selection()
        if selection:
            self.result = int(selection[0])
            self.destroy()


def pick_card(master, project, title="Choose a card", only=None, initial=""):
    dialog = CardPicker(master, project, title, only, initial)
    master.wait_window(dialog)
    # The picker took the grab: a dialog it was opened from gets it back.
    top = master.winfo_toplevel()
    if isinstance(top, tk.Toplevel) and top.winfo_exists():
        grab(top)
    return dialog.result


def grab(window):
    """window.grab_set(), once the window is on screen: a dialog opened by a
    double-click is often not mapped yet, and Tk refuses the grab ("window
    not viewable")."""
    try:
        window.grab_set()
    except tk.TclError:
        window.after(20, lambda: window.winfo_exists() and grab(window))


def card_named(project, text: str) -> int:
    """The card a CardField's text names, or 0."""
    text = text.strip()
    if not text:
        return 0
    # A number, or a card as CardField.set() shows it ("7 Name"); otherwise a
    # name, which may start with a digit ("7 Colored Fish").
    if text.isdigit() and int(text) in project.cards:
        return int(text)
    head = text.split(" ", 1)[0]
    if head.isdigit() and int(head) in project.cards and project.card_label(int(head)) == text:
        return int(head)
    cid = project.resolve(text)
    if cid:
        return cid
    for other, card in project.cards.items():
        if card.name.lower() == text.lower():
            return other
    return 0


class CardField(ttk.Frame):
    """An entry naming a card (number or name) with a "..." picker."""

    def __init__(self, master, project_getter, width=28, only=None):
        super().__init__(master)
        self.project_getter = project_getter
        self.only = only
        self.var = tk.StringVar()
        self.entry = ttk.Entry(self, textvariable=self.var, width=width)
        self.entry.pack(side="left", fill="x", expand=True)
        ttk.Button(self, text="...", width=3, command=self.pick).pack(side="left", padx=(2, 0))

    def pick(self):
        project = self.project_getter()
        cid = pick_card(self.winfo_toplevel(), project, only=self.only, initial="")
        if cid:
            self.set(cid)

    def set(self, cid):
        project = self.project_getter()
        self.var.set(project.card_label(cid) if cid else "")

    def get(self) -> int:
        """The card named, or 0."""
        return card_named(self.project_getter(), self.var.get())


class FormDialog(tk.Toplevel):
    """A small modal form: rows of (label, widget factory); on OK the
    callback gets the dialog and returns an error text or None."""

    def __init__(self, master, title, build, on_ok):
        super().__init__(master)
        self.title(title)
        self.transient(master)
        self.resizable(False, False)
        self.on_ok = on_ok
        self.ok_pressed = False
        body = ttk.Frame(self, padding=10)
        body.pack(fill="both", expand=True)
        build(self, body)
        self.error = ttk.Label(self, style="Error.TLabel")
        self.error.pack(fill="x", padx=10)
        buttons = ttk.Frame(self, padding=(10, 0, 10, 10))
        buttons.pack(fill="x")
        ttk.Button(buttons, text="OK", command=self.ok).pack(side="right")
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="right", padx=4)
        self.bind("<Escape>", lambda e: self.destroy())
        grab(self)

    def ok(self):
        problem = self.on_ok(self)
        if problem:
            self.error.configure(text=problem)
            return
        self.ok_pressed = True
        self.destroy()


def show_text(master, title, text, width=100, height=36):
    window = tk.Toplevel(master)
    window.title(title)
    box = tk.Text(window, width=width, height=height, wrap="none", font=("Consolas", 10))
    bar = ttk.Scrollbar(window, orient="vertical", command=box.yview)
    box.configure(yscrollcommand=bar.set)
    box.insert("1.0", text)
    box.configure(state="disabled")
    box.pack(side="left", fill="both", expand=True)
    bar.pack(side="right", fill="y")
    return window
