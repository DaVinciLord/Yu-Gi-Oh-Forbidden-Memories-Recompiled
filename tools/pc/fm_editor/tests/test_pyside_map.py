"""The modern editor's Map tab (Campaign > Map), on the synthetic campaign map.

A port of what tests/test_map_gui.py drives in the Tk window.
"""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import tempfile
from pathlib import Path
import unittest
from unittest import mock
from types import SimpleNamespace

try:
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QPoint
    from fm_editor.pyside_app import ModernEditor
except ImportError:
    QApplication = None
from fm_editor import campaign_map as cm, manifest, pngio
from fm_editor.tests import map_fixture as mf


@unittest.skipIf(QApplication is None, 'PySide6 is not installed')
class MapTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt = QApplication.instance() or QApplication([])

    def setUp(self):
        f = mf.map_fixture()
        files = SimpleNamespace(wa=f.wa, slus=f.slus, source='synthetic')
        with mock.patch.object(ModernEditor, '_load_game', return_value=files), \
             mock.patch.object(ModernEditor, '_render_preview'):
            self.window = ModernEditor()
        self.window.select_workspace('Campaign')
        self.m = self.window.workspace_controls['Campaign']['map']
        self.addCleanup(self.window.deleteLater)

    def overview(self):
        self.m['overview'].setChecked(True)

    def test_the_places_are_listed_with_their_area(self):
        w, m = self.window, self.m
        self.assertTrue(w._map_available())
        self.assertEqual(m['places'].rowCount(), cm.COUNT)
        rows = [(m['places'].item(r, 0).text(), m['places'].item(r, 2).text())
                for r in range(m['places'].rowCount())]
        self.assertEqual(rows[0], ('0', 'World'))
        self.assertEqual(rows[cm.TOWN_FIRST], (str(cm.TOWN_FIRST), 'Town'))
        m['search'].setText('Place C')
        self.assertEqual(m['places'].rowCount(), 1)
        m['search'].clear()
        self.assertEqual(m['places'].rowCount(), cm.COUNT)

    def test_the_form_shows_the_place_and_writes_it_back(self):
        w, m = self.window, self.m
        loc = w.map_state.locations[0]
        self.assertEqual(m['distance'].value(), loc.distance)
        self.assertEqual(m['heading'].value(), loc.heading)
        self.assertEqual(m['target_x'].value(), loc.target_x)
        self.assertTrue(m['used'].isChecked())
        self.assertEqual(m['steps'].value(), loc.exits[0].steps)
        w.dirty = False
        m['distance'].setValue(1234)
        self.assertEqual(w.map_state.locations[0].distance, 1234)
        self.assertTrue(w.dirty)
        self.assertTrue(cm.changed(w.project, 0))

    def test_the_exit_buttons_switch_between_the_four_exits(self):
        w, m = self.window, self.m
        self.assertEqual([b.text() for b in m['exit_tabs']], ['1 ▶', '2 ◀', '3', '4'])
        w._map_select_exit(2)
        self.assertFalse(m['used'].isChecked())     # the fixture uses two of four
        w._map_select_exit(0)
        self.assertTrue(m['used'].isChecked())

    def test_the_direction_pad_and_the_condition_reach_the_exit(self):
        w, m = self.window, self.m
        m['directions']['up'].setChecked(True)
        self.assertTrue(w.map_state.locations[0].exits[0].buttons & 0x1000)
        m['condition'].setCurrentIndex(2)           # while the flag is clear
        m['flag'].setValue(84)
        self.assertEqual(cm.condition_parts(w.map_state.locations[0].exits[0].condition), ('clear', 84))

    def test_the_marker_belongs_to_the_town_only(self):
        w, m = self.window, self.m
        w._select_map_place(0)
        self.assertFalse(m['marker_x'].isEnabled())
        self.assertIn('draws no marker', m['marker_note'].text())
        w._select_map_place(cm.TOWN_FIRST)
        self.assertTrue(m['marker_x'].isEnabled())
        self.assertEqual(m['marker_note'].text(), '')
        self.assertIn('(town)', m['context'].text())

    def test_an_exit_arrow_is_dragged_on_the_screen(self):
        w, m = self.window, self.m
        w._select_map_place(0)
        before = (w.map_state.locations[0].exits[0].x, w.map_state.locations[0].exits[0].y)
        arrow = next(r for kind, n, r in m['canvas'].targets if kind == 'exit' and n == 0)
        w._map_press(arrow.center())
        w._map_move(arrow.center() + QPoint(10, -6))
        w._map_release(arrow.center() + QPoint(10, -6))
        after = (w.map_state.locations[0].exits[0].x, w.map_state.locations[0].exits[0].y)
        self.assertEqual(after, (before[0] + 5, before[1] - 3))      # the screen is drawn at 2x

    def test_the_marker_is_dragged_on_the_screen(self):
        w, m = self.window, self.m
        w._select_map_place(12)
        before = (w.map_state.locations[12].marker_x, w.map_state.locations[12].marker_y)
        marker = next(r for kind, _n, r in m['canvas'].targets if kind == 'marker')
        w._map_press(marker.center())
        w._map_move(marker.center() + QPoint(8, 12))
        w._map_release(marker.center() + QPoint(8, 12))
        self.assertEqual((w.map_state.locations[12].marker_x, w.map_state.locations[12].marker_y),
                         (before[0] + 4, before[1] + 6))

    def test_a_world_site_is_dragged_in_the_overview(self):
        w, m = self.window, self.m
        self.overview()
        node = next(r for kind, n, r in m['canvas'].targets if kind == 'place' and n == 3)
        if m['canvas'].hit(node.center()) != ('place', 3):
            self.skipTest('place 3 is covered by another node at this size')
        before = (w.map_state.locations[3].target_x, w.map_state.locations[3].target_z)
        w._map_press(node.center())
        w._map_move(node.center() + QPoint(30, -15))
        w._map_release(node.center() + QPoint(30, -15))
        _cx, _cz, scale, _ox, _oy = w._map_world_frame()
        self.assertEqual((w.map_state.locations[3].target_x, w.map_state.locations[3].target_z),
                         (before[0] + round(-15 / scale), before[1] + round(30 / scale)))

    def test_clicking_a_node_in_the_overview_selects_that_place(self):
        w, m = self.window, self.m
        self.overview()
        node = next(r for kind, n, r in m['canvas'].targets if kind == 'place' and n == 6)
        hit = m['canvas'].hit(node.center())
        w._map_press(node.center())
        self.assertEqual(w.map_index, hit[1])
        self.assertIn(str(hit[1]), m['context'].text())

    def test_both_views_draw_and_caption_themselves(self):
        w, m = self.window, self.m
        # Drawn at its own size; what is shown may be shrunk to the panel.
        self.assertEqual(m['canvas'].surface.size().toTuple(), w.MAP_CANVAS)
        self.assertFalse(m['canvas'].pixmap().isNull())
        self.assertIn('The screen at this place', m['caption'].text())
        self.assertTrue(any(kind == 'exit' for kind, _n, _r in m['canvas'].targets))
        self.overview()
        self.assertIn('Every place and where its exits lead', m['caption'].text())
        self.assertEqual(sum(1 for kind, _n, _r in m['canvas'].targets if kind == 'place'), cm.COUNT)

    def test_the_package_choice_redraws_the_other_map(self):
        w, m = self.window, self.m
        self.assertEqual(w._map_package_name(), 'before')
        m['package'].setCurrentIndex(1)
        self.assertEqual(w._map_package_name(), 'after')
        self.assertEqual(w._map_package_sector(), dict(cm.PACKAGES)['after'])
        self.assertIn('after the coup', m['caption'].text())

    def test_reset_place_and_reset_all(self):
        w, m = self.window, self.m
        was = w.map_state.locations[0].distance
        m['distance'].setValue(4321)
        self.assertTrue(cm.changed(w.project, 0))
        w._reset_map_place()
        self.assertFalse(cm.changed(w.project, 0))
        self.assertEqual(w.map_state.locations[0].distance, was)
        m['distance'].setValue(4321)
        w._select_map_place(4)
        m['heading'].setValue(77)
        self.assertTrue(cm.any_changed(w.project))
        with mock.patch('fm_editor.pyside_app.QMessageBox.question',
                        return_value=mock.Mock()) as question:
            from PySide6.QtWidgets import QMessageBox
            question.return_value = QMessageBox.StandardButton.Yes
            w._reset_map_all()
        self.assertFalse(cm.any_changed(w.project))

    def test_a_reference_picture_replaces_the_rendered_screen(self):
        w, m = self.window, self.m
        image = pngio.Image(320, 240, bytes([40, 60, 90, 255]) * (320 * 240))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'shot.png'
            pngio.write(str(path), image)
            with mock.patch('fm_editor.pyside_app.QFileDialog.getOpenFileName',
                            return_value=(str(path), '')):
                w._choose_map_reference()
        self.assertIn(w._map_camera(w.map_index), w.map_references)
        self.assertIn('your reference picture', m['caption'].text())

    def test_the_pictures_window_lists_sprites_and_textures(self):
        w = self.window
        w._show_map_pictures()
        d = w.map_dialog_controls
        self.assertIsNotNone(w.map_dialog)
        self.assertEqual(d['sprite'].count(), 10)
        self.assertIn('textures', d['count'].text())
        self.assertGreater(d['previews'].count(), 1)
        w._revert_map_sprites()
        self.assertIn("disc's again", d['status'].text())
        w.map_dialog.close()

    def test_a_map_edit_survives_saving_and_reopening(self):
        w, m = self.window, self.m
        w._select_map_place(2)
        m['distance'].setValue(4321)
        m['heading'].setValue(999)
        w.project.info.id = 'maptest'
        w.project.info.name = 'Map test'
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / 'mod'
            manifest.save_mod(w.project, str(folder))
            again, notes = manifest.open_mod(w.retail, str(folder))
        self.assertEqual(notes, [])
        self.assertEqual(cm.state(again).locations[2].distance, 4321)
        self.assertEqual(cm.state(again).locations[2].heading, 999)

    def test_a_map_problem_jumps_to_its_place(self):
        w = self.window
        w.select_workspace('Cards')
        w.go_to(SimpleNamespace(area='Map', target=7, where='Place H', level='error'))
        self.assertEqual(w.current_workspace, 'Campaign')
        tabs = w.workspace_controls['Campaign']['tabs']
        self.assertEqual(tabs.tabText(tabs.currentIndex()), 'Map')
        self.assertEqual(w.map_index, 7)


    def test_dragging_still_lands_right_on_a_shrunk_canvas(self):
        """The canvas shrinks with the panel; a drag is in the drawing's own
        pixels whatever it is shown at."""
        w, m = self.window, self.m
        canvas = m['canvas']
        canvas.resize(320, 240)                 # half size
        self.qt.processEvents()
        shown = canvas.pixmap()
        self.assertLess(shown.width(), canvas.surface.width())
        w._select_map_place(0)
        arrow = next(r for kind, n, r in canvas.targets if kind == 'exit' and n == 0)
        # A point in the drawing maps back through the shown scale.
        scale = shown.width() / canvas.surface.width()
        left = (canvas.width() - shown.width()) // 2
        top = (canvas.height() - shown.height()) // 2
        centre = arrow.center()
        on_screen = QPoint(round(centre.x() * scale) + left, round(centre.y() * scale) + top)
        # Mapping down and back is within a pixel of where it started.
        back = canvas.at(on_screen)
        self.assertLessEqual(abs(back.x() - centre.x()), 2)
        self.assertLessEqual(abs(back.y() - centre.y()), 2)
        before = (w.map_state.locations[0].exits[0].x, w.map_state.locations[0].exits[0].y)
        w._map_press(canvas.at(on_screen))
        w._map_move(canvas.at(on_screen) + QPoint(10, -6))
        w._map_release(canvas.at(on_screen) + QPoint(10, -6))
        self.assertEqual((w.map_state.locations[0].exits[0].x, w.map_state.locations[0].exits[0].y),
                         (before[0] + 5, before[1] - 3))


if __name__ == '__main__':
    unittest.main()
