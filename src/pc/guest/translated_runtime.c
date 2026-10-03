#include "../../types.h"
#include "translated_runtime.h"
#include <stdio.h>
#include <stdlib.h>

#define REGION_LIMIT 2048
#define FUNCTION_LIMIT 8192
/* External native data uses explicit guest-visible spans, never truncation. */
#define EXTERNAL_BASE 0x80200000u
#define EXTERNAL_END 0xf0000000u
struct Region { uintptr_t host; size_t length; u32 guest; };
struct Function { u32 guest; uintptr_t host; };
static MemoriesMemory *active;
static struct Region regions[REGION_LIMIT];
static struct Function functions[FUNCTION_LIMIT];
static unsigned region_count, function_count;
static void *(*function_resolver)(u32);

/* PS1 C often carries addresses through signed s32 locals. A subsequent
 * integer-to-pointer cast sign-extends on ARM64; preserve its guest bits.
 * Ordinary macOS user pointers cannot occupy this negative address range. */
static uintptr_t guest_bits(uintptr_t address)
{
    if (address > UINT32_MAX &&
        (address >> 32) == UINT32_MAX && (address & 0x80000000u))
        return (u32)address;
    return address;
}

static void invalid(const char *operation, uintptr_t address, size_t length)
{
    fprintf(stderr, "translated runtime: %s at 0x%llx (%zu bytes)\n", operation,
            (unsigned long long)address, length);
    abort();
}

