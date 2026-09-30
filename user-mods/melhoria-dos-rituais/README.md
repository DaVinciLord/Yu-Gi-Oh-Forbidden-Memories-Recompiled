# Melhoria dos Rituais — 1.1.0-test

Independent code mod by Otavio. Its recipe data stays in a separate mod
created by FM Editor. Install only one version of `melhoria-dos-rituais`.

The original recipe still works on official builds. On builds exposing
condition-based ritual requirements, the mod uses those same requirements
for three distinct materials across field and hand, with at least one on the
field. Removed recipes remain removed. An accepted field-only ritual is
left to the game's original implementation.

The mixed selector reserves specific requirements first and prefers to use
more field materials, then lower printed DEF for a DEF-dominant result or
lower printed ATK for an ATK-dominant or tied result. Every requirement in
one tribute slot must hold. Stats are printed stats, including card edits,
not temporary terrain/equip bonuses.

Runtime extension functions are resolved optionally with `host->symbol`;
there is no dependency on the recipe mod or on a particular mod id.
The successful original proxy/deactivation bridge is retained.

Build from the repository:

```sh
python tools/pc/build_mod.py user-mods/melhoria-dos-rituais
python tools/pc/test_ritual_hand_mod.py
```

The second command compiles a freestanding 32-bit test. Hosts without
32-bit Linux execution can install `unicorn` and `pyelftools` to run it
through emulation. It checks both duel sides, mixed layouts, consumption,
overlapping requirements, bounds, duplicate prevention, result-dependent
selection, fixed/removed recipes and the original fallback.

This directory is outside bundled `mods/`, so the game/editor build does
not install or enable it automatically. The test ZIP contains the mod
manifest, object, source and this README, never the recipe mod.

Automated checks do not cover the game's full ritual animation. In-game
testing of both mixed layouts and of each mod alone is still required.
