"""Window-level editing, history and recovery controls."""
from __future__ import annotations

import json
import shutil
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from . import manifest, recovery
from .icon_choice import IconChoice
from .widgets import scrolled_tree


class Editing:
    def init_editing(self):
        self.history = None
        self.recovery = recovery.Recovery()
        self._history_job = self._recovery_job = None
        self._refreshing = False
        self._pending = set()
        self._recovered = False
        self._recovery_source = None
        self._recovered_from = None     # the crashed session a recovered copy came from
        self._input_before = {}

    def install_editing(self):
        self.edit_state = ttk.Label(self, anchor="e", padding=(6, 2))
        self.edit_state.pack(fill="x", before=self.status)
        # A private tag runs before Text's bindings, avoiding a second undo.
        tag = f"EditorHistory:{self}"
        self.bind_class(tag, "<Control-z>", lambda e: self.shortcut(self.undo))
        self.bind_class(tag, "<Control-y>", lambda e: self.shortcut(self.redo))
        self.bind_class(tag, "<Control-Shift-Z>", lambda e: self.shortcut(self.redo))
        def walk(widget):
            widget.bindtags((tag,) + widget.bindtags())
            for child in widget.winfo_children():
                walk(child)
        walk(self.notebook)
        # Only actual form inputs, not searches, filters or navigation, count
        # as pending edits. Capture user events rather than programmatic fills.
        for tab in (self.cards, self.info, self.limits, self.packs):
            variables = {str(v) for v in getattr(tab, "vars", {}).values()}
            variables.update(str(v) for v in getattr(tab, "adv", {}).values())
            if tab is self.packs:
                variables.add(str(tab.unlock_card.var))
            if tab is self.cards:       # an added card's two boxes
                variables.update((str(tab.drops), str(tab.opponents)))
            texts = [getattr(tab, key, None) for key in ("text", "notes", "description", "settings", "other")]
            def watch(widget):
                tracked = widget in texts or (isinstance(widget, (ttk.Entry, ttk.Combobox, ttk.Spinbox, IconChoice))
                                               and str(widget.cget("textvariable")) in variables) or (
                    isinstance(widget, ttk.Checkbutton) and str(widget.cget("variable")) in variables)
                if tracked:
                    widget.bind("<FocusIn>", lambda e: self._remember_input(e.widget), add=True)
                    widget.bind("<ButtonPress-1>", lambda e: self._remember_input(e.widget), add=True)
                    widget.bind("<KeyPress>", lambda e: self._remember_input(e.widget), add=True)
                    for event in ("<KeyRelease>", "<ButtonRelease-1>", "<<ComboboxSelected>>", "<<Paste>>", "<<Cut>>"):
                        widget.bind(event, lambda e, t=tab: self._queue_input(e, t), add=True)
                for child in widget.winfo_children():
                    watch(child)
            watch(tab)
        self.update_edit_state()

    @staticmethod
    def _input_value(widget):
        if isinstance(widget, ttk.Checkbutton):
            return widget.getvar(widget.cget("variable"))
        return widget.get("1.0", "end-1c") if isinstance(widget, tk.Text) else widget.get()

    def _queue_input(self, event, tab):
        if event.type == tk.EventType.KeyRelease and event.state & 4:
            return  # Ctrl+Z/S can refresh forms; paste/cut have their own events.
        self.after_idle(self._form_input, tab, event.widget)

    def form_applied(self, tab):
        if tab in self._pending:
            self._pending.discard(tab)
            self.update_title()
            self.update_edit_state()
        # Refresh baselines after an Apply normalizes numeric fields.
        for name in list(self._input_before):
            try:
                widget = self.nametowidget(name)
                self._input_before[name] = self._input_value(widget)
            except (KeyError, tk.TclError):
                self._input_before.pop(name, None)

    def _remember_input(self, widget):
        self._input_before[str(widget)] = self._input_value(widget)

    def _form_input(self, tab, widget):
        if self._refreshing or self.project is None or not widget.winfo_exists():
            return
        value = self._input_value(widget)
        if self._input_before.get(str(widget)) == value:
            return
        self._input_before[str(widget)] = value
        self.form_edited(tab)

    def form_edited(self, tab):
        """A form now holds input not yet applied (typed, or put there by a tab)."""
        if self._refreshing or self.project is None:
            return
        self._pending.add(tab)
        self.update_title()
        self.update_edit_state()
        self.schedule_recovery()

    def update_edit_state(self):
        if not hasattr(self, "edit_state"):
            return
        self.edit_menu.entryconfigure(0, state="normal" if self.history and
                                      (self.history.position > 0 or self._pending or self._history_job) else "disabled")
        self.edit_menu.entryconfigure(1, state="normal" if self.history and
                                      self.history.position + 1 < len(self.history.items) else "disabled")
        self.edit_menu.entryconfigure(3, state="normal" if self.project else "disabled")
        self.edit_menu.entryconfigure(4, state="normal" if self._pending else "disabled")
        label = "Choose game files to start" if self.project is None else (
            "Unapplied edits • Apply or leave the tab to apply • Ctrl+S saves" if self._pending else
            "Unsaved changes • Ctrl+S saves" if self.dirty else "No unsaved changes")
        style = "TLabel" if self.project is None else (
            "Warning.TLabel" if self._pending else "Changed.TLabel" if self.dirty else "TLabel")
        self.edit_state.configure(text=label, style=style)

    def forget_recovered_copy(self):
        """The recovered session is saved now: stop offering it at start."""
        if self._recovered_from is not None and self._recovered_from.parent.resolve() == recovery.root().resolve():
            shutil.rmtree(self._recovered_from, ignore_errors=True)
        self._recovered_from = None

    def clear_recovery(self):
        self.recovery.clear()
        if self._recovery_source is not None:
            self._recovery_source.clear()
            self._recovery_source = None

    def cancel_edit_jobs(self):
        for name in ("_history_job", "_recovery_job"):
            job = getattr(self, name, None)
            if job is not None:
                self.after_cancel(job)
                setattr(self, name, None)

    def record_edit(self):
        self._history_job = None
        if self.history and not self._refreshing:
            self.history.record(self.project)
        self.update_edit_state()

    def flush_history(self):
        if self._history_job is not None:
            self.after_cancel(self._history_job)
            self._history_job = None
        if self.history:
            self.history.record(self.project)

    def apply_edits(self):
        if self.commit_all(show=True):
            self.flush_history()
            self.say("Edits applied. Ctrl+S saves the mod folder.")

    def refresh_editors(self):
        card, equip, pack, picture = self.cards.current, self.equips.current, self.packs.index, self.art.current
        followed = self.current_card         # Art's show() makes its card the window's: kept as it was
        self._refreshing = True
        try:
            for tab in self.tabs:
                tab.refresh()
            if card in self.project.cards:
                self.cards.show(card)
                if self.cards.tree.exists(str(card)):
                    self.cards.tree.selection_set(str(card))
                    self.cards.tree.see(str(card))
            if equip and self.equips.equips.exists(str(equip)):
                self.equips.equips.selection_set(str(equip))
                self.equips.select()
            if picture in self.project.cards:       # the Art tab stays on its card (Undo showed the first)
                self.art.show(picture)
                if self.art.tree.exists(str(picture)):
                    self.art.tree.selection_set(str(picture))
                    self.art.tree.see(str(picture))
            self.current_card = followed if followed in self.project.cards else None
            self.packs.goto(pack)
        finally:
            self._refreshing = False
        self._pending.clear()
        self._input_before.clear()

    def discard_forms(self):
        if self.project and self._pending:
            self.refresh_editors()
            self.update_title()
            self.update_edit_state()
            self.schedule_recovery()

    def undo(self):
        self.move_history(-1)

    def redo(self):
        self.move_history(1)

    def move_history(self, delta):
        if self.history is None or not self.commit_all(show=True):
            return
        self.flush_history()
        project = self.history.move(delta, self.project)
        if project is None:
            return
        self.project = project
        self.refresh_editors()
        self.dirty = self.history.dirty or self._recovered
        self.update_title()
        self.update_edit_state()
        self.schedule_recovery()
        self.say("Undid edit." if delta < 0 else "Redid edit.")

    def schedule_recovery(self):
        if self._recovery_job is not None:
            self.after_cancel(self._recovery_job)
        self._recovery_job = self.after(2000, self._autosave_due)

    def _autosave_due(self):
        self._recovery_job = None
        self.autosave()

    def form_drafts(self):
        drafts = {}
        for name in ("cards", "info", "limits", "packs"):
            tab = getattr(self, name)
            if tab not in self._pending:
                continue
            row = {"vars": {k: v.get() for k, v in tab.vars.items()}}
            row["texts"] = {k: getattr(tab, k).get("1.0", "end-1c")
                            for k in ("text", "notes", "description", "settings", "other")
                            if isinstance(getattr(tab, k, None), tk.Text)}
            if name == "cards":
                row["current"] = tab.current
            if name == "packs":
                row["index"] = tab.index
                row["adv"] = {k: v.get() for k, v in tab.adv.items()}
                row["unlock_card"] = tab.unlock_card.var.get()
            drafts[name] = row
        return drafts

    def restore_drafts(self, drafts):
        if not isinstance(drafts, dict):
            return
        for name in ("cards", "info", "limits", "packs"):
            row = drafts.get(name)
            if not isinstance(row, dict):
                continue
            tab = getattr(self, name)
            if name == "cards":
                cid = row.get("current")
                if not isinstance(cid, int) or cid not in self.project.cards:
                    continue
                tab.search.set("")
                tab.filter.set(tab.FILTERS[0])
                tab.fill()
                tab.show(cid)
                if tab.tree.exists(str(cid)):
                    tab.tree.selection_set(str(cid))
            if name == "packs":
                index = row.get("index")
                if not isinstance(index, int) or not 0 <= index < len(self.project.packs):
                    continue
                tab.goto(index)
                if isinstance(row.get("adv"), dict):
                    for key, value in row["adv"].items():
                        if key in tab.adv and isinstance(value, (str, int, bool)):
                            tab.adv[key].set(value)
                if isinstance(row.get("unlock_card"), str):
                    tab.unlock_card.var.set(row["unlock_card"])
            if isinstance(row.get("vars"), dict):
                if name == "cards" and isinstance(row["vars"].get("type"), str):
                    tab.vars["type"].set(row["vars"]["type"])
                    tab.show_kind()
                for key, value in row["vars"].items():
                    if key in tab.vars and isinstance(value, str):
                        tab.vars[key].set(value)
            if isinstance(row.get("texts"), dict):
                for key, value in row["texts"].items():
                    widget = getattr(tab, key, None)
                    if isinstance(widget, tk.Text) and isinstance(value, str):
                        widget.delete("1.0", "end")
                        widget.insert("1.0", value)
            if name == "cards":
                tab.show_trap_threshold()
            self._pending.add(tab)
        self.update_title()
        self.update_edit_state()

    def autosave(self):
        if self._recovery_job is not None:
            self.after_cancel(self._recovery_job)
            self._recovery_job = None
        if not self.project:
            return
        if not self.dirty and not self._pending:
            self.recovery.clear()
            return
        # The history records each edit when idle; with none waiting, its
        # current snapshot is this project.
        snapshot = self.history.items[self.history.position] if self.history and self._history_job is None else None
        try:
            self.recovery.write(self.project, self.form_drafts(), snapshot)
        except (OSError, ValueError) as problem:
            self.edit_state.configure(text=f"Recovery copy failed: {problem}. Use Ctrl+S to save.")
        else:
            self.edit_state.configure(text="Recovery copy updated • Ctrl+S saves the mod folder")

    def recover_work(self):
        if not self.need_game():
            return
        rows = [row for row in recovery.records(self.recovery.folder)
                if self._recovery_source is None or row[0].parent != self._recovery_source.folder]
        if not rows:
            messagebox.showinfo("FM Editor", "No recovery copies or save backups are available.", parent=self)
            return
        window = tk.Toplevel(self)
        window.title("Recover work")
        window.transient(self)
        ttk.Label(window, text="Open a separate copy. Save as chooses where to keep it.", padding=10).pack(anchor="w")
        frame, tree = scrolled_tree(window, [("name", "Mod"), ("time", "Saved (UTC)"),
                                              ("kind", "Copy"), ("source", "Original folder")],
                                    [180, 180, 90, 350], height=12, sort_numeric=())
        frame.pack(fill="both", expand=True, padx=10)
        for i, (_, _, data) in enumerate(rows):
            tree.insert("", "end", iid=str(i), values=(data.get("name", "Mod"), str(data.get("time", "")).replace("T", " ")[:19],
                        "Backup" if data.get("backup") else "Draft", data.get("source") or "Not saved yet"))
        tree.selection_set("0")
        def open_copy():
            chosen = tree.selection()
            if not chosen:
                return
            _, folder, data = rows[int(chosen[0])]
            if self.open_recovery(folder, data):
                window.destroy()
        buttons = ttk.Frame(window, padding=10)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Open copy", command=open_copy).pack(side="left")
        def delete_copy():
            chosen = tree.selection()
            if not chosen:
                return
            index, _, data = rows[int(chosen[0])]
            if messagebox.askyesno("FM Editor", f"Delete this recovery copy of {data.get('name', 'the mod')}?",
                                   parent=window, default="no"):
                import shutil
                try:
                    shutil.rmtree(index.parent)
                except OSError as problem:
                    messagebox.showerror("FM Editor", str(problem), parent=window)
                    return
                tree.delete(chosen[0])
                remaining = tree.get_children()
                if remaining:
                    tree.selection_set(remaining[0])
        ttk.Button(buttons, text="Delete copy", command=delete_copy).pack(side="left", padx=6)
        ttk.Button(buttons, text="Close", command=window.destroy).pack(side="right")
        tree.bind("<Double-1>", lambda e: open_copy())
        window.grab_set()

    def open_recovery(self, folder, data):
        try:
            project, notes = manifest.open_mod(self.retail, folder)
        except (OSError, ValueError) as problem:
            messagebox.showerror("FM Editor", str(problem), parent=self)
            return
        if not self.confirm_discard():
            return
        # Own a separate copy before clearing this window's old session.
        staging = recovery.Recovery()
        try:
            staging.write(project, data.get("forms"))
            project, _ = manifest.open_mod(self.retail, staging.folder / json.loads(
                (staging.folder / "recovery.json").read_text(encoding="utf-8"))["generation"])
        except (OSError, ValueError) as problem:
            staging.clear()
            messagebox.showerror("FM Editor", str(problem), parent=self)
            return
        self.set_project(project)
        self._recovery_source = staging
        # A crashed session's copy (not a save backup) goes once it is saved.
        if not data.get("backup") and Path(folder).parent.name.startswith("session-"):
            self._recovered_from = Path(folder).parent
        self._recovered = True
        self.dirty = True
        self.restore_drafts(data.get("forms"))
        self.update_title()
        self.update_edit_state()
        self.say("Recovered a copy. Save as chooses its destination." + (" " + "; ".join(notes) if notes else ""))
        return True
