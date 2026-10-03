/* Shared save-state container; stack/register payloads belong to each ABI. */
#include "state_io.h"
#include <errno.h>
#include <string.h>

int Memories_StateLoading(const MemoriesState *state) { return state && state->loading; }

void Memories_StateWrite(MemoriesState *state, const void *data, size_t size)
{
    if (size) fwrite(data, 1, size, state->file);
}

/* Chunk: 16-byte tag, 32-bit size, payload. */
const uint8_t *Memories_StateFindChunk(const MemoriesState *state, const char *tag, size_t *size)
{
    size_t at = 16;
    if (!state || !tag || !size || !state->image || state->image_size < at) return NULL;
    char padded[16];
    memset(padded, 0, sizeof(padded));
    strncpy(padded, tag, sizeof(padded) - 1);
    while (at <= state->image_size && state->image_size - at >= 20) {
        uint32_t length;
        memcpy(&length, state->image + at + 16, 4);
        if (length > state->image_size - at - 20) {
            return NULL;
        }
        if (!memcmp(state->image + at, padded, 16)) {
            *size = length;
            return state->image + at + 20;
        }
        at += 20 + length;
    }
    return NULL;
}

int Memories_StateChunk(MemoriesState *state, const char *tag, const MemoriesStateField *fields, size_t count)
{
    size_t total = 0, i, size;
    const uint8_t *from;
    if (!state || !tag || (count && !fields)) { errno = EINVAL; return 0; }
    for (i = 0; i < count; i++) {
        if ((fields[i].size && !fields[i].data) || fields[i].size > UINT32_MAX - total) {
            errno = EINVAL;
            return 0;
        }
        total += fields[i].size;
    }
    if (!state->loading && !state->file) { errno = EINVAL; return 0; }
    if (!state->loading) {
        char padded[16];
        uint32_t length = (uint32_t)total;
        memset(padded, 0, sizeof(padded));
        strncpy(padded, tag, sizeof(padded) - 1);
        Memories_StateWrite(state, padded, 16);
        Memories_StateWrite(state, &length, 4);
        for (i = 0; i < count; i++) {
            Memories_StateWrite(state, fields[i].data, fields[i].size);
        }
        return 0;
    }
    from = Memories_StateFindChunk(state, tag, &size);
    if (!from) {
        fprintf(stderr, "memories-pc: state: no chunk '%s' (%lu bytes in this build); that part keeps its current state\n",
                tag, (unsigned long)total);
        return 0;
    }
    if (size != total) {
        fprintf(stderr, "memories-pc: state: layout changed for '%s' (%lu bytes in the state, %lu in this build); that part keeps its current state\n",
                tag, (unsigned long)size, (unsigned long)total);
        return 0;
    }
    for (i = 0; i < count; i++) {
        if (fields[i].size) memcpy(fields[i].data, from, fields[i].size);
        from += fields[i].size;
    }
    return 1;
}
