/* Indirect calls and jumps that may land in guest code, without DEP.
 *
 * Tables in the retail data image hold MIPS function addresses (the text
 * opcode handlers, callbacks an overlay installs), and native code calls
 * through them. Every unit the build compiles sends its indirect calls and
 * jumps through the thunks below: clang's -mretpoline-external-thunk and
 * GCC's -mindirect-branch=thunk-extern -mindirect-branch-register load the
 * target into a register and call or jump to __x86_indirect_thunk_<register>
 * (tools/pc/build_game32.py, tools/pc/build_mod.py). A target in guest memory
 * goes to Memories_GuestBranchResolver (image.c: the native function of that
 * address, or the MIPS interpreter's entry for an overlay callback), anything
 * else is jumped to as it is. A module function that C calls by name is
 * pinned to its guest address, so that call is direct and no thunk sees it:
 * the build gives each such name a host stub that pushes the address and
 * enters Memories_GuestBranchDirect below, which resolves it the same way.
 *
 * Before these, the only way in was the fault of executing guest RAM, which
 * needs DEP for the process: with DEP off, the MIPS bytes of a handler ran as
 * x86 code (the title's Options: the text handler at 0x80038b4c jumped to
 * 0x902b4950). The fault handler in image.c stays as the second net.
 *
 * The contract, for the compilers' code and for mods built by build_mod.py:
 * every register is kept, the target register too (a compiler may pick a
 * callee-saved one and keep it across the call), and the stack is as it was,
 * the caller's return address on top for a call, so a native function or
 * Memories_MipsThunk starts exactly as it would from a direct call (or from
 * the fault handler's redirect). Flags are not kept: they are dead at an
 * indirect call or jump. Nothing is stored below the stack pointer, where the
 * Windows interrupt clock pushes while the thread is suspended.
 *
 * Fast path: one test. Bits 21-28 and 30 are clear in every guest range
 * (physical 0x10000..0x200000, 0x80000000..0x80200000, 0xA0000000..
 * 0xA0200000); executable code never has them all clear, and the few host
 * addresses that do (0x20000000..0x20200000) come back from the resolver
 * unchanged. Slow path: a copy of the return address becomes the slot the
 * final `ret` takes the destination from (and what a stack walk reads as
 * the frame's return address), eax/ecx/edx/flags are saved, the resolver is
 * called on a 16-byte aligned stack, and everything is restored. */
#include "image.h"

void *(*Memories_GuestBranchResolver)(unsigned address);

#if defined(__i386__)
#ifdef _WIN32
#define SYMBOL(name) "_" #name
#define FUNCTION(name) ""
#define END(name) ""
#else
#define SYMBOL(name) #name
#define FUNCTION(name) ".type " #name ", @function\n"
#define END(name) ".size " #name ", . - " #name "\n"
#endif

/* `load` reads the target once eax/ecx/edx are saved and ebp is the frame:
 * the register itself, or for ebp its saved copy. */
