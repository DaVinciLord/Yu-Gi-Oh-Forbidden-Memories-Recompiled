#ifndef MEMORIES_PC_GUEST_REWIND_H
#define MEMORIES_PC_GUEST_REWIND_H
/* Rewind: a ring of past save-state images in memory (state.c takes one
 * every few frames when the `rewind` setting is on, and holding F8 walks
 * back through them).
 *
 * The ring keeps the newest image whole ("latest") and, for each older one,
 * only the difference to the image that followed it: the XOR of the two,
 * whose unchanged words are zero, stored as runs of zero words and the
 * words between them. Stepping back XORs the newest difference into latest,
 * which then is the image before it, and drops that difference; the oldest
 * differences are dropped first when the ring is over its budget. Images may
 * differ in size: the shorter one counts as followed by zeros.
 *
 * Nothing here knows the state format; tests/pc/rewind_ring_test.c checks
 * the round trip byte for byte. */
#include <stddef.h>
#include <stdint.h>

typedef struct RewindEntry RewindEntry;

typedef struct RewindRing {
    uint8_t *latest;        /* the newest image, zero past latest_size up to capacity */
    size_t latest_size, capacity;
    uint32_t *work;         /* the difference being encoded */
    size_t work_words;
    RewindEntry **entries;  /* oldest first, from `first`, wrapping */
    unsigned first, count, max_entries;
    size_t budget, used;    /* bytes held by the differences */
} RewindRing;

/* An empty ring: at most `max_entries` differences in `budget` bytes. */
void Rewind_Init(RewindRing *ring, size_t budget, unsigned max_entries);
/* Frees everything; the ring is empty (and usable) again. */
void Rewind_Clear(RewindRing *ring);
/* A new newest image. Returns 0, or -1 when out of memory (the ring is then
 * cleared, as its chain would no longer lead back). */
int Rewind_Push(RewindRing *ring, const uint8_t *image, size_t size);
/* Latest becomes the image before it. Returns 1, or 0 when there is none
 * (latest is the oldest image kept, or the ring is empty). */
int Rewind_Back(RewindRing *ring);
/* The newest image, or NULL when nothing was pushed. */
const uint8_t *Rewind_Latest(const RewindRing *ring, size_t *size);
/* Bytes the ring holds in all: differences, latest and the work buffer. */
size_t Rewind_Memory(const RewindRing *ring);

#endif
