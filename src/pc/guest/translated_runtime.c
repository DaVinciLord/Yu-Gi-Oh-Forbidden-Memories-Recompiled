#include "../../types.h"
#include "translated_runtime.h"
#include <stdio.h>
#include <stdlib.h>

#define FUNCTION_LIMIT 8192
/* External native data uses explicit guest-visible spans, never truncation. */
#define EXTERNAL_BASE 0x80200000u
#define EXTERNAL_END 0xf0000000u
/* Automatic globals/heaps are a subset of the external mapping arena. */
#define AUTOMATIC_BASE 0xd0000000u
#define AUTOMATIC_END 0xe0000000u
struct Function {
    u32 guest;
    uintptr_t host;
};
static MemoriesMemory *active;
static GuestRuntimeRegion *regions;
static size_t region_capacity;
static u32 automatic_cursor = AUTOMATIC_BASE;
static struct Function functions[FUNCTION_LIMIT];
static unsigned region_count, function_count;
static void *(*function_resolver)(u32);
static char fatal_detail[512];

const char *GuestRuntime_FatalDetail(void) { return fatal_detail; }

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

/* Keep fatal diagnostics out of the per-access resolver. Inlining this
 * region summary spills SIMD registers even on valid native accesses. */
static __attribute__((cold, noinline, noreturn))
void invalid(const char *operation, uintptr_t address, size_t length)
{
    size_t bytes = 0, heap_bytes = 0;
    unsigned i;
    for (i = 0; i < region_count; ++i) {
        bytes += regions[i].length;
        if (regions[i].flags & MEMORIES_REGION_HEAP) heap_bytes += regions[i].length;
    }
    /* Prepared before abort; the signal handler only copies this text. */
    snprintf(fatal_detail, sizeof(fatal_detail),
             "%s at 0x%llx (%zu bytes); regions=%u live=%zu heap=%zu cursor=0x%x",
             operation, (unsigned long long)address, length,
             region_count, bytes, heap_bytes, automatic_cursor);
    fprintf(stderr, "translated runtime: %s\n", fatal_detail);
    abort();
}

