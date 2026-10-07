---
name: fm-arm64-guest-abi
description: Diagnose and repair FM guest/native pointer, PS1 layout and callback ABI boundaries on macOS ARM64. Use for narrow storage, translated LLVM, overlays or native-call defects in this backend.
---

# FM guest/native contracts

Read [the runtime architecture](../../../notes/macos-arm64.md). Identify the
actual writer, reader, guest token, native pointer and LLVM signature before
changing a bridge. Numerical appearance alone does not identify an address
space.

- Preserve PS1 field sizes, offsets and strides with the existing G32 and
  PSXLONG annotations. Host-only objects retain full-width native pointers.
- Encode registered native pointers with `GuestRuntime_EncodePointer` before
  storing/comparing them in guest space. Resolve guest data and functions
  through their existing runtime contracts; never truncate a native pointer
  or register unknown storage to hide a failed resolution.
- Preserve RAM/scratchpad aliases and legal one-past encodings. Keep callback
  dispatch typed and tied to the active overlay or retail-verified gate.
- Keep matching source changes limited to necessary annotations/contracts.
  Prefer adaptations at PC boundaries or in the structured LLVM pass.
  Preprocessor equivalence is distinct from byte-for-byte console matching.
- Lower guest accesses before optimization. Validate calling conventions,
  signed integer extensions, results and special ABI attributes. Fail clearly
  on unsupported signatures; do not patch IR semantics with regex.

See [boundary regressions](references/boundaries.md) for qsort, sprites,
audio, text and renderer ownership. Select tests for the affected boundary
from the runtime guide: layouts, IR translation, native-call marshalling and
actual function execution prove different contracts.

For a focused fixture, use `guest_test_ir.py` to compile current sources and
select functions with LLVM, then `guest_test_compile.py` for pinned guest
objects and compatible host sanitizers. Do not read stale game-build IR or
import utilities from another test. Keep the real reader/writer and adjacent
sentinels in the regression. Rebuild the game and replay the original scenario
after the isolated test passes.
