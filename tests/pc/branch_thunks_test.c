/* The indirect-branch thunks (src/pc/guest/branch_thunks.c): for each of the
 * seven registers a compiler may call through, a target in guest memory
 * reaches what the resolver names and a host target is jumped to as it is,
 * with every register (the target register too) and the stack as the caller
 * left them; the same through the entry of the stubs the build writes for
 * module functions called by name. Then calls from C, which this file is
 * compiled to route through the thunks: arguments and results pass, and the
 * resolver runs on an aligned stack. Last, tail jmps through the thunks and
 * to a stub.
 * Nothing here maps guest memory: the guest addresses must never be jumped
 * to, or the test faults. */
#include "pc/guest/image.h"
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#if defined(__i386__)
#ifdef _WIN32
#define SYMBOL(name) "_" #name
#else
#define SYMBOL(name) #name
#endif

#define GUEST_RECORD 0x80001000u
#define GUEST_ADD 0x80002004u
#define GUEST_PHYSICAL 0x00012340u
#define GUEST_KSEG1 0xa0002004u

/* What record_registers saw: eax, ecx, edx, ebx, esp, ebp, esi, edi. */
uint32_t seen[8];
uint32_t esp_before;
/* Resolutions of the test's guest addresses, and of anything else: a host
 * address whose bits 21-28 and 30 are clear takes the slow path too, which
 * an address-randomized test executable can be loaded at. */
static unsigned resolved, others, misaligned;
void record_registers(void);
__asm__(".text\n"
        ".globl " SYMBOL(record_registers) "\n"
        SYMBOL(record_registers) ":\n"
        "    movl %eax, " SYMBOL(seen) "\n"
        "    movl %ecx, " SYMBOL(seen) "+4\n"
        "    movl %edx, " SYMBOL(seen) "+8\n"
        "    movl %ebx, " SYMBOL(seen) "+12\n"
        "    movl %esp, " SYMBOL(seen) "+16\n"
        "    movl %ebp, " SYMBOL(seen) "+20\n"
        "    movl %esi, " SYMBOL(seen) "+24\n"
        "    movl %edi, " SYMBOL(seen) "+28\n"
        "    ret\n");

/* call_through_<reg>(target): every register but esp set to a known value,
 * <reg> to `target`, then a call through that register's thunk. */
