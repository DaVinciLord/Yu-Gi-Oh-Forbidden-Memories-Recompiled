# Agent control and replays

Testing a change in the running game is too slow today, so it gets skipped,
and bugs reach players: mods built with the FM Editor broke in game in ways
no unit test saw. This is the plan for tools that let a test, or an agent,
drive the game completely, and that turn a bug report into a replay that
fails until the bug is fixed and is kept from then on.

Status: phase 1 steps 1 and 2 landed, step 5 as a first cut (see the
**Landed** notes under each); the rest is design. Each phase below lands
with its own code and updates this file.

## What exists

- **Before launch, environment variables decide everything:**
  - `MEMORIES_INPUT` is a pad script keyed to *presented* frames, which drifts when a load runs behind VBlanks;
  - `MEMORIES_MODE_AT` and `MEMORIES_TITLE_AT` jump scenes;
  - `MEMORIES_LOAD_STATE` and `MEMORIES_SAVE_STATE` load and save states;
  - `MEMORIES_DEBUG_DECK`, `MEMORIES_DEBUG_CHEST` and `MEMORIES_DEBUG_STARCHIPS` set up a save;
  - `MEMORIES_DUMP_FRAME` writes one picture, then exits;
  - `MEMORIES_FRAME_HASHES` writes a hash per presented frame.
- **Determinism:** a run was deterministic only with HEADLESS (or DETERMINISTIC) and DUMP_FRAME and SPEED=-1 together (`MEMORIES_DETERMINISTIC=1` alone since step 1 below).
  - The silent mixer thread still runs in real time, so the sound driver's work area (`g_SDValue`, `0x801E0384..0x801E1B44`) and the spu chunks differ between two runs.
- **No live channel:** no socket, no pipe, no recorder, and no way to read the game's state as data. Tests patch a state's `memory` chunk offline and read raw addresses. (Steps 2 and 5 below add the channel and its client; no recorder yet.)
- **Debug > Jump to** has only Title Screen.
- **Existing tests:** `tools/pc/smoke.py` (8 frame-hash cases) and `tools/pc/test_packs.py` (state patching) are the closest thing to replays. About 600 one-off agent scripts in `tmp/` repeat the same environment boilerplate, button macros, one-process-per-frame captures and RAM peeks.

## Phase 1: control and replays

### 1. One deterministic switch

`MEMORIES_DETERMINISTIC=1` alone gives the virtual clock, headless or
windowed, with no frame dump needed and no exit. Proven by the smoke hashes
staying the same and by two runs giving identical frame hashes. Stepping the
mixer by virtual time is a separate change; until then, RAM comparisons mask
`g_SDValue` and the spu, libspu, bss and data chunks.

**Landed** (`platform_common.c`, `virtual_clock()`). The old combination
(HEADLESS or DETERMINISTIC, with DUMP_FRAME and SPEED=-1) still selects it,
evaluated as before. In a window the virtual clock is shown at the game
speed: `pace()` sleeps before each VBlank until its real time at the speed
setting, and pause (P, focus loss) and frame step (`.`) hold or release the
next VBlank; neither changes what the game sees. Headless runs flat out
whatever the speed. The display's re-phasing of the VBlank at 100%
(`Platform_NotifyPresent`) is off under the virtual clock. Checked on
Windows, with the duel-hand-camera case's input through the first duel:
7000 frame hashes (3425 distinct) identical between two headless runs (one
under the crash monitor, one without), two windowed runs at SPEED=-1, the
first 1500 of a windowed run paced at 100%, and a run of the origin/master
build with the old combination; the eight smoke cases unchanged.

### 2. A control channel

