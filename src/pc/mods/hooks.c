/* Function hooks (mod API 4): a code mod replaces or wraps one of the game's
 * own functions, by address, and gets the function it displaced back to call.
 *
 * Every game unit is compiled with -fpatchable-function-entry=8,6
 * (tools/pc/build_game32.py): six bytes of nops before the function's entry
 * and two at it. A hooked function's six bytes become `jmp *slot`, an
 * indirect jump through a pointer kept here, and its two become `jmp -8`,
 * back into them. The two-byte store is the only one made to code a thread
 * may be running, and it is one aligned-enough write; everything after that
 * changes only `slot` and the mods' `original` pointers, which are words.
 *
 * Hooks on one function chain in the order they were made: the one made
 * last is called first, and its `original` leads to the one before, down to
 * the game's own code. Only applied mods are in a chain; Hooks_Relink
 * rebuilds every chain when a mod is applied or removed. A function no
 * applied mod hooks gets its two nops back. */
#include "hooks.h"
#include "mods.h"
#include "../compat/mman.h"
#include <stdint.h>
#include <string.h>
#include <stdlib.h>

#if defined(__APPLE__) && defined(__aarch64__) && defined(MEMORIES_TRANSLATED)
#define ARM64_HOOKS 1
#define ENTRY_BYTES 0
static struct { void *function, *body; } registered[8192];
static unsigned registered_count;
void Hooks_Register(void *function, void *body)
{
    for (unsigned i = 0; i < registered_count; i++)
        if (registered[i].function == function) return;
    if (registered_count == 8192) abort();
    registered[registered_count].function = function;
    registered[registered_count++].body = body;
}
#else
#define ENTRY_BYTES 2
#endif

#define PRE 6     /* nops before the entry */
#define TARGETS_MAX 1024
#define HOOKS_MAX 2048

typedef struct {
    unsigned char *entry;
    unsigned char saved[2];  /* the entry's own two nops */
    void *volatile slot;     /* where `jmp *slot` goes */
    int patched;
} Target;

typedef struct {
    int owner, token, target;
    void *replacement;
    void **original;
} Hook;

static Target targets[TARGETS_MAX];
static int target_count;
static Hook hooks[HOOKS_MAX];
static int hook_count, serial;

static int writable(unsigned char *from, size_t size, int on)
{
    uintptr_t page = 4096, start = (uintptr_t)from & ~(page - 1), end = ((uintptr_t)from + size + page - 1) & ~(page - 1);
    return mprotect((void *)start, end - start, on ? PROT_READ | PROT_WRITE | PROT_EXEC : PROT_READ | PROT_EXEC) == 0;
}

/* The six bytes before, and the two at, the entry a patchable function has.
 * GCC writes single-byte nops; clang writes 66 90 at the entry. */
static int patchable(const unsigned char *entry)
{
#ifndef __i386__
    if (entry) return 0;   /* `jmp *[abs32]` is the 32-bit game's; 64-bit host tests hook nothing */
#endif
    for (int i = -PRE; i < 0; i++) if (entry[i] != 0x90) return 0;
    return (entry[0] == 0x90 && entry[1] == 0x90) || (entry[0] == 0x66 && entry[1] == 0x90);
}

static int find_target(unsigned char *entry)
{
    int i;
    for (i = 0; i < target_count; i++) if (targets[i].entry == entry) return i;
#ifdef ARM64_HOOKS
    if (target_count == TARGETS_MAX) return -1;
    for (unsigned r = 0; r < registered_count; r++) if (registered[r].function == entry) {
        targets[i].entry = entry;
        targets[i].slot = registered[r].body;
        return target_count++;
    }
    return -1;
#else
    if (target_count == TARGETS_MAX || !patchable(entry)) return -1;
    targets[i].entry = entry;
    memcpy(targets[i].saved, entry, 2);
    targets[i].slot = entry + 2;
    targets[i].patched = 0;
    /* The jump before the entry is written once and never changes: until
     * the entry points at it, nothing runs it. */
    if (!writable(entry - PRE, PRE + 2, 1)) return -1;
    entry[-6] = 0xFF;
    entry[-5] = 0x25;   /* jmp *[slot] */
    {
        uint32_t slot = (uint32_t)(uintptr_t)&targets[i].slot;
        memcpy(entry - 4, &slot, 4);
    }
    writable(entry - PRE, PRE + 2, 0);
    return target_count++;
#endif
}

