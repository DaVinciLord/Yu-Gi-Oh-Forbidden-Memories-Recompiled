#!/usr/bin/env python3
"""Headless native ARM64 gameplay checks using a user-owned retail disc.

Exercises real name entry, campaign, deck menu and card animations. It uses
controller inputs, never writes gameplay RAM, and keeps all saves/art in tmp.
Build with tools/pc/build_arm64.py first. No window/audio cadence is measured.
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]
CASES = ('fusion-failure', 'fusion', 'equip', 'magic', 'victory', 'free-duel',
         'deck-editor', 'deck-editor-free-duel', 'animated-battle', 'trap', 'trap-threshold',
         'ritual', 'ritual-failure', 'ritual-retail')

def retail_ritual_inputs():
    events = [(int(part.split(':')[0]), part.split(':')[1]) for part in ritual_inputs().split(',')]
    # The unmodified recipe needs Gaia, Kuriboh and Beaver Warrior. The
    # latter two are in hand slot 3 on their respective turns in this deck.
    events += [(13900,'0020'), (13906,'0000'), (18900,'0020'), (18906,'0000')]
    return ','.join(f'{f}:{b}' for f,b in sorted(events))

def check_retail_ritual_recipe(disc):
    from fm_editor.disc import DiscImage
    from fm_editor.gamedata import decode_rituals, TERRAIN_BASE, TERRAIN_STRIDE, RITUAL_OFFSET, RITUAL_LENGTH
    with DiscImage(disc) as image:
        lba, _ = image.find('DATA/WA_MRG.MRG')
        for terrain in range(7):
            offset = TERRAIN_BASE + terrain*TERRAIN_STRIDE + RITUAL_OFFSET
            recipe = decode_rituals(image.read(lba + offset//2048, RITUAL_LENGTH))[670]
            assert recipe == (27,38,58,364), f'unexpected retail ritual recipe: {recipe}'

def ritual_inputs(failure=False):
    events = [(int(part.split(':')[0]), part.split(':')[1])
              for part in inputs(magic=True).split(',') if int(part.split(':')[0]) < 10200]
    events += [(11000, '0008')]
    if failure:
        # Slot 1 holds the ritual; one tribute cannot satisfy three slots.
        events += [(13800,'0020'), (14000,'4000'), (14400,'4000')]
    else:
        # Slot 2 holds a monster on the next two turns. Place each in a
        # different field column, then play the ritual from hand slot 0.
        events += [(13600,'0020'), (13800,'0020'), (14000,'4000'),
                   (14400,'4000'), (14700,'0020'), (15000,'4000'),
                   (15400,'4000'), (17000,'0008'), (18600,'0020'),
                   (18800,'0020'), (19000,'4000'), (19400,'4000'),
                   (19600,'0020'), (19800,'0020'), (20000,'4000'),
                   (20400,'4000'), (22000,'0008'), (24000,'4000'),
                   (24800,'4000'), (26000,'4000'), (26500,'4000')]
    events += [(f+6,'0000') for f, _ in list(events) if f >= 11000]
    return ','.join(f'{f}:{b}' for f, b in sorted(events))

def animated_battle_inputs():
    events = [(int(part.split(':')[0]), part.split(':')[1])
              for part in inputs().split(',') if int(part.split(':')[0]) < 7100]
    # Cast Tremendous Fire, let the CPU summon and attack, then summon
    # Man-eating Plant. Move across the field until Square selects its foe.
    events += [(7200,'2000'), (8000,'0020'), (8400,'4000'),
               (9000,'4000'), (9600,'4000'), (10200,'4000'),
               (11000,'0008'), (14000,'4000'), (14400,'4000'),
               (15000,'4000'), (15400,'4000'), (18000,'4000'),
               (18400,'8000'), (18600,'0020'), (18800,'8000'),
               (19000,'0020'), (19200,'8000'), (19400,'0020'),
               (19600,'8000'), (19800,'0020'), (20000,'8000')]
    events += [(f+6,'0000') for f, _ in list(events) if f >= 7100]
    return ','.join(f'{f}:{b}' for f,b in sorted(events))

def deck_editor_inputs():
    events = [(int(part.split(':')[0]), part.split(':')[1])
              for part in inputs().split(',') if int(part.split(':')[0]) < 7100]
    # Cycle every order in both panes, including shuffle, then remove a card.
    events += [(7100, '0020'), (7160, '0001'), (7230, '0008')]
    events += [(f, '0008') for f in range(7300, 8700, 200)]
    events += [(8700, '4000'), (8900, '0008'), (9100, '0080')]
    events += [(f, '0008') for f in range(9300, 10700, 200)]
    events += [(10600, '0001'), (10650, '0008')]
    # Card 24 was removed from the ID-sorted deck. Find it in the chest,
    # inspect it, return it to the deck, exercise page buttons and leave.
    events += [(f, '0040') for f in range(10700, 11850, 50)]
    events += [(12000, '1000'), (12400, '2000'), (12800, '4000'),
               (13200, '0020'), (13600, '0800'), (14000, '0400'),
               (14400, '0200'), (14800, '0100'), (15200, '2000'),
               (15900, '4000'), (16300, '4000')]
    events += [(f+6, '0000') for f, _ in list(events) if f >= 7100]
    return ','.join(f'{f}:{b}' for f, b in sorted(events))

def inputs(third=False, magic=False):
    events = [(700, '0008'), (800, '4000'), (950, '4000'),
              (1200, '4000'), (1300, '0008'), (1400, '4000'), (1550, '4000')]
    events += [(f, '4000') for f in range(1700, 7100, 100)]
    if magic:
        events += [(7200, '2000'), (8000, '4000'), (8400, '4000'),
                   (9000, '4000'), (9600, '4000'), (10200, '4000')]
        events += [(f+6, '0000') for f, _ in list(events)]
        return ','.join(f'{f}:{b}' for f, b in sorted(events))
    events += [(7200, '2000'), (8000, '0010'), (8200, '0020')]
    if third: events += [(8300, '0020')]
    events += [(8400, '0010'), (8600, '4000'), (9000, '4000'),
               (9600, '4000'), (10200, '4000')]
    events += [(f+6, '0000') for f, _ in list(events)]
    return ','.join(f'{f}:{b}' for f, b in sorted(events))

def run(case, disc, binary, output, language=0, state_frame=None):
    folder = output/case
    mods = folder/'mods'; mods.mkdir(parents=True, exist_ok=True)
    if case in ('equip', 'magic', 'victory', 'animated-battle', 'trap', 'trap-threshold',
                'ritual', 'ritual-failure', 'ritual-retail'):
        fixture = mods/'starter'; fixture.mkdir(exist_ok=True)
        manifest = {
            'id': 'arm64-mechanics', 'name': 'ARM64 mechanics fixture',
            'version': '1', 'enabled': True,
            'starter': ({'name': 'Equip fixture', '75': 20, '657': 20} if case == 'equip'
                        else {'name': 'Damage fixture', '347': 40})}
        if case == 'animated-battle':
            manifest['starter'] = {'name': 'Battle fixture', '75': 20, '347': 20}
        if case.startswith('trap'):
            manifest['starter'] = {'name': 'Trap fixture', '686' if case == 'trap' else '681': 40}
        if case == 'trap-threshold':
            manifest['decks'] = {'all': {'fixed': True, '75': 40}}
        if case.startswith('ritual'):
            manifest['starter'] = {'name': 'Ritual fixture', '1': 30, '670': 10}
            manifest['rituals'] = [{'card': 670, 'tributes': [1, 1, 1], 'result': 364}]
            manifest['decks'] = {'all': {'fixed': True, '75': 40}}
        if case == 'ritual-retail':
            check_retail_ritual_recipe(disc)
            del manifest['rituals']
            manifest['starter'] = {'name': 'Retail ritual fixture', '27': 10, '38': 10, '58': 10, '670': 10}
            manifest['decks'] = {'all': {'fixed': True, '338': 40}}
        if case == 'victory': manifest['limits'] = {'life_points': {'opponent': 1000}}
        (fixture/'mod.json').write_text(json.dumps(manifest))
    env = {k:v for k,v in os.environ.items() if not k.startswith('MEMORIES_')}
    env.update(MEMORIES_HEADLESS='1', MEMORIES_NO_AUDIO='1',
               MEMORIES_NO_GAMEPAD='1', MEMORIES_NO_UPDATE_CHECK='1',
               MEMORIES_SPEED='-1', MEMORIES_TRACE_GAMEPLAY='1', MEMORIES_LANGUAGE=str(language),
               MEMORIES_DISC=str(disc), MEMORIES_USER_DIR=str(folder/'user'),
               MEMORIES_MODS_DIR=str(mods), MEMORIES_INPUT=inputs(case == 'fusion', case in ('magic','victory')),
               MEMORIES_DUMP_FRAME='11500', MEMORIES_DUMP_PATH=str(folder/'end.ppm'))
    if case == 'animated-battle':
        env['MEMORIES_INPUT'] = animated_battle_inputs()
        env['MEMORIES_DUMP_FRAME'] = '32000'
    if case.startswith('trap'):
        # Stop confirming after the face-down trap is placed; selecting it
        # again consumes it. End the turn and let the CPU attack normally.
        env['MEMORIES_INPUT'] = ','.join(part for part in inputs(magic=True).split(',')
                                         if int(part.split(':')[0]) < 9600) + ',11000:0008,11006:0000'
        env['MEMORIES_DUMP_FRAME'] = '20000'
    if case.startswith('ritual'):
        env['MEMORIES_INPUT'] = retail_ritual_inputs() if case == 'ritual-retail' else ritual_inputs(case == 'ritual-failure')
        env['MEMORIES_DUMP_FRAME'] = '16000' if case == 'ritual-failure' else '29000'
    if case.startswith('deck-editor'):
        env['MEMORIES_INPUT'] = deck_editor_inputs()
        env['MEMORIES_DUMP_FRAME'] = '16800'
        if case == 'deck-editor-free-duel':
            env['MEMORIES_MODE_AT'] = '1000:6'
            env['MEMORIES_INPUT'] = ','.join(part for part in env['MEMORIES_INPUT'].split(',')
                                           if int(part.split(':')[0]) < 15900)
            env['MEMORIES_DUMP_FRAME'] = '15600'
    if case == 'free-duel':
        events = [(f,'0040') for f in range(7600,8050,50)]
        events += [(f,'0020') for f in (8100,8150,8200,8250)]
        events += [(8500,'4000'),(8900,'2000'),(9400,'4000'),(9800,'4000'),(10400,'4000')]
        events += [(f+6,'0000') for f,_ in list(events)]
        env['MEMORIES_INPUT'] = inputs().split(',8000:')[0]+','+','.join(f'{f}:{b}' for f,b in sorted(events))
        env['MEMORIES_MODE_AT'] = '1000:6'
    log = folder/'run.log'
    if state_frame is not None:
        assert 30 < state_frame < int(env['MEMORIES_DUMP_FRAME'])
        env['MEMORIES_SAVE_STATE'] = f'{state_frame}:{folder / "replay.state"}'
    with log.open('w') as stream:
        subprocess.run([str(binary)], cwd=ROOT,
                       env=env, stdout=stream, stderr=subprocess.STDOUT,
                       check=True, timeout=240)
    text = log.read_text()
    if state_frame is not None:
        replay = env.copy()
        replay.pop('MEMORIES_SAVE_STATE')
        replay['MEMORIES_LOAD_STATE'] = str(folder / 'replay.state')
        replay['MEMORIES_INPUT'] = ','.join(
            f'{int(part.split(":")[0]) - state_frame + 30}:{part.split(":")[1]}'
            for part in env['MEMORIES_INPUT'].split(',') if int(part.split(':')[0]) > state_frame)
        replay['MEMORIES_DUMP_FRAME'] = str(int(env['MEMORIES_DUMP_FRAME']) - state_frame + 30)
        replay['MEMORIES_DUMP_PATH'] = str(folder / 'replay.ppm')
        with (folder / 'replay.log').open('w') as stream:
            subprocess.run([str(binary)], cwd=ROOT, env=replay, stdout=stream,
                           stderr=subprocess.STDOUT, check=True, timeout=240)
        assert 'ARM64 state loading:' in (folder / 'replay.log').read_text()
        assert (folder / 'end.ppm').read_bytes() == (folder / 'replay.ppm').read_bytes(), f'{case}: state replay pixels differ'
        print(f'{case}: fresh-process save-state replay pixels match', flush=True)
    assert (folder/'end.ppm').is_file(), f'{case}: no completed frame capture; {log}'
    for failure in ('cannot run;', 'using the native stand-in', 'unimplemented game routine'):
        assert failure not in text, f'{case}: gameplay used a fallback: {failure}; {log}'
    if case.startswith('ritual'):
        ending = text[text.index('gameplay frame=' + ('15960' if case == 'ritual-failure' else '28920')):]
        assert 'duel phase=8005 action=83 side=0' in ending, f'{case}: no return to field; {log}'
        if case == 'ritual-failure':
            assert 'duel field= 5:1/3000/2500/0/0\n' in ending
            assert 'hand=670,0,1,1,1' in ending and ':364/' not in text
        elif case == 'ritual-retail':
            field_lines = [line for line in text.splitlines() if line.startswith('duel field=')]
            assert any(set(re.findall(r' \d+:(\d+)/', line)) == {'27','38','58'}
                       for line in field_lines), f'retail tributes not established; {log}'
            assert 'duel field= 5:364/3000/2500/0/0\n' in ending
            assert 'hand=0,670,38,58,670' in ending and 'LP=8000/8000' in ending
        else:
            assert any(len(re.findall(r' \d+:1/', line)) == 3 for line in text.splitlines()
                       if line.startswith('duel field=')), f'three distinct tributes not established; {log}'
            assert 'duel field= 7:364/3000/2500/0/0\n' in ending, f'ritual result/tribute removal incorrect; {log}'
            assert 'hand=0,670,1,1,670' in ending
        print(f'{case}: ritual conditions, card consumption and return to field passed; {log}', flush=True)
        return
    if case.startswith('trap'):
        ending = text[text.index('gameplay frame=19920'):]
        expected = (('traps=1/0', 'LP=8000/8000', 'duel backrow=\n', 'duel opponent=\n')
                    if case == 'trap' else ('traps=0/0', 'LP=7200/8000',
                                           'duel backrow= 10:681/', 'duel opponent= 20:75/'))
        for evidence in ('duel phase=8004', 'turns=1/1', *expected):
            assert evidence in ending, f'{case}: missing {evidence!r}; {log}'
        assert f'duel backrow= 10:{686 if case == "trap" else 681}/' in text
        print(f'{case}: trap placement, attack threshold, counters, LP and return to hand passed; {log}', flush=True)
        return
    if case == 'animated-battle':
        start = text.index('mode=c1')
        ending = text[start:]
        for evidence in ('mode=c3 sub=81', 'LP=7700/6500',
                         'turns=1/1', 'duel phase=8005 action=83 side=0',
                         '5:75/800/600/0/0'):
            assert evidence in ending, f'{case}: missing {evidence!r} after 3D entry; {log}'
        print(f'{case}: 3D animation, damage and return to field passed; {log}', flush=True)
        return
    if case.startswith('deck-editor'):
        for pane in (0, 1):
            for choice in range(7):
                assert f'decklist pane={pane} sort={choice} ' in text, f'missing pane {pane} sort {choice}: {log}'
        ending = (('gameplay frame=15480 mode=c6',) if case == 'deck-editor-free-duel' else
                  ('gameplay frame=16680 mode=c3 sub=81',
                   'duel phase=8004 action=84 side=0 LP=8000/8000'))
        for evidence in ('deck=39 chest=1', 'effect=130', 'first=16 target=16 cursor=7 card=24',
                         'first=32 target=32', *ending):
            assert evidence in text, f'{case}: missing {evidence!r}; {log}'
        assert 'deck=40 chest=0 effect=0' in text[text.index('deck=39 chest=1'):], f'deck not restored: {log}'
        print(f'{case}: all sorts, panes, paging, card viewer, remove/add and exit passed; {log}', flush=True)
        return
    if case == 'victory':
        for evidence in ('LP=8000/0', 'duel phase=800d', 'mode=c2 sub=02 scene=96',
                         'inventory chest=1 starchips=5'):
            assert evidence in text, f'{case}: missing {evidence!r}; {log}'
        print(f'victory: results, reward and campaign dialogue passed; {log}', flush=True)
        return
    assert 'gameplay frame=11400 mode=c3 sub=81' in text, f'{case}: did not remain in duel; {log}'
    if case == 'free-duel':
        assert 'duel phase=8008 action=83 side=0 LP=8000/8000' in text, f'{case}: no guardian-star selection; {log}'
        print(f'free-duel: grid movement, deck menu, Duel Master K and guardian-star selection passed; {log}', flush=True)
        return
    life = '8000/7000' if case == 'magic' else '8000/8000'
    assert f'duel phase=8005 action=83 side=0 LP={life}' in text, f'{case}: no return to player field with expected LP; {log}'
    expected = {
        'fusion-failure': ('fusions=0/0 equips=0/0', '5:549/700/500/0/0'),
        'fusion': ('fusions=1/0 equips=0/0', '5:487/1800/1400/0/0'),
        'equip': ('fusions=0/0 equips=1/0', '5:75/800/600/1000/0'),
        'magic': ('magic=1/0', 'hand=0,347,347,347,347'),
    }[case]
    for evidence in expected:
        assert evidence in text, f'{case}: missing {evidence!r}; {log}'
    print(f'{case}: card animations, counters, field card and statistics passed; {log}', flush=True)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--disc', type=Path, default=ROOT/'game/YGOFM Vanilla (Base).bin')
    p.add_argument('--case', choices=CASES)
    p.add_argument('--binary', type=Path, default=ROOT/'tmp/arm64-build/memories-arm64')
    p.add_argument('--output', type=Path, default=ROOT/f'tmp/arm64-gameplay/run-{os.getpid()}')
    p.add_argument('--language', type=int, choices=range(6), default=0)
    p.add_argument('--state-frame', type=int, help='Save here and replay the remaining inputs in a fresh process')
    args = p.parse_args()
    disc = args.disc.resolve()
    if not disc.is_file(): p.error('a user-owned retail disc is required')
    binary = args.binary.resolve()
    if not binary.is_file(): p.error('build the requested executable first')
    for case in ([args.case] if args.case else CASES):
        run(case, disc, binary, args.output.resolve(), args.language, args.state_frame)
if __name__ == '__main__': main()
