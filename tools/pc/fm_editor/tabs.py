"""The editor's tabs: Cards, Fusions, Equips, Rituals, Duelists, Mod info
and Conflicts. Each works on app.project and calls app.changed() after an
edit."""
from __future__ import annotations

import json
import tkinter as tk
from tkinter import messagebox, ttk

from . import bulk_dialog, guardian_stars, manifest, pools as poolmath, text_menu, validate
from .card_text_box import CardTextBox
from .icon_choice import IconChoice
from . import card_icons
from .card_view_preview import CardViewPreview
from .monster_effects_ui import EffectsBox
from .gamedata import (FUSION_GROUPS, ATTRIBUTE_NAMES, CARD_COUNT, DECK_COPY_LIMIT, DECK_SIZE, DUELIST_NAMES,
                       EQUIP_BONUS_MAX, FRAME_NAMES,
                       POOL_LABELS, POOL_TOTAL, POOLS, STAR_NAMES, STARTER_WEIGHT_LIMIT, TYPE_EQUIP, TYPE_MAGIC, TYPE_NAMES,
                       TYPE_RITUAL, TYPE_TRAP,
                       exodia_piece, type_frame)
from . import fixed_decks
from .fixed_deck_view import FixedDeckView
from .model import KEY_RE, StarterDeck
from .widgets import (CardField, FormDialog, ScrolledForm, ScrolledPage, card_matches, card_named, grab, pick_card, px,
                      fixed_font, scrolled_tree, show_text, ui_font)

ATTRIBUTE_CHOICES = ATTRIBUTE_NAMES + ["6 (magic)", "7 (trap)"]
STAR_CHOICES = ["(none)"] + STAR_NAMES[1:]
EFFECT_NONE = "(none)"
# "By type" leaves "frame" out (a monster with effects is then orange);
# the last writes "Type": its type's frame even with effects (frame -2).
FRAME_CHOICES = ["By type"] + FRAME_NAMES + ["Type, never orange"]
# Each frame's colour, as the hand's frames have it (the duel's palette rows 1-6).
FRAME_COLOURS = ["#e0a838", "#409830", "#b040a0", "#2848b0", "#8868d8", "#e07000"]


def type_label(t: int) -> str:
    return TYPE_NAMES[t] if 0 <= t < len(TYPE_NAMES) else str(t)


def attribute_label(a: int) -> str:
    return ATTRIBUTE_CHOICES[a] if 0 <= a < len(ATTRIBUTE_CHOICES) else str(a)


def frame_label(f: int) -> str:
    if f == -2:
        return FRAME_CHOICES[-1]
    return FRAME_CHOICES[f + 1] if -1 <= f < len(FRAME_NAMES) else str(f)


def frame_value(label: str) -> int:
    """A Frame choice as card.frame: -1 left out, -2 "Type", else the colour."""
    i = parse_choice(label, FRAME_CHOICES)
    return -2 if i == len(FRAME_CHOICES) - 1 else max(-1, i - 1)


def star_choices(project=None) -> list:
    """The stars a card may have in this mod (guardian_stars.choices)."""
    return guardian_stars.choices(project.other.get("guardian_stars") if project is not None else None)


def star_label(s: int, project=None) -> str:
    choices = star_choices(project)
    return choices[s] if 0 <= s < len(choices) else str(s)


def parse_choice(text: str, choices) -> int:
    if text in choices:
        return choices.index(text)
    head = text.split(" ", 1)[0]
    return int(head) if head.lstrip("-").isdigit() else -1


class Tab(ttk.Frame):
    def __init__(self, notebook, app, title):
        # In a page that scrolls when the window is too small for the tab.
        self.page = ScrolledPage(notebook)
        super().__init__(self.page.inner, padding=6)
        self.page.tab = self
        self.grid(row=0, column=0, sticky="nsew")
        self.app = app
        notebook.add(self.page, text=title)

    @property
    def project(self):
        return self.app.project

    def applied(self):
        """Tell the window this form no longer contains unapplied input."""
        callback = getattr(self.app, "form_applied", None)
        if callback:
            callback(self)

    def refresh(self):
        pass

    def commit(self):
        """Store what the tab's form holds; False when it cannot."""
        return True


# --- Cards --------------------------------------------------------------------

HINT_WIDTH = 35     # characters: "Retail: " and the longest name it shows in full


