#include "rewind.h"
#include <stdlib.h>
#include <string.h>

/* A difference: the size of the image it leads back to, then tokens of
 * 32-bit words -- a count of unchanged words, a count of changed ones and
 * those words' XOR -- over the longer of the two images. Trailing unchanged
 * words have no token. */
struct RewindEntry {
    uint32_t before_size;
    uint32_t words;
    uint32_t data[];
};

void Rewind_Init(RewindRing *ring, size_t budget, unsigned max_entries)
{
    memset(ring, 0, sizeof(*ring));
    ring->budget = budget;
    ring->max_entries = max_entries ? max_entries : 1;
}

static void drop_oldest(RewindRing *ring)
{
    RewindEntry *entry = ring->entries[ring->first];
    ring->used -= sizeof(*entry) + (size_t)entry->words * 4;
    free(entry);
    ring->entries[ring->first] = NULL;
    ring->first = (ring->first + 1) % ring->max_entries;
    ring->count--;
}

void Rewind_Clear(RewindRing *ring)
{
    size_t budget = ring->budget;
    unsigned max_entries = ring->max_entries;
    while (ring->count) {
        drop_oldest(ring);
    }
    free(ring->entries);
    free(ring->latest);
    free(ring->work);
    Rewind_Init(ring, budget, max_entries);
}

/* Word `i` of an image of `size` bytes, zeros past its end. */
static inline uint32_t image_word(const uint8_t *image, size_t size, size_t i)
{
    uint32_t word = 0;
    size_t at = i * 4;
    if (at + 4 <= size) {
        memcpy(&word, image + at, 4);
    } else if (at < size) {
        memcpy(&word, image + at, size - at);
    }
    return word;
}

/* Whether 64 bytes are the same: one branch per block, not per word. */
static inline int same_block(const uint32_t *old, const uint8_t *image)
{
    uint64_t a[8], b[8], difference = 0;
    int k;
    memcpy(a, old, 64);
    memcpy(b, image, 64);
    for (k = 0; k < 8; k++) difference |= a[k] ^ b[k];
    return !difference;
}

static int reserve(RewindRing *ring, size_t words)
{
    if (ring->capacity < words * 4) {
        uint8_t *grown = realloc(ring->latest, words * 4);
        if (!grown) return -1;
        memset(grown + ring->capacity, 0, words * 4 - ring->capacity);
        ring->latest = grown;
        ring->capacity = words * 4;
    }
    /* A run of changed words ends only at two unchanged ones, so every
     * token after the first covers at least its own two counts: the tokens
     * never take more than the image and the first token's counts. */
    if (ring->work_words < words + 4) {
        uint32_t *grown = realloc(ring->work, (words + 4) * sizeof(uint32_t));
        if (!grown) return -1;
        ring->work = grown;
        ring->work_words = words + 4;
    }
    if (!ring->entries) {
        ring->entries = calloc(ring->max_entries, sizeof(*ring->entries));
        if (!ring->entries) return -1;
    }
    return 0;
}

int Rewind_Push(RewindRing *ring, const uint8_t *image, size_t size)
{
    size_t longest = size > ring->latest_size ? size : ring->latest_size;
    size_t words = (longest + 3) / 4, whole = size / 4, i = 0, out = 0, bytes;
    uint32_t *old, *work;
    RewindEntry *entry;
    if (size > UINT32_MAX || reserve(ring, words)) {
        Rewind_Clear(ring);
        return -1;
    }
    old = (uint32_t *)(void *)ring->latest;
    if (!ring->latest_size) {
        /* The first image: nothing to lead back to. */
        memcpy(ring->latest, image, size);
        ring->latest_size = size;
        return 0;
    }
    work = ring->work;
    /* Encode the XOR and bring latest up to the new image in one pass. */
    while (i < words) {
        size_t unchanged = i, count_at;
        uint32_t changed = 0;
        /* Most of an image is as it was: skip 64 bytes at a time, then
         * words, then the last partial word and what lies past the image. */
        while (i + 16 <= whole && same_block(&old[i], image + i * 4)) {
            i += 16;
        }
        while (i < whole && !memcmp(&old[i], image + i * 4, 4)) {
            i++;
        }
        while (i >= whole && i < words && image_word(image, size, i) == old[i]) {
            i++;
        }
        if (i == words) {
            break;
        }
        work[out++] = (uint32_t)(i - unchanged);
        count_at = out++;
        while (i < words) {
            uint32_t word = image_word(image, size, i), difference = word ^ old[i];
            /* One unchanged word inside a run stays in it; two end it. */
            if (!difference && (i + 1 >= words || image_word(image, size, i + 1) == old[i + 1])) {
                break;
            }
            work[out++] = difference;
            old[i++] = word;
            changed++;
        }
        work[count_at] = changed;
    }
    bytes = sizeof(*entry) + out * 4;
    entry = malloc(bytes);
    if (!entry) {
        Rewind_Clear(ring);
        return -1;
    }
    entry->before_size = (uint32_t)ring->latest_size;
    entry->words = (uint32_t)out;
    memcpy(entry->data, work, out * 4);
    ring->latest_size = size;
    while (ring->count && (ring->count >= ring->max_entries || ring->used + bytes > ring->budget)) {
        drop_oldest(ring);
    }
    ring->entries[(ring->first + ring->count) % ring->max_entries] = entry;
    ring->count++;
    ring->used += bytes;
    return 0;
}

int Rewind_Back(RewindRing *ring)
{
    unsigned last;
    RewindEntry *entry;
    const uint32_t *in, *end;
    uint32_t *old = (uint32_t *)(void *)ring->latest;
    size_t at = 0;
    if (!ring->count) {
        return 0;
    }
    last = (ring->first + ring->count - 1) % ring->max_entries;
    entry = ring->entries[last];
    in = entry->data;
    end = in + entry->words;
    while (in + 2 <= end) {
        uint32_t changed;
        at += in[0];
        changed = in[1];
        in += 2;
        while (changed-- && in < end) {
            old[at++] ^= *in++;
        }
    }
    ring->latest_size = entry->before_size;
    ring->used -= sizeof(*entry) + (size_t)entry->words * 4;
    free(entry);
    ring->entries[last] = NULL;
    ring->count--;
    return 1;
}

const uint8_t *Rewind_Latest(const RewindRing *ring, size_t *size)
{
    if (size) *size = ring->latest_size;
    return ring->latest_size ? ring->latest : NULL;
}

size_t Rewind_Memory(const RewindRing *ring)
{
    return ring->used + ring->capacity + ring->work_words * sizeof(uint32_t) +
           (ring->entries ? ring->max_entries * sizeof(*ring->entries) : 0);
}
