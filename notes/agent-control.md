# Agent control and replays

Testing a change in the running game is too slow today, so it gets skipped,
and bugs reach players: mods built with the FM Editor broke in game in ways
no unit test saw. This is the plan for tools that let a test, or an agent,
drive the game completely, and that turn a bug report into a replay that
fails until the bug is fixed and is kept from then on.

Status: phase 1 steps 1 to 4 and 6 landed, step 5 in part (see the
**Landed** notes under each). Each phase below lands
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
- **Debug > Jump to** had only Title Screen (step 6 below adds the rest).
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
| `jump TARGET [OPPONENT [DECK]]` | another screen, as Debug > Jump to goes there (step 6; added with it) |

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
  - `jump TARGET [OPPONENT [DECK]]` (step 6): `ok` once taken; the game
    goes there at its next point between two screens' frames.
  - Errors: `err` and the reason (an unknown command, a usage, a line over
    64 KiB). The connection stays open.

### 3. A recorder

`MEMORIES_RECORD=path` records the pad bits at the point the game reads them
(`run_vblank`), once per VBlank, from every source: keyboard, gamepad, mouse,
script and controller. VBlank indices count from the recording's start, so a
replay can begin at a state.

**Landed** (`src/pc/debug/recorder.c`, format in `recorder.h`):

- **Where:** `run_vblank` now ORs every source first (`Platform_Pad`,
  `Control_Pad`, and the part exempt from View > Japanese buttons) and hands
  them to `Recorder_Pads`, which notes them or, playing, replaces them;
  then the deck slot screen's hold, the mods' `INPUT` hooks and the
  Japanese buttons act on them as before, once. A change is buffered at the
  VBlank (it may run from the timer) and written at the end of the
  `VSync(0)` (`Recorder_Point`, before `Control_Point`), with a frame hash
  (`H`) at every such point and a state every `MEMORIES_RECORD_STATES`
  VBlanks (`S`). The file starts with the build and the facts every crash
  report has (`F build`, `os`, `settings`, `mods`) and ends with `E`
  when the game exits.
- **Start:** from boot the indices are the VBlank count; with
  `MEMORIES_LOAD_STATE` the recording starts at the first safe point after
  the startup load (`Memories_StateStartupDone`), and so does a play.
- **Play:** `MEMORIES_PLAY=path` gives the pads the file's bits (the live
  ones are ignored) and ends the game at its `E`. A mod's `host->pad`
  reads the played bits too (`Mods_PadSource`): it used to read the
  keyboard directly, so the hand camera's L1 was lost in a play. It now
  also sees a control client's bits, which it did not.
- **Not recorded:** host actions (F5/F7, the deck slots on F6, the menus,
  Esc), and a `load` through the channel (the indices would jump back): a
  replay that needs those is a scripted one.
- **Checked:** the duel-hand-camera input recorded to frame 7143 and played
  back without it: the 7143 frame hashes and the 213 input changes agree.
  A play from a state with state checkpoints agrees; with its first press
  removed, the check names VBlank 3 and the first RAM range that differs.
  Unset, a run's 7000 frame hashes equal origin/master's.

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

**Landed** (`tools/pc/replay.py`; its docstring has the format):

- **Container:** a folder of text (`replay.json`, `recording.txt` or
  `scenario.py`), which is what `tests/pc/replays/` holds, or the same files
  in a zip (`.yfmreplay`) with any states, to pass around. The header is the
  recording's own lines: the build id, the OS, every setting, the mods that
  were on (the crash reports' `mods` fact: the order is the manifests', not
  the load order yet), the language. A play writes that settings file and
  turns each mod beside the executable on or off as the header says.
- **No game data:** a save state holds the 2 MiB of guest RAM, the disc's
  code and data, so `record` refuses a start state or a state checkpoint for
  a replay under `tests/pc/replays/`: those start from boot and check frame
  hashes. Replays with states stay outside the repository.
- **Making one:** `replay.py record OUT --session FILE.py` runs FILE.py's
  `run(game, out)` on the client with `MEMORIES_RECORD` on and packages the
  recording (`--state` to start at one, `--states-every N` for checkpoints,
  `--hash-every N` to keep every Nth frame hash); `--recording` packages a
  `MEMORIES_RECORD` file made any other way; `--scripted FILE.py` keeps a
  scenario, `run(executable, out)`, whose assertions are the verdict.
- **Checking:** `replay.py play FILE --check` plays a recorded replay with
  `MEMORIES_PLAY`, records the play, and names the first frame hash that
  differs (its VBlank and the frame it was) and, at the first state
  checkpoint whose RAM differs (the `memory` chunk; `g_SDValue` masked, the
  other chunks not compared), the first differing range. `--update` takes
  this build's hashes as the expected ones. `replay.py run` checks every
  replay in `tests/pc/replays/`, like `smoke.py`.