class CardsTab(Tab):
    FILTERS = ["All cards", "Changed", "Added by the mod", "With notes", "Monsters", "Non-monsters"] + TYPE_NAMES
    # The fields whose disc value (a copy's base's) is shown, as a link
    # putting it back, only while the form differs from it (mark).
    MARKED = ("name", "type", "effect", "equip_attack", "equip_defense", "attribute", "level", "attack", "defense", "star1", "star2",
              "password", "starchips", "text", "frame")

    def __init__(self, notebook, app):
        super().__init__(notebook, app, "Cards")
        self.current = None
        self._shown_price = ""
        self._shown_effect = ""
        self._shown_threshold = ""
        self._shown_bonus = ("", "")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        # The list and the form side by side, the line between them dragged
        # where wanted; each scrolls across on its own when it is cut short
        # (the list its columns, the form its controls). Until it is
        # dragged, the form has all the width it needs and the list the rest,
        # down to LIST_LEAST.
        self.panes = ttk.Panedwindow(self, orient="horizontal")
        self.panes.grid(row=0, column=0, sticky="nsew")
        self._sash_dragged = False
        left = ttk.Frame(self.panes)
        self.panes.add(left, weight=1)
        top = ttk.Frame(left)
        top.pack(fill="x")
        ttk.Label(top, text="Search").pack(side="left")
        self.search = tk.StringVar()
        ttk.Entry(top, textvariable=self.search, width=24).pack(side="left", padx=4)
        self.filter = tk.StringVar(value=self.FILTERS[0])
        ttk.Combobox(top, textvariable=self.filter, values=self.FILTERS, state="readonly", width=16).pack(side="left")
        self.search.trace_add("write", lambda *_: self.fill())
        self.filter.trace_add("write", lambda *_: self.fill())
        frame, self.tree = scrolled_tree(left, [("id", "#"), ("name", "Name"), ("type", "Type"), ("atk", "ATK"),
                                                ("def", "DEF"), ("state", "Status")], [50, 160, 100, 50, 50, 60], 10, sort_numeric=("id", "atk", "def"))
        frame.pack(fill="both", expand=True, pady=4)
        self.tree.bind("<<TreeviewSelect>>", lambda e: self.select())
        bottom = ttk.Frame(left)
        bottom.pack(side="bottom", fill="x", before=frame)
        ttk.Button(bottom, text="Add a card (copy of the selected one)", command=self.add_card).pack(side="left")
        self.count = ttk.Label(bottom)
        self.count.pack(side="right")

        self.card_scroll = ScrolledForm(self.panes, horizontal=True)
        self.panes.add(self.card_scroll, weight=0)
        self.panes.bind("<Configure>", lambda e: self.place_sash(), add=True)
        # Only when the form's width changes: scrolling it up and down moves
        # it too, and placing the line then shook the list beside it.
        self._form_width = None
        # The line placed before the form lays out (in place of its own
        # binding): the other way, a wider card's form flashed its bottom
        # scrollbar on until the line made room.
        self.card_scroll.body.bind("<Configure>", lambda e: (self.form_resized(), self.card_scroll._layout()))
        self.panes.bind("<B1-Motion>", lambda e: setattr(self, "_sash_dragged", True), add=True)
        self.panes.bind("<ButtonRelease-1>", lambda e: self.keep_share(), add=True)
        # Resized while another tab was shown, the line was left where it
        # was: placed again when the tab shows (on the window: its destroy
        # cancels what waits).
        self.panes.bind("<Map>", lambda e: self.app.after_idle(self.place_sash), add=True)
        self._sash_share = None
        form = ttk.LabelFrame(self.card_scroll.body, text="Card", padding=8)
        form.pack(fill="both", expand=True)
        self.form = form
        self.vars = {k: tk.StringVar() for k in ("name", "attack", "defense", "type", "attribute", "level",
                                                  "star1", "star2", "password", "starchips", "key", "frame",
                                                  "effect", "trap_threshold", "equip_attack",
                                                  "equip_defense")}
        row = 0
        # Only a monster has these; a magic, trap, ritual or equip card has
        # an effect instead (show_kind).
        self.monster_rows, self.effect_row = [], []
        self.trap_rows = []
        self.equip_rows = []

        self.captions = {}

        def line(label, widget, hint=None, rows=None):
            nonlocal row
            caption = ttk.Label(form, text=label)
            caption.grid(row=row, column=0, sticky="w", pady=2)
            if hint is not None:
                self.captions[next(k for k, v in self.hints.items() if v is hint)] = caption
            widget.grid(row=row, column=1, sticky="we", pady=2)
            if hint is not None:
                hint.grid(row=row, column=2, sticky="w", padx=6)
            if rows is not None:
                rows.extend(w for w in (caption, widget, hint) if w is not None)
            row += 1
            return widget

        self.title = ttk.Label(form, font=ui_font(11))
        self.title.grid(row=row, column=0, columnspan=3, sticky="w", pady=(0, 6))
        row += 1
        self.hints = {}

        # The hints have a fixed width, the longest one's ("Retail: " and a
        # name of 27 letters, show()), so the form is as wide for every card
        # and lays out once: grown after the window is shown, the scrolled
        # form would keep its first width and cut them off.
        def hint(key):
            self.hints[key] = ttk.Label(form, style="Hint.TLabel", width=HINT_WIDTH)
            if key in self.MARKED:
                self.hints[key].bind("<Button-1>", lambda e, k=key: self.restore(k))
            return self.hints[key]

        line("Name", ttk.Entry(form, textvariable=self.vars["name"], width=26), hint("name"))
        line("Type", IconChoice(form, app, self.vars["type"], TYPE_NAMES,
                                lambda label: TYPE_NAMES.index(label) if label in TYPE_NAMES else None, width=18),
             hint("type"))
        # What the card does when played: a disc card of its type whose
        # effect it has (cards.c "effect"), so the game and the CPU play it
        # as that card.
        self.effect_box = line("Retail effect", ttk.Combobox(form, textvariable=self.vars["effect"], state="readonly",
                                                       width=26), hint("effect"), self.effect_row)
        # Its room kept for every card (hidden for a monster, it is the
        # widest there): the form, and the line beside it, stay put from a
        # monster to a magic card.
        form.columnconfigure(1, minsize=self.effect_box.winfo_reqwidth())
        self.edit_equips_button = ttk.Button(form, text="Edit equip targets...", command=self.edit_equips)
        self.edit_equips_button.grid(row=row, column=1, sticky="w", pady=(0, 4))
        self.equip_rows.append(self.edit_equips_button)
        row += 1
        # What the equip adds to the monster's ATK and to its DEF (tables.c
        # "equips" "bonus_attack", "bonus_defense"): the disc's +500 to both,
        # Megamorph's +1000. An equip has no Retail effect to choose.
        for key, label in (("equip_attack", "ATK boost"), ("equip_defense", "DEF boost")):
            line(label, ttk.Spinbox(form, textvariable=self.vars[key], from_=-EQUIP_BONUS_MAX, to=EQUIP_BONUS_MAX,
                                    increment=100, width=10), hint(key), self.equip_rows)
        line("Trigger at ATK ≤", ttk.Spinbox(form, textvariable=self.vars["trap_threshold"], from_=0, to=65535,
                                           increment=50, width=10), hint("trap_threshold"), self.trap_rows)
        line("Attribute", IconChoice(form, app, self.vars["attribute"], ATTRIBUTE_CHOICES, self.attribute_icon, width=18),
             hint("attribute"), self.monster_rows)
        line("Level", ttk.Spinbox(form, textvariable=self.vars["level"], from_=0, to=12, width=8), hint("level"),
             self.monster_rows)
        line("ATK", ttk.Spinbox(form, textvariable=self.vars["attack"], from_=0, to=5110, increment=10, width=8),
             hint("attack"), self.monster_rows)
        line("DEF", ttk.Spinbox(form, textvariable=self.vars["defense"], from_=0, to=5110, increment=10, width=8),
             hint("defense"), self.monster_rows)
        # With their icons (a mod's stars past the disc's ten have none here).
        self.star_boxes = [IconChoice(form, app, self.vars[key], STAR_CHOICES, self.star_icon, width=18)
                           for key in ("star1", "star2")]
        line("Star 1", self.star_boxes[0], hint("star1"), self.monster_rows)
        line("Star 2", self.star_boxes[1], hint("star2"), self.monster_rows)
        # Typing past 8 digits, or anything else, does nothing.
        digits = (self.register(lambda text: text == "" or (len(text) <= 8 and text.isascii() and text.isdigit())),
                  "%P")
        line("Password", ttk.Entry(form, textvariable=self.vars["password"], width=12, validate="key",
                                   validatecommand=digits), hint("password"))
        self.price = line("Starchips", ttk.Entry(form, textvariable=self.vars["starchips"], width=12), hint("starchips"))
        ttk.Label(form, text="0 = free; empty = default price", style="Hint.TLabel").grid(
            row=row, column=1, columnspan=2, sticky="w")
        row += 1
        # The frame the card view, the Library and the duel draw it in: its
        # type's unless the mod picks one (cards.c "frame").
        self.captions["frame"] = ttk.Label(form, text="Frame")
        self.captions["frame"].grid(row=row, column=0, sticky="w", pady=2)
        ttk.Combobox(form, textvariable=self.vars["frame"], values=FRAME_CHOICES, state="readonly",
                     width=18).grid(row=row, column=1, sticky="we", pady=2)
        beside = ttk.Frame(form)
        beside.grid(row=row, column=2, sticky="w", padx=6)
        self.swatch = tk.Label(beside, width=2, relief="solid", borderwidth=1)
        self.swatch.pack(side="left")
        self.hints["frame"] = ttk.Label(beside, style="Hint.TLabel", width=HINT_WIDTH - 4)
        self.hints["frame"].pack(side="left", padx=(6, 0))
        self.hints["frame"].bind("<Button-1>", lambda e: self.restore("frame"))
        row += 1
        # What the monster does on the field (cards.c "monster_effects"),
        # stored as soon as it is changed.
        self.effects_box = EffectsBox(form, app, self.effects_changed)
        self.effects_box.grid(row=row, column=0, columnspan=3, sticky="we", pady=4)
        self.monster_rows.append(self.effects_box)
        row += 1
        self.captions["text"] = ttk.Label(form, text="Card text")
        self.captions["text"].grid(row=row, column=0, sticky="nw", pady=2)
        # 21 columns: the game's 20 letters a line and room for the cursor.
        # Drawn as the card view's panel: icons and colours as the game shows them.
        self.text = CardTextBox(form, app, width=21, height=9, wrap="word", font=fixed_font())
        self.text.grid(row=row, column=1, sticky="nw", pady=2)
        # Beside it, the card view's text box as the game draws it, as tall
        # as the box; the retail text's link under the box.
        self.card_view = CardViewPreview(form, app, self.card_view_values, lambda: self.text.winfo_height())
        self.card_view.grid(row=row, column=2, sticky="nw", padx=6, pady=2)
        self.text.bind("<Configure>", lambda e: self.card_view.later(), add=True)
        row += 1
        self.hints["text"] = ttk.Label(form, style="Hint.TLabel")
        self.hints["text"].grid(row=row, column=1, columnspan=2, sticky="w")
        self.hints["text"].bind("<Button-1>", lambda e: self.restore("text"))
        row += 1
        self.lines = ttk.Label(form, style="Hint.TLabel")
        self.lines.grid(row=row, column=1, columnspan=2, sticky="w")
        row += 1
        self.text.bind("<KeyRelease>", lambda e: (self.count_lines(), self.mark_later()), add=True)
        # Right-click: insert an icon or a colour, shown as the game draws them.
        text_menu.install(app, self.text, lambda: (self.count_lines(), self.mark_later()))
        self.vars["frame"].trace_add("write", lambda *_: self.show_swatch())
        self.vars["type"].trace_add("write", lambda *_: self.show_swatch())
        self.vars["type"].trace_add("write", lambda *_: self.show_kind())
        for key in ("type", "star1", "star2"):
            self.vars[key].trace_add("write", lambda *_: self.card_view.later())
        self.vars["effect"].trace_add("write", lambda *_: self.show_trap_threshold())
        self.added_frame = ttk.LabelFrame(form, text="Added card", padding=6)
        self.added_frame.grid(row=row, column=0, columnspan=3, sticky="we", pady=6)
        row += 1
        ttk.Label(self.added_frame, text="Stable id").grid(row=0, column=0, sticky="w")
        ttk.Entry(self.added_frame, textvariable=self.vars["key"], width=24).grid(row=0, column=1, sticky="w")
        self.base_label = ttk.Label(self.added_frame)
        self.base_label.grid(row=1, column=0, columnspan=2, sticky="w")
        self.drops = tk.BooleanVar()
        self.opponents = tk.BooleanVar()
        ttk.Checkbutton(self.added_frame, text="Can be won in its base's place", variable=self.drops).grid(
            row=2, column=0, columnspan=2, sticky="w")
        ttk.Checkbutton(self.added_frame, text="Opponents' decks can deal it in its base's place",
                        variable=self.opponents).grid(row=3, column=0, columnspan=2, sticky="w")
        ttk.Label(self.added_frame, style="Hint.TLabel", wraplength=px(form, 320), justify="left",
                  text="A new card starts in nobody's chest. Players win it in its base's place (above), "
                       "from a starter deck (Starter decks tab) or with Game > Cheats > Give. Its password "
                       "also works in the Password shop. Set its price with Starchips above.").grid(
            row=4, column=0, columnspan=2, sticky="w", pady=(4, 0))
        ttk.Button(self.added_frame, text="Remove this card", command=self.remove_card).grid(
            row=5, column=0, columnspan=2, sticky="w", pady=(4, 0))
        self.extra = ttk.Label(form, style="Hint.TLabel", wraplength=px(form, 320), justify="left")
        self.extra.grid(row=row, column=0, columnspan=3, sticky="w")
        row += 1
        # The modder's own notes, last: the game shows none of them.
        ttk.Label(form, text="Notes").grid(row=row, column=0, sticky="nw", pady=2)
        self.notes = tk.Text(form, width=36, height=4, wrap="word", undo=True)
        self.notes.grid(row=row, column=1, columnspan=2, sticky="we", pady=2)
        row += 1
        buttons = ttk.Frame(form)
        buttons.grid(row=row, column=0, columnspan=3, sticky="we", pady=(8, 0))
        ttk.Button(buttons, text="Apply", command=self.apply).pack(side="left")
        ttk.Button(buttons, text="Revert to retail", command=self.revert).pack(side="left", padx=4)
        self.status = ttk.Label(form, style="Error.TLabel", wraplength=px(form, 320), justify="left")
        self.status.grid(row=row + 1, column=0, columnspan=3, sticky="w", pady=(6, 0))
        for child in form.winfo_children():
            if isinstance(child, (ttk.Entry, ttk.Spinbox)):
                child.bind("<Return>", lambda e: self.apply())
        self._mark_job = None
        for key in self.MARKED:
            if key in self.vars:
                self.vars[key].trace_add("write", lambda *_: self.mark_later())
        self.fill()
        self.show(None)

    # the list
    def wanted(self, cid) -> bool:
        card = self.project.cards[cid]
        f = self.filter.get()
        if f == "Changed" and not self.project.card_changed(cid):
            return False
        if f == "Added by the mod" and cid not in self.project.added:
            return False
        if f == "With notes" and cid not in self.project.notes:
            return False
        if f == "Monsters" and not card.is_monster():
            return False
        if f == "Non-monsters" and card.is_monster():
            return False
        if f in TYPE_NAMES and card.type != TYPE_NAMES.index(f):
            return False
        search = self.search.get()
        return card_matches(self.project, cid, search) or (
            bool(search.strip()) and search.lower().strip() in self.project.notes.get(cid, "").lower())

    def row(self, cid):
        card = self.project.cards[cid]
        state = ("added" if cid in self.project.added else "changed" if self.project.card_changed(cid)
                 else "notes" if cid in self.project.notes else "")
        attack, defense = (card.attack, card.defense) if card.is_monster() else ("", "")
        return (cid, card.name, type_label(card.type), attack, defense, state), (state,) if state else ()

    def fill(self):
        if not hasattr(self, "tree") or self.project is None:
            return
        self.tree.delete(*self.tree.get_children())
        shown = 0
        for cid in sorted(self.project.cards):
            if self.wanted(cid):
                values, tags = self.row(cid)
                self.tree.insert("", "end", iid=str(cid), values=values, tags=tags)
                shown += 1
        self.tree.sorting.apply()
        self.count.configure(text=f"{shown} cards")
        if self.current and self.tree.exists(str(self.current)):
            self.tree.selection_set(str(self.current))
            self.tree.see(str(self.current))

    def refresh(self):
        self.current = None
        self.fill()
        self.show(None)

    def update_row(self, cid):
        if self.tree.exists(str(cid)):
            values, tags = self.row(cid)
            self.tree.item(str(cid), values=values, tags=tags)
            self.tree.sorting.apply()

    def select(self):
        selection = self.tree.selection()
        cid = int(selection[0]) if selection else None
        if cid == self.current:
            return
        if self.current is not None and not self.apply(quiet=True):
            self.tree.selection_set(str(self.current))    # stay on the card whose form cannot be stored
            return
        self.show(cid)

    def goto(self, cid):
        if self.current is not None and not self.apply(quiet=True):
            return False
        self.search.set("")
        self.filter.set(self.FILTERS[0])
        self.fill()
        if self.tree.exists(str(cid)):
            self.tree.selection_set(str(cid))
            self.tree.see(str(cid))
            # A pending tab-change refresh rebuilds the list. Set the
            # current card now so that refresh keeps this selection.
            self.show(cid)
            return True
        return False

    def show_card(self, cid):
        """Select the card, in the list as it is filtered if it is there."""
        if not self.tree.exists(str(cid)):
            self.goto(cid)
            return
        self.tree.selection_set(str(cid))
        self.tree.see(str(cid))
        self.select()

    def follow(self, cid):
        if cid != self.current and cid in self.project.cards:
            self.show_card(cid)

    # the form
    def show(self, cid):
        self.current = cid
        self.status.configure(text="")
        state = "normal" if cid else "disabled"
        for child in self.form.winfo_children():
            try:
                if isinstance(child, ttk.Combobox):
                    child.configure(state="readonly" if cid else "disabled")
                elif isinstance(child, (ttk.Entry, ttk.Spinbox, ttk.Button)):
                    child.configure(state=state)
            except tk.TclError:
                pass
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.notes.configure(state="normal")
        self.notes.delete("1.0", "end")
        self.notes.edit_reset()
        if not cid:
            self.title.configure(text="Select a card")
            for var in self.vars.values():
                var.set("")
            self.added_frame.grid_remove()
            self.extra.configure(text="")
            self.effects_box.show(None)
            self.reference = None
            for label in self.hints.values():
                label.configure(text="")
            self.mark()
            self.lines.configure(text="")
            self.text.configure(state="disabled")
            self.notes.configure(state="disabled")
            if self.app.text_preview is not None:
                self.app.text_preview.later()
            return
        card = self.project.cards[cid]
        self.app.current_card = cid
        self.title.configure(text=f"#{cid}" + ("  (added by the mod)" if cid in self.project.added else ""))
        self.vars["name"].set(card.name)
        self.vars["attack"].set(card.attack)
        self.vars["defense"].set(card.defense)
        # Before the type, whose trace fills the effect list for it.
        self.vars["effect"].set(self.effect_label(self.effect_shown(cid)))
        self.vars["type"].set(type_label(card.type))
        threshold = self.project.trap_threshold_override(cid)
        self._shown_threshold = "" if threshold is None else str(threshold)
        self.vars["trap_threshold"].set(self._shown_threshold)
        self.show_trap_threshold()
        self.show_bonus(cid, card.type)
        self.vars["attribute"].set(attribute_label(card.attribute))
        self.vars["level"].set(card.level)
        # The mod's stars (the Guardian Stars tab) are in the lists too.
        for box in self.star_boxes:
            box.configure(values=star_choices(self.project))
        self.vars["star1"].set(star_label(card.star1, self.project))
        self.vars["star2"].set(star_label(card.star2, self.project))
        self.vars["frame"].set(frame_label(card.frame))
        self.vars["password"].set(self.project.password(cid))
        price = self.project.starchip_cost(cid)
        self._shown_price = "" if price is None else str(price)
        self.vars["starchips"].set(self._shown_price)
        self.price.configure(state="normal")
        self.text.insert("1.0", card.description)
        self.notes.insert("1.0", self.project.notes.get(cid, ""))
        self.notes.edit_reset()
        self.effects_box.show(cid)
        self.caption_icons()
        # The form may want another width now (a hint, an icon): no event
        # says so where the panes hold it at a width of their own.
        self.app.after_idle(self.relayout)
        self.count_lines()
        self.reference = self.project.retail.cards.get(cid) or self.project.cards.get(self.project.base_of(cid))
        self.mark()
        if cid in self.project.added:
            added = self.project.added[cid]
            self.vars["key"].set(added.key)
            self.drops.set(added.drops)
            self.opponents.set(added.opponents)
            self.base_label.configure(text=f"Copy of {self.project.card_label(added.base)}; "
                                           f"identity {self.project.identity(cid)}")
            self.added_frame.grid()
            extra = added.extra
        else:
            self.added_frame.grid_remove()
            extra = self.project.card_extra.get(cid, {})
        self._shown_effect = self.vars["effect"].get()
        kept = sorted(set(extra) - {"effect", "trap_threshold", "monster_effects"})
        self.extra.configure(text=("Kept as written in mod.json: " + ", ".join(kept)) if kept else "")

    # What differs from the disc
    def retail_values(self) -> dict:
        """key -> (the form's text for the disc's value or None, the words
        for it, whether the form differs from it). A copy's are its base's."""
        cid, ref, p = self.current, self.reference, self.project
        if not cid or ref is None or cid not in p.cards:
            return {}
        values = {"name": ref.name, "type": type_label(ref.type), "attribute": attribute_label(ref.attribute),
                  "level": str(ref.level), "attack": str(ref.attack), "defense": str(ref.defense),
                  "star1": star_label(ref.star1, p), "star2": star_label(ref.star2, p), "frame": frame_label(ref.frame)}
        shown = {key: (value, value, self.vars[key].get().strip() != value.strip()) for key, value in values.items()}
        for key in ("star1", "star2", "attribute"):
            choices = star_choices(p) if key != "attribute" else ATTRIBUTE_CHOICES
            number = ref.attribute if key == "attribute" else getattr(ref, key)
            shown[key] = (values[key], values[key], parse_choice(self.vars[key].get(), choices) != number)
        shown["frame"] = (values["frame"], values["frame"].lower(),
                          frame_value(self.vars["frame"].get()) != ref.frame)
        shown["text"] = (ref.description, "text", self.text.get("1.0", "end-1c") != ref.description)
        # The effect only against the disc card's own type: another type's
        # list has none of its choices.
        default = self.effect_default(cid)
        if parse_choice(self.vars["type"].get(), TYPE_NAMES) == ref.type and self.effect_kind(default) >= 0:
            label = self.effect_label(default)
            shown["effect"] = (label, label, self.vars["effect"].get() != label)
        if parse_choice(self.vars["type"].get(), TYPE_NAMES) == TYPE_EQUIP:
            for key, points in zip(("equip_attack", "equip_defense"), p.equip_bonus_default(cid)):
                shown[key] = (str(points), f"{points:+d}", self.vars[key].get().strip() not in ("", str(points)))
        if cid in p.retail.cards:
            retail = p.retail.passwords.get(cid) or ""
            typed = self.vars["password"].get().strip()
            shown["password"] = (retail, retail or "none", (typed.zfill(8) if typed else "") != (retail.zfill(8) if retail else ""))
            price = str(p.retail.starchips.get(cid, ""))
            shown["starchips"] = (price, price or "unknown", self.vars["starchips"].get().strip() not in ("", price))
        else:
            shown["password"] = (None, "card view only", False)
            shown["starchips"] = ("", "999999", self.vars["starchips"].get().strip() not in ("", "999999"))
        return shown

    def mark_later(self):
        if self._mark_job is None:
            self._mark_job = self.app.after_idle(self.mark)   # the window cancels its own jobs on close

    def mark(self):
        """A field that differs from the disc: its caption in the changed
        colour and, beside it, the disc's value, a click putting it back.
        The disc's value is not repeated beside the fields that have it."""
        if self._mark_job is not None:
            self.app.after_cancel(self._mark_job)
            self._mark_job = None
        shown = self.retail_values()
        what = ("Retail" if self.current in self.project.retail.cards else "Base") if shown else ""
        for key in self.MARKED:
            value, words, differs = shown.get(key, (None, "", False))
            hint, caption = self.hints[key], self.captions.get(key)
            if key == "password" and value is None and shown:
                hint.configure(text="Card view only", style="Hint.TLabel", cursor="")
            elif differs:
                text = f"{what}: {words} (restore)" if key != "text" else f"Restore {what.lower()} text"
                if len(text) > HINT_WIDTH:
                    text = f"{what}: {words[:HINT_WIDTH - len(what) - 13]}… (restore)"
                hint.configure(text=text, style="Changed.TLabel", cursor="hand2")
            else:
                hint.configure(text="", style="Hint.TLabel", cursor="")
            if caption is not None:
                caption.configure(style="Changed.TLabel" if differs else "TLabel")

    def restore(self, key):
        """Put the disc's value back in the form (Apply stores it)."""
        value, _, differs = self.retail_values().get(key, (None, "", False))
        if value is None or not differs:
            return
        if key == "text":
            self.text.delete("1.0", "end")
            self.text.insert("1.0", value)
            self.count_lines()
        else:
            self.vars[key].set(value)
        edited = getattr(self.app, "form_edited", None)
        if edited:
            edited(self)
        self.mark()

    # A magic, trap, ritual or equip card's effect
    def effect_kind(self, eid: int) -> int:
        """The type of the disc card `eid`, if it is no monster; else -1."""
        card = self.project.retail.cards.get(eid) if self.project else None
        return card.type if card and not card.is_monster() else -1

    def effect_label(self, eid: int) -> str:
        if self.effect_kind(eid) < 0:
            return EFFECT_NONE
        card = self.project.retail.cards[eid]
        # Names describe fixed retail behaviors, not the mod's current cards.
        # Only duplicate names need a number to distinguish the choices.
        duplicate = any(other.id != eid and other.type == card.type and other.name == card.name
                        for other in self.project.retail.cards.values())
        return f"{card.name} ({eid})" if duplicate or card.name == EFFECT_NONE else card.name

    def effect_default(self, cid: int) -> int:
        """The effect the card has with no "effect" key: a disc card its own,
        a copy its base's (cards.c Cards_EffectId)."""
        return self.project.effect_of(self.project.base_of(cid)) if cid in self.project.added else cid

    def chosen_effect(self) -> int:
        kind = parse_choice(self.vars["type"].get(), TYPE_NAMES)
        return next((eid for eid in self.project.retail.cards
                     if self.effect_kind(eid) == kind and self.effect_label(eid) == self.vars["effect"].get()), 0)

    def show_trap_threshold(self):
        threshold = None
        if self.project is not None and parse_choice(self.vars["type"].get(), TYPE_NAMES) == TYPE_TRAP:
            threshold = self.project.trap_threshold_default(self.chosen_effect())
        for widget in self.trap_rows:
            widget.grid() if threshold is not None else widget.grid_remove()
        self.hints["trap_threshold"].configure(text=f"Blank: effect default ({threshold})" if threshold is not None else "")

    def show_bonus(self, cid, kind):
        """The equip's ATK and DEF boosts in the form; blank for another card."""
        shown = self.project.equip_bonus_of(cid) if kind == TYPE_EQUIP else ("", "")
        self._shown_bonus = tuple(str(points) for points in shown)
        for key, text in zip(("equip_attack", "equip_defense"), self._shown_bonus):
            self.vars[key].set(text)

    def effect_shown(self, cid: int) -> int:
        eid = self.project.effect_of(cid)
        return eid if self.effect_kind(eid) == self.project.cards[cid].type else 0

    def show_kind(self):
        """The monster's rows for a monster, the effect for the rest."""
        kind = parse_choice(self.vars["type"].get(), TYPE_NAMES)
        monster = not (kind >= TYPE_MAGIC and self.project is not None)
        for widget in self.monster_rows:
            widget.grid() if monster else widget.grid_remove()
        for widget in self.effect_row:
            widget.grid_remove() if monster or kind == TYPE_EQUIP else widget.grid()
        for widget in self.equip_rows:
            widget.grid() if kind == TYPE_EQUIP and self.current is not None else widget.grid_remove()
        self.show_trap_threshold()
        if monster:
            self.refill_monster()
            return
        # The disc's cards of the same type: one of another would be played
        # as its own type, and the CPU would not know what to do with it.
        # "(none)" only for a card with no effect of its own to fall back on.
        own = self.current is not None and self.effect_kind(self.effect_default(self.current)) == kind
        choices = [] if own else [EFFECT_NONE]
        choices += [self.effect_label(eid) for eid in sorted(self.project.retail.cards) if self.effect_kind(eid) == kind]
        self.effect_box.configure(values=choices)
        # An "effect" written for another type (shown as none) fits this one:
        # shown, so that the change of type keeps it.
        if self.current is not None and self.vars["effect"].get() == self._shown_effect:
            stored = self.project.effect_of(self.current)
            if self.effect_kind(stored) == kind and self.effect_label(stored) in choices:
                self.vars["effect"].set(self.effect_label(stored))
        if self.vars["effect"].get() not in choices:
            self.vars["effect"].set(choices[0] if not own else self.effect_label(self.effect_default(self.current)))

    def effects_changed(self, cid):
        """The Monster effects box stored a change to the card."""
        self.show_swatch()
        self.app.changed()
        self.update_row(cid)
        self.status.configure(text="\n".join(i.message for i in validate.validate_card(self.project, cid)))

    def edit_equips(self):
        """Apply the card and open its target list without another search."""
        if not self.apply() or self.current is None or self.project.cards[self.current].type != TYPE_EQUIP:
            return
        self.app.open_card(self.app.equips, self.current)

    def refill_monster(self):
        """A card applied as a non-monster lost its ATK, DEF, level and stars;
        made a monster again, it gets the disc card's (a copy's base's) back."""
        cid = self.current
        if self.project is None or cid not in self.project.cards or self.project.cards[cid].is_monster():
            return
        src = self.project.retail.cards.get(self.project.base_of(cid))
        if src is None or not src.is_monster():
            return
        self.vars["attack"].set(src.attack)
        self.vars["defense"].set(src.defense)
        self.vars["level"].set(src.level)
        self.vars["attribute"].set(attribute_label(src.attribute))
        self.vars["star1"].set(star_label(src.star1, self.project))
        self.vars["star2"].set(star_label(src.star2, self.project))

    def store_effect(self, cid: int, card) -> bool:
        """The Effect list into the card's "effect"; whether that changed it.
        Left out when it is what the card has anyway, or for a monster, which
        never plays one. An "effect" the form has not been touched for stays
        as written, whatever it names. An equip has no list: one the mod
        names stays (a copy of Megamorph is still one), another type's goes."""
        extra = self.project.added[cid].extra if cid in self.project.added else self.project.card_extra.get(cid, {})
        if card.type == TYPE_EQUIP:
            named = self.project.resolve(extra["effect"]) if "effect" in extra else None
            if not named or self.effect_kind(named) == TYPE_EQUIP:
                return False
            del extra["effect"]
            if cid not in self.project.added and not extra:
                self.project.card_extra.pop(cid, None)
            return True
        if self.vars["effect"].get() == self._shown_effect and card.type == self.project.cards[cid].type:
            return False
        chosen = 0 if card.is_monster() else self.chosen_effect()
        default = self.effect_default(cid)
        wanted = chosen if chosen and chosen != default else None
        had = extra.get("effect")
        if wanted is None:
            if "effect" not in extra:
                return False
            del extra["effect"]
        else:
            if had is not None and self.project.resolve(had) == wanted:
                return False
            extra["effect"] = wanted
            if cid not in self.project.added:
                self.project.card_extra[cid] = extra
        if cid not in self.project.added and not extra:
            self.project.card_extra.pop(cid, None)
        return True

    def show_swatch(self):
        """The colour the frame will be: the chosen one, or the type's (a
        monster with effects is orange, as cards.c Cards_FrameColor draws it)."""
        frame = frame_value(self.vars["frame"].get())
        kind = parse_choice(self.vars["type"].get(), TYPE_NAMES)
        if frame == -1 and 0 <= kind < TYPE_MAGIC and self.project is not None and self.current in self.project.cards \
                and self.project.monster_effects_of(self.current)[0]:
            frame = FRAME_NAMES.index("Orange")
        elif frame < 0 and kind >= 0:
            frame = type_frame(kind)
        if 0 <= frame < len(FRAME_COLOURS):
            self.swatch.configure(background=FRAME_COLOURS[frame])
        else:
            self.swatch.configure(background=self.swatch.master.winfo_toplevel().cget("background"))

    def count_lines(self):
        text = self.text.get("1.0", "end-1c")
        lines = validate.text_lines(text)
        self.lines.configure(text=f"{lines} of 8 lines (20 letters a line, as the game wraps it)",
                             style="Error.TLabel" if lines > 8 else "Hint.TLabel")
        if self.app.text_preview is not None:
            self.app.text_preview.later()
        self.card_view.later()

    def attribute_icon(self, label):
        """An attribute's ball off the disc (card_icons.py), or None."""
        return card_icons.photos(self.app, self).get("attribute", {}).get(parse_choice(label, ATTRIBUTE_CHOICES))

    def caption_icons(self):
        """The level star, the sword and the shield beside their captions,
        once there are game files to take them from."""
        shown = card_icons.photos(self.app, self, 2)     # 8 and 9 pixels: doubled, by the 16 of the lists' icons
        for key, name in (("level", "level"), ("attack", "attack"), ("defense", "defense")):
            caption = self.captions.get(key)
            if caption is not None:
                caption.configure(image=shown.get(name) or "", compound="left")
        # The starchip: the text's own star icon ({f8 0B 26}, as the pack shop writes prices).
        icons = text_menu.pictures(self.app, self, 1)
        if self.captions.get("starchips") is not None:
            self.captions["starchips"].configure(image=(icons.icons.get(0x26) if icons else None) or "",
                                                 compound="left")

    LIST_LEAST = 320

    def relayout(self):
        if self.winfo_exists():
            self.form.columnconfigure(1, minsize=self.effect_box.winfo_reqwidth())
            self.card_scroll._layout()
            self.place_sash()

    def keep_share(self):
        """A dragged line keeps its share of the width as the window grows
        and shrinks: ttk gave all of a change to the list, and a window
        maximized and restored squeezed the form to nothing."""
        width = self.panes.winfo_width()
        if self._sash_dragged and width > 1:
            self._sash_share = self.panes.sashpos(0) / width

    def keep_line(self, tries=10):
        """The dragged line at its share. ttk may still be laying the panes
        out (and holds the line within the size it had): checked, and tried
        again a little later, a few times at most."""
        width = self.panes.winfo_width()
        if self._sash_share is None or width <= 1 or not self.panes.winfo_ismapped():
            return
        at = round(width * self._sash_share)
        if abs(self.panes.sashpos(0) - at) > 1:
            self.panes.sashpos(0, at)
            if abs(self.panes.sashpos(0) - at) > 1 and tries > 1:
                self.app.after(20, lambda: self.keep_line(tries - 1))

    def rescaled(self):
        """A ttk Panedwindow asks for its panes' sizes as they are now, so
        View > Interface size's fonts (zoom.py) made it ask for a maximized
        window's width and, restored, it stayed that wide, the form off to
        the right: asked instead what the list and the form ask."""
        want = sum(self.nametowidget(pane).winfo_reqwidth() for pane in self.panes.panes()) + px(self, 6)
        if int(self.panes.cget("width")) != want:
            self.panes.configure(width=want)     # which puts the line at 0
        self.panes.update_idletasks()
        if self._sash_dragged:
            # Once the window is laid out: ttk moves it as it goes.
            self.app.after(0, self.keep_line)
        else:
            self.place_sash()

    def form_resized(self):
        width = self.card_scroll.body.winfo_reqwidth()
        if width != self._form_width:
            self._form_width = width
            self.place_sash()

    def place_sash(self):
        """The line between the list and the form, until it is dragged: the
        form as wide as its controls, the list the rest (at least LIST_LEAST)."""
        if not self.panes.winfo_exists() or not self.panes.winfo_ismapped():
            return
        width = self.panes.winfo_width()
        if self._sash_dragged:
            # Once ttk has shared the change out by the panes' weights.
            if self._sash_share is not None and width > 1:
                self.app.after_idle(self.keep_line)
            return
        scroll = self.card_scroll
        # The pane's own edges take a few pixels more than the scrollbar:
        # what the form's canvas still lacks once placed is taken too.
        form = scroll.body.winfo_reqwidth() + scroll.bar.winfo_reqwidth()
        # The line itself is a few pixels wide too: left out, the form came
        # out that much short, and every card shown moved the line there and
        # back (with the bottom scrollbar flashing on), shaking the form.
        line = max(0, scroll.winfo_x() - self.panes.sashpos(0)) if scroll.winfo_ismapped() else 0
        at = max(px(self, self.LIST_LEAST), width - form - line)
        if abs(self.panes.sashpos(0) - at) > 1:
            self.panes.sashpos(0, at)
            self.panes.update_idletasks()
        short = scroll.body.winfo_reqwidth() - scroll.canvas.winfo_width()
        if short > 0 and self.panes.sashpos(0) - short >= px(self, self.LIST_LEAST):
            self.panes.sashpos(0, self.panes.sashpos(0) - short)

    def star_icon(self, label):
        """A guardian star's icon ({f8 0B 18} Mars ... 21 Venus), or None."""
        star = parse_choice(label, star_choices(self.project))
        return 0x17 + star if 1 <= star <= 10 else None

    def card_view_values(self):
        """What the card view preview draws: the form's type, stars and text,
        and the mod's colours for the card (card_text_colors)."""
        if self.current is None or self.project is None or self.current not in self.project.cards:
            return None
        values = [parse_choice(self.vars["type"].get(), TYPE_NAMES),
                  parse_choice(self.vars["star1"].get(), star_choices(self.project)),
                  parse_choice(self.vars["star2"].get(), star_choices(self.project))]
        if min(values) < 0:
            return None
        card_type, star1, star2 = values
        if card_type >= TYPE_MAGIC:
            star1 = star2 = 0
        elif star2 == star1:
            star2 = 0           # one star, shown once (stars.c)
        names = {s: star_label(s, self.project) for s in (star1, star2) if s > 10}
        return card_type, star1, star2, self.text.get("1.0", "end-1c"), self.text_colours(), names

    def text_colours(self):
        """The card's own card_text_colors rule: {"description", "guardian_star"}."""
        rules = self.project.other.get("card_text_colors")
        out = {}
        if isinstance(rules, dict) and isinstance(rules.get("cards"), list):
            for rule in rules["cards"]:
                if isinstance(rule, dict) and self.project.resolve(rule.get("card")) == self.current:
                    out.update({k: rule[k] for k in ("description", "guardian_star")
                                if isinstance(rule.get(k), int) and 0 <= rule[k] < 8})
        return out

    def read_form(self, cid):
        """The card as the form has it, or an error text."""
        card = self.project.cards[cid].copy()
        try:
            card.attack = int(self.vars["attack"].get())
            card.defense = int(self.vars["defense"].get())
            card.level = int(self.vars["level"].get())
        except ValueError:
            return "ATK, DEF and level are whole numbers"
        card.name = self.vars["name"].get()
        card.description = self.text.get("1.0", "end-1c")
        values = [parse_choice(self.vars["type"].get(), TYPE_NAMES),
                  parse_choice(self.vars["attribute"].get(), ATTRIBUTE_CHOICES),
                  parse_choice(self.vars["star1"].get(), star_choices(self.project)),
                  parse_choice(self.vars["star2"].get(), star_choices(self.project))]
        if min(values) < 0:
            return "choose a type, an attribute and two stars"
        card.type, card.attribute, card.star1, card.star2 = values
        if not card.is_monster():
            # As the disc's: no ATK, DEF, level or stars, and the magic or
            # trap attribute.
            card.attack = card.defense = card.level = card.star1 = card.star2 = 0
            card.attribute = 7 if card.type == TYPE_TRAP else 6
        card.frame = frame_value(self.vars["frame"].get())
        return card

    def apply(self, quiet=False):
        cid = self.current
        if not cid or cid not in self.project.cards:
            return True
        card = self.read_form(cid)
        if isinstance(card, str):
            self.status.configure(text=card)
            return False
        password = self.vars["password"].get().strip()
        if password and not (len(password) <= 8 and password.isdigit() and password.isascii()):
            self.status.configure(text="a password is up to 8 digits, or empty for none")
            return False
        password = password.zfill(8) if password else ""
        price_text = self.vars["starchips"].get().strip()
        price = None
        if price_text:
            if not price_text.isascii() or not price_text.isdigit() or len(price_text) > 6:
                self.status.configure(text="Starchips is a whole number from 0 to 999999, or empty for the default")
                return False
            price = int(price_text)
        price_changed = price_text != self._shown_price
        if price_changed and not isinstance(self.project.other.get("passwords", {}), dict):
            self.status.configure(text='The mod\'s "passwords" must be an object before editing Starchips')
            return False
        changed = not card.same(self.project.cards[cid])
        threshold_text = self.vars["trap_threshold"].get().strip()
        threshold_active = card.type == TYPE_TRAP and self.project.trap_threshold_default(self.chosen_effect()) is not None
        threshold_changed = threshold_active and threshold_text != self._shown_threshold
        threshold_clear = (not threshold_active and self.project.trap_threshold_override(cid) is not None and
                           (card.type != self.project.cards[cid].type or self.vars["effect"].get() != self._shown_effect))
        if threshold_changed and threshold_text and (not threshold_text.isascii() or not threshold_text.isdigit() or
                                                      len(threshold_text) > 5 or int(threshold_text) > 65535):
            self.status.configure(text="Trigger ATK is a whole number from 0 to 65535, or blank for the effect default")
            return False
        bonus_texts = tuple(self.vars[key].get().strip() for key in ("equip_attack", "equip_defense"))
        bonus_changed = card.type == TYPE_EQUIP and bonus_texts != self._shown_bonus
        bonus = []
        for text in bonus_texts if bonus_changed else ():
            points = None
            try:
                points = int(text) if text.isascii() else None
            except ValueError:
                pass
            if text and (points is None or abs(points) > EQUIP_BONUS_MAX):
                self.status.configure(text=f"ATK and DEF boosts are whole numbers from -{EQUIP_BONUS_MAX} to "
                                           f"{EQUIP_BONUS_MAX}, or empty for the default")
                return False
            bonus.append(points)
        if cid in self.project.added:
            added = self.project.added[cid]
            key = self.vars["key"].get().strip()
            if key != added.key:
                if not KEY_RE.match(key) or any(a.key == key for a in self.project.added.values()):
                    self.status.configure(text="the stable id is letters, digits, _ and -, and unique")
                    return False
                self.project.set_card_key(cid, key)
                changed = True
            if (added.drops, added.opponents) != (self.drops.get(), self.opponents.get()):
                added.drops, added.opponents = self.drops.get(), self.opponents.get()
                changed = True
        # Stored with the rest, once the form has passed every check.
        notes = self.notes.get("1.0", "end-1c")
        if notes != self.project.notes.get(cid, "") and (notes.strip() or cid in self.project.notes):
            self.project.set_notes(cid, notes)
            changed = True
        if password != self.project.password(cid):
            self.project.set_password(cid, password)
            self.vars["password"].set(password)
            changed = True
        if price_changed:
            self.project.set_starchips(cid, price)
            changed = True
        if self.store_effect(cid, card):
            changed = True
        if threshold_changed:
            self.project.set_trap_threshold(cid, int(threshold_text) if threshold_text else None)
            self._shown_threshold = threshold_text
            changed = True
        elif threshold_clear:
            self.project.set_trap_threshold(cid, None)
            self.vars["trap_threshold"].set("")
            self._shown_threshold = ""
            changed = True
        had = self.project.equip_bonus.get(cid)
        if bonus_changed:       # after the effect, which the default follows; empty: the default
            default = self.project.equip_bonus_default(cid)
            self.project.set_equip_bonus(cid, *(d if b is None else b for b, d in zip(bonus, default)))
        elif card.type != TYPE_EQUIP:
            self.project.set_equip_bonus(cid, None)
        changed = changed or self.project.equip_bonus.get(cid) != had
        self.show_bonus(cid, card.type)
        self._shown_effect = self.vars["effect"].get()
        cost = self.project.starchip_cost(cid)
        self._shown_price = "" if cost is None else str(cost)
        self.vars["starchips"].set(self._shown_price)
        if changed:
            self.project.cards[cid] = card
            self.app.changed()
            self.update_row(cid)
        problems = [i.message for i in validate.validate_card(self.project, cid)] if changed or not quiet else []
        self.status.configure(text="\n".join(problems))
        self.applied()
        return True

    def commit(self):
        return self.apply(quiet=True)

    def revert(self):
        cid = self.current
        if not cid:
            return
        self.project.revert_card(cid)
        self.app.changed()
        self.update_row(cid)
        self.show(cid)

    def add_card(self):
        base = self.current or pick_card(self, self.project, "Base of the new card", only=lambda c: c <= CARD_COUNT)
        if not base:
            return
        if not self.apply(quiet=True):
            return
        source = self.project.cards[base]
        base = self.project.base_of(base)
        cid = self.project.add_card(base)
        # The selected card as it is (an added card's own stats too); its base
        # is the disc's card under it.
        self.project.cards[cid] = source.copy(id=cid, name=source.name + " II")
        self.app.changed()
        self.filter.set(self.FILTERS[0])
        self.search.set("")
        self.fill()
        self.current = None
        self.tree.selection_set(str(cid))
        self.tree.see(str(cid))

    def remove_card(self):
        cid = self.current
        if cid not in self.project.added:
            return
        if not messagebox.askyesno("Remove card", f"Remove {self.project.card_label(cid)} and every fusion, "
                                   "equip, ritual and pool entry that names it?", parent=self):
            return
        self.project.remove_card(cid)
        self.app.changed()
        self.current = None
        self.fill()
        self.show(None)