- **Where:** a command loop serviced at `Memories_StatePoint` (the end of `VSync(0)`), the one point where the game's state is whole.
- **Transport:** TCP on localhost (`MEMORIES_CONTROL=port`). Not stdin: the game runs as a child of the crash monitor, and a socket also reaches an Android device through `adb forward`. Linux and Windows from the start.
- **Cost:** nothing when no controller is attached. A run without it is the same, bit for bit.
- **Lockstep:** while a controller is attached the game advances only when told to, and the freeze watchdog is off.
- **Commands** are line-based and kept dumb on purpose; no game knowledge goes in C:

| Command | Does |
|---|---|
| `step N` | run N VBlanks |
| `pad P BITS` | hold pad P's active-high bits from now on, read at each VBlank |
| `shot PATH` | write the presented picture as PNG, and keep running |
| `hash` | the VRAM hash of the last presented frame |
| `peek ADDR LEN` / `poke ADDR HEX` | guest memory |
| `save PATH` / `load PATH` | a save state |
| `info` | frame, VBlank, mode, build id |
| `quit` | exit |

**Landed** (`src/pc/debug/control.c`, `control_net.c`, `control_protocol.c`;
`tools/pc/yfm_control.py` is the client, section 5):

- **Where:** `Control_Point()`, called by `Memories_VSync` right after
  `Memories_StatePoint` at the end of every `VSync(0)`, whoever called it.
  Checked that it is reached often enough: with `step 1` from boot through
  the duel-hand-camera input to frame 7000 (title, new game, name entry, the
  story, the map and the first duel), every stop came one VBlank after the
  last, except in the opening logos and movie (mode byte 0, about frames
  316-600), where the game presents every 3 to 5 VBlanks and polls
  `VSync(-1)` between. No load ran past a VBlank without reaching it. So
  `step N` runs until at least N VBlanks have passed and stops at the next
  point; its reply says where (`ok frame F vblank V`). `save` and `load` are
  refused (`err not at a state point`) when that `VSync(0)` came from
  native code, as `Memories_StatePoint` refuses its own.
- **Transport:** `MEMORIES_CONTROL=port` listens on 127.0.0.1 only (0 lets
  the system pick; the port is logged). The listener opens at the first
  `VSync(0)` of the game process, so under the crash monitor it is the
  child's (checked with `netstat`: the listening PID is the game's, not the
  launched monitor's), and it works with `MEMORIES_NO_MONITOR=1`. Neither
  socket is inherited (`WSA_FLAG_NO_HANDLE_INHERIT`, `SOCK_CLOEXEC`), so a
  restart can listen again; Linux sends with `MSG_NOSIGNAL`. The game waits
  at its first `VSync(0)` for the first client, so a run is the client's
  from its first frame. A client that leaves (closes without `quit`) lets
  the game run on with its pads released; the next client stops it at the
  next point.
