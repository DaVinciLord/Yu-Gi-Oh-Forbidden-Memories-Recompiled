---
name: fm-arm64-mods
description: Build and validate FM code mods as translated macOS ARM64 dylibs with typed hooks. Use for code mods in this backend, preserving existing Linux/Windows artifacts; ordinary data mods do not need translation.
---

# Native macOS code mods

Read [the modding contract](../../../notes/modding.md) and inspect the source,
manifest, imports and entry point. An ELF i386 `.o` cannot load into ARM64;
an ordinary LP64 rebuild does not preserve PS1 guest records.

```sh
python3 tools/pc/build.py --target macos
python3 tools/pc/build_mod.py /path/to/mod --target macos --game /path/to/game-build --out /path/to/isolated-mod
```

`--game` names the build directory containing exports, LLVM signatures and the
game summary, not its executable. Keep original sources and `.o` artifacts.
On macOS an explicit `.o` library name selects its `.dylib` counterpart.
`--out` writes the library; it does not copy the manifest/assets. Prepare the
complete isolated mod directory before a gameplay test.

`MemoriesModInit` returns int and takes `(const MemoriesModHost *, MemoriesMod *)`.
Imports must match the game's LLVM ABI. Mod storage registers at load and
unregisters before unloading. The translated builder rejects constructors,
destructors, TLS and machine assembly; do not bypass those constraints.

Hooks use typed LLVM wrappers and registered original bodies. Do not copy
instruction-patching machinery from i386. Variadic and returns-twice helpers
are not arbitrary hook targets. Verify hook chaining, activation/deactivation,
original calls and cleanup when changing this lifecycle.

Run `test_arm64_mod_loader.py --sanitize` and `test_arm64_mod_hooks.py --sanitize`
for infrastructure evidence. Both use repository fixtures and need no external
mod. Validate each real mod's behavior separately; `test_arm64_life_points.py`
requires an explicit `--mod` and is specific to that mod. For LP changes,
check initial values, damage, campaign/Free Duel scope, sound options and
fresh-process restore. Choose equivalent observable assertions for other mods.

Distinguish successful library loading, a hook invocation and correct gameplay.
Deploy into the user's mod directory only when requested, and identify the
exact game/mod paths validated. One passing mod does not prove universal
compatibility.
