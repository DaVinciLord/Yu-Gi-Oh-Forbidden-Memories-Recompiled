#!/usr/bin/env python3
"""Build unchanged pinned SDL3 statically for macOS arm64 in repository tmp.

Prerequisite: python3 -m pip install --target tmp/pc/native-tools cmake ninja
No global installation, downloads, or SDL source edits are performed here.
"""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tmp/pc/native-tools"
CMAKE = TOOLS / "cmake/data/bin/cmake"
NINJA = TOOLS / "bin/ninja"
BUILD = ROOT / "tmp/pc/sdl-arm64/build"
INSTALL = ROOT / "tmp/pc/sdl-arm64/install"


def main():
    if not CMAKE.exists() or not NINJA.exists():
        raise SystemExit("Install isolated cmake/ninja wheels as documented above")
    subprocess.run([str(CMAKE), "-S", str(ROOT / "tmp/pc/sdl-source/SDL3-3.4.16"), "-B", str(BUILD), "-G", "Ninja", f"-DCMAKE_MAKE_PROGRAM={NINJA}", "-DCMAKE_OSX_ARCHITECTURES=arm64", "-DCMAKE_BUILD_TYPE=Release", f"-DCMAKE_INSTALL_PREFIX={INSTALL}", "-DSDL_STATIC=ON", "-DSDL_SHARED=OFF", "-DSDL_TESTS=OFF", "-DSDL_TEST_LIBRARY=OFF", "-DSDL_EXAMPLES=OFF", "-DSDL_INSTALL=ON"], check=True)
    subprocess.run([str(CMAKE), "--build", str(BUILD), "--parallel", "8"], check=True)
    subprocess.run([str(CMAKE), "--install", str(BUILD)], check=True)
    print(f"Native static SDL3: {INSTALL}")


if __name__ == "__main__":
    main()
