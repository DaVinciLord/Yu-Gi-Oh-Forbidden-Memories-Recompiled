#ifndef MEMORIES_PC_GUEST_LOW_MEMORY_H
#define MEMORIES_PC_GUEST_LOW_MEMORY_H
/* Host memory whose address the game is handed.
 *
 * The game keeps its pointers in 4-byte slots (G32, src/port_ptr.h), so a
 * block the port allocates and gives the game, or that native code returns
 * to it as a pointer (a kanji ROM glyph, compiled text, a mod's card name),
 * must lie below 4 GB. A 32-bit build has nothing else: there these are
 * malloc and free, word for word. The 64-bit build's process heap can be
 * anywhere (MEMORIES_X64_HIGH_HEAP=1 puts it above 4 GB to prove it), so
 * there they come from a 16 MiB region at the fixed address
 * MEMORIES_LOW_MEMORY_BASE, below the interpreter's stack and after the
 * compiled text's region (src/pc/text/translation.c), which
 * Memories_GuestMap holds from the start like the other fixed regions.
 * Like those, a fixed address keeps the blocks where they were for save
 * states (X3).
 *
 * Memories_LowAlloc returns NULL when the region is full or cannot be had,
 * as malloc does when out of memory; Memories_LowFree takes NULL and only
 * blocks Memories_LowAlloc returned. Game thread only. */
#if defined(__x86_64__) || defined(__aarch64__)
#include <stddef.h>
#define MEMORIES_LOW_MEMORY_BASE 0x9E000000u
#define MEMORIES_LOW_MEMORY_SIZE 0x01000000u
void *Memories_LowAlloc(size_t size);
void Memories_LowFree(void *block);
#else
/* <stdlib.h> is the user's to include: the mod SDK ships this header, and
 * its own C library's declarations must come from where they always have. */
#define Memories_LowAlloc malloc
#define Memories_LowFree free
#endif

#endif
