#!/usr/bin/env python3
"""Launch the experimental macOS ARM64 build with isolated user settings."""
import argparse
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--disc', type=Path, default=ROOT / 'game/YGOFM Vanilla (Base).bin')
    parser.add_argument('--headless', action='store_true')
    parser.add_argument('--frames', type=int, help='dump a frame and exit (validation only)')
    parser.add_argument('--input', help='scripted pad input in the existing frame:hex format')
    args = parser.parse_args()
    binary = ROOT / 'tmp/arm64-build/memories-arm64'
    if not binary.is_file():
        parser.error('build first with python3 tools/pc/build_arm64.py')
    if not args.disc.is_file():
        parser.error('provide the user-owned USA disc with --disc')
    if args.frames is not None and args.frames <= 0:
        parser.error('--frames must be positive')
    env = {**os.environ, 'MEMORIES_DISC': str(args.disc.resolve()),
           'MEMORIES_USER_DIR': str(ROOT / 'tmp/arm64-build/user'),
           'MEMORIES_NO_UPDATE_CHECK': '1'}
    if args.headless:
        env['MEMORIES_HEADLESS'] = '1'
    else:
        env.pop('MEMORIES_HEADLESS', None)
    if args.frames:
        env['MEMORIES_DETERMINISTIC'] = '1'
        env['MEMORIES_DUMP_FRAME'] = str(args.frames)
        env['MEMORIES_DUMP_PATH'] = str(ROOT / f'tmp/arm64-build/frame{args.frames}.ppm')
    if args.input:
        env['MEMORIES_INPUT'] = args.input
    return subprocess.call([str(binary)], cwd=ROOT, env=env)


if __name__ == '__main__':
    raise SystemExit(main())
