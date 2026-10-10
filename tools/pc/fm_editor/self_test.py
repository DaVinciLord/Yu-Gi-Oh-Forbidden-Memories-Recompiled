"""Exercise a shipped editor without a ROM or a source checkout.

The JSON report is required: Windows' windowed executable has no stdout,
and merely staying alive would also pass an editor stuck at an error box.
"""
from __future__ import annotations

import json
from contextlib import ExitStack
from pathlib import Path
import tempfile
import traceback
from unittest import mock

# Every box tkinter.messagebox can show: one the run did not expect fails it
# at once, with its text, instead of waiting for a click until the timeout.
MESSAGE_BOXES = ("showinfo", "showwarning", "showerror", "askquestion", "askokcancel",
                 "askyesno", "askyesnocancel", "askretrycancel")


def require(condition, message):
    """A failed check, even under python -O (where assert is skipped)."""
    if not condition:
        raise AssertionError(message)


def exercise(folder: Path) -> dict:
    from . import build_info, file_dialogs, manifest, pngio, settings, validate
    from .app import App
    from .tests.map_fixture import MapFixture

    fixture = MapFixture()
    game = folder / "game"
    (game / "DATA").mkdir(parents=True)
    (game / "SLUS_014.11").write_bytes(fixture.slus)
    (game / "DATA/WA_MRG.MRG").write_bytes(fixture.wa)
    callbacks = []

    def unexpected_dialog(kind):
        def show(*args, **kwargs):
            raise AssertionError(f"unexpected messagebox.{kind}: {args} {kwargs}")
        return show

    with ExitStack() as patches:
        patches.enter_context(mock.patch.object(settings, "path",
                                                return_value=folder / "config/settings.json"))
        for kind in MESSAGE_BOXES:
            patches.enter_context(mock.patch(f"tkinter.messagebox.{kind}",
                                             side_effect=unexpected_dialog(kind)))
        app = App(ask=False, autostart=False)
        app.report_callback_exception = lambda *exc: callbacks.append("".join(traceback.format_exception(*exc)))
        try:
            app.update()
            app.start(str(game), None, False)
            require(app.project is not None, "synthetic game did not open")
            tabs = []
            for tab in app.tabs:
                app.notebook.select(tab)
                app.update()
                tabs.append(app.notebook.tab(tab, "text"))
            app.notebook.select(app.ui)
            pages = []
            for name in app.ui.pages:
                app.ui.page_name.set(name)
                app.ui.show_page()
                app.update()
                pages.append(name)
            app.notebook.select(app.cards)
            app.cards.goto(1)
            app.cards.vars["name"].set("Packaged editor smoke card")
            require(app.cards.apply(), "card Apply failed")
            app.project.set_tags(1, ["smoke"])
            art = folder / "picture.png"
            pngio.write(art, pngio.Image(102, 96, bytes((50, 100, 200, 255)) * (102 * 96)))
            app.art.goto(1)
            app.art.use_file("art", str(art))
            app.info.vars["id"].set("editor-smoke")
            require(app.info.commit(), "Mod info Apply failed")
            with mock.patch.object(file_dialogs, "askdirectory", return_value=str(folder / "mods")):
                require(app.save(ask=True, export=True), "Export failed")
            saved = folder / "mods/editor-smoke"
            value = json.loads((saved / "mod.json").read_text(encoding="utf-8"))
            require(value["min_api"] == 11, value)
            app.load_mod(saved)
            app.update()
            require(app.project.cards[1].name == "Packaged editor smoke card", "card name did not reopen")
            problems = validate.errors(validate.validate(app.project))
            require(not problems, f"reopened mod does not validate: {problems}")
            require(manifest.build(app.project) == value, "reopened manifest changed")
            require(list(saved.rglob("*.png")), "exported art is missing")
            require(not callbacks, "\n".join(callbacks))
            return {"build": build_info.current(), "tabs": tabs, "ui_pages": pages,
                    "export_reopen": True, "art": True}
        finally:
            app.dirty = False
            app.destroy()


def run(output) -> int:
    report = {"ok": False}
    try:
        with tempfile.TemporaryDirectory(prefix="fm-editor-smoke-") as folder:
            report.update(exercise(Path(folder)))
        report["ok"] = True
    except Exception:
        report["error"] = traceback.format_exc()
    Path(output).write_text(json.dumps(report, indent=2), encoding="utf-8")
    return 0 if report["ok"] else 1