#define THUNK(reg, load)                                                                  \
    ".p2align 4\n"                                                                        \
    ".globl " SYMBOL(__x86_indirect_thunk_##reg) "\n"                                     \
    FUNCTION(__x86_indirect_thunk_##reg)                                                  \
    SYMBOL(__x86_indirect_thunk_##reg) ":\n"                                              \
    "    testl $0x5fe00000, %" #reg "\n"                                                  \
    "    jz 1f\n"                                                                         \
    "    jmp *%" #reg "\n"                                                                \
    "1:  pushl (%esp)\n"                                                                  \
    "    pushl %ebp\n"                                                                    \
    "    movl %esp, %ebp\n"                                                               \
    "    pushfl\n"                                                                        \
    "    pushl %eax\n"                                                                    \
    "    pushl %ecx\n"                                                                    \
    "    pushl %edx\n"                                                                    \
    "    movl " load ", %eax\n"                                                           \
    "    jmp memories_branch_resolve\n"                                                   \
    END(__x86_indirect_thunk_##reg)

__asm__(".text\n"
        /* eax: the target. The frame: ebp+4 the slot, ebp-4 flags, then
         * eax, ecx, edx. */
        ".p2align 4\n"
        "memories_branch_resolve:\n"
#if defined(__PIC__) && defined(__ELF__)
        /* Position-independent (Android's shared object): the resolver's
         * address from the GOT; the flags are saved already. */
        "    call 3f\n"
        "3:  popl %ecx\n"
        "    addl $_GLOBAL_OFFSET_TABLE_+(.-3b), %ecx\n"
        "    movl " SYMBOL(Memories_GuestBranchResolver) "@GOT(%ecx), %ecx\n"
        "    movl (%ecx), %ecx\n"
#else
        "    movl " SYMBOL(Memories_GuestBranchResolver) ", %ecx\n"
#endif
        "    testl %ecx, %ecx\n"
        "    jz 2f\n"
        "    andl $-16, %esp\n"
        "    subl $12, %esp\n"
        "    pushl %eax\n"
        "    call *%ecx\n"
        "2:  movl %eax, 4(%ebp)\n"
        "    leal -16(%ebp), %esp\n"
        "    popl %edx\n"
        "    popl %ecx\n"
        "    popl %eax\n"
        "    popfl\n"
        "    popl %ebp\n"
        "    ret\n"
        /* The entry of a host stub the build writes for a module function
         * that C calls by name (tools/pc/build_game32.py, guest_branches.c):
         * the stub pushes the guest address, which becomes the slot. */
        ".p2align 4\n"
        ".globl " SYMBOL(Memories_GuestBranchDirect) "\n"
        FUNCTION(Memories_GuestBranchDirect)
        SYMBOL(Memories_GuestBranchDirect) ":\n"
        "    pushl %ebp\n"
        "    movl %esp, %ebp\n"
        "    pushfl\n"
        "    pushl %eax\n"
        "    pushl %ecx\n"
        "    pushl %edx\n"
        "    movl 4(%ebp), %eax\n"
        "    jmp memories_branch_resolve\n"
        END(Memories_GuestBranchDirect)
        THUNK(eax, "%eax")
        THUNK(ecx, "%ecx")
        THUNK(edx, "%edx")
        THUNK(ebx, "%ebx")
        THUNK(esi, "%esi")
        THUNK(edi, "%edi")
        THUNK(ebp, "(%ebp)"));
#elif defined(__arm__)
/* 32-bit ARM (A32). No compiler routes indirect calls through named thunks
 * for Spectre as the x86 ones do, but clang's -mharden-sls=blr turns every
 * `blx rN` into `bl __llvm_slsblr_thunk_arm_rN`, and emits those thunks as
 * weak definitions of its own, which the strong ones below replace at link.
 * With -fno-optimize-sibling-calls (an indirect tail call would be a `bx rN`)
 * and -fno-jump-tables, no other indirect branch is left in a unit
 * (tools/pc/build_game32.py checks the objects). The contract is the x86
 * one, in AAPCS terms: the thunk is reached by `bl`, so LR is already the
 * caller's return address; every register is kept but R12 (IP), which AAPCS
 * lets a call's veneer change, and which carries the resolved target; the
 * stack is as the caller left it. VFP registers D0-D7 are kept too, which a
 * hard-float ABI (Linux armhf) passes arguments in.
 *
 * Fast path: bits 21-28 and 30 of the target clear, as on x86, tested in
 * two parts (an A32 immediate is 8 bits rotated). Slow path: R0-R3, R12, LR
 * and D0-D7 are saved (88 bytes: the stack stays 8-byte aligned), the
 * resolver is called with the target, and everything but R12 is restored. */
#define THUNK(n)                                                                          \
    ".p2align 2\n"                                                                        \
    ".globl __llvm_slsblr_thunk_arm_r" #n "\n"                                            \
    ".type __llvm_slsblr_thunk_arm_r" #n ", %function\n"                                  \
    "__llvm_slsblr_thunk_arm_r" #n ":\n"                                                  \
    "    tst r" #n ", #0x0fe00000\n"                                                      \
    "    tsteq r" #n ", #0x50000000\n"                                                    \
    "    bxne r" #n "\n"                                                                  \
    "    push {r0-r3, r12, lr}\n"                                                         \
    "    mov r0, r" #n "\n"                                                               \
    "    b memories_branch_resolve\n"                                                     \
    ".size __llvm_slsblr_thunk_arm_r" #n ", . - __llvm_slsblr_thunk_arm_r" #n "\n"

#if defined(__ARM_FP)
#define SAVE_VFP "    vpush {d0-d7}\n"
#define RESTORE_VFP "    vpop {d0-d7}\n"
#else
#define SAVE_VFP "    sub sp, sp, #64\n"
#define RESTORE_VFP "    add sp, sp, #64\n"
#endif

__asm__(".syntax unified\n"
        ".arm\n"
        ".text\n"
        /* R0: the target; R0-R3, R12, LR saved below the caller's stack. */
        ".p2align 2\n"
        "memories_branch_resolve:\n"
        SAVE_VFP
        "    ldr r1, 2f\n"
        "1:  ldr r1, [pc, r1]\n"       /* &Memories_GuestBranchResolver, from the GOT */
        "    ldr r1, [r1]\n"
        "    cmp r1, #0\n"
        "    beq 3f\n"
        "    blx r1\n"
        "3:  mov r12, r0\n"
        RESTORE_VFP
        "    pop {r0-r3}\n"
        "    add sp, sp, #4\n"          /* the saved R12 */
        "    pop {lr}\n"
        "    bx r12\n"
        "2:  .word Memories_GuestBranchResolver(GOT_PREL) - ((1b + 8) - 2b)\n"
        /* The entry of a host stub the build writes for a module function
         * that C calls by name (tools/pc/build_game32.py, guest_branches.c):
         * the stub leaves the guest address in R12. */
        ".p2align 2\n"
        ".globl Memories_GuestBranchDirect\n"
        ".type Memories_GuestBranchDirect, %function\n"
        "Memories_GuestBranchDirect:\n"
        "    push {r0-r3, r12, lr}\n"
        "    mov r0, r12\n"
        "    b memories_branch_resolve\n"
        ".size Memories_GuestBranchDirect, . - Memories_GuestBranchDirect\n"
        THUNK(0) THUNK(1) THUNK(2) THUNK(3) THUNK(4) THUNK(5) THUNK(6) THUNK(7) THUNK(8) THUNK(9)
        THUNK(10) THUNK(11) THUNK(12)
#if defined(__thumb__)
        ".thumb\n" /* the compiler's own code follows */
#endif
        );
#endif
