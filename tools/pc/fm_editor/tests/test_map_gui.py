"""The Map tab, driven as a user would, on the synthetic campaign map.
Skipped where there is no Tk or no display."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

try:
    import tkinter as tk
except ImportError:
    tk = None

from fm_editor import campaign_map as cm
from fm_editor.tests import map_fixture as mf


class MapGuiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if tk is None:
            raise unittest.SkipTest("this Python has no Tk")
        try:
            probe = tk.Tk()
            probe.destroy()
        except tk.TclError as problem:
            raise unittest.SkipTest(f"no display for Tk: {problem}")
        cls.tmp = tempfile.TemporaryDirectory()
        folder = Path(cls.tmp.name) / "game"
        (folder / "DATA").mkdir(parents=True)
        f = mf.map_fixture()
        (folder / "SLUS_014.11").write_bytes(f.slus)
        (folder / "DATA" / "WA_MRG.MRG").write_bytes(f.wa)
        cls.game = folder

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        from fm_editor import settings
        from fm_editor.app import App
        self.settings = Path(self.tmp.name) / "config" / "settings.json"
        patcher = mock.patch.object(settings, "path", lambda: self.settings)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.app = App(ask=False, autostart=False)
        self.app.withdraw()
        self.app.start(str(self.game), None, False)
        self.app.notebook.select(self.app.map)
        self.app.update()

    def tearDown(self):
        self.app.dirty = False
        self.app.destroy()

    def test_edit_drag_save(self):
        app, tab = self.app, self.app.map
        self.assertEqual(tab.tree.item("0", "values")[1], "Place A")
        tab.select(13)
        self.assertEqual(tab.vars["marker_x"].get(), mf.locations()[13].marker_x)
        # A field of the form, then the D-pad and a destination of exit 2.
        tab.vars["marker_x"].set(250)
        self.assertEqual(cm.state(app.project).locations[13].marker_x, 250)
        self.assertTrue(app.dirty)
        tab.exit_vars[1]["up"].set(True)
        tab.exit_vars[1]["destination"].set(cm.label(app.project, 2))
        e = cm.state(app.project).locations[13].exits[1]
        self.assertEqual((e.buttons, e.destination), (0x9000, 2))
        self.assertEqual(list(tab.tree.item("13", "tags")), ["changed"])
        # A new exit gets the usual length.
        tab.exit_vars[2]["used"].set(True)
        app.update()
        self.assertEqual(cm.state(app.project).locations[13].exits[2].steps, 16)
        # Drag the marker 20 screen pixels right and 10 down (40 and 20 on the 2x canvas).
        loc = cm.state(app.project).locations[13]
        x, y = loc.marker_x * 2, loc.marker_y * 2
        before = (loc.marker_x, loc.marker_y)
        tab.press(mock.Mock(x=x, y=y))
        tab.motion(mock.Mock(x=x + 40, y=y + 20))
        tab.release(mock.Mock(x=x + 40, y=y + 20))
        loc = cm.state(app.project).locations[13]
        self.assertEqual((loc.marker_x, loc.marker_y), (before[0] + 20, before[1] + 10))
        # The overview draws, and a world site dragged moves its camera.
        tab.view.set("overview")
        tab.draw()
        sx, sy = tab.node(4)
        target = (cm.state(app.project).locations[4].target_x, cm.state(app.project).locations[4].target_z)
        tab.press(mock.Mock(x=round(sx), y=round(sy)))
        tab.motion(mock.Mock(x=round(sx) + 10, y=round(sy)))
        tab.release(mock.Mock(x=round(sx) + 10, y=round(sy)))
        self.assertEqual(tab.index, 4)
        loc = cm.state(app.project).locations[4]
        self.assertEqual(loc.target_x, target[0])
        self.assertNotEqual(loc.target_z, target[1])
        # A problem goes to its place.
        cm.state(app.project).locations[6].exits[0].steps = 0
        issue = next(i for i in app.conflicts.run() if i.area == "Map")
        app.go_to(issue)
        self.assertEqual(tab.index, 6)
        cm.state(app.project).locations[6].exits[0].steps = 16
        tab.reset_place()
        self.assertFalse(cm.changed(app.project, 6))
        # Saved: the patches of both packages.
        out = Path(self.tmp.name) / "saved-map"
        app.project.info.id = "map-test"
        app.project.source_dir = out
        self.assertTrue(app.save())
        data = json.loads((out / "mod.json").read_text(encoding="utf-8"))
        runs = data["data"][-1]["patch"]
        sectors = {int(r["at"], 16) // cm.SECTOR for r in runs}
        self.assertEqual(sectors, {s + cm.TABLE_OFFSET // cm.SECTOR for _, s in cm.PACKAGES})
        app.load_mod(out)
        self.assertEqual(cm.state(app.project).locations[13].marker_x, before[0] + 20)

    def test_screen_picture(self):
        tab = self.app.map
        tab.select(0)
        tab.view.set("screen")
        tab.draw()
        self.assertTrue(tab.canvas.find_withtag("exit0"))
        self.assertIn("drawn from the disc's map model", tab.caption.cget("text"))
        tab.select(12)
        self.assertTrue(tab.canvas.find_withtag("marker"))

    def test_pictures(self):
        from fm_editor import map_art, pngio
        tab = self.app.map
        tab.select(12)
        tab.show_pictures()
        dialog = tab.pictures
        self.app.update()
        self.assertIn("1 textures, 0 replaced", dialog.count.cget("text"))
        picture = Path(self.tmp.name) / "marker.png"
        pngio.write(picture, pngio.Image(64, 64, bytes((255, 0, 255, 255)) * 4096))
        dialog.sprite.set(map_art.SPRITES[0][0])
        dialog.import_sprite(str(picture))
        self.assertEqual(set(map_art.state(self.app.project).strips), {0})
        self.assertTrue(self.app.dirty)
        folder = Path(self.tmp.name) / "textures-out"
        dialog.export_textures(str(folder))
        dialog.import_textures(str(folder))
        self.assertIn("1 replaced", dialog.count.cget("text"))
        tab.draw()
        self.assertTrue(tab.canvas.find_withtag("marker"))
        dialog.revert_textures()
        dialog.revert_sprites()
        self.assertEqual(map_art.state(self.app.project).strips, {})
        dialog.destroy()
        # A new project after the dialog was closed: the tab fills again.
        from fm_editor.model import Project
        self.app.dirty = False
        self.app.set_project(Project(self.app.retail))
        self.assertEqual(len(tab.tree.get_children()), cm.COUNT)
        self.assertEqual(tab.heading.cget("text").split(":")[0], str(tab.index))

    def test_dark(self):
        self.app.theme.use(True)
        self.app.map.draw()
        self.app.update()
        self.app.theme.use(False)


if __name__ == "__main__":
    unittest.main()
