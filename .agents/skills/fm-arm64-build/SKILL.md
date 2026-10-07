---
name: fm-arm64-build
description: Build, package and launch the FM macOS Apple Silicon port with its pinned guest toolchain. Use for this repository's translated PS1 backend, including fresh-build and artifact checks.
---

# FM macOS ARM64 builds

Locate the checkout containing `tools/pc/build.py` and confirm its Git state.
Read [macOS build instructions](../../../notes/macos-build.md) and use the
shared driver for ordinary builds:

```sh
python3 tools/pc/build.py --target macos
python3 tools/pc/test_macos_linkage.py --binary tmp/pc/macos/memories-arm64
```

Commands run from the repository root. Python and the Xcode SDK are required;
the scripts fetch checksum-verified dependencies and pinned LLVM. Do not
replace that toolchain with system Clang or a global dependency installation.
For diagnostic builds, inspect `build_arm64.py --help`: optimization is on by
default; `--no-optimize` and `--instrument-softgpu` preserve comparison paths.
The complete build requires no retail disc.

A fresh-build audit must regenerate objects and dependencies, not just reuse
an existing binary. Shared archives may be reused after checksum validation;
disclose any symlinked toolchain/cache. Check the build identity and linkage
of the actual binary tested. Source, toolchain or translator edits require a
rebuild before gameplay validation.

For packaging, follow the build guide and run `test_package_macos.py` against
the resulting archive. Declaring macOS 11 as a deployment target does not
prove execution on macOS 11. Ad-hoc signing does not prove notarization or a
quarantined download's launch behavior.

For isolated gameplay, supply a private disc and user directory explicitly:

```sh
MEMORIES_DISC='/path/to/disc.bin' MEMORIES_USER_DIR='/path/to/test/user' ./tmp/pc/macos/memories-arm64
```

Keep private retail files, copied saves and generated output under ignored
paths. `run_arm64.py` uses its own test user directory; inspect its options
before relying on environment overrides. For delivery, identify one absolute
binary/app path and a copyable launch command. Linkage is separate evidence
from gameplay, visible rendering and audio. Follow the task's publication
scope; a build request does not authorize commits, pushes or workflows.