# --- Fusions -------------------------------------------------------------------

def fusion_pairs(p):
    """({pair: what its card's own list makes}, every pair the Fusions tab lists)."""
    named = {pair for pair in p.own_fusion_pairs()[0] if pair[0] in p.cards and pair[1] in p.cards}
    # A card's own "fusions" list makes what no rule of the mod decides
    # first: the row shows what the game plays. A copy's pair its base's
    # rule decides is no row of its own (it would read "forbidden").
    removes = p.removed_results() if named else set()
    own = {pair: p.own_fusion(pair, removes) for pair in named}
    pairs = set(p.fusions) | set(p.retail.fusions) | p.fusion_explicit | \
        {pair for pair, made in own.items() if made is not None}
    return own, pairs


def labelled_card(p, text: str):
    """The card whose whole label (Project.card_label) the text is, or None."""
    head = text.split(" ", 1)[0]
    if head.isdigit() and int(head) in p.cards and p.card_label(int(head)) == text:
        return int(head)
    return None


class FusionsTab(Tab):
    LIMIT = 3000

    def __init__(self, notebook, app):
        super().__init__(notebook, app, "Fusions")
        top = ttk.Frame(self)
        top.pack(fill="x")
        ttk.Label(top, text="Card (name or #)").pack(side="left")
        self.search = tk.StringVar()
        ttk.Entry(top, textvariable=self.search, width=28).pack(side="left", padx=4)
        self.changed_only = tk.BooleanVar()
        ttk.Checkbutton(top, text="Changed only", variable=self.changed_only, command=self.fill).pack(side="left")
        self.search.trace_add("write", lambda *_: self.fill())
        self.count = ttk.Label(top)
        self.count.pack(side="right")
        # {"remove": "all"}: the disc's pairs are no fusions; they are left
        # out of the list unless asked for, so it shows what still fuses.
        self.all_banner = ttk.Frame(self)
        self.all_note = ttk.Label(self.all_banner, style="Warning.TLabel")
        self.all_note.pack(side="left")
        self.show_removed = tk.BooleanVar()
        ttk.Checkbutton(self.all_banner, text="Show the removed disc fusions", variable=self.show_removed,
                        command=self.fill).pack(side="left", padx=8)
        frame, self.tree = scrolled_tree(self, [("a", "Card A"), ("b", "Card B"), ("result", "Result"),
                                                ("state", "")], [260, 260, 260, 80], 24, selectmode="extended")
        frame.pack(fill="both", expand=True, pady=4)
        self.list_frame = frame
        self.tree.bind("<Double-1>", lambda e: self.edit())
        buttons = ttk.Frame(self)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Add fusion...", command=self.add).pack(side="left")
        ttk.Button(buttons, text="Change result...", command=self.edit).pack(side="left", padx=4)
        ttk.Button(buttons, text="Remove (no fusion)", command=self.remove).pack(side="left")
        ttk.Button(buttons, text="Remove recipes of...", command=self.remove_result).pack(side="left", padx=(4, 0))
        ttk.Button(buttons, text="Revert to retail", command=self.revert).pack(side="left", padx=4)
        ttk.Button(buttons, text="Bulk...", command=lambda: bulk_dialog.open_bulk(self)).pack(side="left")
        self.all_button = ttk.Button(buttons, text="Remove all fusions...", command=self.remove_all)
        self.all_button.pack(side="left", padx=4)
        ttk.Label(self, text="A pair fuses the same in either order. Brown rows are the retail table's "
                             "\"glitch\" fusions.", style="Hint.TLabel").pack(anchor="w", pady=(2, 0))

    def refresh(self):
        # A search still naming a whole card (after Undo, another mod) is
        # the followed one, so the tab keeps following.
        self.followed = labelled_card(self.project, self.search.get().strip())
        self.fill()

    def show_card(self, cid):
        """The fusions the card is in or makes."""
        self.followed = cid
        self.search.set(self.project.card_label(cid))

    def follow(self, cid):
        """The window's card, when it changed, unless the search is the
        modder's own."""
        followed = getattr(self, "followed", None)
        text = self.search.get().strip()
        if cid != followed and cid in self.project.cards and (not text or labelled_card(self.project, text) == followed):
            self.show_card(cid)

    def fill(self):
        if self.project is None:
            return
        self.tree.delete(*self.tree.get_children())
        p = self.project
        text = self.search.get().strip()
        own, pairs = fusion_pairs(p)
        # A card's whole label ("1 Blue-eyes White Dragon", as the right-click
        # menu and the Add dialog put it) finds that card only.
        exact = labelled_card(p, text)
        rows, hidden = [], 0
        hide = p.fusion_remove_all and not self.show_removed.get()
        for pair in pairs:
            status = "own list" if own.get(pair) is not None else p.fusion_status(pair)
            if self.changed_only.get() and status in ("", "glitch"):
                continue
            if hide and status == "removed" and not p.fusions.get(pair) and pair not in p.fusion_explicit:
                hidden += 1
                continue
            result = own.get(pair) if status == "own list" else p.fusions.get(pair) or p.retail.fusions.get(pair)
            if exact is not None:
                if exact not in (pair[0], pair[1], result):
                    continue
            elif text and not (card_matches(p, pair[0], text) or card_matches(p, pair[1], text)
                               or card_matches(p, result, text)):
                continue
            rows.append((pair, status))
        rows.sort()
        for pair, status in rows[:self.LIMIT]:
            result = p.fusions.get(pair)
            retail = p.retail.fusions.get(pair)
            if status == "own list":
                shown = f"{p.card_label(own[pair]) if own[pair] else '(none)'} (a card's own fusions list)"
            else:
                shown = p.card_label(result) if result else \
                    f"(none; retail {p.card_label(retail)})" if retail else "(none: forbidden)"
            tag = "changed" if status == "own list" else status
            self.tree.insert("", "end", iid=f"{pair[0]}:{pair[1]}", tags=(tag,) if tag else (),
                             values=(p.card_label(pair[0]), p.card_label(pair[1]), shown, status))
        more = f" (first {self.LIMIT} shown; search to narrow)" if len(rows) > self.LIMIT else ""
        self.count.configure(text=f"{len(rows)} fusions{more}")
        self.all_button.configure(text="Restore disc fusions" if p.fusion_remove_all else "Remove all fusions...")
        if p.fusion_remove_all:
            shown = "shown in red" if self.show_removed.get() else f"{hidden} hidden here"
            self.all_note.configure(text="Every disc fusion is removed: only the fusions listed here work "
                                         f"(the disc's are {shown}).")
            self.all_banner.pack(fill="x", pady=(4, 0), before=self.list_frame)
        else:
            self.all_banner.pack_forget()

    def selected(self):
        return [tuple(int(x) for x in iid.split(":")) for iid in self.tree.selection()]

    def dialog(self, title, pair=None, result=None):
        fields = {}

        def build(dialog, body):
            for i, (key, label) in enumerate((("a", "Card A"), ("b", "Card B"), ("r", "Result"))):
                ttk.Label(body, text=label).grid(row=i, column=0, sticky="w", pady=2)
                fields[key] = CardField(body, lambda: self.project, width=36)
                fields[key].grid(row=i, column=1, sticky="we", pady=2)
            if pair:
                fields["a"].set(pair[0])
                fields["b"].set(pair[1])
            if result:
                fields["r"].set(result)

        def ok(dialog):
            a, b, r = fields["a"].get(), fields["b"].get(), fields["r"].get()
            if not (a and b and r):
                return "name three cards (a number, a name, or pick one with ...)"
            if pair and self.project.pair(a, b) != pair:
                self.project.set_fusion(pair[0], pair[1], None)     # the fusion moved to other cards
            self.project.set_fusion(a, b, r)
            self.app.changed()
            self.search.set(self.project.card_label(a).split(" ", 1)[1] if " " in self.project.card_label(a) else "")
            self.fill()
            return None

        FormDialog(self, title, build, ok)

    def add(self):
        self.dialog("Add fusion")

    def edit(self):
        chosen = self.selected()
        if chosen:
            pair = chosen[0]
            self.dialog("Change fusion", pair, self.project.fusions.get(pair) or self.project.retail.fusions.get(pair))

    def remove(self):
        if not self.selected():
            return
        for pair in self.selected():
            self.project.set_fusion(pair[0], pair[1], None)
        self.app.changed()
        self.fill()

    def revert(self):
        if not self.selected():
            return
        for pair in self.selected():
            self.project.revert_fusion(pair)
        self.app.changed()
        self.fill()

    def remove_all(self):
        """{"remove": "all"} (notes/gameplay-tables.md): no fusion at all, or,
        once that is on, the disc's table back."""
        p = self.project
        if p.fusion_remove_all:
            if not messagebox.askyesno("Restore disc fusions", "Bring back every fusion of the disc's table?\n\n"
                                       "Fusions the mod adds or changes since stay as they are.", parent=self):
                return
            p.restore_disc_fusions()
        else:
            if not messagebox.askyesno("Remove all fusions", "Remove every fusion?\n\n"
                                       "No recipe on the disc makes anything any more (one \"remove\": \"all\" "
                                       "rule), the mod's own fusion rules are dropped, and the recipes an added "
                                       "card's own list makes are blocked. Fusions added afterwards still work.\n\n"
                                       "Undo, or Restore disc fusions, brings the disc's back.", parent=self):
                return
            p.remove_all_fusions()
        self.app.changed()
        self.fill()

    def remove_result(self):
        """{"remove": card} (notes/gameplay-tables.md): one rule takes away
        every disc recipe of the card; reverting one of them writes it back."""
        fields = {}
        chosen = self.selected()

        def build(dialog, body):
            ttk.Label(body, text="Result").grid(row=0, column=0, sticky="w", pady=2)
            fields["r"] = CardField(body, lambda: self.project, width=36)
            fields["r"].grid(row=0, column=1, sticky="we", pady=2)
            if chosen:
                fields["r"].set(self.project.fusions.get(chosen[0]) or self.project.retail.fusions.get(chosen[0]))
            ttk.Label(body, text="No recipe on the disc makes this card any more: one \"remove\" rule in place of\n"
                                 "a rule per pair. The mod's own fusions, and an added card's own recipes, still\n"
                                 "make it. Revert a pair to bring that recipe back.",
                      style="Hint.TLabel").grid(row=1, column=0, columnspan=2, sticky="w", pady=(6, 0))

        def ok(dialog):
            result = fields["r"].get()
            if not result:
                return "name the card (a number, a name, or pick one with ...)"
            if not self.project.retail_recipes(result):
                return f"no recipe on the disc makes {self.project.card_label(result)}"
            self.project.remove_recipes(result)
            self.app.changed()
            self.fill()
            return None

        dialog = FormDialog(self, "Remove disc recipes", build, ok)
        dialog.fields = fields
        return dialog


