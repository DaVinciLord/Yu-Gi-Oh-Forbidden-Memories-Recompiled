/* The registers a signal handler reads from its ucontext (Linux and Android),
 * named per architecture: the program counter, the stack pointer and the
 * frame pointer that crash reports walk from. 32-bit x86 (the desktop builds
 * and Android x86) and 32-bit ARM in A32 state (Android armeabi-v7a, and the
 * same for a Linux armhf build: glibc and bionic share the kernel's
 * sigcontext names). An ARM frame built with -fno-omit-frame-pointer in A32
 * keeps the caller's frame pointer at [fp] and the return address at [fp+4],
 * as i386's EBP chain does, so a walk reads both the same way. The mod SDK
 * (MEMORIES_MOD) has no system headers and no use for these: there the
 * header is empty, and compiles on its own as every SDK header must
 * (tools/pc/check_mod_abi.py). */
#ifndef MEMORIES_PC_PLATFORM_SIGNAL_CONTEXT_H
#define MEMORIES_PC_PLATFORM_SIGNAL_CONTEXT_H
#if !defined(_WIN32) && !defined(MEMORIES_MOD)
#include <ucontext.h>

#if defined(__i386__)
#define SIGNAL_CONTEXT_PC(user) ((user)->uc_mcontext.gregs[REG_EIP])
#define SIGNAL_CONTEXT_SP(user) ((user)->uc_mcontext.gregs[REG_ESP])
#define SIGNAL_CONTEXT_FP(user) ((user)->uc_mcontext.gregs[REG_EBP])
#elif defined(__arm__)
#define SIGNAL_CONTEXT_PC(user) ((user)->uc_mcontext.arm_pc)
#define SIGNAL_CONTEXT_SP(user) ((user)->uc_mcontext.arm_sp)
#define SIGNAL_CONTEXT_FP(user) ((user)->uc_mcontext.arm_fp)
#elif defined(__aarch64__)
/* AArch64 (Android arm64-v8a): X29 is the frame pointer; a frame record
 * holds the caller's X29 at [fp] and the return address at [fp+8]. */
#define SIGNAL_CONTEXT_PC(user) ((user)->uc_mcontext.pc)
#define SIGNAL_CONTEXT_SP(user) ((user)->uc_mcontext.sp)
#define SIGNAL_CONTEXT_FP(user) ((user)->uc_mcontext.regs[29])
#else
#error "signal_context.h: no register names for this architecture"
#endif

#endif
#endif
