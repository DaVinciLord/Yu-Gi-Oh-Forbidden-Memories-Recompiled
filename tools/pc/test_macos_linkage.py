#!/usr/bin/env python3
"""Verify real Mach-O architecture, linkage and installed font rendering."""
import argparse
from pathlib import Path
import subprocess
import re
from macos_deps import ROOT, INSTALL, ensure, sdk_path
from llvm_guest import compiler, toolchain


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, default=ROOT / 'tmp/pc/macos-local-deps/memories-arm64')
    args = parser.parse_args()
    ensure()
    for name in ('libSDL3.a', 'libfreetype.a', 'libpng16.a', 'libz.a', 'libzstd.a'):
        archive = INSTALL / 'lib' / name
        arch = subprocess.check_output(['lipo', '-archs', str(archive)], text=True).strip()
        assert arch == 'arm64', f'{archive}: wrong architectures: {arch}'
    for binary in (args.binary.resolve(), compiler()):
        commands = subprocess.check_output(['otool', '-l', str(binary)], text=True)
        rpaths = re.findall(r'cmd LC_RPATH\s+cmdsize \d+\s+path (.*?) \(offset', commands)
        lines = subprocess.check_output(['otool', '-L', str(binary)], text=True).splitlines()[1:]
        for line in lines:
            dependency = line.strip().split(' (')[0]
            if dependency.startswith(('/System/Library/', '/usr/lib/')): continue
            if dependency.startswith('@loader_path/'):
                resolved = (binary.parent / dependency.removeprefix('@loader_path/')).resolve()
                assert resolved.is_relative_to(toolchain()) and resolved.is_file(), dependency
                continue
            if dependency.startswith('@rpath/'):
                candidates = [Path(path.replace('@loader_path', str(binary.parent))) / dependency.removeprefix('@rpath/')
                              for path in rpaths]
                assert any(path.resolve().is_relative_to(toolchain()) and path.is_file() for path in candidates), dependency
                continue
            raise AssertionError(f'{binary}: unexpected runtime dependency {dependency}')
    test = ROOT / 'tmp/pc/macos-fonts-test'
    command = [str(toolchain() / 'bin/clang'), '-isysroot', str(sdk_path()), '-Wall', '-Wextra', '-Werror',
               '-Isrc', '-I' + str(INSTALL / 'include/freetype2'), 'tests/pc/macos_fonts_test.c',
               'src/pc/platform/macos_fonts.c', str(INSTALL / 'lib/libfreetype.a'),
               '-framework', 'CoreText', '-framework', 'CoreFoundation', '-o', str(test)]
    subprocess.run(command, cwd=ROOT, check=True)
    subprocess.run([str(test)], check=True)
    print('macOS static library architectures, system/local runtime linkage and fonts passed')


if __name__ == '__main__':
    main()