void GuestRuntime_Reset(void)
{
    active = NULL;
    function_resolver = NULL;
    region_count = function_count = 0;
}
int GuestRuntime_IsBound(void) { return active != NULL; }
MemoriesMemory *GuestRuntime_Memory(void) { return active; }
void GuestRuntime_SetFunctionResolver(void *(*resolver)(u32)) { function_resolver = resolver; }
int GuestRuntime_Bind(MemoriesMemory *memory)
{
    if (!memory) return -1;
    GuestRuntime_Reset();
    active = memory;
    return 0;
}
static u32 canonical(u32 address)
{
    if (address < MEMORIES_RAM_SIZE ||
        (address >= 0x80000000u && address - 0x80000000u < MEMORIES_RAM_SIZE) ||
        (address >= 0xa0000000u && address - 0xa0000000u < MEMORIES_RAM_SIZE))
        return 0x80000000u | (address & (MEMORIES_RAM_SIZE - 1u));
    return address;
}
int GuestRuntime_RegisterData(void *host, size_t length, u32 guest)
{
    unsigned i;
    uintptr_t start = (uintptr_t)host;
    if (!active || !host || !length || region_count == REGION_LIMIT ||
        length > UINTPTR_MAX - start || guest < EXTERNAL_BASE || guest >= EXTERNAL_END ||
        length > EXTERNAL_END - guest) return -1;
    for (i = 0; i < region_count; ++i) {
        const struct Region *r = &regions[i];
        if ((start < r->host + r->length && r->host < start + length) ||
            (guest < r->guest + r->length && r->guest < guest + length)) return -1;
    }
    regions[region_count++] = (struct Region){start, length, guest};
    return 0;
}
int GuestRuntime_RegisterFunction(u32 guest, void (*host)(void))
{
    unsigned i;
    guest = canonical(guest);
    if (!active || !host || (guest & 3u) || guest < 0x80010000u ||
        guest >= 0x80200000u || function_count == FUNCTION_LIMIT) return -1;
    for (i = 0; i < function_count; ++i)
        if (functions[i].guest == guest && functions[i].host == (uintptr_t)host) return -1;
    functions[function_count++] = (struct Function){guest, (uintptr_t)host};
    return 0;
}
void GuestRuntime_RegisterAutomatic(void *host, size_t length)
{
    u32 candidate = 0xd0000000u;
    unsigned i;
    int moved;
    if (!host || !length) return;
    for (i = 0; i < region_count; ++i)
        if (regions[i].host == (uintptr_t)host && regions[i].length == length) return;
    /* First fit allows freed allocation spans to be reused, as native malloc
     * does; fixed guest arenas and the native main stack live elsewhere. */
    do {
        moved = 0;
        if (length > 0xe0000000u - candidate) invalid("guest token arena exhausted", (uintptr_t)host, length);
        for (i = 0; i < region_count; ++i) {
            const struct Region *r = &regions[i];
            if (candidate < r->guest + r->length && r->guest < candidate + length) {
                size_t next = ((size_t)r->guest + r->length + 15u) & ~(size_t)15u;
                if (next >= 0xe0000000u) invalid("guest token arena exhausted", (uintptr_t)host, length);
                candidate = (u32)next;
                moved = 1;
                break;
            }
        }
    } while (moved);
    if (GuestRuntime_RegisterData(host, length, candidate)) invalid("cannot register native allocation", (uintptr_t)host, length);
}
int GuestRuntime_UnregisterData(void *host)
{
    unsigned i;
    for (i = 0; i < region_count; ++i) if (regions[i].host == (uintptr_t)host) {
        regions[i] = regions[--region_count];
        return 0;
    }
    return -1;
}
void *GuestRuntime_ResolveData(void *pointer, size_t length)
{
    uintptr_t address = guest_bits((uintptr_t)pointer);
    unsigned i;
    void *host;
    if (address > UINT32_MAX) return pointer;
    if (!active) invalid("memory context is unbound", address, length);
    host = Memories_Resolve(active, (u32)address, length, 1);
    if (host) return host;
    for (i = 0; i < region_count; ++i) {
        const struct Region *r = &regions[i];
        size_t offset;
        if (address < r->guest) continue;
        offset = address - r->guest;
        if (offset < r->length && length <= r->length - offset)
            return (void *)(r->host + offset);
    }
    invalid("invalid guest data span", address, length);
    return NULL;
}
void *GuestRuntime_ResolveFunction(void *pointer)
{
    uintptr_t address = guest_bits((uintptr_t)pointer);
    u32 guest;
    unsigned i;
    if (address > UINT32_MAX) return pointer;
    guest = canonical((u32)address);
    if (function_resolver) {
        void *target = function_resolver(guest);
        if (target) return target;
    }
    for (i = 0; i < function_count; ++i)
        if (functions[i].guest == guest) return (void *)functions[i].host;
    invalid("unknown guest function", address, 0);
    return NULL;
}
u32 GuestRuntime_EncodePointer(void *pointer)
{
    uintptr_t host = guest_bits((uintptr_t)pointer);
    uintptr_t ram, scratch;
    unsigned i;
    if (host <= UINT32_MAX) return (u32)host;
    if (!active) invalid("memory context is unbound", host, 0);
    ram = (uintptr_t)active->ram;
    scratch = (uintptr_t)active->scratchpad;
    /* Prefer an address inside storage to another allocation's one-past.
     * Native globals may be adjacent while guest tokens are aligned apart.
     * RAM and scratchpad are also adjacent in MemoriesMemory. */
    if (host >= ram && host - ram < MEMORIES_RAM_SIZE) return 0x80000000u + (u32)(host - ram);
    if (host >= scratch && host - scratch < MEMORIES_SCRATCHPAD_SIZE) return 0x1f800000u + (u32)(host - scratch);
    for (i = 0; i < function_count; ++i) if (functions[i].host == host) return functions[i].guest;
    for (i = 0; i < region_count; ++i) {
        const struct Region *r = &regions[i];
        if (host >= r->host && host - r->host < r->length) return r->guest + (u32)(host - r->host);
    }
    /* Keep one-past encodings for legal pointer arithmetic only after all
     * containing regions and function entries have been considered. */
    if (host == ram + MEMORIES_RAM_SIZE) return 0x80000000u + MEMORIES_RAM_SIZE;
    if (host == scratch + MEMORIES_SCRATCHPAD_SIZE) return 0x1f800000u + MEMORIES_SCRATCHPAD_SIZE;
    for (i = 0; i < region_count; ++i) {
        const struct Region *r = &regions[i];
        if (host == r->host + r->length) return r->guest + (u32)r->length;
    }
    invalid("unregistered native pointer cannot fit guest storage", host, 0);
    return 0;
}
