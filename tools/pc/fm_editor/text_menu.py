"""The card text box's right-click menu: cut, copy and paste, an icon
("{f8 0B NN}") or a colour ("{f8 0A NN}") inserted where the cursor is,
each shown as the game draws it (notes/more-cards.md, "Card text codes"),
so the codes need not be looked up."""
from __future__ import annotations

import base64
import sys
import tkinter as tk

from . import card_links, card_text, pngio

ICON_GROUPS = (("Monster types", range(0x00, 0x14)), ("Card kinds", range(0x14, 0x18)),
               ("Guardian stars", range(0x18, 0x22)), ("Buttons", range(0x22, 0x29)))
ZOOM = 2


class Pictures:
    """The icons and colour swatches of one set of game files, made once."""

    def __init__(self, master, wa):
        self.icons, self.swatches = {}, {}
        try:
            font = card_text.RetailFont(wa)
        except (ValueError, TypeError):
            return
        for n in range(len(card_text.ICON_NAMES)):
            icon = font.icon(n)
            if icon is not None:
                image = pngio.scale_nearest(pngio.Image(*icon), ZOOM)
                self.icons[n] = tk.PhotoImage(master=master, data=base64.b64encode(pngio.encode(image)), format="png")
        for n in range(len(card_text.COLOUR_NAMES)):
            rgb = font.ramps[n][15]
            image = pngio.Image(16 * ZOOM, 12 * ZOOM, bytes((*rgb, 255)) * (16 * 12 * ZOOM * ZOOM))
            self.swatches[n] = tk.PhotoImage(master=master, data=base64.b64encode(pngio.encode(image)), format="png")


_pictures = {}      # game files' source -> Pictures


def pictures(app, widget):
    files = getattr(app, "files", None)
    if files is None or getattr(files, "wa", None) is None:
        return None
    key = getattr(files, "source", id(files))
    if key not in _pictures:
        _pictures[key] = Pictures(widget, files.wa)
    return _pictures[key]


def insert_code(text: tk.Text, code: str):
    """At the cursor, in place of a selection."""
    if text.tag_ranges("sel"):
        text.delete("sel.first", "sel.last")
    text.insert("insert", code)


def colour(text: tk.Text, n: int):
    """A selection is coloured and the text after it goes back to white;
    without one, the colour starts at the cursor."""
    if text.tag_ranges("sel") and n:
        first, last = text.index("sel.first"), text.index("sel.last")
        text.insert(last, card_text.colour_code(0))
        text.insert(first, card_text.colour_code(n))
        text.tag_remove("sel", "1.0", "end")
    else:
        insert_code(text, card_text.colour_code(n))


def fill(menu: tk.Menu, app, text: tk.Text, after):
    def run(action):
        def command():
            action()
            text.focus_set()
            after()
        return command

    editable = str(text.cget("state")) == "normal"
    state = "normal" if editable else "disabled"
    has_selection = bool(text.tag_ranges("sel"))
    menu.add_command(label="Cut", state=state if has_selection else "disabled",
                     command=run(lambda: text.event_generate("<<Cut>>")))
    menu.add_command(label="Copy", state="normal" if has_selection else "disabled",
                     command=lambda: text.event_generate("<<Copy>>"))
    menu.add_command(label="Paste", state=state, command=run(lambda: text.event_generate("<<Paste>>")))
    menu.add_separator()
    shown = pictures(app, text)
    icons = tk.Menu(menu, tearoff=False)
    for title, codes in ICON_GROUPS:
        group = tk.Menu(icons, tearoff=False)
        for n in codes:
            image = shown.icons.get(n) if shown else None
            label = f"{card_text.ICON_NAMES[n]}   {card_text.icon_code(n)}"
            group.add_command(label=label, image=image or "", compound="left" if image else "none",
                              command=run(lambda n=n: insert_code(text, card_text.icon_code(n))))
        icons.add_cascade(label=title, menu=group)
    menu.add_cascade(label="Insert icon", menu=icons, state=state)
    colours = tk.Menu(menu, tearoff=False)
    for n, name in enumerate(card_text.COLOUR_NAMES):
        image = shown.swatches.get(n) if shown else None
        label = f"{name}{' (back to normal)' if n == 0 else ''}   {card_text.colour_code(n)}"
        colours.add_command(label=label, image=image or "", compound="left" if image else "none",
                            command=run(lambda n=n: colour(text, n)))
    menu.add_cascade(label="Text colour" + (" (of the selection)" if has_selection else ""), menu=colours,
                     state=state)


def install(app, text: tk.Text, after=lambda: None):
    """Give the text box the menu; `after` runs once the text is changed
    (the tab's line count and marks)."""
    def popup(event):
        card_links.close_menu()
        # The cursor goes where the click is, as a text editor's does,
        # unless the click is inside the selection (which then stays).
        at = text.index(f"@{event.x},{event.y}")
        inside = text.tag_ranges("sel") and text.compare("sel.first", "<=", at) and text.compare(at, "<", "sel.last")
        if not inside:
            text.tag_remove("sel", "1.0", "end")
            text.mark_set("insert", at)
        menu = tk.Menu(text, tearoff=False)
        card_links._open_menu = menu
        fill(menu, app, text, after)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return "break"

    text.bind("<Button-3>", popup)
    if sys.platform == "darwin":
        text.bind("<Button-2>", popup)
