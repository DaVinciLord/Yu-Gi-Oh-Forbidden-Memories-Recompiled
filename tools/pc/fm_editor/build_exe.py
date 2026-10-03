#!/usr/bin/env python3
"""Build the editor as a program of its own with PyInstaller.

    python -m pip install pyinstaller
    python tools/pc/fm_editor/build_exe.py [--dist tmp/pc/fm-editor] [--version v0.1.3]

Writes <dist>/fm-editor, a program that needs no Python on the player's
machine. On Windows that is fm-editor.exe, fm-editor.pkg and
fm-editor-files/, which stay together; elsewhere one file. The build files stay under <dist>; nothing it writes
belongs in git.

Windows gets no one-file build: that is a small loader with the whole
program appended, unpacked to a temporary folder on every start, which is
what droppers look like to virus scanners (Defender flagged it as
Trojan:Win32/Wacatac.B!ml). The folder build carries version information
too, which scanners also like to see.
"""
import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def version_info(label: str) -> str:
    """A PyInstaller version file for fm-editor.exe."""
    match = re.match(r"v(\d+)\.(\d+)\.(\d+)", label)
    numbers = tuple(int(n) for n in match.groups()) + (0,) if match else (0, 0, 0, 0)
    text = label or "development build"
    strings = {"CompanyName": "Yu-Gi-Oh! Forbidden Memories Recompiled",
               "FileDescription": "FM Editor (Yu-Gi-Oh! Forbidden Memories Recompiled mod editor)",
               "FileVersion": text, "InternalName": "fm-editor", "OriginalFilename": "fm-editor.exe",
               "ProductName": "Yu-Gi-Oh! Forbidden Memories Recompiled", "ProductVersion": text,
               "Comments": "https://github.com/Unchiga/Yu-Gi-Oh-Forbidden-Memories-Recompiled"}
    entries = ",\n".join(f"          StringStruct({key!r}, {value!r})" for key, value in strings.items())
    return f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={numbers}, prodvers={numbers}, mask=0x3f, flags=0x0, OS=0x40004,
                    fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
{entries}])]),
    VarFileInfo([VarStruct('Translation', [0x0409, 1200])])
  ]
)
"""


def say(text):
    """Print a line that may hold letters the console cannot encode. CI builds
    under a path like "Jos\u00e9-\u00e9-\u042f-\u6771\u4eac-\U0001f600" and a cp1252 stdout would
    raise on it, which is no reason for a build to fail."""
    stream = sys.stdout
    encoding = getattr(stream, "encoding", None) or "utf-8"
    stream.write(text.encode(encoding, "replace").decode(encoding, "replace") + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dist", type=Path, default=ROOT / "tmp" / "pc" / "fm-editor")
    parser.add_argument("--console", action="store_true", help="keep a console window (for the command line)")
    parser.add_argument("--version", default="", help="the release, vX.Y.Z[-PRE], for the version information")
    parser.add_argument("--without-qt", action="store_true",
                        help="build without PySide6 installed: the old Tk window alone")
    arguments = parser.parse_args()
    try:
        import PySide6      # noqa: F401
    except ImportError:
        # The Qt window is the editor; the Tk one is on its way out. A build
        # without PySide6 here carries no window worth shipping, so say so
        # rather than hand over an editor that opens the old one.
        print("PySide6 is not installed: the build would carry no Qt window.\n"
              "    python -m pip install PySide6\n"
              "or pass --without-qt to build the old Tk window on its own.", file=sys.stderr)
        if not arguments.without_qt:
            return 1
    dist = arguments.dist.resolve()
    work = dist / "build"
    work.mkdir(parents=True, exist_ok=True)
    build = ["--noconfirm", "--clean", "--distpath", str(dist), "--workpath", str(work)]
    program = ["--name", "fm-editor", "--specpath", str(work), "--paths", str(HERE.parent),
               "--hidden-import", "text_listing", "--collect-submodules", "fm_editor",
               # The Qt window loads its forms beside itself at run time, so
               # they must be in the build and not only the modules.
               "--add-data", f"{HERE / 'ui'}{os.pathsep}fm_editor/ui"]
    if sys.platform == "win32":
        version_file = work / "version.txt"
        version_file.write_text(version_info(arguments.version), encoding="utf-8")
        program += ["--onedir", "--contents-directory", "fm-editor-files", "--version-file", str(version_file)]
    else:
        program.append("--onefile")
    if not arguments.console:
        program.append("--windowed")
    program.append(str(HERE / "__main__.py"))
    makespec = [sys.executable, "-m", "PyInstaller.utils.cliutils.makespec", *program]
    say(" ".join(makespec))
    if subprocess.run(makespec, cwd=str(ROOT)).returncode != 0:
        return 1
    spec = work / "fm-editor.spec"
    text = spec.read_text()
    if sys.platform.startswith("linux"):
        # Tk draws text through fontconfig. The build machine's is older
        # than the player's and chokes on its config files; every desktop
        # has fontconfig and FreeType, so the player's are used.
        assert "\npyz = " in text, "unexpected PyInstaller spec"
        text = text.replace("\npyz = ", "\na.binaries = [b for b in a.binaries\n"
                            "              if not b[0].startswith(('libfontconfig', 'libfreetype'))]\npyz = ", 1)
    if sys.platform == "win32":
        # The Python archive as fm-editor.pkg beside the .exe: a folder
        # build still appends it to the loader by default.
        assert "    exclude_binaries=True,\n" in text, "unexpected PyInstaller spec"
        text = text.replace("    exclude_binaries=True,\n", "    exclude_binaries=True,\n    append_pkg=False,\n", 1)
    spec.write_text(text)
    command = [sys.executable, "-m", "PyInstaller", *build, str(spec)]
    say(" ".join(command))
    result = subprocess.run(command, cwd=str(ROOT))
    if result.returncode == 0:
        built = dist / "fm-editor" / "fm-editor.exe" if sys.platform == "win32" else dist / "fm-editor"
        print(f"built {built}")
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