void GuestRuntime_Reset(void)
{
    fatal_detail[0] = 0;
    active = NULL;
    function_resolver = NULL;
    region_count = function_count = 0;
    free(regions);
    regions = NULL;
    region_capacity = 0;
    automatic_cursor = AUTOMATIC_BASE;
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
/* Function tokens use the cached RAM alias; data aliases are resolved by
 * Memories_Resolve. External native regions retain their assigned tokens. */
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
    if (!active || !host || !length ||
        length > UINTPTR_MAX - start || guest < EXTERNAL_BASE || guest >= EXTERNAL_END ||
        length > EXTERNAL_END - guest) return -1;
    for (i = 0; i < region_count; ++i) {
        const GuestRuntimeRegion *r = &regions[i];
        if ((start < r->host + r->length && r->host < start + length) ||
            (guest < r->guest + r->length && r->guest < guest + length)) return -1;
    }
    if (GuestRuntime_ReserveRegions((size_t)region_count + 1)) return -1;
    regions[region_count++] = (GuestRuntimeRegion){start, length, guest, 0, 0};
    return 0;
}
int GuestRuntime_ReserveRegions(size_t count)
{
    size_t capacity = region_capacity ? region_capacity : 128;
    GuestRuntimeRegion *grown;
    if (count <= region_capacity) return 0;
    if (count > UINT32_MAX || count > SIZE_MAX / sizeof(*regions)) return -1;
    while (capacity < count) {
        if (capacity > SIZE_MAX / 2) return -1;
        capacity *= 2;
    }
    if (capacity > SIZE_MAX / sizeof(*regions)) return -1;
    grown = realloc(regions, capacity * sizeof(*regions));
    if (!grown) return -1;
    regions = grown;
    region_capacity = capacity;
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
    u32 candidate = automatic_cursor;
    unsigned i;
    int moved;
    if (!host || !length) return;
    for (i = 0; i < region_count; ++i)
        if (regions[i].host == (uintptr_t)host && regions[i].length == length) return;
    /* Try the cursor first, then the complete arena. A larger temporary
     * allocation may skip a small free span and leave the cursor above it.
     * Failing at the upper end must not hide that reusable lower span. */
    int wrapped = 0;
    do {
        moved = 0;
        if (length > AUTOMATIC_END - candidate) {
            if (wrapped) invalid("guest token arena exhausted", (uintptr_t)host, length);
            candidate = AUTOMATIC_BASE;
            wrapped = 1;
            moved = 1;
            continue;
        }
        for (i = 0; i < region_count; ++i) {
            const GuestRuntimeRegion *r = &regions[i];
            if (candidate < r->guest + r->length && r->guest < candidate + length) {
                size_t next = ((size_t)r->guest + r->length + 15u) & ~(size_t)15u;
                candidate = next >= AUTOMATIC_END ? AUTOMATIC_END : (u32)next;
                moved = 1;
                break;
            }
        }
    } while (moved);
    if (GuestRuntime_RegisterData(host, length, candidate)) invalid("cannot register native allocation", (uintptr_t)host, length);
    automatic_cursor = (u32)(((size_t)candidate + length + 15u) & ~(size_t)15u);
}
unsigned GuestRuntime_RegionCount(void) { return region_count; }
const GuestRuntimeRegion *GuestRuntime_Region(unsigned index)
{
    return index < region_count ? &regions[index] : NULL;
}
void GuestRuntime_RegisterGlobal(void *host, size_t length, uint64_t identity, unsigned flags)
{
    unsigned i;
    GuestRuntime_RegisterAutomatic(host, length);
    for (i = 0; i < region_count; ++i) if (regions[i].host == (uintptr_t)host) {
        if (!regions[i].identity) regions[i].identity = identity;
        regions[i].flags |= MEMORIES_REGION_GLOBAL | flags;
        return;
    }
}
void GuestRuntime_RegisterAllocation(void *host, size_t length)
{
    unsigned i;
    GuestRuntime_RegisterAutomatic(host, length);
    for (i = 0; i < region_count; ++i) if (regions[i].host == (uintptr_t)host) {
        regions[i].flags |= MEMORIES_REGION_HEAP;
        return;
    }
}
int GuestRuntime_RegisterAllocationAt(void *host, size_t length, uint32_t guest)
{
    if (GuestRuntime_RegisterData(host, length, guest)) return -1;
    regions[region_count - 1].flags = MEMORIES_REGION_HEAP;
    return 0;
}
int GuestRuntime_RegisterMapping(void *host, size_t length, uint32_t guest)
{
    if (GuestRuntime_RegisterData(host, length, guest)) return -1;
    regions[region_count - 1].flags = MEMORIES_REGION_MAPPING;
    return 0;
}
int GuestRuntime_UnregisterData(void *host)
{
    unsigned i;
    for (i = 0; i < region_count; ++i) if (regions[i].host == (uintptr_t)host) {
        if (regions[i].guest >= AUTOMATIC_BASE && regions[i].guest < automatic_cursor)
            automatic_cursor = regions[i].guest;
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
    /* Full-width host pointers already address native storage. */
    if (address > UINT32_MAX) return pointer;
    if (!active) invalid("memory context is unbound", address, length);
    host = Memories_Resolve(active, (u32)address, length, 1);
    if (host) return host;
    for (i = 0; i < region_count; ++i) {
        const GuestRuntimeRegion *r = &regions[i];
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
        const GuestRuntimeRegion *r = &regions[i];
        if (host >= r->host && host - r->host < r->length) return r->guest + (u32)(host - r->host);
    }
    /* Keep one-past encodings for legal pointer arithmetic only after all
     * containing regions and function entries have been considered. */
    if (host == ram + MEMORIES_RAM_SIZE) return 0x80000000u + MEMORIES_RAM_SIZE;
    if (host == scratch + MEMORIES_SCRATCHPAD_SIZE) return 0x1f800000u + MEMORIES_SCRATCHPAD_SIZE;
    for (i = 0; i < region_count; ++i) {
        const GuestRuntimeRegion *r = &regions[i];
        if (host == r->host + r->length) return r->guest + (u32)r->length;
    }
    invalid("unregistered native pointer cannot fit guest storage", host, 0);
    return 0;
}
