"""The Cards tab's card text box, drawn as the card view's text panel: its
dark blue, white letters, an icon code ({f8 0B NN}) shown as the icon off
the disc, two letters wide as the game sets it, and a colour code
({f8 0A NN}) as a thin bar of its colour, the letters after it in that
colour (notes/more-cards.md, "Card text codes").

What it holds is still the text with its codes: get() gives them back for
the pictures, insert() and a paste turn the codes in what they insert into
pictures, and a code typed in full becomes one. Copy and cut put the codes
on the clipboard. Without the game files (no icons to show) the codes stay
as written."""
from __future__ import annotations

import base64
import re
import tkinter as tk
from tkinter import font as tkfont

from . import card_text, pngio

PANEL = "#%02x%02x%02x" % card_text.PANEL
INK = "#f8f8f8"
SELECT = "#4060a0"
# The codes the box shows as pictures (card_text.CODE, less {g X}), for
# Python and for Tk's own search.
PICTURED = re.compile(r"\{f8 *(0[AaBb]) *([0-9A-Fa-f]{1,2})\}")
PICTURED_TCL = r"\{f8 *0[AaBb] *[0-9A-Fa-f]{1,2}\}"


class CardTextBox(tk.Text):
    keeps_colours = True    # the theme (theme.py) leaves the card view's colours, in either look
    def __init__(self, master, app, **options):
        super().__init__(master, background=PANEL, foreground=INK, insertbackground=INK, selectbackground=SELECT,
                         selectforeground=INK, inactiveselectbackground=SELECT, **options)
        self.app = app
        self.codes = {}         # embedded image name -> its code
        self._source = None     # the game files the pictures are of
        self._icons, self._bars, self._inks = {}, {}, {}
        for event, handler in (("<<Copy>>", self._copy), ("<<Cut>>", self._cut), ("<<Paste>>", self._paste)):
            self.bind(event, handler)
        self.bind("<KeyRelease>", lambda e: self.picture_codes(), add=True)

    # --- the pictures -----------------------------------------------------------

    def _pictures(self) -> bool:
        """Made for the game files the window has now; False without them."""
        files = getattr(self.app, "files", None)
        source = getattr(files, "source", None) if files is not None else None
        if files is None or getattr(files, "wa", None) is None:
            return False
        if source == self._source and self._inks:
            return True
        try:
            font = card_text.RetailFont(files.wa)
        except (ValueError, TypeError):
            return False
        self._source, self._icons, self._bars, self._inks = source, {}, {}, {}
        measure = tkfont.Font(font=self.cget("font"))
        letter, line = measure.measure("0"), measure.metrics("linespace")
        # An icon is two letters wide in the game: as near that here as whole
        # zooms come (16 texels a side, the font's letters about 8 across).
        zoom = max(1, round(2 * letter / 16))
        for n in range(len(card_text.ICON_NAMES)):
            icon = font.icon(n)
            if icon is not None:
                image = pngio.scale_nearest(pngio.Image(*icon), zoom)
                self._icons[n] = tk.PhotoImage(master=self, data=base64.b64encode(pngio.encode(image)),
                                               format="png")
        for n, ramp in enumerate(font.ramps[:len(card_text.COLOUR_NAMES)]):
            rgb = ramp[15]
            self._inks[n] = "#%02x%02x%02x" % rgb
            self.tag_configure(f"colour{n}", foreground=self._inks[n])
            bar = pngio.Image(3, line, bytes((*rgb, 255)) * (3 * line))
            self._bars[n] = tk.PhotoImage(master=self, data=base64.b64encode(pngio.encode(bar)), format="png")
        return True

    def _picture(self, code: str):
        match = PICTURED.fullmatch(code)
        if not match:
            return None
        n = int(match.group(2), 16)
        return (self._icons if match.group(1).upper() == "0B" else self._bars).get(n)

    # --- what it holds ----------------------------------------------------------

    def get(self, index1, index2=None):
        """The text with its codes: a picture gives back the code it shows."""
        if index2 is None:
            index2 = f"{index1}+1c"
        out = []
        for key, value, _ in self.dump(index1, index2, text=True, image=True):
            out.append(value if key == "text" else self.codes.get(value, ""))
        return "".join(out)

    def insert(self, index, chars, *args):
        """As Text.insert, the codes in chars shown as their pictures."""
        if not chars or not self._pictures():
            super().insert(index, chars, *args)
            self.recolour()
            return
        self.mark_set("card_text_at", index)
        self.mark_gravity("card_text_at", "right")
        at = 0
        for match in PICTURED.finditer(chars):
            image = self._picture(match.group(0))
            if image is None:
                continue
            if match.start() > at:
                super().insert("card_text_at", chars[at:match.start()], *args)
            name = self.image_create("card_text_at", image=image)
            self.codes[name] = "{f8 %s %s}" % (match.group(1).upper(), match.group(2).upper().zfill(2))
            at = match.end()
        if at < len(chars):
            super().insert("card_text_at", chars[at:], *args)
        self.mark_unset("card_text_at")
        self.recolour()

    def delete(self, index1, index2=None):
        super().delete(index1, index2)
        self.recolour()

    def picture_codes(self):
        """A code typed or pasted in full becomes its picture, the cursor
        staying after it."""
        if not self._pictures():
            return
        count = tk.IntVar()
        start = "1.0"
        while True:
            found = self.search(PICTURED_TCL, start, "end", regexp=True, count=count)
            if not found:
                break
            end = f"{found}+{count.get()}c"
            code = super().get(found, end)
            if self._picture(code) is None:
                start = end
                continue
            super().delete(found, end)
            self.insert(found, code)      # the cursor, after the code, stays after its picture
            start = f"{found}+1c"
        self.recolour()

    def recolour(self):
        """The letters after a colour code in its colour, as the game draws
        them; white again after {f8 0A 00}."""
        for n in self._inks:
            self.tag_remove(f"colour{n}", "1.0", "end")
        if not self._inks:
            return
        colour = 0
        for key, value, index in self.dump("1.0", "end-1c", text=True, image=True):
            if key == "image":
                match = PICTURED.fullmatch(self.codes.get(value, ""))
                if match and match.group(1).upper() == "0A":
                    colour = int(match.group(2), 16)
            elif colour in self._inks and colour:
                self.tag_add(f"colour{colour}", index, f"{index}+{len(value)}c")

    # --- the clipboard: the codes, not the pictures --------------------------------

    def _copy(self, event=None):
        if self.tag_ranges("sel"):
            self.clipboard_clear()
            self.clipboard_append(self.get("sel.first", "sel.last"))
        return "break"

    def _cut(self, event=None):
        if self.tag_ranges("sel") and str(self.cget("state")) == "normal":
            self._copy()
            self.delete("sel.first", "sel.last")
            self.event_generate("<KeyRelease>")
        return "break"

    def _paste(self, event=None):
        if str(self.cget("state")) != "normal":
            return "break"
        try:
            chars = self.clipboard_get()
        except tk.TclError:
            return "break"
        if self.tag_ranges("sel"):
            self.delete("sel.first", "sel.last")
        self.insert("insert", chars)
        self.see("insert")
        self.event_generate("<KeyRelease>")
        return "break"
