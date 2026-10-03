"""Which window the command line opens.

    python -m unittest discover -s tools/pc/fm_editor/tests -t tools/pc
"""
import builtins
import contextlib
import io
import tempfile
import sys
import unittest
from unittest import mock

from fm_editor import cli

# Both windows are optional: a runner may have PySide6, Tk, or neither, and a
# test that patches a window that is not installed would raise rather than skip.
try:
    import PySide6     # noqa: F401
    HAS_QT = True
except ImportError:
    HAS_QT = False
try:
    import tkinter     # noqa: F401
    HAS_TK = True
except ImportError:
    HAS_TK = False


def patched(target, which, label):
    """Patch a window's main(), or nothing at all where it is not installed."""
    if (label == "qt" and not HAS_QT) or (label == "tk" and not HAS_TK):
        return contextlib.nullcontext()
    return mock.patch(target, lambda game, mod: (which.setdefault("w", label), 0)[1])


class WindowTest(unittest.TestCase):
    def opened(self, argv):
        """Which window `argv` would open, without opening one."""
        which = {}
        with patched("fm_editor.pyside_app.main", which, "qt"), \
             patched("fm_editor.app.main", which, "tk"):
            self.assertEqual(cli.main(argv), 0)
        return which.get("w")

    @unittest.skipUnless(HAS_QT, "PySide6 is not installed")
    def test_the_qt_window_is_the_one_that_opens(self):
        self.assertEqual(self.opened([]), "qt")
        self.assertEqual(self.opened(["--mod", "somewhere"]), "qt")

    @unittest.skipUnless(HAS_TK, "tkinter is not installed")
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

    @unittest.skipUnless(HAS_TK, "tkinter is not installed")
    def test_without_pyside_the_old_one_opens_instead(self):
        """An optional dependency: the editor still runs without it, and says
        so rather than showing a ModuleNotFoundError."""
        said = io.StringIO()
        which = {}
        with self.without_pyside(), \
             patched("fm_editor.app.main", which, "tk"), \
             mock.patch("sys.stderr", said):
            self.assertEqual(cli.main([]), 0)
        self.assertEqual(which.get("w"), "tk")
        self.assertIn("could not start", said.getvalue())
        self.assertIn("pip install PySide6", said.getvalue())
        self.assertNotIn("Traceback", said.getvalue())

    @unittest.skipUnless(HAS_TK, "tkinter is not installed")
    def test_a_built_editor_says_nothing_about_pip(self):
        """It carries its own Python: there is nothing to install into."""
        said = io.StringIO()
        which = {}
        with self.without_pyside(), \
             mock.patch.object(sys, "frozen", True, create=True), \
             patched("fm_editor.app.main", which, "tk"), \
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
             mock.patch("sys.stderr", said), mock.patch("sys.stdout", io.StringIO()):
            self.assertEqual(build_exe.main(), 1)
        self.assertIn("PySide6 is not installed", said.getvalue())
        self.assertIn("pip install PySide6", said.getvalue())

    def test_a_broken_qt_falls_back_rather_than_aborting(self):
        """Qt wants system libraries of its own; without one it raises
        something that is not an ImportError, and a player should still get
        the old window."""
        said = io.StringIO()
        which = {}
        def explode(name, *args, **rest):
            if "pyside_app" in name:
                raise RuntimeError("libxcb-cursor0: cannot open shared object file")
            return self._real_import(name, *args, **rest)
        self._real_import = builtins.__import__
        with mock.patch.object(builtins, "__import__", explode), \
             patched("fm_editor.app.main", which, "tk"), \
             mock.patch("sys.stderr", said):
            self.assertEqual(cli.main([]), 0)
        self.assertEqual(which.get("w"), "tk")
        self.assertIn("libxcb-cursor0", said.getvalue())

    def test_without_qt_is_how_to_ask_for_the_old_window_alone(self):
        from fm_editor import build_exe
        said = io.StringIO()
        with tempfile.TemporaryDirectory() as dist, self.without_pyside(), \
             mock.patch.object(sys, "argv", ["build_exe.py", "--without-qt", "--dist", dist]), \
             mock.patch("sys.stderr", said), mock.patch("sys.stdout", io.StringIO()), \
             mock.patch("subprocess.run", return_value=mock.Mock(returncode=1)):
            self.assertEqual(build_exe.main(), 1)      # it went on to the build
        self.assertIn("PySide6 is not installed", said.getvalue())

    def test_the_build_prints_a_path_a_cp1252_console_cannot_encode(self):
        """CI builds under Jos\u00e9-\u00e9-\u042f-\u6771\u4eac-\U0001f600; the print must not end the build."""
        from fm_editor import build_exe
        narrow = io.TextIOWrapper(io.BytesIO(), encoding="cp1252", errors="strict")
        with mock.patch("sys.stdout", narrow):
            build_exe.say("makespec /tmp/Jos\u00e9-\u00e9-\u042f-\u6771\u4eac-\U0001f600/build")
        narrow.seek(0)
        self.assertIn("makespec", narrow.buffer.getvalue().decode("cp1252"))
