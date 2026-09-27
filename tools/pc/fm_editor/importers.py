"""The window's File > Import entries."""
from __future__ import annotations

import re
from pathlib import Path
from tkinter import filedialog, messagebox

from . import disc, importer


def slug(text: str) -> str:
    """A mod id out of a file name."""
    text = re.sub(r"[^A-Za-z0-9_-]+", "-", Path(text).stem).strip("-").lower()
    return (text or "imported-mod")[:63]


def ask_modded_files(app):
    """A modified game: its .bin, or its SLUS_014.11 (WA_MRG.MRG found in
    DATA/ beside it or asked for)."""
    path = filedialog.askopenfilename(
        parent=app, title="The modified game: its .bin disc image, or its SLUS_014.11",
        filetypes=[("Disc image or executable", "*.bin *.iso *.img SLUS_014.11 *.11"), ("All files", "*.*")])
    if not path:
        return None, None
    path = Path(path)
    try:
        if path.suffix.lower() in (".bin", ".iso", ".img"):
            return disc.load(path), path.stem
        wa = path.parent / "DATA" / "WA_MRG.MRG"
        if not wa.is_file():
            wa = path.parent / "WA_MRG.MRG"
        if not wa.is_file():
            chosen = filedialog.askopenfilename(parent=app, title="The modified game's WA_MRG.MRG",
                                                filetypes=[("WA_MRG.MRG", "*.MRG"), ("All files", "*.*")])
            if not chosen:
                return None, None
            wa = Path(chosen)
        return disc.load_pair(path, wa), path.parent.name
    except (disc.GameFilesError, OSError) as problem:
        messagebox.showerror("Import", str(problem), parent=app)
        return None, None


def import_modded_game(app):
    if not app.need_game() or not app.confirm_discard():
        return
    files, name = ask_modded_files(app)
    if files is None:
        return
    app.config(cursor="watch")
    app.update()
    try:
        result = importer.import_modded(app.files, files, slug(name), name)
    except ValueError as problem:
        messagebox.showerror("Import", str(problem), parent=app)
        return
    finally:
        app.config(cursor="")
    app.set_project(result.project)
    app.changed()
    app.say(f"Imported {files.source}: save it to write the mod folder.")
    app.report("Import report", "Compared with your retail game:\n\n" + "\n".join("- " + line for line in result.report)
               + "\n\nThe report is saved with the mod as import-report.txt.")


def install(app):
    app.add_import("Import a modified game (.bin or SLUS_014.11)...", lambda: import_modded_game(app))