- **Lockstep:** while a client is attached the game runs only for a `step`.
  The watchdog is off (`Platform_ControlAttach`: the Windows stall
  reporter, the Linux interrupt watchdog and the crash monitor's freeze
  check), and the time the client takes counts for nothing
  (`Platform_ControlHold`: the virtual clock's spin check and the real-time
  clock's catch-up start again when the game goes on); in a window the
  events are pumped while it waits, and the virtual clock neither paces nor
  pauses. Checked: 7000 frames stepped one at a time hash the same as a free
  deterministic run, and a 3 s wait between two steps changes nothing.
  `MEMORIES_CLOCK=interrupt` keeps its timer running while the client holds
  the game (logged); lockstep needs the default cooperative clock.
- **Cost:** with `MEMORIES_CONTROL` unset, `Control_Point` returns at its
  first test and the pads it adds are 0. The eight smoke cases pass, and
  7000 frame hashes of a run without it equal the origin/master build's.
- **Commands as built** (numbers: hex where marked, else decimal; `0x`
  accepted on both):
  - `step N`: `ok frame F vblank V` once stopped. `step 0` answers at once.
  - `pad P BITS`: P is 1 or 2, BITS hex. ORed into what `run_vblank` gives
    the game, with the keyboard's and the controllers' and like
    `MEMORIES_INPUT`'s: the mods' `INPUT` hooks see them, the deck slot
    screen holds them back with the rest, and View > Japanese buttons does
    not exchange them. Pad 2 counts as connected once set.
  - `shot PATH`: `Memories_DumpFrame`'s picture (widescreen and the scaled
    picture as it dumps them) as PNG, or as PPM for a `.ppm` path.
  - `hash`: FNV-1a of VRAM, the hash `MEMORIES_FRAME_HASHES` writes. Taken
    at the stop, after the VBlank: checked equal to that file's line for
    the same frame at 140 frames through the first duel.
  - `peek ADDR LEN` (ADDR hex, LEN up to 16384) answers `ok HEX`; `poke ADDR
    HEX`. KSEG0, KSEG1 and physical addresses name the same 2 MiB of RAM;
    the scratchpad is `1F800000`-`1F8003FF`; anything else, or a range past
    an end, is refused. A poke into RAM tells the module registry
    (`Memories_GuestWritten`).
  - `save PATH`; `load PATH` resumes the state and answers at the next stop,
    one frame into it (`ok frame F vblank V`), or `err` with the reason
    (no notice on screen). The frame count is the run's own and is not in a
    state; the VBlank count is. Checked in the story and in the duel: the 60
    frames after a load hash as the 60 after the save; and, since states
    carry the random seed (chunk `rng`, which this check found missing), a
    pack bought from a state twice, loaded in place, deals the same cards.
    A state saved during the opening movie did not resume pixel-exact.
  - `info`: `ok frame F vblank V mode M build B` (M the raw mode byte
    `D_8009B26C`, B the build id in hex).
  - `quit`: `ok`, then the game ends as when its window is closed (exit 0).
  - Errors: `err` and the reason (an unknown command, a usage, a line over
    64 KiB). The connection stays open.

### 3. A recorder

`MEMORIES_RECORD=path` records the pad bits at the point the game reads them
(`run_vblank`), once per VBlank, from every source: keyboard, gamepad, mouse,
script and controller. VBlank indices count from the recording's start, so a
replay can begin at a state.

### 4. Replays

A replay is a file with:
- **a header:** the build id, OS, mods and load order, language and settings;
- **a start:** boot, or a state;
- **its kind:**
  - **recorded:** the exact per-VBlank input stream, plus checkpoints (a frame hash every N VBlanks, and optional states). Exact, but code that shifts timing breaks it;
  - **scripted:** a Python scenario on the client below (`wait_until`, semantic actions). It survives timing changes.

The two kinds are named in the format from the start, so the first one does
not decide the shape of the second.

`tools/pc/replay.py play FILE --check` runs a replay and reports the first
VBlank whose frame differs. When a state checkpoint exists, it also reports
the first RAM range that differs, with the noisy ranges above masked.

Replays live in `tests/pc/replays/`. They need the disc, which the port's CI
does not have (only the matching build gets the retail executable, through a
secret). So they are a **local gate**, run like `smoke.py` before a PR, until
CI can hold retail inputs.

### 5. The Python client

`tools/pc/yfm_control.py` holds all the game knowledge:
- **Launch:** starts the game with the usual private settings, user and mods folders.
- **Symbols and structs:** reads symbols from the symbol table the port already ships for state relocation, and decodes structs from `src/game/*.h` and `notes/`. `state()` gives the mode, both duel sides (LP, hand, field), the deck, chest, starchips and opponent as data.
- **Primitives:** `press(keys)`, `wait_until(predicate, timeout)`, `shot()`, `ram()`.
- **Semantic layer:** `goto_free_duel(opponent, deck)`, `play_card`, `attack`, `fuse`, built on pad and poke.

**First cut landed** (`tools/pc/yfm_control.py`, `Game`):

