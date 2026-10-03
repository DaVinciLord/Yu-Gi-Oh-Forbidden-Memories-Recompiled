#include "../../types.h"
#include "translated_runtime.h"
#include <setjmp.h>
#include <stdio.h>
#include <stdlib.h>
#define JUMP_LIMIT 32
static struct { void *key; jmp_buf context; } jumps[JUMP_LIMIT];
void *GuestRuntime_JumpBuffer(void *guest)
{
    void *key = GuestRuntime_ResolveData(guest, 12 * sizeof(s32));
    unsigned i;
    for (i = 0; i < JUMP_LIMIT; ++i) if (jumps[i].key == key) return jumps[i].context;
    for (i = 0; i < JUMP_LIMIT; ++i) if (!jumps[i].key) {
        jumps[i].key = key;
        return jumps[i].context;
    }
    fputs("translated runtime: native jump context registry full\n", stderr);
    abort();
}
void *GuestRuntime_JumpBufferForRestore(void *guest)
{
    void *key = GuestRuntime_ResolveData(guest, 12 * sizeof(s32));
    unsigned i;
    for (i = 0; i < JUMP_LIMIT; ++i) if (jumps[i].key == key) return jumps[i].context;
    fputs("translated runtime: longjmp has no captured native context\n", stderr);
    abort();
}
