#ifndef MEMORIES_TRANSLATED_RUNTIME_H
#define MEMORIES_TRANSLATED_RUNTIME_H
#include "pc/memory.h"
/* Experimental native backend helpers used by translated LLVM IR.
 * Registration is single-threaded, before timers/game execution start. */
int GuestRuntime_Bind(MemoriesMemory *memory);
void GuestRuntime_Reset(void);
void GuestRuntime_SetFunctionResolver(void *(*resolver)(uint32_t));
int GuestRuntime_IsBound(void);
MemoriesMemory *GuestRuntime_Memory(void);
int GuestRuntime_RegisterData(void *host, size_t length, uint32_t guest);
void GuestRuntime_RegisterAutomatic(void *host, size_t length);
int GuestRuntime_UnregisterData(void *host);
int GuestRuntime_RegisterFunction(uint32_t guest, void (*host)(void));
void *GuestRuntime_ResolveData(void *address, size_t length);
void *GuestRuntime_ResolveFunction(void *address);
uint32_t GuestRuntime_EncodePointer(void *host);
/* Generated, typed dispatch for calls leaving an interpreted MIPS module. */
uint32_t GuestRuntime_InvokeNative(unsigned index, const uint32_t *arguments);
#endif
