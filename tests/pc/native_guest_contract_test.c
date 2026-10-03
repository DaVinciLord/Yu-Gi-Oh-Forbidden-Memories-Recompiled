/* Isolated prototype: no change to the runtime CALL32 contract. */
#include "types.h"
#include "port_ptr.h"
#include "pc/memory.h"
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

typedef s32 (*Callback)(s32, s32);
struct GuestRecord { u8 *G32 data; Callback G32 callback; s32 value; };
_Static_assert(sizeof(struct GuestRecord) == 12, "guest layout");
_Static_assert(offsetof(struct GuestRecord, callback) == 4, "callback offset");
_Static_assert(offsetof(struct GuestRecord, value) == 8, "value offset");
#define CHECK(c) do { if (!(c)) { fprintf(stderr, "%d: %s\n", __LINE__, #c); return 1; } } while (0)

static s32 add(s32 first, s32 second) { return first + second; }
static s32 subtract(s32 first, s32 second) { return first - second; }
struct Function { u32 guest; Callback host; };
static const struct Function functions[] = {{0x80010000u, add}, {0x80010004u, subtract}};

static Callback resolve_callback(u32 address)
{
    size_t i;
    /* Only RAM aliases: MMIO, scratchpad, null and other segments are invalid. */
    if (address < MEMORIES_RAM_SIZE ||
        (address >= 0x80000000u && address < 0x80000000u + MEMORIES_RAM_SIZE) ||
        (address >= 0xa0000000u && address < 0xa0000000u + MEMORIES_RAM_SIZE)) {
        address = 0x80000000u | (address & (MEMORIES_RAM_SIZE - 1u));
    } else {
        return NULL;
    }
    for (i = 0; i < sizeof(functions) / sizeof(functions[0]); ++i)
        if (functions[i].guest == address) return functions[i].host;
    return NULL;
}

int main(void)
{
    MemoriesMemory *memory = calloc(1, sizeof(*memory));
    struct GuestRecord record;
    Callback host;
    u8 *bytes;
    const u32 aliases[] = {0x00010000u, 0x80010000u, 0xa0010000u};
    size_t i;
    CHECK(memory != NULL);
    /* Store guest addresses, never native addresses. Do not dereference or
     * invoke a G32 field directly on a translated-memory host. */
    record.data = (u8 *G32)(uintptr_t)0x80000100u;
    record.callback = (Callback G32)(uintptr_t)0x80010000u;
    record.value = -7;
    CHECK((uintptr_t)record.data == 0x80000100u);
    CHECK((uintptr_t)record.callback == 0x80010000u);
    bytes = Memories_Resolve(memory, (u32)(uintptr_t)record.data, 4, 4);
    CHECK(bytes != NULL);
    CHECK((uintptr_t)bytes > UINT32_MAX);
    Memories_WriteLE32(bytes, 0xfedcba98u);
    CHECK(Memories_ReadLE32(Memories_Resolve(memory, 0x100u, 4, 4)) == 0xfedcba98u);
    CHECK(Memories_Resolve(memory, 0xa0000100u, 4, 4) == bytes);
    bytes = Memories_Resolve(memory, 0x1f800320u, 4, 4);
    CHECK(bytes != NULL);
    Memories_WriteLE32(bytes, 42);
    CHECK(Memories_ReadLE32(Memories_Resolve(memory, 0x9f800320u, 4, 4)) == 42);
    host = resolve_callback((u32)(uintptr_t)record.callback);
    CHECK(host == add);
    CHECK((uintptr_t)host > UINT32_MAX);
    CHECK(host(record.value, 12) == 5);
    for (i = 0; i < sizeof(aliases) / sizeof(aliases[0]); ++i) {
        host = resolve_callback(aliases[i]);
        CHECK(host != NULL && host(20, -3) == 17);
    }
    host = resolve_callback(0x80010004u);
    CHECK(host != NULL && host(20, -3) == 23);
    CHECK(resolve_callback(0) == NULL);
    CHECK(resolve_callback(0x80010008u) == NULL);
    CHECK(resolve_callback(0x80010001u) == NULL);
    CHECK(resolve_callback(0xc0010000u) == NULL);
    CHECK(resolve_callback(0x1f800000u) == NULL);
    CHECK(resolve_callback(0xffffffffu) == NULL);
    free(memory);
    puts("Translated guest storage, RAM/scratchpad aliases and full-width callbacks passed");
    return 0;
}
