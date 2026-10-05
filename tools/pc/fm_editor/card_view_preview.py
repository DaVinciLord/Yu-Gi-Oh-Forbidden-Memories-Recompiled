"""Beside the Cards tab's card text: the card view's panel as the game draws
it (card_view.py), following the text, the type and the stars as they are
typed; its language (the port's translations: their layout, names and
European spacing) and size are the window's settings."""
from __future__ import annotations

import base64
import sys
import tkinter as tk
from pathlib import Path
from tkinter import ttk

from . import card_view, pngio, settings

SCALES = ("1x", "2x", "3x")


class CardViewPreview(ttk.Frame):
    def __init__(self, master, app, values):
        """values() gives (type, star 1, star 2, text, colours, the mod's star
        names) of the form, or None when there is no card."""
        super().__init__(master)
        self.app, self.values = app, values
        self._view, self._source, self._job, self._photo = None, None, None, None
        saved = settings.load()
        self.language = tk.StringVar(self, value=saved.get("card_view_language", "en-us"))
        self.scale = tk.StringVar(self, value=saved.get("card_view_scale", "2x"))
        self.picture = ttk.Label(self)
        self.picture.grid(row=0, column=0, columnspan=2, sticky="nw")
        self.note = ttk.Label(self, style="Hint.TLabel")
        self.note.grid(row=1, column=0, columnspan=2, sticky="w")
        controls = ttk.Frame(self)
        controls.grid(row=2, column=0, columnspan=2, sticky="w", pady=(2, 0))
        self.languages = ttk.Combobox(controls, state="readonly", width=16)
        self.languages.pack(side="left")
        self.languages.bind("<<ComboboxSelected>>", lambda e: self._chose_language())
        ttk.Combobox(controls, textvariable=self.scale, values=SCALES, state="readonly", width=4).pack(
            side="left", padx=(4, 0))
        self.scale.trace_add("write", lambda *_: (settings.save("card_view_scale", self.scale.get()), self.later()))
        self._fill_languages()

    def _folders(self):
        """Where the translations may be: the repository's, beside the editor
        program, and beside (or above) the game files it reads."""
        folders = list(card_view.language_folders())
        folders.append(Path(sys.executable).resolve().parent / "languages")
        files = getattr(self.app, "files", None)
        source = Path(files.source) if files is not None and getattr(files, "source", None) else None
        if source is not None:
            folders += [source / "languages", source.parent / "languages", source.parent.parent / "languages"]
        return folders

    def _fill_languages(self):
        found = ["en-us"] + [code for code in card_view.LANGUAGES if code != "en-us" and
                             any((folder / f"{code}.txt").is_file() for folder in self._folders())]
        self.codes = found
        self.languages.configure(values=[card_view.LANGUAGES[c] for c in found])
        if self.language.get() not in found:
            self.language.set("en-us")
        self.languages.set(card_view.LANGUAGES[self.language.get()])

    def _chose_language(self):
        label = self.languages.get()
        code = next((c for c in self.codes if card_view.LANGUAGES[c] == label), "en-us")
        self.language.set(code)
        settings.save("card_view_language", code)
        self.later()

    def later(self):
        """Drawn again a moment after a change (a picture a key is too many).
        The window's timer, as the tabs' are: the window cancels its own on
        close (App.destroy), which a widget's would outlive."""
        if self._job is None:
            self._job = self.app.after(120, self.draw)

    def view(self):
        files = getattr(self.app, "files", None)
        if files is None:
            return None
        if self._view is None or self._source is not files.source:
            try:
                self._view = card_view.CardView(files.slus, files.wa)
            except (ValueError, IndexError) as problem:
                self._view = None
                self.note.configure(text=str(problem))
                return None
            self._source = files.source
            self._view.folders = self._folders()
            self._fill_languages()
        return self._view

    def draw(self):
        self._job = None
        if not self.winfo_exists():
            return
        view, values = self.view(), self.values()
        if view is None or values is None:
            self.picture.configure(image="")
            self._photo = None
            return
        card_type, star1, star2, text, colours, star_names = values
        scale = SCALES.index(self.scale.get()) + 1 if self.scale.get() in SCALES else 2
        image = view.render(card_type, star1, star2, text, language=self.language.get(), colours=colours,
                            scale=scale, star_names=star_names)
        self._photo = tk.PhotoImage(master=self, data=base64.b64encode(pngio.encode(image)), format="png")
        self.picture.configure(image=self._photo)
        self.note.configure(text="The card view as the game draws it" +
                            ("" if self.language.get() == "en-us" else
                             f", in {card_view.LANGUAGES[self.language.get()]}'s layout and spacing"))