- **In `tests/pc/replays/`:** `first-duel` (recorded: boot to the first
  card played in the first story duel, a frame hash every 4 frames;
  `session.py` records it again) and `state-load-rng` (scripted: a real bug,
  below).
- **The bug as a replay:** `state-load-rng` buys a pack from a state, loads
  the state in the same game and buys it again with the same presses. On
  this branch without "Port: save states carry the game's random seed" it
  fails (`dealt {2, 3, 4, 7, 8}, then {4, 8, 8, 8, 9} after loading it`);
  with it, it passes.

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
- **Semantic layer** (on pad presses and waits on what the game holds):
  `goto(target, opponent, deck)` (step 6) and `duel_ready()`; in a duel
  `phase()` (`gDuel_wSceneStateFlags & 0xF`, the index into
  `gDuel_apfnSceneStateHandler`: 4 hand, 5 field, 7 placement, 8 position
  and guardian star, 9 battle, 10 turn switch, 12-14 the result), `turn()`
  (`D_8009B1D5`), `wait_turn()`, `field()` (four rows of five as the player
  sees them, laid out by the game's grid `D_800907D8[0]`), `play_card(slot,
  face_up, star)`, `fuse(slots)` (Up marks each, in order), `attack(column,
  target)` and `end_turn()`. The hand's cursor is found by
  `gDuel_wSelectedCardID`, the field's and the attack target's by their
  `DuelFieldCursor` column bytes (`0x800E9F57`, `0x800E9F73`, found by
  watching RAM while pressing). A card goes to the zone the game offers
  first; the game asks for a card every turn, so an attack follows a play.
  A card record counts only with `DUEL_CARD_FLAG_OCCUPIED`; its flags are
  decoded (face down, defense position, used this turn). Checked in a duel
  against duelist 3 with cards 1-40: a monster played, the turn ended and
  the opponent's monster came, a second played and an attack on the
  opponent's defending monster (6500 LP after it, the attacker kept), and
  a fusion of two hand cards.
- **Acceptance rewrites:** see Acceptance below.

### 6. Jump to

One code path, used by both Debug > Jump to and the client's `goto`. It
wraps the game's own debug menu (mode 0, 20 entries) with parameters: the
opponent, and the deck through the `DEBUG_DECK` path. Built once, offered in
two places.

**Landed** (`src/pc/platform/title_jump.c` and its game side
`src/pc/overrides/title_jump.c`; the channel's `jump`; the client's
`goto`; Debug > Jump to):

- **The path:** a jump to another screen is held (`TitleJump_RequestTo`)
  and taken where Title Screen's is, between two mode runners. From
  anywhere but the debug menu the game first leaves for the title exactly
  as Title Screen does (the sequence checked from eleven screens). The
  title skips its opening movie and its menu gives way at once with the
  choice retail has no case for, 10 (the hidden SAVE), which
  `Main_ApplyMenuSelection` turns into the debug menu (mode 0). Once that
  menu is idle (mode byte `0xC0`, no step running), the target's entry is
  taken as Cross takes it: the cursor on it and `D_8009B2EB = entry + 1`.
  Entries: Free Duel 8, DeckEdit 7, Detail 3 (the Library), Password 11,
  3D MAP 6 (the campaign map), Option 16; `debug` stops at the menu. The
  menu's DUEL entry fights duelist 1 with the debug arming, so `duel` is
  armed as the Free Duel screen arms one (`func_80024DC8(-1, opponent,
  0x6000, 0x6000)`, back to Free Duel after), with the deck first set
  through `MEMORIES_DEBUG_DECK`'s parser (`Cheats_SetDeck`); a duel with
  no deck given and none in the save is refused. The credits have no entry:
  their mode is set, as `MEMORIES_MODE_AT` does. A state load drops a
  waiting jump, as it does Title Screen's request.
- **Offered in two places:** Debug > Jump to lists Debug Menu, Free Duel,
  Build Deck, Library, Password, Map, Options and Credits under Title
  Screen (no parameters there: a duel needs an opponent and a deck, which
  only the channel takes); `jump TARGET [OPPONENT [DECK]]` on the channel,
  and `Game.goto(target, opponent, deck)` on the client, which steps until
  the target's mode runs. `Game.duel_ready()` then leaves the deck screen
  every duel opens with (Circle) and waits for the dealt hand.
- **Checked:** one game, from before the title, jumping in turn to the
  Library, Build Deck, Password, the map, Options, Free Duel, the debug
  menu, a duel against duelist 3 with cards 1-40 (its hand dealt from
  them), the title and the credits; each screen's picture is the one its
  menu opens. `pc_title_jump` covers the request, the title's hand-over,
  the wait for the idle menu and the state load.
- **Not yet:** a jump during the credits restarts the game (Title Screen's
  rule) and is lost with the process.

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