# --- Equips ---------------------------------------------------------------------

class EquipsTab(Tab):
    def __init__(self, notebook, app):
        super().__init__(notebook, app, "Equips")
        self.current = None
        left = ttk.Frame(self)
        left.pack(side="left", fill="y")
        ttk.Label(left, text="Equip cards").pack(anchor="w")
        frame, self.equips = scrolled_tree(left, [("id", "#"), ("name", "Equip card"), ("n", "Fits")],
                                           [50, 200, 50], 26, sort_numeric=("id", "n"))
        frame.pack(fill="y", expand=True)
        self.equips.bind("<<TreeviewSelect>>", lambda e: self.select())
        right = ttk.Frame(self)
        right.pack(side="left", fill="both", expand=True, padx=(8, 0))
        self.heading = ttk.Label(right, font=ui_font(11))
        self.heading.pack(anchor="w")
        frame, self.monsters = scrolled_tree(right, [("id", "#"), ("name", "Monster"), ("type", "Type"),
                                                     ("atk", "ATK"), ("def", "DEF"), ("state", "")],
                                                     [50, 220, 100, 50, 50, 80], 22, selectmode="extended",
                                                     sort_numeric=("id", "atk", "def"))
        frame.pack(fill="both", expand=True, pady=4)
        buttons = ttk.Frame(right)
        buttons.pack(fill="x")
        self.actions = buttons
        ttk.Button(buttons, text="Add a monster...", command=self.add).pack(side="left")
        self.type_choice = tk.StringVar(value=TYPE_NAMES[0])
        ttk.Button(buttons, text="Add every", command=lambda: self.by_type(True)).pack(side="left", padx=(8, 2))
        ttk.Combobox(buttons, textvariable=self.type_choice, values=TYPE_NAMES[:20], state="readonly",
                     width=14).pack(side="left")
        ttk.Button(buttons, text="Remove every", command=lambda: self.by_type(False)).pack(side="left", padx=2)
        ttk.Button(buttons, text="Remove selected", command=self.remove).pack(side="left", padx=(8, 0))
        ttk.Button(buttons, text="Revert to retail", command=self.revert).pack(side="left", padx=4)

    def refresh(self):
        self.current = None
        self.followed = None
        self.fill_equips()
        self.fill()

    def show_card(self, cid):
        """An equip card's targets."""
        self.followed = cid
        self.fill_equips()
        if self.equips.exists(str(cid)):
            self.equips.selection_set(str(cid))
            self.equips.see(str(cid))
            self.select()

    def follow(self, cid):
        if cid != getattr(self, "followed", None) and cid in self.project.equip_cards():
            self.show_card(cid)

    def fill_equips(self):
        if self.project is None:
            return
        self.equips.delete(*self.equips.get_children())
        p = self.project
        cards = p.equip_cards()
        for cid in cards:
            if cid not in p.cards:
                continue
            now = p.equip_targets(cid)
            changed = now != p.equip_baseline(cid)
            self.equips.insert("", "end", iid=str(cid), values=(cid, p.cards[cid].name, len(now)),
                               tags=("changed",) if changed else ())
        self.equips.sorting.apply()
        if self.current and self.equips.exists(str(self.current)):
            self.equips.selection_set(str(self.current))

    def select(self):
        selection = self.equips.selection()
        if selection and int(selection[0]) != self.current:
            self.current = int(selection[0])
            self.fill()

    def fill(self):
        self.monsters.delete(*self.monsters.get_children())
        p = self.project
        editable = p is not None and self.current in p.equip_cards()
        for action in self.actions.winfo_children():
            action.state(["!disabled"] if editable else ["disabled"])
        if not editable:
            self.current = None
            self.heading.configure(text="Select an equip card")
            return
        self.heading.configure(text=f"{p.card_label(self.current)} may equip:")
        now = p.equip_targets(self.current)
        retail = p.equip_baseline(self.current)
        for cid in sorted(now | retail):
            state = "" if cid in now and cid in retail else "added" if cid in now else "removed"
            card = p.cards.get(cid)
            if card is None:
                continue
            self.monsters.insert("", "end", iid=str(cid), values=(
                cid, card.name, type_label(card.type), card.attack, card.defense, state),
                tags=(state,) if state else ())
        self.monsters.sorting.apply()

    def edited(self):
        self.app.changed()
        self.fill()
        self.fill_equips()

    def add(self):
        if not self.current:
            return
        cid = pick_card(self, self.project, "Monster it may equip", only=lambda c: 0 <= self.project.cards[c].type < 20)
        if cid:
            self.project.equips.setdefault(self.current, self.project.equip_targets(self.current)).add(cid)
            self.edited()

    def by_type(self, allow):
        if not self.current:
            return
        t = TYPE_NAMES.index(self.type_choice.get())
        members = {cid for cid, card in self.project.cards.items() if card.type == t}
        now = self.project.equips.setdefault(self.current, self.project.equip_targets(self.current))
        if allow:
            now |= members
        else:
            now -= members
        self.edited()

    def remove(self):
        if not self.current:
            return
        now = self.project.equips.setdefault(self.current, self.project.equip_targets(self.current))
        for iid in self.monsters.selection():
            now.discard(int(iid))
        self.edited()

    def revert(self):
        if self.current:
            self.project.equips[self.current] = self.project.equip_baseline(self.current)
            self.edited()


