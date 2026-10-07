# Boundaries worth preserving

| Boundary | Contract | Focused evidence |
| --- | --- | --- |
| Translated text cursors | Compare guest tokens with guest tokens; encode a native results-buffer address before retargeting | `test_arm64_result_text.py`, names on/off in English/French |
| Sprite angle | PSXLONG occupies four bytes and must not absorb adjacent storage | `test_libgs_sprite_guest.py`, zero/90-degree angles and sentinels |
| Audio pointer tables | Guest pointer entries and their strides remain four bytes | `test_sound_bank_pointers.py`, real command functions |
| Darwin qsort | Comparator operands may be temporary copies outside the source array; expose them through registered scratch storage and release it, preserving nested contexts | `test_translated_ir.py`, gameplay `deck-editor-add-sorted` |
| Overlay calls | Validate each LLVM import against the typed bridge and active module/gate | `test_direct_overlay_bridge.py`, `test_duel_effect_bridge.py` |
| Renderer heaps | GL/texture caches remain host-owned; guest-state restoration must not free live host buffers | `test_host_renderer_boundaries.py --differential`, normal HD duel with fresh-process restore |

The translator rejects non-C calling conventions and unsupported ABI attributes
such as byval/sret; ordinary small-integer signed extensions still matter.
`GsSetAmbient` and `GsSetProjection` use PSXLONG/i32 signatures.

Guest fixtures use the pinned LLVM frontend and native objects. Compatible
host sanitizer runners use Apple Clang; never mix LLVM and Apple sanitizer
ABIs. The pinned LLVM ASan runtime can hang before main on macOS. Record the
compiler/runtime used and distinguish that environment failure from a game
failure. The dedicated IR and narrow-store canaries cover guest operations
that are not instrumented by host sanitizers.
