#!/usr/bin/env python3
"""Retail-disc regression: packaged 3D Monsters loads and renders on the field."""
import argparse
from pathlib import Path

from yfm_control import Game

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--mods', type=Path, required=True)
    parser.add_argument('--disc', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=ROOT / 'tmp/3d-monsters-regression')
    parser.add_argument('--window', action='store_true', help='show a real 4x macOS window')
    args = parser.parse_args()
    mods = args.mods
    env = {'MEMORIES_DISC': str(args.disc.resolve()), 'MEMORIES_TRACE': 'mods',
           'MEMORIES_SPEED': '-1', 'MEMORIES_PAUSE_ON_FOCUS_LOSS': '0'}
    if args.window:
        env.update(MEMORIES_INTERNAL_SCALE='4', MEMORIES_HD_TEXT='1', MEMORIES_NO_AUDIO='1')
    pictures = []
    for enabled in (0, 1):
        folder = args.output / ('on' if enabled else 'off')
        # Same real fusion and field camera, with only this mod changing.
        with Game(args.binary, out=folder, mods_dir=mods, headless=not args.window,
                  settings={'mod.3d-monsters': enabled, 'mod.hand-camera': 0,
                            'mod.ai-hard-mode': 0, 'mod.yamyi-mods': 0,
                            'mod.drop-missing-cards': 0},
                  env=env) as game:
            game.wait_until(lambda g: g.resident('main_menu'), 3000)
            game.goto('duel', opponent=1, deck='425,425,337,330,339,1,1,1')
            game.duel_ready(before_deal=lambda g: g.arrange_deck(0, [425,425,337,330,339]))
            game.fuse([0, 1], face_up=True)
            game.end_turn()
            game.wait_turn()
            game.press('circle', after=90)
            assert game.u16(0x800F284C) < 512, 'camera did not return above the field'
            pictures.append(game.shot('terrain.png').read_bytes())
        log = (folder / 'game.log').read_text()
        loaded = 'card 613 stance 0 loaded' in log
        assert loaded == bool(enabled), f'3D model load differs from mod state: {folder}'
    assert pictures[0] != pictures[1], 'enabling 3D Monsters did not change the field image'
    print(f'3D Monsters: real fusion, disc model load and field image change passed; {args.output}')


if __name__ == '__main__':
    main()
