# macOS arm64: native validation and architecture gate

## Implemented

`python3 tools/pc/test_native.py` builds and runs ROM-free components with
Apple Clang, without downloading Linux tools or requiring CMake, SDL or a ROM.
Run it from the repository root. `--sanitize` enables ASan/UBSan for components.
Artifacts and scratch data stay under `tmp/native-tests/`.

The runner covers the existing core RNG/comparator/translated memory test,
ten game-file discovery scenarios, state remapping and text-entry layouts.
It is deliberately scoped to Darwin arm64; it does not change the existing
Linux/Windows build or claim to build the game runtime. RNG substitution applies
only to the decompiled RNG caller, as in CMake. Assertions remain enabled.

The separate unsanitized Darwin diagnostic checks G32 field width, offsets,
structure size and PSXLONG. It also checks that a failed fixed-address
reservation leaves an existing allocation intact. It uses Mach allocation
without VM_FLAGS_OVERWRITE and releases every successful allocation.
Four one-page reservations probe physical RAM above page zero, scratchpad,
KSEG0 and KSEG1. These are reservation probes, not shared-memory aliases.

Exit codes: 0 means component checks and address reservations passed (not a
working runtime); 77 means components passed but fixed addresses are blocked;
other nonzero codes indicate a build/test/unexpected VM error. A CI job must
report 77 as an unresolved architecture gate, not a green runtime test.

## Results on 2026-10-02

macOS 26.6.2 / native arm64, Apple Clang:

- 16 component scenarios passed normally and with ASan/UBSan.
- Reservation collision preserved the existing memory value.
- G32 widths/offsets and PSXLONG assertions passed.
- All four fixed reservations returned KERN_INVALID_ADDRESS.
- Standard executable starts; PAGEZERO 0x4000 and 0x10000 executables both
  exit by SIGKILL before main, although codesign verification succeeds.
  The cause of the kill is still undetermined. This does not prove that every
  possible fixed-address approach on Darwin is impossible.

The first investigation suggested proving memory and callbacks before portable
build work. The practical revision is to make the native validation path
available first, and keep fixed-address feasibility as an explicit blocker.
Do not spend effort linking hundreds of game units before resolving this gate.
No production assert, G32 cast or i386 dependency was removed to hide a failure.
No matching game sources changed; console matching was not run.

## Approved bounded architectural experiment

The user approved this isolated experiment. Use the existing Memories_Resolve
as the reference contract for translating guest data addresses, and a separate
function-address map for resolving callbacks. A successful callback probe must
store a 32-bit guest address, resolve to a full-width native function and invoke
it with arguments/return values intact; truncating a native function is invalid.
This would be an isolated experiment, not a change to CALL32 or an automatic
rewrite of game pointers. Audit pinned globals and pointer dereferences to
estimate the integration cost before proposing a runtime migration.

Remaining gaps: actual shared fixed RAM aliases, native callbacks in guest-width
storage, globals/pins, MIPS bridge, context switching, renderer, full game build
and gameplay. The runtime milestone remains unfulfilled.

## Prototype implemented and validated

`tests/pc/native_guest_contract_test.c` stores both data and callback guest
addresses in an actual 12-byte G32 structure. It resolves data using the existing
Memories_Resolve and callbacks using a local two-entry typed function map.
The test requires native data and function addresses above UINT32_MAX: this
prevents an accidental low-address success from concealing pointer truncation.
It checks RAM aliases, scratchpad aliases, signed arguments and return values,
two callback targets, unknown/unaligned/null addresses and invalid segments.
Both ordinary and ASan/UBSan runs pass on this machine.

This proves a small explicit-translation contract, not transparent compatibility
with existing game C. The production CALL32 still casts; the prototype invokes
the resolved native callback directly. The local function map has no overlay
residency, MIPS fallback, arbitrary signature dispatch or registration lifecycle.

Integration assessment: build_game32.py currently binds tentative/undefined
globals to absolute retail symbols, while compiled game C dereferences G32
fields directly. Changing Memories_Resolve or CALL32 alone cannot translate
these accesses. A production approach must handle both generated global bindings
and stored-pointer dereferences, preserve pointer arithmetic/identity and layouts,
and distinguish native pointers from guest tokens. The next bounded step is to
prototype one real game unit with generated bindings and explicit dereference
translation, before selecting a source transformation strategy. No generalized
transformation or new runtime architecture has been implemented.

## Continuation: real unit and actual disc loading

Two parallel Codex agents investigated Darwin address feasibility and a real
translated game unit. Fixed reservations remain unavailable even after targeted
release of owned PAGEZERO subranges. A high-address (16 GiB) control reservation
works. Reduced PAGEZERO binaries still die before main; no system setting or
security bypass was used. This is evidence for this host, not every macOS version.

`test_translated_game_unit.py` generates a fail-closed adapted copy of the real
func_80038898 under tmp/. It translates the guest stream read/increment and
resolves two pinned globals. Three RAM aliases and two consecutive commands
pass in both ordinary and ASan/UBSan runs. Actual ygo_types.h layouts are used;
matching sources are unchanged. This generator supports only the exact known
unit body and is not a general translator.

