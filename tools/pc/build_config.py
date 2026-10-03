"""Shared game modules and native source selection for all PC targets."""
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
TARGETS = {
    'linux': {'architecture': 'i386', 'driver': 'build_game32.py', 'build': 'tmp/pc/game32', 'executable': 'memories-pc'},
    'windows': {'architecture': 'i686', 'driver': 'build_game32.py', 'build': 'tmp/pc/win32', 'executable': 'memories-pc.exe'},
    'macos': {'architecture': 'arm64', 'driver': 'build_arm64.py', 'build': 'tmp/pc/macos', 'executable': 'memories-arm64'},
}

def game_sources():
    """The same resident and overlay inventory for every PC architecture."""
    groups = {'resident': sorted(p.relative_to(ROOT).as_posix() for directory in ('src/game', 'src/pc/game')
                                 for p in (ROOT / directory).glob('*.c'))}
    groups.update((name, sorted(p.relative_to(ROOT).as_posix() for p in ROOT.glob(pattern)))
                  for name, pattern, _, _ in MODULES)
    return groups

BACKENDS = {"sdl": ["src/pc/platform/sdl.c", "src/pc/render/gl_picture.c", "src/pc/render/present_pass.c"],
            "x11": ["src/pc/platform/x11.c", "src/pc/platform/audio_alsa.c", "src/pc/platform/gamepad_evdev.c"]}

MODULES = [("main_menu", "src/overlays/main_menu/*.c", 0x0F, 0),
           ("password", "src/overlays/password/*.c", 0x15, 0x80168000),
           ("overworld", "src/overlays/overworld/*.c", 0x14, 0x80168000),
           ("free_duel", "src/overlays/free_duel/*.c", 0x13, 0x80168000),
           ("duel_effects", "src/overlays/duel_effects/*.c", 0x18, 0x80146000),
           ("credits", "src/overlays/credits/*.c", 0x10, 0x80180000)]

MODULE_CONFIG = {"overworld": "overworld_before_coup"}

GATED_MODULES = {"duel_effects", "credits"}

COMMON_FILES = ['rng.c','compat/fs.c','compat/gte.c','compat/pgxp.c','compat/libgs_ot.c',
                'render/packets.c','render/soft_gpu.c','render/texture_dump.c','render/texture_pack.c']
FIXED_MEMORY = {'src/pc/guest/resolve.c','src/pc/guest/image.c','src/pc/guest/branch_thunks.c','src/pc/guest/state.c'}

def native_sources(architecture, backend='sdl'):
    patterns = ['guest/*.c','sdk/*.c','platform/*.c','overlays/*.c','overrides/*.c','audio/*.c',
                'mods/*.c','debug/*.c','cards/*.c','free_duel/*.c','saves/*.c','text/*.c']
    sources = {str(p.relative_to(ROOT)).replace('\\','/') for pattern in patterns for p in (ROOT/'src/pc').glob(pattern)}
    sources |= {'src/pc/'+p for p in COMMON_FILES}
    backends = {source for files in BACKENDS.values() for source in files}
    sources -= backends
    if backend: sources.update(BACKENDS[backend])
    if architecture == 'arm64':
        sources -= FIXED_MEMORY
        sources.add('src/pc/memory.c')
        sources.update(str(p.relative_to(ROOT)) for p in (ROOT/'src/pc/guest').glob('translated*.S'))
    elif architecture in ('i386', 'i686'):
        sources.update(str(p.relative_to(ROOT)).replace('\\','/') for p in (ROOT/'src/pc/guest').glob('*.S'))
        sources = {s for s in sources if not s.startswith('src/pc/guest/translated') and s != 'src/pc/guest/state_translated.c'}
    else: raise ValueError('Unsupported PC architecture: '+architecture)
    return sorted(sources)
