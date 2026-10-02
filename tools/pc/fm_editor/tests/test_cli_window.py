"""Which window the command line opens.

    python -m unittest discover -s tools/pc/fm_editor/tests -t tools/pc
"""
import builtins
import io
import tempfile
import sys
import unittest
from unittest import mock

from fm_editor import cli


class WindowTest(unittest.TestCase):
    def opened(self, argv):
        """Which window `argv` would open, without opening one."""
        which = {}
        with mock.patch("fm_editor.pyside_app.main", lambda game, mod: (which.setdefault("w", "qt"), 0)[1]), \
             mock.patch("fm_editor.app.main", lambda game, mod: (which.setdefault("w", "tk"), 0)[1]):
            self.assertEqual(cli.main(argv), 0)
        return which.get("w")

    def test_the_qt_window_is_the_one_that_opens(self):
        self.assertEqual(self.opened([]), "qt")
        self.assertEqual(self.opened(["--mod", "somewhere"]), "qt")

    def test_classic_asks_for_the_old_one(self):
        self.assertEqual(self.opened(["--classic"]), "tk")

    def without_pyside(self):
        """PySide6 itself absent, as it is on a machine that never had it."""
        real = builtins.__import__

        def absent(name, *args, **rest):
            if name == "PySide6" or name.startswith("PySide6."):
                raise ModuleNotFoundError("No module named 'PySide6'", name="PySide6")
            return real(name, *args, **rest)

        gone = {name: module for name, module in list(sys.modules.items())
                if name == "PySide6" or name.startswith("PySide6.")
                or name == "fm_editor.pyside_app" or name.startswith("fm_editor.qt")}
        for name in gone:
            del sys.modules[name]
        self.addCleanup(sys.modules.update, gone)
        return mock.patch.object(builtins, "__import__", absent)

    def test_without_pyside_the_old_one_opens_instead(self):
        """An optional dependency: the editor still runs without it, and says
        so rather than showing a ModuleNotFoundError."""
        said = io.StringIO()
        which = {}
        with self.without_pyside(), \
             mock.patch("fm_editor.app.main", lambda game, mod: (which.setdefault("w", "tk"), 0)[1]), \
             mock.patch("sys.stderr", said):
            self.assertEqual(cli.main([]), 0)
        self.assertEqual(which.get("w"), "tk")
        self.assertIn("PySide6 is not installed", said.getvalue())
        self.assertIn("pip install PySide6", said.getvalue())
        self.assertNotIn("Traceback", said.getvalue())

    def test_a_built_editor_says_nothing_about_pip(self):
        """It carries its own Python: there is nothing to install into."""
        said = io.StringIO()
        which = {}
        with self.without_pyside(), \
             mock.patch.object(sys, "frozen", True, create=True), \
             mock.patch("fm_editor.app.main", lambda game, mod: (which.setdefault("w", "tk"), 0)[1]), \
             mock.patch("sys.stderr", said):
            self.assertEqual(cli.main([]), 0)
        self.assertEqual(which.get("w"), "tk")
        self.assertEqual(said.getvalue(), "")


if __name__ == "__main__":
    unittest.main()


class BuildTest(unittest.TestCase):
    """What the build does when the Qt window cannot go in it."""

    def without_pyside(self):
        real = builtins.__import__

        def absent(name, *args, **rest):
            if name == "PySide6" or name.startswith("PySide6."):
                raise ModuleNotFoundError("No module named 'PySide6'", name="PySide6")
            return real(name, *args, **rest)

        return mock.patch.object(builtins, "__import__", absent)

    def test_it_refuses_rather_than_ship_an_editor_with_no_window(self):
        """The Tk window is on its way out: a build without PySide6 would
        carry nothing worth releasing."""
        from fm_editor import build_exe
        said = io.StringIO()
        with self.without_pyside(), mock.patch.object(sys, "argv", ["build_exe.py"]), \
             mock.patch("sys.stderr", said):
            self.assertEqual(build_exe.main(), 1)
        self.assertIn("PySide6 is not installed", said.getvalue())
        self.assertIn("pip install PySide6", said.getvalue())

    def test_without_qt_is_how_to_ask_for_the_old_window_alone(self):
        from fm_editor import build_exe
        said = io.StringIO()
        with tempfile.TemporaryDirectory() as dist, self.without_pyside(), \
             mock.patch.object(sys, "argv", ["build_exe.py", "--without-qt", "--dist", dist]), \
             mock.patch("sys.stderr", said), \
             mock.patch("subprocess.run", return_value=mock.Mock(returncode=1)):
            self.assertEqual(build_exe.main(), 1)      # it went on to the build
        self.assertIn("PySide6 is not installed", said.getvalue())
