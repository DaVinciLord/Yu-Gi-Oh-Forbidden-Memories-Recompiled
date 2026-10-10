#!/usr/bin/env python3
"""Retail-disc regression: packaged 3D Monsters loads and renders on the field."""
import argparse
import json
import shutil
import statistics
import struct
import time
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
    parser.add_argument('--texture-mod', type=Path, help='optional local HD texture mod directory')
    parser.add_argument('--timing-batches', type=int, default=5, help='120-frame batches per warmed stress scene')
    parser.add_argument('--stress', action='store_true', help='inject 1, 3, 4, 5 and 10 different face-up monsters into the isolated duel')
    args = parser.parse_args()
    if args.timing_batches < 1:
        parser.error('--timing-batches must be positive')
    mods = args.mods
    if args.texture_mod:
        if not (args.texture_mod / 'mod.json').is_file():
            parser.error('--texture-mod must contain mod.json')
        mods = args.output / 'mods'
        if mods.exists():
            parser.error('use a fresh --output directory for the texture-mod test')
        shutil.copytree(args.mods, mods)
        (mods / 'assets-hd').symlink_to(args.texture_mod.resolve(), target_is_directory=True)
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
            if enabled and args.stress:
                original = game.peek('D_801A7AD8', 30 * 28)
                slots = [*range(5, 10), *range(20, 25)]
                cards = [613, 1, 425, 11, 2, 3, 4, 5, 6, 7]
                timings = []
                for count in (1, 3, 4, 5, 10):
                    records = bytearray(original)
                    for index, slot in enumerate(slots):
                        struct.pack_into('<h', records, slot * 28 + 12, cards[index] if index < count else 0)
                        struct.pack_into('<H', records, slot * 28 + 22, 0x8000 if index < count else 0)
                    game.poke('D_801A7AD8', records)
                    game.step(30)  # exclude initial disc reads from the steady measurement
                    samples = []
                    for _ in range(args.timing_batches):
                        started = time.perf_counter()
                        game.step(120)  # one command; no waits between individual frames
                        samples.append((time.perf_counter() - started) * 1000 / 120)
                    # Batch timings measure throughput, not individual-frame
                    # percentiles or the game's paced FPS counter.
                    result = {'monsters': count, 'ms_per_frame': statistics.median(samples),
                              'batch_ms_per_frame': samples}
                    timings.append(result)
                    print(result, flush=True)
                    game.shot(f'field-{count}.png')
                (folder / 'timings.json').write_text(json.dumps(timings, indent=2) + '\n')
        log = (folder / 'game.log').read_text()
        loaded = 'card 613 stance 0 loaded' in log
        assert loaded == bool(enabled), f'3D model load differs from mod state: {folder}'
    assert pictures[0] != pictures[1], 'enabling 3D Monsters did not change the field image'
    print(f'3D Monsters: real fusion, disc model load and field image change passed; {args.output}')


if __name__ == '__main__':
    main()