# --- Rituals ---------------------------------------------------------------------

class RitualsTab(Tab):
    def __init__(self, notebook, app):
        super().__init__(notebook, app, "Rituals")
        frame, self.tree = scrolled_tree(self, [("ritual", "Ritual card"), ("t1", "Tribute 1"), ("t2", "Tribute 2"),
                                                ("t3", "Tribute 3"), ("result", "Summons"), ("state", "")],
                                         [210, 170, 170, 170, 200, 70], 24)
        frame.pack(fill="both", expand=True)
        self.tree.bind("<Double-1>", lambda e: self.edit())
        buttons = ttk.Frame(self)
        buttons.pack(fill="x", pady=(4, 0))
        ttk.Button(buttons, text="Edit recipe...", command=self.edit).pack(side="left")
        ttk.Button(buttons, text="Remove recipe", command=self.remove).pack(side="left", padx=4)
        ttk.Button(buttons, text="Revert to retail", command=self.revert).pack(side="left")
        ttk.Label(buttons, text="A ritual is a ritual card (an added copy has its base's recipe until given its "
                                "own); the three tributes are monsters on the field; custom recipes may use conditions.",
                  style="Hint.TLabel").pack(side="right")

    def refresh(self):
        self.fill()

    def fill(self):
        if self.project is None:
            return
        p = self.project
        self.tree.delete(*self.tree.get_children())
        for ritual in sorted(set(p.ritual_cards()) | set(p.rituals) | set(p.retail.rituals)):
            if ritual not in p.cards:
                continue
            conditional = ritual in p.ritual_requirements
            state = p.ritual_status(ritual)
            recipe = p.rituals.get(ritual) or (None, None, None, None)
            if ritual in p.added and ritual not in p.rituals and not conditional:
                # Without a recipe of its own, a copy is its base's ritual.
                recipe = p.rituals.get(p.base_of(ritual)) or recipe
                state = state or "as base"
            labels = [p.card_label(c) if c else "-" for c in recipe]
            if conditional:
                for i, req in enumerate(p.ritual_requirements[ritual]):
                    parts = []
                    if req.get("card"):
                        parts.append(p.card_label(req["card"]))
                    if req.get("type") is not None:
                        parts.append(str(req["type"]))
                    if req.get("fusion_group") is not None:
                        parts.append(f'Group: {req["fusion_group"]}')
                    if req.get("min_attack") is not None:
                        parts.append(f'ATK ≥ {req["min_attack"]}')
                    if req.get("min_defense") is not None:
                        parts.append(f'DEF ≥ {req["min_defense"]}')
                    if req.get("max_attack") is not None:
                        parts.append(f'ATK ≤ {req["max_attack"]}')
                    if req.get("max_defense") is not None:
                        parts.append(f'DEF ≤ {req["max_defense"]}')
                    if req.get("min_level") is not None:
                        parts.append(f'Level ≥ {req["min_level"]}')
                    if req.get("max_level") is not None:
                        parts.append(f'Level ≤ {req["max_level"]}')
                    if req.get("defense_gt_attack"):
                        parts.append("DEF > ATK")
                    labels[i] = " & ".join(parts) or "-"
            self.tree.insert("", "end", iid=str(ritual), values=[p.card_label(ritual)] + labels + [state],
                             tags=(state,) if state else ())

    def selected(self):
        selection = self.tree.selection()
        return int(selection[0]) if selection else None

    def show_card(self, cid):
        if self.tree.exists(str(cid)):
            self.tree.selection_set(str(cid))
            self.tree.see(str(cid))

    def edit(self):
        ritual = self.selected()
        if not ritual:
            return
        p = self.project
        recipe = (p.rituals.get(ritual) or p.retail.rituals.get(ritual) or p.rituals.get(p.base_of(ritual))
                  or (0, 0, 0, 0))      # an added copy starts from its base's
        saved = p.ritual_requirements.get(ritual)
        requirements = [dict(r) for r in saved] if saved else [{"card": recipe[i]} if recipe[i] else {} for i in range(3)]

        dialog = tk.Toplevel(self)
        dialog.title("Ritual recipe")
        dialog.transient(self)
        dialog.resizable(True, False)
        dialog.minsize(px(dialog, 620), 0)
        grab(dialog)
        dialog.bind("<Escape>", lambda e: dialog.destroy())
        dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
        body = ttk.Frame(dialog, padding=12)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text=self.project.card_label(ritual), font=ui_font(10)).pack(
            anchor="w", pady=(0, 8))

        panels = []
        numeric_inputs = [dict(), dict(), dict()]
        card_inputs = [None, None, None]   # a Specific Card's text, read on Save
        open_index = tk.IntVar(value=0)

        def describe(req):
            parts = []
            if req.get("card"):
                parts.append("Specific Card")
            if req.get("type") is not None:
                parts.append("Monster Type")
            if req.get("fusion_group") is not None:
                parts.append("Fusion Group")
            if req.get("min_attack") is not None:
                parts.append("Minimum ATK")
            if req.get("min_defense") is not None:
                parts.append("Minimum DEF")
            if req.get("max_attack") is not None:
                parts.append("Maximum ATK")
            if req.get("max_defense") is not None:
                parts.append("Maximum DEF")
            if req.get("min_level") is not None:
                parts.append("Minimum Level")
            if req.get("max_level") is not None:
                parts.append("Maximum Level")
            if req.get("defense_gt_attack"):
                parts.append("DEF > ATK")
            return parts

        def render(index):
            panel = panels[index][1]
            for child in panel.winfo_children():
                child.destroy()
            req = requirements[index]
            kinds = describe(req)
            for kind in kinds:
                row = ttk.Frame(panel)
                row.pack(fill="x", pady=2)
                ttk.Label(row, text=kind, width=18).pack(side="left")
                if kind == "Specific Card":
                    field = CardField(row, lambda: self.project, width=36,
                                      only=lambda c: 0 <= self.project.cards[c].type < 20)
                    field.pack(side="left", fill="x", expand=True)
                    # Typed text survives a redraw, as the numbers' does.
                    if card_inputs[index] is not None:
                        field.var.set(card_inputs[index].get())
                    else:
                        field.set(req["card"])
                    card_inputs[index] = field.var
                elif kind == "Monster Type":
                    value = tk.StringVar(value=req["type"])
                    combo = ttk.Combobox(row, textvariable=value, values=TYPE_NAMES[:20], state="readonly", width=22)
                    combo.pack(side="left")
                    combo.bind("<<ComboboxSelected>>", lambda e, v=value, r=req: r.__setitem__("type", v.get()))
                elif kind == "Fusion Group":
                    value = tk.StringVar(value=req["fusion_group"])
                    combo = ttk.Combobox(row, textvariable=value, values=FUSION_GROUPS, state="readonly", width=22)
                    combo.pack(side="left")
                    combo.bind("<<ComboboxSelected>>",
                               lambda e, v=value, r=req: r.__setitem__("fusion_group", v.get()))
                elif kind in ("Minimum ATK", "Minimum DEF", "Maximum ATK", "Maximum DEF", "Minimum Level", "Maximum Level"):
                    if kind == "Minimum ATK":
                        key, limit = "min_attack", 9999
                    elif kind == "Minimum DEF":
                        key, limit = "min_defense", 9999
                    elif kind == "Maximum ATK":
                        key, limit = "max_attack", 9999
                    elif kind == "Maximum DEF":
                        key, limit = "max_defense", 9999
                    elif kind == "Minimum Level":
                        key, limit = "min_level", 12
                    else:
                        key, limit = "max_level", 12
                    # Keep pending edits when changing panels or adding another
                    # condition rebuilds the widgets. Save validates the text.
                    previous = numeric_inputs[index].get(key)
                    value = previous[0] if previous else tk.StringVar(value=str(req[key]))
                    entry = ttk.Entry(row, textvariable=value, width=10)
                    entry.pack(side="left")
                    numeric_inputs[index][key] = (value, limit)
                else:
                    ttk.Label(row, text="Required").pack(side="left")
                def delete(k=kind, r=req, n=index):
                    keys = {"Specific Card": "card", "Monster Type": "type", "Fusion Group": "fusion_group",
                            "Minimum ATK": "min_attack", "Minimum DEF": "min_defense",
                            "Maximum ATK": "max_attack", "Maximum DEF": "max_defense",
                            "Minimum Level": "min_level", "Maximum Level": "max_level",
                            "DEF > ATK": "defense_gt_attack"}
                    if len(describe(r)) <= 1:
                        return
                    r.pop(keys[k], None)
                    numeric_inputs[n].pop(keys[k], None)
                    if keys[k] == "card":
                        card_inputs[n] = None
                    render(n)
                ttk.Button(row, text="Remove", command=delete,
                           state="normal" if len(kinds) > 1 else "disabled").pack(side="right", padx=(6, 0))
            ttk.Button(panel, text="+ Add requirement", command=lambda n=index: add_requirement(n)).pack(
                anchor="w", pady=(6, 0))

        def add_requirement(index):
            req = requirements[index]
            menu = tk.Menu(dialog, tearoff=False)
            choices = [("Specific Card", "card"), ("Monster Type", "type"), ("Fusion Group", "fusion_group"),
                       ("Minimum ATK", "min_attack"), ("Minimum DEF", "min_defense"),
                       ("Maximum ATK", "max_attack"), ("Maximum DEF", "max_defense"),
                       ("Minimum Level", "min_level"), ("Maximum Level", "max_level"),
                       ("DEF > ATK", "defense_gt_attack")]
            def add(key):
                if key in req:
                    return
                if key == "card":
                    cid = pick_card(dialog, self.project, "Specific ritual tribute",
                                    only=lambda c: 0 <= self.project.cards[c].type < 20)
                    if not cid: return
                    req[key] = cid
                elif key == "type":
                    req[key] = TYPE_NAMES[0]
                elif key == "fusion_group":
                    req[key] = "Elf"
                elif key in ("min_attack", "min_defense", "max_attack", "max_defense"):
                    req[key] = 1000
                elif key == "min_level":
                    req[key] = 1
                elif key == "max_level":
                    req[key] = 12
                else:
                    req[key] = True
                render(index)
            for label, key in choices:
                menu.add_command(label=label, state="disabled" if key in req else "normal",
                                 command=lambda k=key: add(k))
            widget = panels[index][1].winfo_children()[-1]
            menu.tk_popup(widget.winfo_rootx(), widget.winfo_rooty() + widget.winfo_height())

        def show_panel(index):
            open_index.set(index)
            for i, (button, panel) in enumerate(panels):
                button.configure(text=("▼ " if i == index else "▶ ") + f"TRIBUTE {i + 1}")
                if i == index:
                    panel.pack(fill="x", padx=(18, 0), pady=(2, 8))
                    render(i)
                else:
                    panel.pack_forget()

        for i in range(3):
            section = ttk.Frame(body)
            section.pack(fill="x")
            header = ttk.Button(section, command=lambda n=i: show_panel(n))
            header.pack(fill="x")
            panel = ttk.Frame(section, padding=(4, 4))
            panels.append((header, panel))
        show_panel(0)

        ttk.Separator(body).pack(fill="x", pady=(4, 8))
        summon = ttk.Frame(body)
        summon.pack(fill="x")
        ttk.Label(summon, text="Summons", width=18).pack(side="left")
        result = CardField(summon, lambda: self.project, width=38, only=lambda c: 0 <= self.project.cards[c].type < 20)
        result.pack(side="left", fill="x", expand=True)
        if recipe[3]:
            result.set(recipe[3])
        error = ttk.Label(body, style="Error.TLabel")
        error.pack(fill="x", pady=(6, 0))
        buttons = ttk.Frame(body)
        buttons.pack(fill="x", pady=(8, 0))

        def fail(index, text):
            error.configure(text=f"Tribute {index + 1}: {text}")
            show_panel(index)

        def save():
            for index, req in enumerate(requirements):
                if "card" in req and card_inputs[index] is not None:
                    text = card_inputs[index].get().strip()
                    cid = card_named(self.project, text)
                    if text and not cid:
                        return fail(index, f"no card \"{text}\".")
                    if cid:
                        req["card"] = cid
                    else:
                        req.pop("card")
                for key, (value, limit) in numeric_inputs[index].items():
                    try:
                        number = int(value.get())
                    except ValueError:
                        return fail(index, "ATK, DEF and Level requirements must be whole numbers.")
                    if not 0 <= number <= limit:
                        return fail(index, f"{key.replace('_', ' ').title()} must be between 0 and {limit}.")
                    req[key] = number
            result_id = result.get()
            for index, req in enumerate(requirements):
                for low, high, what in (("min_attack", "max_attack", "ATK"), ("min_defense", "max_defense", "DEF"),
                                        ("min_level", "max_level", "Level")):
                    if req.get(low) is not None and req.get(high) is not None and req[low] > req[high]:
                        return fail(index, f"Minimum {what} cannot be greater than Maximum {what}.")
                if not req:
                    return fail(index, "needs at least one requirement.")
            if not result_id:
                error.configure(text="Summons must name a monster.")
                return
            display = [req.get("card", 0) for req in requirements]
            self.project.rituals[ritual] = tuple(display + [result_id])
            traditional = all(set(req) == {"card"} for req in requirements)
            if traditional:
                self.project.ritual_requirements.pop(ritual, None)
            else:
                self.project.ritual_requirements[ritual] = [dict(req) for req in requirements]
            self.app.changed()
            self.fill()
            dialog.destroy()

        ttk.Button(buttons, text="Save", command=save).pack(side="right")
        ttk.Button(buttons, text="Cancel", command=dialog.destroy).pack(side="right", padx=4)
        dialog.bind("<Control-s>", lambda e: save())

    def remove(self):
        ritual = self.selected()
        if ritual:
            self.project.rituals.pop(ritual, None)
            self.project.ritual_requirements.pop(ritual, None)
            self.app.changed()
            self.fill()

    def revert(self):
        ritual = self.selected()
        if ritual:
            self.project.revert_ritual(ritual)
            self.app.changed()
            self.fill()


