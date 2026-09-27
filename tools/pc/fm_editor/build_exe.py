#!/usr/bin/env python3
"""Build the editor as one executable with PyInstaller.

    python -m pip install pyinstaller
    python tools/pc/fm_editor/build_exe.py [--dist tmp/pc/fm-editor]

Writes <dist>/fm-editor(.exe), a program of its own beside the game: it
needs no Python on the player's machine. The build files stay under <dist>;
nothing it writes belongs in git.
"""
import argparse
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dist", type=Path, default=ROOT / "tmp" / "pc" / "fm-editor")
    parser.add_argument("--console", action="store_true", help="keep a console window (for the command line)")
    arguments = parser.parse_args()
    dist = arguments.dist.resolve()
    work = dist / "build"
    work.mkdir(parents=True, exist_ok=True)
    build = ["--noconfirm", "--clean", "--distpath", str(dist), "--workpath", str(work)]
    program = ["--onefile", "--name", "fm-editor", "--specpath", str(work), "--paths", str(HERE.parent),
               "--hidden-import", "text_listing", "--collect-submodules", "fm_editor"]
    if not arguments.console:
        program.append("--windowed")
    program.append(str(HERE / "__main__.py"))
    command = [sys.executable, "-m", "PyInstaller", *build, *program]
    if sys.platform.startswith("linux"):
        # Tk draws text through fontconfig. The build machine's is older
        # than the player's and chokes on its config files; every desktop
        # has fontconfig and FreeType, so the player's are used.
        makespec = [sys.executable, "-m", "PyInstaller.utils.cliutils.makespec", *program]
        print(" ".join(makespec))
        if subprocess.run(makespec, cwd=str(ROOT)).returncode != 0:
            return 1
        spec = work / "fm-editor.spec"
        text = spec.read_text()
        assert "\npyz = " in text, "unexpected PyInstaller spec"
        text = text.replace("\npyz = ", "\na.binaries = [b for b in a.binaries\n"
                            "              if not b[0].startswith(('libfontconfig', 'libfreetype'))]\npyz = ", 1)
        spec.write_text(text)
        command = [sys.executable, "-m", "PyInstaller", *build, str(spec)]
    print(" ".join(command))
    result = subprocess.run(command, cwd=str(ROOT))
    if result.returncode == 0:
        suffix = ".exe" if sys.platform == "win32" else ""
        print(f"built {dist / ('fm-editor' + suffix)}")
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