`src/pc/guest/translated_image.c` adds an experimental loader into MemoriesMemory,
without changing image.c. It validates signature, image bounds and aligned entry
inside the initialized image before writing memory. Failure leaves RAM and the
entry output unchanged. Synthetic tests cover truncation, invalid entry, empty/
oversized payload, RAM bounds and null arguments.

`tools/pc/native_loader.c` reuses GameFiles_ReadExecutable to load the user's
USA disc. Dead stripping removes unused interactive discovery functions; no
success stubs or dynamic unresolved symbols are used. Observed real input:
1,902,592 executable bytes; entry 0x800129d8. Translated native memory lies above
4 GiB. No retail bytes were copied into tracked files.

Run from repository root:

    python3 tools/pc/test_native.py --disc 'game/YGOFM Vanilla (Base).bin'
    python3 tools/pc/test_native.py --sanitize --disc 'game/YGOFM Vanilla (Base).bin'
    python3 tools/pc/test_native.py --fixed-address-probe

Default runner now reports native component validation separately from the
old fixed-address diagnostic. The explicit diagnostic returns 77 when blocked;
default component runs return 0. Both 16-scenario runs and real-disc loading pass.
Basic-types and check-g32 pass. Full console matching and Linux/Windows builds
were not run; existing build paths and shared game sources remain unchanged.

The loader DOES NOT execute the MIPS entry or start the game's native main loop.
The next architectural gate is a translated-memory backend: generated pinned
global bindings, G32 load/store/dereference and pointer arithmetic, full-width
callbacks and guest-compatible allocation. Inventory currently reports 387
G32 members and 121 G32 globals; these are storage declarations, not a count of
all accesses or an effort estimate. Single-unit feasibility does not establish
that every access can be automatically adapted. Preserve matching sources and
existing Linux/Windows paths, with explicit adapters/generated build copies,
before addressing the remaining context, SDK and window backends. This is a
substantial backend change and needs user agreement before generalization.

## Native executable integration (continuation, 2026-10-02)

The user authorized continuing toward compiling and starting the native game.
The earlier bounded prototype limits above describe historical milestones.
`python3 tools/pc/build_arm64.py` now builds and links 737 ARM64 units into
`tmp/arm64-build/memories-arm64`, using isolated native SDL3 dependencies.
The game/overlay originals remain unchanged: ELF section stripping, guest
storage layout corrections, pinned symbol bindings and dereference/callback
translation apply only to generated copies/LLVM IR under tmp/.

The translated runtime maps RAM/scratchpad aliases to host allocations above
4 GiB, preserves 32-bit guest pointer storage, and resolves native callbacks
without truncation. Native setjmp/longjmp keeps a full-width host context.
Darwin paths, crash registers and actual Mach-O text ranges are supported.
Executable i386 mods and save states explicitly report unsupported behavior.

The executable genuinely loads the user-provided disc and calls the native
game entry. First launches still stop at frame 0; no gameplay or rendered
frame has been verified. Runtime failures identified compiler-fortified libc
boundaries and an unannotated retail filename pointer table. Both have
regression checks; table corrections are generated, not edits to matching
sources. The next observed boundary is libds ISO path string search.

Validation: the 16 native component scenarios plus real-disc loader pass;
translated IR contract tests pass with ASan/UBSan. A successful link or loader
check must not be reported as a working game. Remaining risks include SDK
stored layouts, other libc boundaries, overlay/global reset lifecycle and
input/audio/rendering execution. Linux/Windows and console matching were not
run in this session.

Follow-up launch evidence: all seven retail ISO9660 file paths resolve to
sector positions. Signed s32-to-pointer round trips are normalized to their
guest bits at runtime (normal and ASan/UBSan regression tests pass). The game
now reaches frame 1 / vblank 2. Eighteen retail guest pointer globals and four
table cursors are corrected by a symbol/path allow-list adapter; layout tests
prove four-byte slots and preserve unrelated native pointers. Remaining
observed failure is an absolute sound-state macro overriding the header's
guest-width pointer declaration. No rendered output is yet verified.

## Verified native window and title screen

The ARM64 executable runs in a real Cocoa window on Apple M3 with CoreAudio
and the Apple OpenGL/Metal-backed renderer initialized. Frame 120 shows the
Konami splash. A subsequent windowed run reaches frame 600 / vblank 2384,
shows the complete Forbidden Memories title screen with PUSH START BUTTON,
and exits cleanly through the requested frame dump (exit 0). Captures remain
ignored under tmp/arm64-build/; proprietary pixels are not tracked. This
verifies startup and rendering, not complete gameplay or audio fidelity.

Observed failures through startup were corrected with concrete regressions:
GsDrawOt's guest descriptor tag, menu entry transition cursor/cast and the
secondary sound note parser's byte-view pointer loads. Game/overlay originals
remain unchanged. Actual SDK GsDrawOt and generated actual sound/menu functions
are exercised with neighboring sentinel words and the observed retail pointer
values, normally and with ASan/UBSan.