# --- Duelists ---------------------------------------------------------------------

class DuelistsTab(Tab):
    def __init__(self, notebook, app):
        super().__init__(notebook, app, "Duelists")
        self.duelist = 1
        left = ttk.Frame(self)
        left.pack(side="left", fill="y")
        frame, self.list = scrolled_tree(left, [("id", "#"), ("name", "Opponent"), ("state", "")],
                                         [36, 170, 60], 26, sort_numeric=("id",))
        frame.pack(fill="y", expand=True)
        self.list.bind("<<TreeviewSelect>>", lambda e: self.select())
        right = ttk.Frame(self)
        right.pack(side="left", fill="both", expand=True, padx=(8, 0))
        top = ttk.Frame(right)
        top.pack(fill="x")
        self.pool = tk.StringVar(value="deck")
        for pool in POOLS:
            ttk.Radiobutton(top, text=POOL_LABELS[pool], value=pool, variable=self.pool,
                            command=self.fill).pack(side="left", padx=(0, 8))
        self.total = ttk.Label(top, font=ui_font(10))
        self.total.pack(side="right")
        frame, self.tree = scrolled_tree(right, [("id", "#"), ("name", "Card"), ("type", "Type"),
                                                 ("atk", "ATK"), ("def", "DEF"), ("w", "Weight"),
                                                 ("pct", "Chance"), ("retail", "Retail"), ("state", "")],
                                         [50, 220, 100, 50, 50, 60, 60, 60, 70], 22, selectmode="extended",
                                         sort_numeric=("id", "atk", "def", "w", "pct", "retail"))
        frame.pack(fill="both", expand=True, pady=4)
        self.tree.bind("<<TreeviewSelect>>", lambda e: self.pick_row())
        edit = ttk.Frame(right)
        edit.pack(fill="x")
        self.fixed = FixedDeckView(self, right, top)     # the deck pool may be forty cards written down
        ttk.Button(edit, text="Add a card...", command=self.add).pack(side="left")
        ttk.Label(edit, text="Weight").pack(side="left", padx=(10, 2))
        self.weight = tk.StringVar()
        entry = ttk.Entry(edit, textvariable=self.weight, width=7)
        entry.pack(side="left")
        entry.bind("<Return>", lambda e: self.set_weight())
        ttk.Button(edit, text="Set", command=self.set_weight).pack(side="left", padx=2)
        ttk.Button(edit, text="Remove selected", command=self.remove).pack(side="left", padx=(8, 0))
        ttk.Button(edit, text="Normalize to 2048", command=self.normalize).pack(side="left", padx=4)
        ttk.Button(edit, text="Revert pool", command=self.revert).pack(side="left")
        ttk.Label(right, text="Weights are chances out of 2048. A deck is 40 cards dealt from at least 14; "
                              "a drop pool needs one card left.", style="Hint.TLabel").pack(anchor="w", pady=(4, 0))

    def refresh(self):
        self.fill_list()
        self.fill()

    def fill_list(self):
        if self.project is None:
            return
        self.list.delete(*self.list.get_children())
        for d, name in enumerate(DUELIST_NAMES[:len(self.project.pools)]):
            changed = any({c: w for c, w in self.project.pools[d][p].items() if w} != self.project.retail.pools[d][p]
                          for p in POOLS)
            state = "fixed" if fixed_decks.deck_of(self.project, d) else "changed" if changed else ""
            self.list.insert("", "end", iid=str(d), values=(d, name, state), tags=("changed",) if state else ())
        self.list.sorting.apply()
        if self.list.exists(str(self.duelist)):
            self.list.selection_set(str(self.duelist))

    def select(self):
        selection = self.list.selection()
        if selection:
            self.duelist = int(selection[0])
            self.fill()

    def current_pool(self):
        return self.project.pools[self.duelist][self.pool.get()]

    def fill(self):
        if self.project is None or self.fixed.fill():
            return
        p = self.project
        self.tree.delete(*self.tree.get_children())
        pool = self.current_pool()
        retail = p.retail.pools[self.duelist][self.pool.get()]
        for cid in sorted(set(pool) | set(retail), key=lambda c: (-pool.get(c, 0), c)):
            weight, before = pool.get(cid, 0), retail.get(cid, 0)
            if not weight and not before:
                continue
            state = "" if weight == before else "added" if not before else "removed" if not weight else "changed"
            card = p.cards.get(cid)
            self.tree.insert("", "end", iid=str(cid), tags=(state,) if state else (), values=(
                cid, card.name if card else "?", type_label(card.type) if card else "",
                card.attack if card else "", card.defense if card else "", weight,
                f"{weight * 100 / POOL_TOTAL:.2f}%", before, state))
        self.tree.sorting.apply()
        total = sum(pool.values())
        cards = sum(1 for w in pool.values() if w)
        self.total.configure(text=f"{DUELIST_NAMES[self.duelist]}: {cards} cards, total {total} / {POOL_TOTAL}",
                             style="Ok.TLabel" if total == POOL_TOTAL else "Error.TLabel")

    def pick_row(self):
        selection = self.tree.selection()
        if len(selection) == 1:
            self.weight.set(str(self.current_pool().get(int(selection[0]), 0)))

    def edited(self):
        pool = self.current_pool()
        for cid in [c for c, w in pool.items() if not w]:
            del pool[cid]
        self.app.changed()
        self.fill()
        self.fill_list()

    def add(self):
        cid = pick_card(self, self.project, "Card to add to the pool")
        if not cid:
            return
        try:
            weight = int(self.weight.get() or "0")
        except ValueError:
            weight = 0
        self.current_pool()[cid] = weight if weight > 0 else 1
        self.edited()
        if self.tree.exists(str(cid)):
            self.tree.selection_set(str(cid))
            self.tree.see(str(cid))

    def set_weight(self):
        try:
            weight = int(self.weight.get())
        except ValueError:
            messagebox.showerror("Weight", "A weight is a whole number, 0 or more.", parent=self)
            return
        if weight < 0 or weight > 0xFFFF:
            messagebox.showerror("Weight", "A weight is 0 to 65535 (out of 2048).", parent=self)
            return
        pool = self.current_pool()
        chosen = [int(i) for i in self.tree.selection()]
        for cid in chosen:
            pool[cid] = weight
        self.edited()
        for cid in chosen:
            if self.tree.exists(str(cid)):
                self.tree.selection_add(str(cid))

    def remove(self):
        pool = self.current_pool()
        for iid in self.tree.selection():
            pool.pop(int(iid), None)
        self.edited()

    def normalize(self):
        self.project.pools[self.duelist][self.pool.get()] = poolmath.normalize(self.current_pool())
        self.edited()

    def revert(self):
        self.project.revert_pool(self.duelist, self.pool.get())
        self.edited()

    def goto(self, target):
        d, pool = target
        self.duelist = d
        self.pool.set(pool)
        self.fill_list()
        self.list.see(str(d))
        self.fill()