- **Launch:** like `smoke.py`: a `tmp/pc/control/run-XXXXXXXX` folder of
  its own (or `out=`) with the settings file (`settings=` by key, the rest
  the defaults), the user folder and the log; the mods shipped beside the
  executable, or `mods_dir=`; `MEMORIES_DETERMINISTIC=1`, headless by
  default; Wine for a Windows build off Windows (`smoke.launcher`). A free
  port is picked and retried if the game cannot listen on it. The process
  ends with its `Game` (`with`, `quit()`, or when the object or the
  interpreter goes), since a game whose client has gone runs on.
- **Primitives:** `step`, `info`, `mode`, `resident(module)` (an overlay's
  identifier word at its load address), `pad`, `press(keys, hold=6,
  after=6)` and `presses` (names: `start`, `cross`, `up+cross`...),
  `wait_until(predicate, timeout)`, `wait_mode`, `press_until(predicate,
  keys)` (a press every so many VBlanks until something holds: dialogue
  and menus without counting frames), `shot`, `hash`, `peek`/`poke`/`u8`/
  `u16`/`u32` by address or symbol, `save`/`load`, `quit`.
- **Symbols:** deviation from the plan: the table shipped for state
  relocation (`symbols/<build id>.txt`) holds only host addresses (every
  function, and the variables of the game's own sections), none of the
  guest globals a test reads. The client reads names from
  `config/pc/guest_addresses.txt`, the table the build pins those globals
  with, and falls back to constants, each with the header it comes from.
- **`state()`:** the mode (and its flags), the opponent
  (`gDuel_bOpponentID`), the starchips, the deck (`gDuel_awPlayerDeck`),
  the chest (`gLibrary_abCardChest`) and, in the story or a duel, both sides
  (`D_800E9FF0`, `duel_side_state.h`): LP shown and real, the maximum, the
  deck cursor, the hand and the field. Cards come from the 30 records at
  `D_801A7AD8` (`duel_card.h`), 15 a side: five hand slots, five monster
  zones, five spell and trap zones (`D_800907CC`, `D_800907D8`); a hand slot
  is empty when its byte at +0x1A is negative (the record keeps the card).
  Checked against pictures of the first duel's hand and its first monster.
- **Example:** `tools/pc/examples/control_first_duel.py` boots, starts a new
  game, follows the story to the first duel by the mode and the modules,
  reads both LP and the hand, plays the first card and takes four pictures,
  in one process (about 13 s), with no frame number anywhere. Two runs
  agree on every number and picture.
- **Not yet:** the semantic layer, and the acceptance rewrites. A first
  purchase of `test_packs.py` and its "same input, same pack" check ran on
  the client in one process (the opening still its `MEMORIES_INPUT`),
  pokes in place of a state patched offline; that check is what showed
  states did not carry the random seed.

### 6. Jump to

One code path, used by both Debug > Jump to and the client's `goto`. It
wraps the game's own debug menu (mode 0, 20 entries) with parameters: the
opponent, and the deck through the `DEBUG_DECK` path. Built once, offered in
two places.

### Acceptance

The tool is accepted when it does these in game, with less code than today:
- **`fx.py`:** the duel-effect scenarios rewritten on the client.
- **`test_packs.py`:** rewritten on the client.
- **A real recent bug:** one (the Raigeki crash, or the CPU planning with replaced cards from #232) turned into a replay that fails on the build before its fix and passes on master.

If the API cannot express these cleanly, the API is wrong.

## Phase 2: a bug report that is a replay

**Help > Report a problem** writes a zip a player can attach:
- a replay of the last minutes: a recent state checkpoint plus the input recorded since;
- the active mods, with versions and load order;
- the settings and system info (Help > System info);
- the end of the log;
- a picture.

An agent reproduces the report from the replay, fixes the bug, and the
replay joins `tests/pc/replays/`.

## Rules

- **Opt-in:** pixel-identical when off.
- **Port only:** everything is under `src/pc` and `tools/pc`, so the console build is untouched.
- **x64-clean:** G32 annotations; `check-g32` stays at 0.
- `src/pc/render/present_pass.c` is not touched.