Launch from repo root with `python3 tools/pc/run_arm64.py`; the default disc is
the user's ignored USA .bin and settings stay under tmp/arm64-build/user.
`--headless --frames 120` is a bounded frame capture; `--input` accepts the
existing scripted pad format. The current O0 diagnostic build has substantial
performance overhead (~10 FPS in the later startup). Input response and safe
post-translation optimization are being validated next. Save states and i386
code mods remain explicitly unavailable in this experimental backend.

Input validation also passed: scripted Start at frame570, released at576,
followed by a clean windowed frame620 capture (exit0). The image shows the
front-end menu NEW GAME / LOAD / 2P DUEL / TRADE / OPTION. Startup, rendering
and Start input are verified on this M3. No duel/save/load gameplay claim is
made. Build with `python3 tools/pc/build_arm64.py --optimize` to retain the
unoptimized translation frontend while optimizing transformed object code
and ordinary runtime helpers. That option is currently under final runtime
validation; the unoptimized path remains available.

Optimized runtime validation passed: windowed frame820 exits0, with Start
at700/release712 yielding the same five-item menu. Earlier Start570 was too
early for the faster optimized introduction, so its frame620 showed the title
instead. The optimized build reaches about60FPS in portions of the intro;
later menu processing remains around20FPS with noticeable translation
overhead. It is not uniformly60FPS. A compiler-created memchr call exposed a
retail-name stub collision; a bounded guest-preserving libc bridge and explicit
HOST_LIBC exclusion fix it, with O2+ASan/UBSan tests. Final stub census contains
no ordinary libc names. Launch with `python3 tools/pc/run_arm64.py`; Enter is
the default Start key. This remains an experimental startup-capable port,
with full duel/save/load validation and performance work outstanding.

## Performance correction after user feedback

Baseline menu: ~22FPS, drawing ~26ms per batch. CPU sampling overwhelmingly
lands in GuestRuntime_ResolveData. SoftGpu's host-owned per-pixel VRAM/raster
accesses were needlessly translated. The optimized build now compiles only
this audited component normally, resolving its nine pointer API boundaries
once per call. SDK/game code remains translated. Generated source adapter
fails closed if audited signatures change.

Measured in a real Cocoa window with CoreAudio active: drawing ~1.1ms, game
processing ~2.1ms, presentation ~2.9ms. Consecutive menu120-frame windows
report59.91 and59.96FPS, zero missed VBlanks. Two independent launches reach
frame1000 and exit0; actual window screenshot at820 shows correct menu and
copyright. Intro/movie stages still report15FPS; this change does not establish
60FPS throughout every scene or duel.

Differential regression: fully instrumented and native-boundary SoftGpu
produce identical full-VRAM hash d31a62f999bbd9db after512 seeded varied
textured/sprite/triangle/blend/mask/clip commands. Existing CLUT/fill/widescreen
checks and guest upload/readback aliases pass normally and with ASan/UBSan.
`--instrument-softgpu` restores the old raster instrumentation for A/B tests.

A frame820 PPM exit capture showed transient stripes while actual window820
and later frame1000 captures are correct. Dumps occur before Platform_Present,
and a screenshot requested at the same exit frame is never presented/saved;
the capture ordering issue remains documented rather than inferred to be a
steady renderer regression. Comparison by frame alone also differs in VBlank
phase because runtime speed changed. Audio DSP optimizations were audited but
deferred because menu60FPS is achieved without them.

## New-game integration validation

The retail NameEntry_Main overlay now resolves through the active shared-bank
module rather than a resident fatal stub. Constant-expression pointer narrowing
in translated instructions now registers full-width native callbacks before
storing their guest tokens; the selection-frame callback is exercised by the
actual name keyboard. Static initializer narrowing remains rejected.

A scripted new game dismisses the initial instruction dialog, enters A, selects
END and advances the multi-page duelist-code warning. Name writes and glyph
transfer are traced at the actual guest buffer801d060c. Name-entry processing
reports59.84–60.02FPS with zero missed VBlanks across120-frame windows. The
warning requires additional confirmations: an earlier frame1900 capture was
an incomplete input sequence, not evidence of a stuck dialog.

At the transition after name completion, the current run aborts with an
unregistered pointer0x23000200000004 near frame2040. Campaign/duel execution
therefore remains unverified; this is the next concrete integration failure.
Memory-card SDK public scalars and output buffers now use32-bit PSXLONG on
ARM64; isolated raw-card create/write/read/directory tests pass, but actual
in-game save/load remains to be verified.

LLDB identifies that transition failure inside func_80045208 sound bank
descriptor loading, called by campaign Script_RunTick through a text sound
command. Two raw pointer-table views in sound_output_state.c still load64-bit
words from32-bit guest bank descriptors; this concrete failure is being fixed
in generated source with guarded descriptor-layout regressions.
