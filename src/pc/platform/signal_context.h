/* The registers a signal handler reads from its ucontext (Linux and Android),
 * named per architecture: the program counter, the stack pointer and the
 * frame pointer that crash reports walk from. 32-bit x86 (the desktop builds
 * and Android x86) and 32-bit ARM in A32 state (Android armeabi-v7a, and the
 * same for a Linux armhf build: glibc and bionic share the kernel's
 * sigcontext names). An ARM frame built with -fno-omit-frame-pointer in A32
 * keeps the caller's frame pointer at [fp] and the return address at [fp+4],
 * as i386's EBP chain does, so a walk reads both the same way. */
#ifndef MEMORIES_PC_PLATFORM_SIGNAL_CONTEXT_H
#define MEMORIES_PC_PLATFORM_SIGNAL_CONTEXT_H
#ifndef _WIN32
#include <ucontext.h>

#if defined(__i386__)
#define SIGNAL_CONTEXT_PC(user) ((user)->uc_mcontext.gregs[REG_EIP])
#define SIGNAL_CONTEXT_SP(user) ((user)->uc_mcontext.gregs[REG_ESP])
#define SIGNAL_CONTEXT_FP(user) ((user)->uc_mcontext.gregs[REG_EBP])
#elif defined(__arm__)
#define SIGNAL_CONTEXT_PC(user) ((user)->uc_mcontext.arm_pc)
#define SIGNAL_CONTEXT_SP(user) ((user)->uc_mcontext.arm_sp)
#define SIGNAL_CONTEXT_FP(user) ((user)->uc_mcontext.arm_fp)
#else
#error "signal_context.h: no register names for this architecture"
#endif

#endif
#endif
