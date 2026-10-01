"""The Limits tab: a mod's "limits" (limits.py, notes/gameplay-tables.md): the
numbers the game caps. The simple part is what most mods change (the ATK and
DEF cap, the LP a duel starts with, how far healing goes); the advanced part
has every other limit and each duelist's own LP. An empty field is the game's
own number."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from . import limits
from .gamedata import DUELIST_NAMES
from .tabs import Tab


class LimitsTab(Tab):
    def __init__(self, notebook, app):
        super().__init__(notebook, app, "Limits")
        ttk.Label(self, style="Hint.TLabel", wraplength=900, justify="left",
                  text="The numbers the game caps. Leave a field empty for the game's own number (in brackets). "
                       "ATK, DEF and LP are kept in 16 bits, so 32767 is as high as they go; the duel's numbers "
                       "take a fifth digit past 9999.").pack(anchor="w", pady=(0, 6))
        self.vars = {}
        simple = ttk.LabelFrame(self, text="Limits", padding=6)
        simple.pack(fill="x")
        self._fields(simple, limits.FIELDS)
        self.advanced_shown = tk.BooleanVar(self, value=False)
        ttk.Checkbutton(self, text="Show advanced", variable=self.advanced_shown,
                        command=self._show_advanced).pack(anchor="w", pady=(6, 0))
        self.advanced = ttk.Frame(self)
        numbers = ttk.LabelFrame(self.advanced, text="Advanced", padding=6)
        numbers.pack(side="left", fill="y")
        self._fields(numbers, limits.ADVANCED)
        per = ttk.LabelFrame(self.advanced, text="Starting LP by duelist (empty: the side's own)", padding=6)
        per.pack(side="left", fill="both", expand=True, padx=(8, 0))
        self.duelists = ttk.Treeview(per, columns=("player", "opponent"), height=8)
        self.duelists.heading("#0", text="Duelist")
        self.duelists.heading("player", text="Player's LP")
        self.duelists.heading("opponent", text="Duelist's LP")
        self.duelists.column("#0", width=180)
        self.duelists.column("player", width=90, anchor="e")
        self.duelists.column("opponent", width=90, anchor="e")
        self.duelists.pack(fill="both", expand=True)
        self.duelists.bind("<<TreeviewSelect>>", lambda e: self._pick_duelist())
        row = ttk.Frame(per)
        row.pack(fill="x", pady=(4, 0))
        self.duelist_name = tk.StringVar()
        self.duelist_player = tk.StringVar()
        self.duelist_opponent = tk.StringVar()
        ttk.Combobox(row, textvariable=self.duelist_name, values=["all"] + DUELIST_NAMES[1:],
                     width=22).pack(side="left")
        ttk.Label(row, text="Player").pack(side="left", padx=(6, 2))
        ttk.Entry(row, textvariable=self.duelist_player, width=7).pack(side="left")
        ttk.Label(row, text="Duelist").pack(side="left", padx=(6, 2))
        ttk.Entry(row, textvariable=self.duelist_opponent, width=7).pack(side="left")
        ttk.Button(row, text="Set", command=self._set_duelist).pack(side="left", padx=(6, 0))
        ttk.Button(row, text="Remove", command=self._remove_duelist).pack(side="left", padx=(4, 0))
        self.status = ttk.Label(self, style="Error.TLabel", wraplength=900, justify="left")
        self.status.pack(anchor="w", pady=(6, 0))
        buttons = ttk.Frame(self)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Apply", command=self.commit).pack(side="left")
        ttk.Button(buttons, text="Game's numbers", command=self.clear).pack(side="left", padx=4)
        self.per_duelist = {}

    def _fields(self, parent, fields):
        for row, (key, label, retail, low, high, _) in enumerate(fields):
            ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=1)
            var = self.vars[key] = tk.StringVar()
            entry = ttk.Entry(parent, textvariable=var, width=10)
            entry.grid(row=row, column=1, sticky="w", pady=1, padx=(6, 0))
            entry.bind("<FocusOut>", lambda e: self.commit())
            own = "the start" if retail is None else str(retail)
            ttk.Label(parent, style="Hint.TLabel", text=f"({own}; {low}-{high})").grid(row=row, column=2, sticky="w",
                                                                                      padx=(6, 0))

    def _show_advanced(self):
        if self.advanced_shown.get():
            self.advanced.pack(fill="both", expand=True, pady=(4, 0), before=self.status)
        else:
            self.advanced.pack_forget()

    def _fill_duelists(self):
        self.duelists.delete(*self.duelists.get_children())
        for name, (player, opponent) in self.per_duelist.items():
            self.duelists.insert("", "end", iid=name, text=name,
                                 values=("" if player is None else player, "" if opponent is None else opponent))

    def _pick_duelist(self):
        chosen = self.duelists.selection()
        if not chosen:
            return
        player, opponent = self.per_duelist.get(chosen[0], (None, None))
        self.duelist_name.set(chosen[0])
        self.duelist_player.set("" if player is None else str(player))
        self.duelist_opponent.set("" if opponent is None else str(opponent))

    def _set_duelist(self):
        name = self.duelist_name.get().strip()
        try:
            values = [int(v.get()) if v.get().strip() else None for v in (self.duelist_player, self.duelist_opponent)]
        except ValueError:
            self.status.configure(text="A duelist's LP is a whole number")
            return
        if not name:
            return
        if values == [None, None]:
            self.per_duelist.pop(name, None)
        else:
            self.per_duelist[name] = tuple(values)
        self._fill_duelists()
        self.commit()

    def _remove_duelist(self):
        for name in self.duelists.selection():
            self.per_duelist.pop(name, None)
        self._fill_duelists()
        self.commit()

    def clear(self):
        for var in self.vars.values():
            var.set("")
        self.per_duelist = {}
        self._fill_duelists()
        self.commit()

    def refresh(self):
        if self.project is None:
            return
        flat = limits.flatten(self.project.other.get("limits"))
        for key, var in self.vars.items():
            var.set(str(flat[key]) if key in flat else "")
        self.per_duelist = dict(flat.get("duelists", {}))
        self._fill_duelists()
        self._report()

    def _report(self):
        problems = limits.check(self.project.other.get("limits")) if self.project else []
        self.status.configure(text="\n".join(f"{level}: {where}: {message}" for level, where, message in problems))

    def commit(self):
        if self.project is None:
            return True
        flat = {"duelists": dict(self.per_duelist)}
        for key, var in self.vars.items():
            text = var.get().strip()
            if not text:
                continue
            try:
                flat[key] = int(text)
            except ValueError:
                self.status.configure(text=f"Not applied: {key} is a whole number")
                return False
        before = self.project.other.get("limits")
        after = limits.build(flat, before)
        if after is None:
            self.project.other.pop("limits", None)
        else:
            self.project.other["limits"] = after
        self._report()
        if after != before:
            self.app.changed()
        return True
