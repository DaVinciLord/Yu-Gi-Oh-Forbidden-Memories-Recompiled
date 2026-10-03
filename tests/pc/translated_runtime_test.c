#include "types.h"
#include "pc/guest/translated_runtime.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/wait.h>
#include <unistd.h>
#include <signal.h>
static s32 sum(s32 a, s32 b) { return a + b; }
static void expect_abort(int which)
{
    pid_t child = fork();
    int status;
    assert(child >= 0);
    if (!child) {
        if (which == 0) GuestRuntime_ResolveData((void *)(uintptr_t)0xffffffffu, 1);
        if (which == 1) GuestRuntime_ResolveData((void *)(uintptr_t)0xd0000007u, 2);
        if (which == 2) GuestRuntime_ResolveFunction((void *)(uintptr_t)0x80010008u);
        if (which == 3) GuestRuntime_EncodePointer((void *)(uintptr_t)0xfeed00000000ull);
        _exit(0);
    }
    assert(waitpid(child, &status, 0) == child);
    assert(WIFSIGNALED(status) && WTERMSIG(status) == SIGABRT);
}
int main(void)
{
    MemoriesMemory *memory = calloc(1, sizeof(*memory));
    u8 external[8] = {0};
    u8 adjacent[34] = {0};
    s32 (*function)(s32, s32);
    unsigned i;
    assert(memory && GuestRuntime_Bind(memory) == 0);
    assert(GuestRuntime_Bind(NULL) == -1);
    assert(GuestRuntime_ResolveData((void *)(uintptr_t)0x80000100u, 4) == memory->ram + 0x100);
    assert(GuestRuntime_ResolveData((void *)(uintptr_t)0xa0000100u, 4) == memory->ram + 0x100);
    assert(GuestRuntime_ResolveData(NULL, 1) == memory->ram); /* console kernel RAM */
    assert(GuestRuntime_EncodePointer(memory->ram + 0x123) == 0x80000123u);
    assert(GuestRuntime_EncodePointer(memory->scratchpad + 0x123) == 0x1f800123u);
    assert(GuestRuntime_EncodePointer(memory->scratchpad) == 0x1f800000u);
    assert(GuestRuntime_ResolveData((void *)(uintptr_t)GuestRuntime_EncodePointer(memory->scratchpad), 1) == memory->scratchpad);
    assert(GuestRuntime_EncodePointer(NULL) == 0);
    assert(GuestRuntime_RegisterData(external, sizeof(external), 0xd0000000u) == 0);
    assert(GuestRuntime_RegisterData(external, 1, 0xd0000010u) == -1);
    assert(GuestRuntime_RegisterData(external + 1, 1, 0xd0000000u) == -1);
    assert(GuestRuntime_EncodePointer(external + 7) == 0xd0000007u);
    assert(!GuestRuntime_RegisterData(adjacent, 14, 0xd0001000u));
    assert(!GuestRuntime_RegisterData(adjacent + 14, 20, 0xd0002000u));
    assert(GuestRuntime_EncodePointer(adjacent + 14) == 0xd0002000u);
    assert(GuestRuntime_ResolveData((void *)(uintptr_t)GuestRuntime_EncodePointer(adjacent + 14), 20) == adjacent + 14);
    assert(GuestRuntime_EncodePointer(adjacent + 34) == 0xd0002014u);
    assert(GuestRuntime_EncodePointer(external + 8) == 0xd0000008u);
    assert(GuestRuntime_ResolveData((void *)(uintptr_t)0xd0000007u, 1) == external + 7);
    assert(GuestRuntime_ResolveData(external, sizeof(external)) == external);
    assert(GuestRuntime_ResolveData((void *)(intptr_t)(int32_t)0xd0000007u, 1) == external + 7);
    assert(GuestRuntime_ResolveData((void *)(intptr_t)(int32_t)0x80000100u, 4) == memory->ram + 0x100);
    assert(GuestRuntime_EncodePointer((void *)(intptr_t)(int32_t)0xd0000007u) == 0xd0000007u);
    assert(GuestRuntime_RegisterFunction(0x80010000u, (void (*)(void))sum) == 0);
    assert(GuestRuntime_RegisterFunction(0xa0010000u, (void (*)(void))sum) == -1);
    assert(GuestRuntime_RegisterFunction(0x80010001u, (void (*)(void))sum) == -1);
    assert(GuestRuntime_EncodePointer((void *)(uintptr_t)sum) == 0x80010000u);
    function = (s32 (*)(s32, s32))GuestRuntime_ResolveFunction((void *)(uintptr_t)0x10000u);
    assert(function(10, -3) == 7);
    function = (s32 (*)(s32, s32))GuestRuntime_ResolveFunction((void *)(intptr_t)(int32_t)0x80010000u);
    assert(function(10, -3) == 7);
    for (i = 0; i < 4; ++i) expect_abort((int)i);
    GuestRuntime_Reset();
    free(memory);
    puts("Translated runtime: data/function round trips and fail-closed invalid addresses passed");
    return 0;
}
