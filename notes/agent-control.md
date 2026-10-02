# Agent control and replays

Testing a change in the running game is too slow today, so it gets skipped,
and bugs reach players: mods built with the FM Editor broke in game in ways
no unit test saw. This is the plan for tools that let a test, or an agent,
drive the game completely, and that turn a bug report into a replay that
fails until the bug is fixed and is kept from then on.

Status: design. Each phase below lands with its own code and updates this
file.

## What exists

- **Before launch, environment variables decide everything:**
  - `MEMORIES_INPUT` is a pad script keyed to *presented* frames, which drifts when a load runs behind VBlanks;
  - `MEMORIES_MODE_AT` and `MEMORIES_TITLE_AT` jump scenes;
  - `MEMORIES_LOAD_STATE` and `MEMORIES_SAVE_STATE` load and save states;
  - `MEMORIES_DEBUG_DECK`, `MEMORIES_DEBUG_CHEST` and `MEMORIES_DEBUG_STARCHIPS` set up a save;
  - `MEMORIES_DUMP_FRAME` writes one picture, then exits;
  - `MEMORIES_FRAME_HASHES` writes a hash per presented frame.
- **Determinism:** a run is deterministic only with HEADLESS (or DETERMINISTIC) and DUMP_FRAME and SPEED=-1 together.
  - The silent mixer thread still runs in real time, so the sound driver's work area (`g_SDValue`, `0x801E0384..0x801E1B44`) and the spu chunks differ between two runs.
- **No live channel:** no socket, no pipe, no recorder, and no way to read the game's state as data. Tests patch a state's `memory` chunk offline and read raw addresses.
- **Debug > Jump to** has only Title Screen.
- **Existing tests:** `tools/pc/smoke.py` (8 frame-hash cases) and `tools/pc/test_packs.py` (state patching) are the closest thing to replays. About 600 one-off agent scripts in `tmp/` repeat the same environment boilerplate, button macros, one-process-per-frame captures and RAM peeks.

## Phase 1: control and replays

### 1. One deterministic switch

`MEMORIES_DETERMINISTIC=1` alone gives the virtual clock, headless or
windowed, with no frame dump needed and no exit. Proven by the smoke hashes
staying the same and by two runs giving identical frame hashes. Stepping the
mixer by virtual time is a separate change; until then, RAM comparisons mask
`g_SDValue` and the spu, libspu, bss and data chunks.

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
