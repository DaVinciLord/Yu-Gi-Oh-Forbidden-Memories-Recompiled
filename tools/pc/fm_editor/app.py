"""The FM Editor window."""
from __future__ import annotations

import os
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import disc, gamedata, manifest, validate
from .model import KEY_RE, Project
from .tabs import CardsTab, DuelistsTab, EquipsTab, FusionsTab, ModInfoTab, ProblemsTab, RitualsTab

APP_TITLE = "FM Editor"


class App(tk.Tk):
    def __init__(self, game=None, mod=None, ask=True, autostart=True):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1280x800")
        self.minsize(1000, 640)
        try:
            ttk.Style(self).theme_use("vista" if os.name == "nt" else "clam")
        except tk.TclError:
            pass
        self.retail = None
        self.files = None
        self.project = None
        self.dirty = False
        self.hooks = []            # extra menu entries (importers) add themselves here
        self.build_menu()
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True)
        self.cards = CardsTab(self.notebook, self)
        self.fusions = FusionsTab(self.notebook, self)
        self.equips = EquipsTab(self.notebook, self)
        self.rituals = RitualsTab(self.notebook, self)
        self.duelists = DuelistsTab(self.notebook, self)
        self.info = ModInfoTab(self.notebook, self)
        self.problems = ProblemsTab(self.notebook, self)
        self.tabs = [self.cards, self.fusions, self.equips, self.rituals, self.duelists, self.info, self.problems]
        self.status = ttk.Label(self, relief="sunken", anchor="w", padding=(6, 2))
        self.status.pack(fill="x", side="bottom")
        self.notebook.bind("<<NotebookTabChanged>>", lambda e: self.tab_changed())
        self.protocol("WM_DELETE_WINDOW", self.quit_app)
        # On the window, not bind_all: a dialog's keys stay its own. Text's
        # own Ctrl+O inserts a line, so the text boxes get the shortcut too.
        self.bind("<Control-s>", lambda e: self.shortcut(self.save))
        self.bind("<Control-o>", lambda e: self.shortcut(self.open_mod))
        self.bind_class("Text", "<Control-o>", lambda e: self.shortcut(self.open_mod))
        if autostart:
            self.after(50, lambda: self.start(game, mod, ask))

    def shortcut(self, action):
        if self.grab_current() is None:     # not while a dialog is up
            action()
        return "break"

    # --- menus -------------------------------------------------------------

    def build_menu(self):
        bar = tk.Menu(self)
        self.file_menu = tk.Menu(bar, tearoff=False)
        self.file_menu.add_command(label="New mod", command=self.new_mod)
        self.file_menu.add_command(label="Open mod folder...", accelerator="Ctrl+O", command=self.open_mod)
        self.file_menu.add_command(label="Save", accelerator="Ctrl+S", command=self.save)
        self.file_menu.add_command(label="Save as...", command=lambda: self.save(ask=True))
        self.file_menu.add_separator()
        self.import_index = self.file_menu.index("end")
        self.file_menu.add_command(label="Game files...", command=self.choose_game)
        self.file_menu.add_separator()
        self.file_menu.add_command(label="Exit", command=self.quit_app)
        bar.add_cascade(label="File", menu=self.file_menu)
        tools = tk.Menu(bar, tearoff=False)
        tools.add_command(label="Check the mod", command=self.show_problems)
        tools.add_command(label="Preview mod.json", command=lambda: self.info.preview())
        bar.add_cascade(label="Tools", menu=tools)
        helps = tk.Menu(bar, tearoff=False)
        helps.add_command(label="About", command=self.about)
        bar.add_cascade(label="Help", menu=helps)
        self.config(menu=bar)

    def add_import(self, label, command):
        """An importer's menu entry, above "Game files..."."""
        self.file_menu.insert_command(self.import_index, label=label, command=command)
        self.import_index += 1

    # --- starting ----------------------------------------------------------------

    def start(self, game, mod, ask):
        files = None
        try:
            files = disc.load(game) if game else disc.find_game()
        except (disc.GameFilesError, OSError) as problem:
            messagebox.showerror(APP_TITLE, str(problem), parent=self)
        while files is None or not self.use_game(files):
            files = None
            if not ask:
                self.say("No game files: File > Game files... to choose them.")
                return
            answer = messagebox.askokcancel(
                APP_TITLE, "The editor reads the retail tables from your own copy of Yu-Gi-Oh! Forbidden "
                "Memories (USA, SLUS-01411).\n\nChoose the .bin disc image the port runs from (or, next, "
                "a folder holding SLUS_014.11 and DATA/WA_MRG.MRG).", parent=self)
            if not answer:
                self.say("No game files: File > Game files... to choose them.")
                return
            files = self.ask_game_files()
        if mod:
            self.load_mod(mod)

    def ask_game_files(self):
        path = filedialog.askopenfilename(parent=self, title="The game's disc image",
                                          filetypes=[("Disc image", "*.bin *.iso *.img"), ("SLUS_014.11", "SLUS_014.11"),
                                                     ("All files", "*.*")])
        if not path:
            path = filedialog.askdirectory(parent=self, title="Or a folder with SLUS_014.11 and DATA/WA_MRG.MRG")
        if not path:
            return None
        try:
            return disc.load(path)
        except (disc.GameFilesError, OSError) as problem:
            messagebox.showerror(APP_TITLE, str(problem), parent=self)
            return None

    def use_game(self, files):
        try:
            self.retail = gamedata.load_game(files)
        except Exception as problem:     # a file that is not the game
            messagebox.showerror(APP_TITLE, f"Could not read the game's tables: {problem}", parent=self)
            return False
        self.files = files
        self.set_project(Project(self.retail))
        notes = "; ".join(self.retail.notes)
        self.say(f"Game files: {files.source}" + (f" ({notes})" if notes else ""))
        return True

    def choose_game(self):
        if not self.confirm_discard():
            return
        files = self.ask_game_files()
        if files:
            self.use_game(files)

    # --- the project ---------------------------------------------------------------

    def set_project(self, project):
        self.project = project
        self.dirty = False
        for tab in self.tabs:
            tab.refresh()
        self.update_title()

    def changed(self):
        if not self.dirty:
            self.dirty = True
            self.update_title()

    def update_title(self):
        if self.project is None:
            self.title(APP_TITLE)
            return
        where = f" - {self.project.source_dir}" if self.project.source_dir else ""
        self.title(f"{'*' if self.dirty else ''}{self.project.info.name} ({self.project.info.id}){where} - {APP_TITLE}")

    def say(self, text):
        self.status.configure(text=text)

    def commit_all(self, show=False):
        """Store every tab's form. With show, a form that cannot be stored
        is brought up with the reason."""
        for tab in self.tabs:
            if not tab.commit():
                if show:
                    self.notebook.select(tab)
                    messagebox.showerror(APP_TITLE, f"The {self.notebook.tab(tab, 'text')} tab holds something "
                                         "that cannot be stored (the tab says what). Correct it or revert it first.",
                                         parent=self)
                return False
        return True

    def tab_changed(self):
        self.commit_all()
        current = self.notebook.nametowidget(self.notebook.select())
        # Other tabs may have changed what this one shows (a card's name or
        # type): fill it again, keeping its selection.
        if current is self.problems:
            current.run()
        elif current is self.equips:
            current.fill_equips()
            current.fill()
        elif current is self.duelists:
            current.fill_list()
            current.fill()
        elif current in (self.fusions, self.rituals, self.cards):
            current.fill()

    def need_game(self):
        if self.retail is None:
            messagebox.showinfo(APP_TITLE, "Choose the game files first (File > Game files...).", parent=self)
            return False
        return True

    def confirm_discard(self):
        if not self.commit_all(show=True):
            return False
        if not self.dirty:
            return True
        answer = messagebox.askyesnocancel(APP_TITLE, "Save the changes to this mod first?", parent=self)
        if answer is None:
            return False
        return self.save() if answer else True

    def new_mod(self):
        if self.need_game() and self.confirm_discard():
            self.set_project(Project(self.retail))
            self.say("New mod: everything as retail.")

    def open_mod(self):
        if not self.need_game() or not self.confirm_discard():
            return
        folder = filedialog.askdirectory(parent=self, title="A mod folder (the one holding mod.json)",
                                         initialdir=str(self.mods_dir()))
        if folder:
            self.load_mod(folder)

    def load_mod(self, folder):
        folder = Path(folder)
        if not (folder / "mod.json").is_file():
            messagebox.showerror(APP_TITLE, f"{folder} has no mod.json.", parent=self)
            return
        try:
            project, messages = manifest.open_mod(self.retail, folder)
        except (ValueError, OSError) as problem:
            messagebox.showerror(APP_TITLE, f"Could not read {folder / 'mod.json'}: {problem}", parent=self)
            return
        self.set_project(project)
        self.say(f"Opened {folder}")
        if messages:
            self.report("Opened with notes", "What the editor noticed while reading mod.json:\n\n" +
                        "\n".join("- " + m for m in messages))

    def report(self, title, text):
        from .widgets import show_text
        show_text(self, title, text, width=110, height=24)

    def mods_dir(self) -> Path:
        folder = disc.user_dir() / "mods"
        return folder if folder.is_dir() else Path.cwd()

    def save(self, ask=False):
        if self.project is None or not self.commit_all(show=True):
            return False
        issues = validate.validate(self.project)
        errors = validate.errors(issues)
        if errors:
            self.problems.run()
            self.notebook.select(self.problems)
            if not messagebox.askyesno(APP_TITLE, f"The loader would refuse {len(errors)} thing(s) in this mod "
                                       f"(see Problems), for example:\n\n{errors[0]}\n\nSave anyway?",
                                       icon="warning", default="no", parent=self):
                return False
        folder = self.project.source_dir
        if ask or folder is None:
            chosen = filedialog.askdirectory(
                parent=self, initialdir=str(self.mods_dir()),
                title=f"Where to save: an empty folder, or its parent (a folder \"{self.project.info.id}\" is made)")
            if not chosen:
                return False
            chosen = Path(chosen)
            if chosen.is_dir() and any(chosen.iterdir()) and not (chosen / "mod.json").exists():
                if not KEY_RE.match(self.project.info.id or ""):
                    self.notebook.select(self.info)
                    messagebox.showerror(APP_TITLE, "The mod's folder is named after its id: give it one of "
                                         "letters, digits, hyphens and underscores (Mod info), or choose an empty "
                                         "folder.", parent=self)
                    return False
                chosen = chosen / self.project.info.id
            folder = chosen
            if (folder / "mod.json").exists() and folder != self.project.source_dir:
                if not messagebox.askyesno(APP_TITLE, f"{folder} already holds a mod. Replace its mod.json?",
                                           parent=self):
                    return False
        try:
            path = manifest.save_mod(self.project, folder)
        except (ValueError, OSError) as problem:
            messagebox.showerror(APP_TITLE, str(problem), parent=self)
            return False
        self.dirty = False
        self.update_title()
        self.info.refresh()
        self.say(f"Saved {path}. Enable it in the game under Game > Mods and restart the game.")
        return True

    def show_problems(self):
        self.notebook.select(self.problems)
        self.problems.run()

    def go_to(self, issue):
        target = issue.target
        if issue.area == "Cards" and target:
            self.notebook.select(self.cards)
            self.cards.goto(target)
        elif issue.area == "Fusions" and target:
            self.notebook.select(self.fusions)
            self.fusions.search.set(str(target[0]))
        elif issue.area == "Equips" and target:
            self.notebook.select(self.equips)
            if self.equips.equips.exists(str(target)):
                self.equips.equips.selection_set(str(target))
        elif issue.area == "Rituals" and target:
            self.notebook.select(self.rituals)
            if self.rituals.tree.exists(str(target)):
                self.rituals.tree.selection_set(str(target))
        elif issue.area == "Duelists" and target:
            self.notebook.select(self.duelists)
            self.duelists.goto(target)
        elif issue.area == "Mod info":
            self.notebook.select(self.info)

    def about(self):
        messagebox.showinfo(APP_TITLE, "FM Editor\n\nMakes mods for the PC port of Yu-Gi-Oh! Forbidden Memories. "
                            "It reads the retail tables from your own game files and saves a mod folder whose "
                            "mod.json holds only what you changed. It never writes the disc or game/.\n\n"
                            "tools/pc/fm_editor/README.md", parent=self)

    def quit_app(self):
        if self.confirm_discard():
            self.destroy()


def main(game=None, mod=None):
    from . import importers
    app = App(game, mod)
    importers.install(app)
    app.mainloop()
    return 0