# --- Starter decks ---------------------------------------------------------------

class StarterTab(Tab):
    """The decks a new game may be dealt in place of the disc's weighted
    pools ("starter", notes/starter-deck.md). The disc has none of these, so
    every deck here is the mod's own: the list is what it offers, and one of
    them is picked for each new game, by their weights."""

    def __init__(self, notebook, app):
        super().__init__(notebook, app, "Starter decks")
        self.deck = 0
        left = ttk.Frame(self)
        left.pack(side="left", fill="y")
        frame, self.list = scrolled_tree(left, [("n", "#"), ("name", "Deck"), ("w", "Weight"), ("cards", "Cards")],
                                         [30, 150, 55, 60], 22)
        frame.pack(fill="y", expand=True)
        self.list.bind("<<TreeviewSelect>>", lambda e: self.select())
        buttons = ttk.Frame(left)
        buttons.pack(fill="x", pady=(4, 0))
        ttk.Button(buttons, text="Add deck", command=self.add_deck).pack(side="left")
        ttk.Button(buttons, text="Edit...", command=self.edit_deck).pack(side="left", padx=2)
        ttk.Button(buttons, text="Remove", command=self.remove_deck).pack(side="left")
        right = ttk.Frame(self)
        right.pack(side="left", fill="both", expand=True, padx=(8, 0))
        top = ttk.Frame(right)
        top.pack(fill="x")
        self.title = ttk.Label(top, font=ui_font(10))
        self.title.pack(side="left")
        self.total = ttk.Label(top, font=ui_font(10))
        self.total.pack(side="right")
        frame, self.tree = scrolled_tree(right, [("id", "#"), ("name", "Card"), ("type", "Type"),
                                                 ("copies", "Copies"), ("state", "")],
                                         [50, 260, 110, 60, 150], 20, selectmode="extended")
        frame.pack(fill="both", expand=True, pady=4)
        self.tree.bind("<<TreeviewSelect>>", lambda e: self.pick_row())
        edit = ttk.Frame(right)
        edit.pack(fill="x")
        ttk.Button(edit, text="Add a card...", command=self.add_card).pack(side="left")
        ttk.Label(edit, text="Copies").pack(side="left", padx=(10, 2))
        self.copies = tk.StringVar()
        entry = ttk.Entry(edit, textvariable=self.copies, width=5)
        entry.pack(side="left")
        entry.bind("<Return>", lambda e: self.set_copies())
        ttk.Button(edit, text="Set", command=self.set_copies).pack(side="left", padx=2)
        ttk.Button(edit, text="Remove selected", command=self.remove_card).pack(side="left", padx=(8, 0))
        ttk.Label(right, text=f"A deck is exactly {DECK_SIZE} cards written down, so it may hold a card the mod "
                              f"adds. More than {DECK_COPY_LIMIT} copies, or more than one Exodia piece, is dealt "
                              "as written but Build Deck will not take it back.",
                  style="Hint.TLabel", wraplength=px(self, 520), justify="left").pack(anchor="w", pady=(4, 0))

    # --- the list ----------------------------------------------------------

    def decks(self):
        return self.project.starter if self.project else []

    def current(self):
        decks = self.decks()
        return decks[self.deck] if 0 <= self.deck < len(decks) else None

    def refresh(self):
        self.fill_list()
        self.fill()

    def fill_list(self):
        if self.project is None:
            return
        self.list.delete(*self.list.get_children())
        for i, deck in enumerate(self.decks()):
            self.list.insert("", "end", iid=str(i), tags=() if deck.complete() else ("error",),
                             values=(i + 1, deck.name or "(unnamed)", deck.weight, f"{deck.total()}/{DECK_SIZE}"))
        if self.decks():
            self.deck = min(self.deck, len(self.decks()) - 1)
            if self.list.exists(str(self.deck)):
                self.list.selection_set(str(self.deck))

    def select(self):
        selection = self.list.selection()
        if selection:
            self.deck = int(selection[0])
            self.fill()

    def fill(self):
        if self.project is None:
            return
        deck = self.current()
        self.tree.delete(*self.tree.get_children())
        if deck is None:
            self.title.configure(text="No starter deck")
            self.total.configure(text="", style="TLabel")
            return
        p = self.project
        for cid in sorted(deck.cards):
            copies = deck.cards[cid]
            card = p.cards.get(cid)
            notes = []
            if copies > DECK_COPY_LIMIT:
                notes.append(f"over {DECK_COPY_LIMIT}")
            if exodia_piece(cid) and copies > 1:
                notes.append("Exodia piece")
            self.tree.insert("", "end", iid=str(cid), tags=("warning",) if notes else (), values=(
                cid, card.name if card else "?", type_label(card.type) if card else "", copies, ", ".join(notes)))
        # A card the editor could not place keeps its place in the deck, and
        # its row, so its copies are not quietly lost.
        for name, copies in deck.kept.items():
            self.tree.insert("", "end", iid=f"kept:{name}", tags=("removed",),
                             values=("", name, "", copies, "no such card; kept as written"))
        self.title.configure(text=deck.name or "(unnamed)")
        total = deck.total()
        self.total.configure(text=f"{total} / {DECK_SIZE} cards",
                             style="Ok.TLabel" if total == DECK_SIZE else "Error.TLabel")

    def pick_row(self):
        selection = self.tree.selection()
        deck = self.current()
        if len(selection) == 1 and deck and not selection[0].startswith("kept:"):
            self.copies.set(str(deck.cards.get(int(selection[0]), 0)))

    def edited(self):
        deck = self.current()
        if deck:
            for cid in [c for c, n in deck.cards.items() if not n]:
                del deck.cards[cid]
        self.app.changed()
        self.fill()
        self.fill_list()

    # --- decks -------------------------------------------------------------

    def deck_dialog(self, title, deck):
        fields = {}

        def build(dialog, body):
            ttk.Label(body, text="Name").grid(row=0, column=0, sticky="w", pady=2)
            fields["name"] = tk.StringVar(value=deck.name)
            ttk.Entry(body, textvariable=fields["name"], width=32).grid(row=0, column=1, sticky="we", pady=2)
            ttk.Label(body, text="Weight").grid(row=1, column=0, sticky="w", pady=2)
            fields["weight"] = tk.StringVar(value=str(deck.weight))
            ttk.Entry(body, textvariable=fields["weight"], width=10).grid(row=1, column=1, sticky="w", pady=2)
            ttk.Label(body, text=f"How often this deck is the one picked, against the other decks\n"
                                 f"offered. 0 is a deck that is kept but never picked.",
                      style="Hint.TLabel").grid(row=2, column=0, columnspan=2, sticky="w", pady=(6, 0))

        def ok(dialog):
            text = fields["weight"].get().strip()
            if not text.isdigit() or int(text) > STARTER_WEIGHT_LIMIT:
                return f"a weight is a whole number, 0 to {STARTER_WEIGHT_LIMIT}"
            deck.name = fields["name"].get().strip()
            deck.weight = int(text)
            self.app.changed()
            self.fill()
            self.fill_list()
            return None

        FormDialog(self, title, build, ok)

    def add_deck(self):
        if self.project is None:
            return
        deck = StarterDeck(name=f"Deck {len(self.decks()) + 1}")
        self.project.starter.append(deck)
        self.deck = len(self.decks()) - 1
        self.edited()
        if self.list.exists(str(self.deck)):
            self.list.selection_set(str(self.deck))
        self.deck_dialog("Add starter deck", deck)

    def edit_deck(self):
        deck = self.current()
        if deck:
            self.deck_dialog("Starter deck", deck)

    def remove_deck(self):
        deck = self.current()
        if deck is None:
            return
        if not messagebox.askyesno("Remove deck", f"Remove {deck.name or 'this deck'} and its "
                                                  f"{deck.total()} cards?", parent=self):
            return
        self.project.starter.pop(self.deck)
        self.deck = max(0, self.deck - 1)
        self.edited()

    # --- cards -------------------------------------------------------------

    def add_card(self):
        deck = self.current()
        if deck is None:
            messagebox.showinfo("Starter decks", "Add a deck first.", parent=self)
            return
        cid = pick_card(self, self.project, "Card to add to the deck")
        if not cid:
            return
        try:
            copies = int(self.copies.get() or "0")
        except ValueError:
            copies = 0
        deck.cards[cid] = copies if 0 < copies <= DECK_SIZE else 1
        self.edited()
        if self.tree.exists(str(cid)):
            self.tree.selection_set(str(cid))
            self.tree.see(str(cid))

    def set_copies(self):
        deck = self.current()
        if deck is None:
            return
        try:
            copies = int(self.copies.get())
        except ValueError:
            messagebox.showerror("Copies", "Copies are a whole number.", parent=self)
            return
        if not 0 <= copies <= DECK_SIZE:
            messagebox.showerror("Copies", f"A card's copies are 0 to {DECK_SIZE}.", parent=self)
            return
        chosen = [i for i in self.tree.selection() if not i.startswith("kept:")]
        for iid in chosen:
            deck.cards[int(iid)] = copies
        self.edited()
        for iid in chosen:
            if self.tree.exists(iid):
                self.tree.selection_add(iid)

    def remove_card(self):
        deck = self.current()
        if deck is None:
            return
        for iid in self.tree.selection():
            if iid.startswith("kept:"):
                deck.kept.pop(iid[5:], None)
            else:
                deck.cards.pop(int(iid), None)
        self.edited()

    def goto(self, target):
        self.deck = target if isinstance(target, int) else 0
        self.fill_list()
        if self.list.exists(str(self.deck)):
            self.list.see(str(self.deck))
        self.fill()