#define DRIVER(reg)                                                               \
    void call_through_##reg(uint32_t target);                                     \
    __asm__(".text\n"                                                             \
            ".globl " SYMBOL(call_through_##reg) "\n"                             \
            SYMBOL(call_through_##reg) ":\n"                                      \
            "    movl 4(%esp), %eax\n"                                            \
            "    pushal\n"                                                        \
            "    pushl %eax\n"                                                    \
            "    movl $0x11111111, %eax\n"                                        \
            "    movl $0x22222222, %ecx\n"                                        \
            "    movl $0x33333333, %edx\n"                                        \
            "    movl $0x44444444, %ebx\n"                                        \
            "    movl $0x66666666, %ebp\n"                                        \
            "    movl $0x77777777, %esi\n"                                        \
            "    movl $0x88888888, %edi\n"                                        \
            "    popl %" #reg "\n"                                                \
            "    movl %esp, " SYMBOL(esp_before) "\n"                             \
            "    call " SYMBOL(__x86_indirect_thunk_##reg) "\n"                   \
            "1:  cmpl %esp, " SYMBOL(esp_before) "\n"                             \
            "    je 2f\n"                                                         \
            "    movl $0, " SYMBOL(esp_before) "\n"                               \
            "2:  popal\n"                                                         \
            "    ret\n");
DRIVER(eax)
DRIVER(ecx)
DRIVER(edx)
DRIVER(ebx)
DRIVER(esi)
DRIVER(edi)
DRIVER(ebp)

/* A module function the C calls by name, as build_game32.py writes its host
 * stub (guest_branches.c), and a driver that calls it directly with every
 * register set to its known value (the argument is not used). */
__asm__(".text\n"
        "direct_record:\n"
        "    pushl $0x80001000\n"
        "    jmp " SYMBOL(Memories_GuestBranchDirect) "\n"
        ".globl " SYMBOL(call_direct) "\n"
        SYMBOL(call_direct) ":\n"
        "    pushal\n"
        "    movl $0x11111111, %eax\n"
        "    movl $0x22222222, %ecx\n"
        "    movl $0x33333333, %edx\n"
        "    movl $0x44444444, %ebx\n"
        "    movl $0x66666666, %ebp\n"
        "    movl $0x77777777, %esi\n"
        "    movl $0x88888888, %edi\n"
        "    movl %esp, " SYMBOL(esp_before) "\n"
        "    call direct_record\n"
        "    cmpl %esp, " SYMBOL(esp_before) "\n"
        "    je 1f\n"
        "    movl $0, " SYMBOL(esp_before) "\n"
        "1:  popal\n"
        "    ret\n");
void call_direct(uint32_t unused);

/* tail_<reg>(a, b, c): a sibling call as a compiler emits one, the target
 * (tail_target) in <reg> and a jmp through that register's thunk, with the
 * caller's return address on top of the stack and the arguments above it;
 * tail_direct, a jmp to a build-style stub. */
uint32_t tail_target;
#define TAIL(reg)                                                                 \
    int tail_##reg(int a, int b, int c);                                          \
    __asm__(".text\n"                                                             \
            ".globl " SYMBOL(tail_##reg) "\n"                                     \
            SYMBOL(tail_##reg) ":\n"                                              \
            "    movl " SYMBOL(tail_target) ", %" #reg "\n"                       \
            "    jmp " SYMBOL(__x86_indirect_thunk_##reg) "\n");
TAIL(eax)
TAIL(ecx)
TAIL(edx)
int tail_direct(int a, int b, int c);
__asm__(".text\n"
        "direct_add:\n"
        "    pushl $0x80002004\n"
        "    jmp " SYMBOL(Memories_GuestBranchDirect) "\n"
        ".globl " SYMBOL(tail_direct) "\n"
        SYMBOL(tail_direct) ":\n"
        "    jmp direct_add\n");

static int add3(int a, int b, int c) { return a + b + c; }

static void *resolve(unsigned address)
{
    /* The thunk aligns the stack to 16 before the call, so this frame's
     * base (below the return address and the saved ebp) is 8 past it. */
    if (((uintptr_t)__builtin_frame_address(0) & 15) != 8) misaligned++;
    if (address == GUEST_RECORD || address == GUEST_ADD || address == GUEST_KSEG1 || address == GUEST_PHYSICAL) {
        resolved++;
    } else {
        others++;
    }
    if (address == GUEST_RECORD) return (void *)(uintptr_t)record_registers;
    if (address == GUEST_ADD || address == GUEST_KSEG1 || address == GUEST_PHYSICAL) return (void *)(uintptr_t)add3;
    return (void *)(uintptr_t)address;
}

static int check_registers(const char *name, void (*driver)(uint32_t), int slot, uint32_t target)
{
    static const uint32_t magic[8] = {0x11111111, 0x22222222, 0x33333333, 0x44444444, 0, 0x66666666, 0x77777777,
                                      0x88888888};
    int i, failures = 0;
    memset(seen, 0, sizeof(seen));
    driver(target);
    for (i = 0; i < 8; i++) {
        uint32_t expected = i == slot ? target : magic[i];
        if (i == 4) continue;
        if (seen[i] != expected) {
            printf("FAIL %s -> 0x%08x: register %d is 0x%08x, not 0x%08x\n", name, target, i, seen[i], expected);
            failures++;
        }
    }
    if (!esp_before || seen[4] != esp_before - 4) {
        printf("FAIL %s -> 0x%08x: the stack moved\n", name, target);
        failures++;
    }
    return failures;
}

typedef int (*Add)(int, int, int);

static int __attribute__((noinline)) call_from_c(Add function, int x)
{
    return function(x, 1, 2);   /* what the compiler makes of it: a call or a jmp through a thunk */
}

int main(void)
{
    static const struct { const char *name; void (*driver)(uint32_t); int slot; } drivers[] = {
        {"eax", call_through_eax, 0}, {"ecx", call_through_ecx, 1}, {"edx", call_through_edx, 2},
        {"ebx", call_through_ebx, 3}, {"ebp", call_through_ebp, 5}, {"esi", call_through_esi, 6},
        {"edi", call_through_edi, 7}};
    volatile Add through;
    unsigned i, before;
    int failures = 0;
    if (!((uintptr_t)record_registers & 0x5fe00000u) || !((uintptr_t)add3 & 0x5fe00000u)) {
        /* The checks below tell a host target by its taking the fast path. */
        printf("FAIL the test's code at 0x%08x lies where the thunks' fast path takes it for guest memory; "
               "link it at a fixed base (--disable-dynamicbase)\n", (unsigned)(uintptr_t)record_registers);
        return 1;
    }
    Memories_GuestBranchResolver = resolve;
    for (i = 0; i < sizeof(drivers) / sizeof(drivers[0]); i++) {
        before = resolved;
        failures += check_registers(drivers[i].name, drivers[i].driver, drivers[i].slot, GUEST_RECORD);
        if (resolved != before + 1) {
            printf("FAIL %s: the guest target was not resolved\n", drivers[i].name);
            failures++;
        }
        before = resolved;
        failures += check_registers(drivers[i].name, drivers[i].driver, drivers[i].slot,
                                    (uint32_t)(uintptr_t)record_registers);
        if (resolved != before) {
            printf("FAIL %s: a host target was resolved as a guest one\n", drivers[i].name);
            failures++;
        }
    }
    before = resolved;
    failures += check_registers("direct call", call_direct, -1, GUEST_RECORD);
    if (resolved != before + 1) failures++, printf("FAIL direct call: the guest address was not resolved\n");
    through = (Add)(uintptr_t)GUEST_ADD;
    if (through(1, 2, 3) != 6) failures++, printf("FAIL call to a KSEG0 guest address\n");
    through = (Add)(uintptr_t)GUEST_KSEG1;
    if (through(10, 20, 30) != 60) failures++, printf("FAIL call to a KSEG1 guest address\n");
    through = (Add)(uintptr_t)GUEST_PHYSICAL;
    if (through(5, 5, 5) != 15) failures++, printf("FAIL call to a physical guest address\n");
    if (call_from_c((Add)(uintptr_t)GUEST_ADD, 4) != 7) failures++, printf("FAIL call to a guest address from C\n");
    {
        static const struct { const char *name; int (*tail)(int, int, int); } tails[] = {
            {"eax", tail_eax}, {"ecx", tail_ecx}, {"edx", tail_edx}};
        for (i = 0; i < sizeof(tails) / sizeof(tails[0]); i++) {
            tail_target = GUEST_ADD;
            before = resolved;
            if (tails[i].tail(1, 2, 3) != 6 || resolved != before + 1) {
                failures++, printf("FAIL tail jmp through %s to a guest address\n", tails[i].name);
            }
            tail_target = (uint32_t)(uintptr_t)add3;
            before = resolved;
            if (tails[i].tail(4, 5, 6) != 15 || resolved != before) {
                failures++, printf("FAIL tail jmp through %s to a host function\n", tails[i].name);
            }
        }
        if (tail_direct(7, 8, 9) != 24) failures++, printf("FAIL tail jmp to a direct-call stub\n");
    }
    through = add3;
    before = resolved;
    if (through(1, 1, 1) != 3 || resolved != before) failures++, printf("FAIL call to a host function\n");
    if (misaligned) failures++, printf("FAIL the resolver ran on a misaligned stack %u times\n", misaligned);
    if (others && ((uintptr_t)record_registers & 0x5fe00000u) && ((uintptr_t)add3 & 0x5fe00000u) &&
        ((uintptr_t)main & 0x5fe00000u)) {
        failures++, printf("FAIL host targets went to the resolver %u times\n", others);
    }
    printf("%s\n", failures ? "branch thunks: FAILED" : "branch thunks: ok");
    return failures != 0;
}
#elif defined(__arm__)
/* 32-bit ARM (A32): the thunks clang's -mharden-sls=blr calls
 * (__llvm_slsblr_thunk_arm_r0..r12), the same checks. Built for an ARM
 * target outside CMake (a 32-bit x86 host builds the section above): with
 * NDK clang, e.g.
 *   clang --target=armv7a-linux-androideabi24 -marm -static -O2 -Isrc
 *         -mharden-sls=blr -fno-optimize-sibling-calls -fno-jump-tables
 *         tests/pc/branch_thunks_test.c src/pc/guest/branch_thunks.c
 * and run under qemu-arm (user mode) or on a device. */
#define GUEST_RECORD 0x80001000u
#define GUEST_ADD 0x80002004u
#define GUEST_PHYSICAL 0x00012340u
#define GUEST_KSEG1 0xa0002004u

/* What record_registers saw: R0-R12, SP, LR, then D0 and D7. */
uint32_t seen[19];
uint32_t sp_before, lr_expected, driver_target, tail_target;
static const uint64_t vfp_magic[2] = {0x0123456789abcdefull, 0xfedcba9876543210ull};
static unsigned resolved, others, misaligned;
void record_registers(void);
__asm__(".syntax unified\n.arm\n.text\n"
        ".globl record_registers\n"
        "record_registers:\n"
        "    str r12, [sp, #-8]!\n"
        "    ldr r12, =seen\n"
        "    stm r12, {r0-r11}\n"
        "    ldr r0, [sp], #8\n"
        "    str r0, [r12, #48]\n"
        "    str sp, [r12, #52]\n"
        "    str lr, [r12, #56]\n"
        "    vstr d0, [r12, #60]\n"
        "    vstr d7, [r12, #68]\n"
        "    bx lr\n"
        ".ltorg\n");

/* call_through_rN(target): R0-R12 set to 0x01010101 * (number + 1), D0 and
 * D7 to vfp_magic, RN to `target`, then a call through RN's thunk. */
#define DRIVER(n)                                                                   \
    void call_through_r##n(uint32_t target);                                        \
    __asm__(".syntax unified\n.arm\n.text\n"                                        \
            ".globl call_through_r" #n "\n"                                         \
            "call_through_r" #n ":\n"                                               \
            "    push {r4-r12, lr}\n"                                               \
            "    ldr r1, =driver_target\n"                                          \
            "    str r0, [r1]\n"                                                    \
            "    ldr r1, =vfp_magic\n"                                              \
            "    vldr d0, [r1]\n"                                                   \
            "    vldr d7, [r1, #8]\n"                                               \
            "    ldr r1, =lr_expected\n"                                            \
            "    adr r2, 1f\n"                                                      \
            "    str r2, [r1]\n"                                                    \
            "    ldr r1, =sp_before\n"                                              \
            "    str sp, [r1]\n"                                                    \
            "    ldr r0, =0x01010101\n    ldr r1, =0x02020202\n"                    \
            "    ldr r2, =0x03030303\n    ldr r3, =0x04040404\n"                    \
            "    ldr r4, =0x05050505\n    ldr r5, =0x06060606\n"                    \
            "    ldr r6, =0x07070707\n    ldr r7, =0x08080808\n"                    \
            "    ldr r8, =0x09090909\n    ldr r9, =0x0a0a0a0a\n"                    \
            "    ldr r10, =0x0b0b0b0b\n   ldr r11, =0x0c0c0c0c\n"                   \
            "    ldr r12, =0x0d0d0d0d\n"                                            \
            "    ldr r" #n ", =driver_target\n"                                     \
            "    ldr r" #n ", [r" #n "]\n"                                          \
            "    bl __llvm_slsblr_thunk_arm_r" #n "\n"                              \
            "1:  pop {r4-r12, lr}\n"                                                \
            "    bx lr\n"                                                           \
            ".ltorg\n");
DRIVER(0) DRIVER(1) DRIVER(2) DRIVER(3) DRIVER(4) DRIVER(5) DRIVER(6)
DRIVER(7) DRIVER(8) DRIVER(9) DRIVER(10) DRIVER(11) DRIVER(12)

/* A module function the C calls by name, as build_game32.py writes its host
 * stub (guest_branches.c): the address in R12, a branch to
 * Memories_GuestBranchDirect. call_direct calls it with the registers set as
 * the drivers set them. tail_rN(a, b, c): a branch (not a call) through a
 * thunk, as an indirect tail call would be; tail_direct: a branch to a stub. */
__asm__(".syntax unified\n.arm\n.text\n"
        "direct_record:\n"
        "    movw r12, #0x1000\n"
        "    movt r12, #0x8000\n"
        "    b Memories_GuestBranchDirect\n"
        ".globl call_direct\n"
        "call_direct:\n"
        "    push {r4-r12, lr}\n"
        "    ldr r1, =vfp_magic\n"
        "    vldr d0, [r1]\n"
        "    vldr d7, [r1, #8]\n"
        "    ldr r1, =lr_expected\n"
        "    adr r2, 1f\n"
        "    str r2, [r1]\n"
        "    ldr r1, =sp_before\n"
        "    str sp, [r1]\n"
        "    ldr r0, =0x01010101\n    ldr r1, =0x02020202\n"
        "    ldr r2, =0x03030303\n    ldr r3, =0x04040404\n"
        "    ldr r4, =0x05050505\n    ldr r5, =0x06060606\n"
        "    ldr r6, =0x07070707\n    ldr r7, =0x08080808\n"
        "    ldr r8, =0x09090909\n    ldr r9, =0x0a0a0a0a\n"
        "    ldr r10, =0x0b0b0b0b\n   ldr r11, =0x0c0c0c0c\n"
        "    ldr r12, =0x0d0d0d0d\n"
        "    bl direct_record\n"
        "1:  pop {r4-r12, lr}\n"
        "    bx lr\n"
        ".globl tail_r3\n"
        "tail_r3:\n"
        "    ldr r3, =tail_target\n"
        "    ldr r3, [r3]\n"
        "    b __llvm_slsblr_thunk_arm_r3\n"
        ".globl tail_r12\n"
        "tail_r12:\n"
        "    ldr r12, =tail_target\n"
        "    ldr r12, [r12]\n"
        "    b __llvm_slsblr_thunk_arm_r12\n"
        "direct_add:\n"
        "    movw r12, #0x2004\n"
        "    movt r12, #0x8000\n"
        "    b Memories_GuestBranchDirect\n"
        ".globl tail_direct\n"
        "tail_direct:\n"
        "    b direct_add\n"
        ".ltorg\n");
void call_direct(uint32_t unused);
int tail_r3(int a, int b, int c);
int tail_r12(int a, int b, int c);
int tail_direct(int a, int b, int c);

static int add3(int a, int b, int c) { return a + b + c; }

static void *resolve(unsigned address)
{
    uintptr_t sp;
    __asm__ volatile("mov %0, sp" : "=r"(sp));
    if (sp & 7) misaligned++; /* AAPCS: 8-byte aligned at a call */
    if (address == GUEST_RECORD || address == GUEST_ADD || address == GUEST_KSEG1 || address == GUEST_PHYSICAL) {
        resolved++;
    } else {
        others++;
    }
    if (address == GUEST_RECORD) return (void *)(uintptr_t)record_registers;
    if (address == GUEST_ADD || address == GUEST_KSEG1 || address == GUEST_PHYSICAL) return (void *)(uintptr_t)add3;
    return (void *)(uintptr_t)address;
}

/* `slot`: the register that held the target, -1 for none. R12 is the one
 * register a thunk may change (to the resolved target, on the slow path). */
static int check_registers(const char *name, void (*driver)(uint32_t), int slot, uint32_t target, int slow)
{
    int i, failures = 0;
    memset(seen, 0, sizeof(seen));
    driver(target);
    for (i = 0; i < 13; i++) {
        uint32_t expected = i == slot ? target : 0x01010101u * (uint32_t)(i + 1);
        if (i == 12 && slow) expected = (uint32_t)(uintptr_t)record_registers;
        if (seen[i] != expected) {
            printf("FAIL %s -> 0x%08x: r%d is 0x%08x, not 0x%08x\n", name, target, i, seen[i], expected);
            failures++;
        }
    }
    if (seen[13] != sp_before) failures++, printf("FAIL %s -> 0x%08x: the stack moved\n", name, target);
    if (seen[14] != lr_expected) failures++, printf("FAIL %s -> 0x%08x: lr is not the return address\n", name, target);
    if (memcmp((const char *)seen + 60, &vfp_magic[0], 8) || memcmp((const char *)seen + 68, &vfp_magic[1], 8)) {
        failures++, printf("FAIL %s -> 0x%08x: d0 or d7 changed\n", name, target);
    }
    return failures;
}

typedef int (*Add)(int, int, int);

static int __attribute__((noinline)) call_from_c(Add function, int x)
{
    return function(x, 1, 2) + 0; /* a call through a thunk: sibling calls are off */
}

int main(void)
{
    static void (*const drivers[13])(uint32_t) = {
        call_through_r0, call_through_r1, call_through_r2, call_through_r3, call_through_r4,
        call_through_r5, call_through_r6, call_through_r7, call_through_r8, call_through_r9,
        call_through_r10, call_through_r11, call_through_r12};
    volatile Add through;
    unsigned i, before;
    int failures = 0;
    char name[8];
    if (!((uintptr_t)record_registers & 0x5fe00000u) || !((uintptr_t)add3 & 0x5fe00000u)) {
        printf("FAIL the test's code at 0x%08x lies where the thunks' fast path takes it for guest memory; "
               "link it elsewhere\n", (unsigned)(uintptr_t)record_registers);
        return 1;
    }
    Memories_GuestBranchResolver = resolve;
    for (i = 0; i < 13; i++) {
        snprintf(name, sizeof(name), "r%u", i);
        before = resolved;
        failures += check_registers(name, drivers[i], (int)i, GUEST_RECORD, 1);
        if (resolved != before + 1) failures++, printf("FAIL %s: the guest target was not resolved\n", name);
        before = resolved;
        failures += check_registers(name, drivers[i], (int)i, (uint32_t)(uintptr_t)record_registers, 0);
        if (resolved != before) failures++, printf("FAIL %s: a host target was resolved as a guest one\n", name);
    }
    before = resolved;
    failures += check_registers("direct call", call_direct, -1, GUEST_RECORD, 1);
    if (resolved != before + 1) failures++, printf("FAIL direct call: the guest address was not resolved\n");
    through = (Add)(uintptr_t)GUEST_ADD;
    if (through(1, 2, 3) != 6) failures++, printf("FAIL call to a KSEG0 guest address\n");
    through = (Add)(uintptr_t)GUEST_KSEG1;
    if (through(10, 20, 30) != 60) failures++, printf("FAIL call to a KSEG1 guest address\n");
    through = (Add)(uintptr_t)GUEST_PHYSICAL;
    if (through(5, 5, 5) != 15) failures++, printf("FAIL call to a physical guest address\n");
    if (call_from_c((Add)(uintptr_t)GUEST_ADD, 4) != 7) failures++, printf("FAIL call to a guest address from C\n");
    {
        static const struct { const char *name; int (*tail)(int, int, int); } tails[] = {
            {"r3", tail_r3}, {"r12", tail_r12}};
        for (i = 0; i < sizeof(tails) / sizeof(tails[0]); i++) {
            tail_target = GUEST_ADD;
            before = resolved;
            if (tails[i].tail(1, 2, 3) != 6 || resolved != before + 1) {
                failures++, printf("FAIL tail branch through %s to a guest address\n", tails[i].name);
            }
            tail_target = (uint32_t)(uintptr_t)add3;
            before = resolved;
            if (tails[i].tail(4, 5, 6) != 15 || resolved != before) {
                failures++, printf("FAIL tail branch through %s to a host function\n", tails[i].name);
            }
        }
        if (tail_direct(7, 8, 9) != 24) failures++, printf("FAIL tail branch to a direct-call stub\n");
    }
    through = add3;
    before = resolved;
    if (through(1, 1, 1) != 3 || resolved != before) failures++, printf("FAIL call to a host function\n");
    if (misaligned) failures++, printf("FAIL the resolver ran on a misaligned stack %u times\n", misaligned);
    if (others) failures++, printf("FAIL host targets went to the resolver %u times\n", others);
    printf("%s\n", failures ? "branch thunks: FAILED" : "branch thunks: ok");
    return failures != 0;
}
#else
int main(void)
{
    puts("branch thunks: 32-bit x86 and ARM only");
    return 0;
}
#endif
