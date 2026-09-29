/* 32-bit ARM (A32) counterpart of state_i386.S: the VSync entry that records
 * what the game caller expects back, the return into that caller, and the
 * stack switch where the C library has no ucontext (Android's bionic).
 * The build assembles it for ARM targets only (tools/pc/build_game32.py).
 * Callee-saved under AAPCS: R4-R11, SP, and D8-D15 of the VFP (the caller's
 * LR is its return address). Position-independent: the one variable is
 * reached through the GOT, so the same file serves a shared object
 * (Android's libmain.so) and an executable. */
    .syntax unified
    .arm
    .text

/* Memories_StateEntry's layout (state.h): R4-R11 at 0, SP at 32, LR at 36,
 * D8-D15 at 40. R12 is free at a call. */
    .globl VSync
    .type VSync, %function
    .p2align 2
VSync:
    ldr r12, 2f
1:  ldr r12, [pc, r12]
    stm r12, {r4-r11}
    str sp, [r12, #32]
    str lr, [r12, #36]
#if defined(__ARM_FP)
    add r12, r12, #40
    vstmia r12, {d8-d15}
#endif
    b Memories_VSync
2:  .word Memories_StateEntry(GOT_PREL) - ((1b + 8) - 2b)
    .size VSync, . - VSync

/* void Memories_StateReturn(const MemoriesStateEntry *entry, int value):
 * return `value` from the VSync call that `entry` describes. */
    .globl Memories_StateReturn
    .type Memories_StateReturn, %function
    .p2align 2
Memories_StateReturn:
#if defined(__ARM_FP)
    add r2, r0, #40
    vldmia r2, {d8-d15}
#endif
    ldm r0, {r4-r11}
    ldr sp, [r0, #32]
    ldr lr, [r0, #36]
    mov r0, r1
    bx lr
    .size Memories_StateReturn, . - Memories_StateReturn

/* void Memories_ContextSwitch(uint32_t *from_sp, const uint32_t *to_sp):
 * keeps the callee-saved registers on the stack being left (R12 as well, so
 * that the frame stays a multiple of 8 bytes) and resumes the one whose
 * stack pointer `to_sp` holds: D8-D15, then R4-R12 and LR, then a branch to
 * LR. state.c's switch_frame builds a first frame the same way. */
    .globl Memories_ContextSwitch
    .type Memories_ContextSwitch, %function
    .p2align 2
Memories_ContextSwitch:
    push {r4-r12, lr}
#if defined(__ARM_FP)
    vpush {d8-d15}
#else
    sub sp, sp, #64
#endif
    str sp, [r0]
    ldr sp, [r1]
#if defined(__ARM_FP)
    vpop {d8-d15}
#else
    add sp, sp, #64
#endif
    pop {r4-r12, lr}
    bx lr
    .size Memories_ContextSwitch, . - Memories_ContextSwitch
    .section .note.GNU-stack, "", %progbits
