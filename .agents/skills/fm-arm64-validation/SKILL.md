---
name: fm-arm64-validation
description: Validate FM macOS ARM64 behavior with isolated contracts, retail gameplay, saves and visible HD rendering. Use when evidence of a real game scenario is required; distinguish each test's coverage.
---

# Observable FM validation

Identify the expected behavior, language/options, menu route and exact binary.
Use the [runtime validation matrix](../../../notes/macos-arm64.md) to choose
existing runners. Build first after source changes; provide `--binary` and
`--disc` where supported so the evidence identifies the artifacts tested.

ROM-free checks include layouts/store canaries, LLVM, `test_native.py`,
`test_guest_contracts.py`, typed hooks and the autonomous mod-loader fixture.
Retail runners cover results, sorted decks, village progression, full duels,
normal saves and native state restoration. Their fixture decks/data mods or
debug routes are documented by each runner; respect the requested scenario.

Keep settings, captures and generated mods isolated. Copy existing saves
rather than modifying originals. Inspect exit status, scenario assertions
and fallback diagnostics; retain the failing log and capture paths. A selected
campaign route does not prove completion of the whole campaign. A forced
victory fixture does not prove ordinary gameplay. Headless checks do not prove
window presentation or audio fidelity.

For save-state evidence, compare restored RAM/gameplay and pixels after the
same remaining inputs in a fresh process. `.sav` transfers ordinary progress;
`.state` requires the compatible executable/build UUID, mods and language.
A loopback bind failure blocks the control test and is not a passing result.

For a real-window request, use `test_macos_hd_render.py` and the normal-save
`test_arm64_full_duel.py --window` path where appropriate. Inspect the captured
visual content. Use available GUI tools only when interaction is necessary,
verify focus after transitions, and recover it before continuing input.
Use the actual packaged app when validating distribution behavior.

Report the absolute tested artifact, current passed scenarios and precise
limits. Never promote historical results, title-screen startup or a generated
screenshot alone into evidence of completed gameplay.