static void set_entry(Target *target, int hooked)
{
#ifdef ARM64_HOOKS
    target->patched = hooked;
#else
    uint16_t value;
    if (hooked == target->patched) return;
    if (hooked) value = (uint16_t)(0xEB | (0xF8 << 8));   /* jmp -8: back to the jmp *[slot] */
    else memcpy(&value, target->saved, 2);
    if (!writable(target->entry, 2, 1)) return;
    __atomic_store_n((uint16_t *)target->entry, value, __ATOMIC_SEQ_CST);
    writable(target->entry, 2, 0);
    target->patched = hooked;
#endif
}

static void *original_body(Target *target)
{
#ifdef ARM64_HOOKS
    for (unsigned r = 0; r < registered_count; r++)
        if (registered[r].function == target->entry) return registered[r].body;
    abort();
#else
    return target->entry + ENTRY_BYTES;
#endif
}

#ifdef ARM64_HOOKS
void *Hooks_Resolve(void *function, void *body)
{
    for (int t = 0; t < target_count; t++) if (targets[t].entry == function)
        return __atomic_load_n(&targets[t].slot, __ATOMIC_SEQ_CST);
    return body;
}
#endif

void Hooks_Relink(void)
{
    for (int t = 0; t < target_count; t++) {
        void *body = original_body(&targets[t]);
        void *next = body;
        for (int h = 0; h < hook_count; h++) {
            if (hooks[h].target != t || !Mods_Active(hooks[h].owner)) continue;
            if (hooks[h].original) __atomic_store_n(hooks[h].original, next, __ATOMIC_SEQ_CST);
            next = hooks[h].replacement;
        }
        /* An unapplied mod's `original` still leads somewhere real. */
        for (int h = 0; h < hook_count; h++) {
            if (hooks[h].target == t && !Mods_Active(hooks[h].owner) && hooks[h].original)
                __atomic_store_n(hooks[h].original, body, __ATOMIC_SEQ_CST);
        }
        __atomic_store_n(&targets[t].slot, next, __ATOMIC_SEQ_CST);
        set_entry(&targets[t], next != body);
    }
}

int Hooks_Add(int owner, void *function, void *replacement, void **original)
{
    int target;
    if (!function || !replacement || function == replacement || hook_count == HOOKS_MAX || serial == 0x7fffffff) return 0;
    target = find_target(function);
    if (target < 0) return 0;
    if (original) *original = original_body(&targets[target]);
    hooks[hook_count++] = (Hook){owner, ++serial, target, replacement, original};
    Hooks_Relink();
    return serial;
}

void Hooks_Remove(int owner, int token)
{
    for (int i = 0; i < hook_count; i++) {
        if (hooks[i].owner != owner || hooks[i].token != token) continue;
        memmove(hooks + i, hooks + i + 1, (size_t)(--hook_count - i) * sizeof(*hooks));
        Hooks_Relink();
        return;
    }
}

void Hooks_Clear(int owner)
{
    int kept = 0;
    for (int i = 0; i < hook_count; i++) if (hooks[i].owner != owner) hooks[kept++] = hooks[i];
    if (kept == hook_count) return;
    hook_count = kept;
    Hooks_Relink();
}

int Hooks_At(int index, int *owner, const void **function)
{
    if (index < 0 || index >= hook_count) return 0;
    *owner = hooks[index].owner;
    *function = targets[hooks[index].target].entry;
    return 1;
}

int Hooks_IsHooked(const void *function)
{
    int i;
    for (i = 0; i < target_count; i++)
        if (targets[i].entry == function) return targets[i].patched;
    return 0;
}