# --- Mod info -------------------------------------------------------------------

class ModInfoTab(Tab):
    def __init__(self, notebook, app):
        super().__init__(notebook, app, "Mod info")
        form = ttk.Frame(self)
        form.pack(fill="x")
        self.vars = {k: tk.StringVar() for k in ("id", "name", "version", "author")}
        labels = {"id": "Id (letters, digits, - and _)", "name": "Name", "version": "Version", "author": "Author"}
        for row, key in enumerate(self.vars):
            ttk.Label(form, text=labels[key]).grid(row=row, column=0, sticky="w", pady=2)
            entry = ttk.Entry(form, textvariable=self.vars[key], width=50)
            entry.grid(row=row, column=1, sticky="w", pady=2)
            entry.bind("<FocusOut>", lambda e: self.commit())
        ttk.Label(form, text="Description").grid(row=4, column=0, sticky="nw", pady=2)
        self.description = tk.Text(form, width=70, height=4, wrap="word")
        self.description.grid(row=4, column=1, sticky="w", pady=2)
        self.folder = ttk.Label(form, style="Hint.TLabel")
        self.folder.grid(row=5, column=1, sticky="w")
        boxes = ttk.Frame(self)
        boxes.pack(fill="both", expand=True, pady=(8, 0))
        left = ttk.LabelFrame(boxes, text="Settings (JSON list; see notes/modding.md)", padding=4)
        left.pack(side="left", fill="both", expand=True)
        self.settings = tk.Text(left, width=50, height=14, wrap="none", font=fixed_font())
        self.settings.pack(fill="both", expand=True)
        right = ttk.LabelFrame(boxes, text="Other mod.json keys, kept as written (data, text, textures, audio, "
                                           "requires...)", padding=4)
        right.pack(side="left", fill="both", expand=True, padx=(8, 0))
        self.other = tk.Text(right, width=60, height=14, wrap="none", font=fixed_font())
        self.other.pack(fill="both", expand=True)
        self.status = ttk.Label(self, style="Error.TLabel")
        self.status.pack(anchor="w")
        buttons = ttk.Frame(self)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Apply", command=self.commit).pack(side="left")
        ttk.Button(buttons, text="Preview mod.json", command=self.preview).pack(side="left", padx=4)

    def refresh(self):
        if self.project is None:
            return
        info = self.project.info
        for key, var in self.vars.items():
            var.set(getattr(info, key))
        for box, value in ((self.description, info.description),
                           (self.settings, json.dumps(info.settings, indent=2, ensure_ascii=False) if info.settings else ""),
                           (self.other, json.dumps(self.shown_other(), indent=2, ensure_ascii=False)
                            if self.shown_other() else "")):
            box.delete("1.0", "end")
            box.insert("1.0", value)
        source = self.project.source_dir
        self.folder.configure(text=f"Folder: {source}" if source else "Not saved yet")
        self.status.configure(text="")

    def commit(self):
        if self.project is None:
            return True
        info = self.project.info
        before = (info.id, info.name, info.version, info.author, info.description, info.settings, self.project.other)
        try:
            settings_text = self.settings.get("1.0", "end").strip()
            settings = json.loads(settings_text) if settings_text else []
            if not isinstance(settings, list):
                raise ValueError("settings is a JSON list")
            other_text = self.other.get("1.0", "end").strip()
            other = json.loads(other_text) if other_text else {}
            if not isinstance(other, dict):
                raise ValueError("the other keys are a JSON object")
            reserved = set(other) & {"id", "name", "version", "author", "description", "settings", "cards",
                                     "fusions", "equips", "rituals", "drops", "decks", "limits", "guardian_stars"}
            if reserved:
                raise ValueError(f"edit {', '.join(sorted(reserved))} in the editor's own tabs")
        except ValueError as problem:
            self.status.configure(text=f"Not applied: {problem}")
            return False
        info.id = self.vars["id"].get().strip()
        info.name = self.vars["name"].get()
        info.version = self.vars["version"].get().strip()
        info.author = self.vars["author"].get()
        info.description = self.description.get("1.0", "end-1c")
        info.settings = settings
        # "limits" is the Limits tab's (limits_tab.py), "guardian_stars" the
        # Guardian Stars tab's (guardian_stars_tab.py), not this box's.
        for key in ("limits", "guardian_stars"):
            if key in self.project.other:
                other[key] = self.project.other[key]
        self.project.other = other
        self.status.configure(text="")
        after = (info.id, info.name, info.version, info.author, info.description, info.settings, self.project.other)
        if after != before:
            self.app.changed()
        self.applied()
        return True

    def shown_other(self) -> dict:
        """The other keys this box shows: all but the Limits and Guardian Stars tabs'."""
        return {key: value for key, value in self.project.other.items() if key not in ("limits", "guardian_stars")}

    def preview(self):
        if self.app.commit_all():
            show_text(self, "mod.json preview", manifest.dumps(manifest.build(self.project)))


# --- Conflicts ------------------------------------------------------------------

class ConflictsTab(Tab):
    def __init__(self, notebook, app):
        super().__init__(notebook, app, "Conflicts")
        top = ttk.Frame(self)
        top.pack(fill="x")
        ttk.Button(top, text="Check now", command=self.run).pack(side="left")
        self.summary = ttk.Label(top)
        self.summary.pack(side="left", padx=8)
        ttk.Label(top, text="Double-click a line to go to it.", style="Hint.TLabel").pack(side="right")
        # The other installed mods this one is checked against (validate.cross_mod):
        # the player's mods folder, or one chosen here (kept in the editor's settings).
        other = ttk.Frame(self)
        other.pack(fill="x", pady=(4, 0))
        ttk.Button(other, text="Other mods folder...", command=self.choose_folder).pack(side="left")
        ttk.Button(other, text="Player's folder", command=lambda: self.set_folder(None)).pack(side="left", padx=4)
        self.others = ttk.Label(other, style="Hint.TLabel", wraplength=900, justify="left")
        self.others.pack(side="left", padx=8, fill="x", expand=True)
        from . import settings
        self.other_folder = settings.load().get("other_mods")
        frame, self.tree = scrolled_tree(self, [("level", "Level"), ("area", "Where"), ("what", "What"),
                                                ("message", "Conflict")], [70, 90, 260, 560], 26)
        frame.pack(fill="both", expand=True, pady=4)
        self.tree.bind("<Double-1>", lambda e: self.go())
        self.issues = []

    def choose_folder(self):
        from tkinter import filedialog
        folder = filedialog.askdirectory(parent=self, title="A folder of mods to check this one against",
                                         initialdir=self.other_folder or str(self.app.mods_dir()))
        if folder:
            self.set_folder(folder)

    def set_folder(self, folder):
        from . import settings
        self.other_folder = folder
        settings.save("other_mods", folder)
        self.run()

    def refresh(self):
        self.run()

    def run(self):
        if self.project is None:
            return []
        self.app.commit_all()
        self.issues = validate.validate(self.project)
        try:
            from pathlib import Path
            folders = [Path(self.other_folder)] if self.other_folder else None
            others, said = validate.cross_mod(self.project, folders)
        except Exception as problem:   # noqa: BLE001 -- never let another mod stop this one opening
            others, said = [], f"The other mods could not be checked: {type(problem).__name__}: {problem}"
        self.issues += others
        self.others.configure(text=said)
        self.tree.delete(*self.tree.get_children())
        for i, issue in enumerate(self.issues):
            self.tree.insert("", "end", iid=str(i), values=(issue.level, issue.area, issue.where, issue.message),
                             tags=(issue.level,))
        errors = len(validate.errors(self.issues))
        notes = sum(1 for issue in self.issues if issue.level == "note")
        self.summary.configure(text=f"{errors} errors, {len(self.issues) - errors - notes} warnings, {notes} notes",
                               style="Error.TLabel" if errors else "Ok.TLabel")
        return self.issues

    def go(self):
        selection = self.tree.selection()
        if selection:
            self.app.go_to(self.issues[int(selection[0])])
