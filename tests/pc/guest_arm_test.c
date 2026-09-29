/* The 32-bit ARM (A32) pieces of src/pc/guest, where no x86 host can run
 * them (CTest builds the x86 ones): image.c's fault handler, the save-state
 * entry and stack switch (state_arm.S), and setjmp (setjmp_arm.S). Built
 * outside CMake, with NDK clang, and run under qemu-arm (user mode) or on a
 * device (notes/pc-build.md, "Android"):
 *   clang --target=armv7a-linux-androideabi24 -marm -static -O2 -Isrc
 *         -Wl,--image-base=0x40000000 tests/pc/guest_arm_test.c
 *         src/pc/guest/branch_thunks.c src/pc/guest/state_arm.S
 *         src/pc/guest/setjmp_arm.S
 * `guest_arm_test call` also calls into guest RAM without the thunks, which
 * needs a kernel that honours PROT_EXEC: qemu user mode runs the bytes
 * instead (4.2 does), a device or the emulator faults. */
#if defined(__arm__)
#include "pc/guest/image.c"
#include "pc/guest/state.h"
#include <sys/syscall.h>

/* What image.c needs from the rest of the port. */
#ifdef __ANDROID__
/* android.c's, for bionic below API 30 (android_compat.h). */
#include <fcntl.h>
#include <linux/ashmem.h>
#include <sys/ioctl.h>
int memories_memfd_create(const char *name, unsigned flags) { return (int)syscall(__NR_memfd_create, name, flags); }
int memories_ashmem_create(const char *name, unsigned size)
{
    char label[ASHMEM_NAME_LEN];
    int fd = open("/dev/ashmem", O_RDWR | O_CLOEXEC);
    if (fd < 0) return -1;
    snprintf(label, sizeof(label), "%s", name);
    if (ioctl(fd, ASHMEM_SET_NAME, label) || ioctl(fd, ASHMEM_SET_SIZE, (size_t)size)) {
        close(fd);
        return -1;
    }
    return fd;
}
#endif
static int answer(void) { return 42; }
const MemoriesGuestFunction Memories_FunctionMap[] = {{0x80001000u, (void (*)(void))answer, 0, 0}};
const unsigned Memories_FunctionMapCount = 1;
int Memories_ModuleIsResident(unsigned bank, unsigned identifier) { (void)bank, (void)identifier; return 1; }
int Memories_MipsInOverlay(uint32_t address) { (void)address; return 0; }
uint32_t Memories_MipsThunkTarget;
uint32_t Memories_MipsThunk(uint32_t a0, uint32_t a1, uint32_t a2, uint32_t a3, uint32_t a4, uint32_t a5,
                            uint32_t a6, uint32_t a7, uint32_t a8, uint32_t a9, uint32_t a10, uint32_t a11)
{
    (void)a0, (void)a1, (void)a2, (void)a3, (void)a4, (void)a5, (void)a6, (void)a7, (void)a8, (void)a9, (void)a10,
        (void)a11;
    return 0;
}
void Crash_ReportFatal(const char *kind, const char *detail) { printf("FAIL fatal: %s: %s\n", kind, detail); }
void Crash_HandleSignal(int number, siginfo_t *info, void *context)
{
    (void)context;
    printf("FAIL signal %d at 0x%08x\nguest ARM: FAILED\n", number, info ? (unsigned)(uintptr_t)info->si_addr : 0u);
    fflush(stdout);
    _exit(1);
}
void Profile_Flush(void) {}
int Log_Wanted(LogChannel channel) { (void)channel; return 0; }
void Log_Printf(LogChannel channel, const char *format, ...) { (void)channel, (void)format; }
void Log_Drain(void) {}
void Log_Enable(LogChannel channel, int on) { (void)channel, (void)on; }

/* ---- low and scratchpad accesses, one A32 instruction each ------------- */
/* t_<name>(base, r1, r2): the instruction with R0 as its base; out[0..3]
 * get R0-R3 after it. */
uint32_t out[4];
#define ACCESS(name, instruction)                                              \
    void t_##name(uint32_t base, uint32_t r1, uint32_t r2);                    \
    __asm__(".syntax unified\n.arm\n.text\n.globl t_" #name "\nt_" #name ":\n"  \
            "    push {r4, lr}\n"                                              \
            "    mov r3, #0\n"                                                 \
            "    " instruction "\n"                                            \
            "    ldr r4, =out\n"                                               \
            "    stm r4, {r0-r3}\n"                                            \
            "    pop {r4, pc}\n"                                               \
            ".ltorg\n");
ACCESS(ldr, "ldr r1, [r0, #4]")
ACCESS(ldr_into_base, "ldr r0, [r0, #4]")
ACCESS(ldr_post, "ldr r1, [r0], #4")
ACCESS(ldr_pre, "ldr r1, [r0, #4]!")
ACCESS(ldr_register, "ldr r1, [r0, r2]")
ACCESS(str, "str r1, [r0, #12]")
ACCESS(strb, "strb r1, [r0, #1]")
ACCESS(ldrsh, "ldrsh r1, [r0, #2]")
ACCESS(ldrd, "ldrd r2, r3, [r0]")
ACCESS(ldm, "ldm r0!, {r1, r2}")
ACCESS(vldr, "vldr d0, [r0, #8]\n    vmov r1, r2, d0")
/* A call into guest RAM that no thunk sees. */
int call_raw(uint32_t address);
__asm__(".syntax unified\n.arm\n.text\n.globl call_raw\ncall_raw:\n"
        "    push {r4, lr}\n"
        "    blx r0\n"
        "    pop {r4, pc}\n");

static int failures;
static void expect(const char *what, uint32_t got, uint32_t want)
{
    if (got != want) failures++, printf("FAIL %s: 0x%08x, not 0x%08x\n", what, got, want);
}

static void fault_tests(int call)
{
    volatile uint32_t *ram = (volatile uint32_t *)(uintptr_t)MEMORIES_GUEST_RAM;
    if (Memories_GuestMap()) {
        failures++, printf("FAIL Memories_GuestMap\n");
        return;
    }
    ram[1] = 0x11111111u, ram[2] = 0x600df00du, ram[3] = 0x33333333u, ram[4] = 0;
    ram[0] = 0xfffe0102u; /* halfword at 2: 0xfffe (-2) */
    t_ldr(4, 0, 0);
    expect("ldr [low+4]", out[1], 0x600df00du);
    expect("ldr keeps its base", out[0], 4);
    t_ldr_into_base(4, 0, 0);
    expect("ldr into its base", out[0], 0x600df00du);
    t_ldr_post(8, 0, 0);
    expect("ldr post-indexed", out[1], 0x600df00du);
    expect("ldr post-indexed base", out[0], 12);
    t_ldr_pre(4, 0, 0);
    expect("ldr pre-indexed", out[1], 0x600df00du);
    expect("ldr pre-indexed base", out[0], 8);
    t_ldr_register(4, 0, 4);
    expect("ldr register offset", out[1], 0x600df00du);
    t_str(4, 0xcafef00du, 0);
    expect("str", ram[4], 0xcafef00du);
    expect("str keeps its base", out[0], 4);
    t_strb(12, 0x5a, 0);
    expect("strb", ram[3], 0x33335a33u);
    t_ldrsh(0, 0, 0);
    expect("ldrsh", out[1], 0xfffffffeu);
    t_ldrd(8, 0, 0);
    expect("ldrd low", out[2], 0x600df00du);
    expect("ldrd high", out[3], 0x33335a33u);
    t_ldm(4, 0, 0);
    expect("ldm first", out[1], 0x11111111u);
    expect("ldm second", out[2], 0x600df00du);
    expect("ldm writeback", out[0], 12);
    t_vldr(0, 0, 0);
    expect("vldr low", out[1], 0x600df00du);
    expect("vldr high", out[2], 0x33335a33u);
    /* The retail scratchpad view, where it could not be mapped. */
    munmap((void *)(uintptr_t)MEMORIES_GUEST_SCRATCHPAD_RETAIL, 0x1000);
    scratchpad_retail_view = 0;
    ((volatile uint32_t *)(uintptr_t)MEMORIES_GUEST_SCRATCHPAD)[3] = 0x5c5c5c5cu;
    t_ldr(MEMORIES_GUEST_SCRATCHPAD_RETAIL + 8, 0, 0);
    expect("ldr through the retail scratchpad", out[1], 0x5c5c5c5cu);
    expect("its base", out[0], MEMORIES_GUEST_SCRATCHPAD_RETAIL + 8);
    if (call) {
        expect("call into guest RAM", (uint32_t)call_raw(0x80001000u), 42);
    }
}

/* ---- setjmp, the VSync entry, the stack switch ------------------------- */
int Psx_setjmp(int *buffer) __attribute__((returns_twice));
void Psx_longjmp(int *buffer, int value) __attribute__((noreturn));
int VSync(int mode);
void Memories_StateReturn(const MemoriesStateEntry *entry, int value) __attribute__((noreturn));
void Memories_ContextSwitch(uint32_t *from_sp, const uint32_t *to_sp);
MemoriesStateEntry Memories_StateEntry;

/* D8-D15: set to a pattern, read back. */
void set_d8_d15(const uint64_t *values);
void get_d8_d15(uint64_t *values);
__asm__(".syntax unified\n.arm\n.text\n"
        ".globl set_d8_d15\nset_d8_d15:\n    vldmia r0, {d8-d15}\n    bx lr\n"
        ".globl get_d8_d15\nget_d8_d15:\n    vstmia r0, {d8-d15}\n    bx lr\n");

static int jump_buffer[12];
static uint64_t pattern[8], other[8], seen_vfp[8];

static void __attribute__((noinline)) clobber_and_jump(void)
{
    set_d8_d15(other);
    Psx_longjmp(jump_buffer, 0);
}

static uint32_t vsync_sp;
/* What VSync's assembly entry continues in: the state machinery's C, which
 * here returns straight into the caller the entry recorded. */
int Memories_VSync(int mode)
{
    uint32_t sp;
    __asm__ volatile("mov %0, sp" : "=r"(sp));
    if (mode != 7) failures++, printf("FAIL VSync's argument: %d\n", mode);
    vsync_sp = sp;
    set_d8_d15(other);
    Memories_StateReturn(&Memories_StateEntry, 263);
}

static uint32_t main_context, other_context;
static volatile int steps;
static unsigned char other_stack[16384] __attribute__((aligned(16)));

static void other_side(void)
{
    uint32_t sp;
    __asm__ volatile("mov %0, sp" : "=r"(sp));
    if (sp & 7) failures++, printf("FAIL the switched-to function starts on a misaligned stack\n");
    steps = 1;
    set_d8_d15(other);
    Memories_ContextSwitch(&other_context, &main_context);
    steps = 3;
    Memories_ContextSwitch(&other_context, &main_context);
    for (;;) {}
}

static void asm_tests(void)
{
    volatile int rounds = 0;
    int value, i;
    uint32_t caller_sp;
    for (i = 0; i < 8; i++) pattern[i] = 0x0101010101010101ull * (uint64_t)(i + 1), other[i] = ~pattern[i];
    set_d8_d15(pattern);
    value = Psx_setjmp(jump_buffer);
    if (rounds++ == 0) clobber_and_jump();
    get_d8_d15(seen_vfp);
    expect("longjmp(buffer, 0) returns", (uint32_t)value, 1);
    expect("setjmp returned twice", (uint32_t)rounds, 2);
    if (memcmp(seen_vfp, pattern, sizeof(pattern))) failures++, printf("FAIL longjmp did not restore D8-D15\n");

    set_d8_d15(pattern);
    __asm__ volatile("mov %0, sp" : "=r"(caller_sp));
    value = VSync(7);
    get_d8_d15(seen_vfp);
    expect("VSync returns what StateReturn gives", (uint32_t)value, 263);
    expect("the entry's stack pointer is the caller's", Memories_StateEntry.sp, caller_sp);
    if (Memories_StateEntry.lr - (uint32_t)(uintptr_t)asm_tests > 4096u || vsync_sp >= caller_sp) {
        failures++, printf("FAIL the entry's return address (0x%08x) is not in the caller\n", Memories_StateEntry.lr);
    }
    if (memcmp(seen_vfp, pattern, sizeof(pattern))) failures++, printf("FAIL StateReturn did not restore D8-D15\n");

    {
        /* A first frame as state.c's switch_frame builds it. */
        uint32_t limit = (uint32_t)(uintptr_t)(other_stack + sizeof(other_stack));
        uint32_t start = (limit - 32u) & ~15u;
        uint32_t *frame = (uint32_t *)(uintptr_t)(start - 104u);
        memset(frame, 0, 104u);
        frame[25] = (uint32_t)(uintptr_t)other_side;
        other_context = (uint32_t)(uintptr_t)frame;
        set_d8_d15(pattern);
        Memories_ContextSwitch(&main_context, &other_context);
        get_d8_d15(seen_vfp);
        expect("the switch ran the other side", (uint32_t)steps, 1);
        if (memcmp(seen_vfp, pattern, sizeof(pattern))) failures++, printf("FAIL the switch lost D8-D15\n");
        steps = 2;
        Memories_ContextSwitch(&main_context, &other_context);
        expect("the switch resumed the other side", (uint32_t)steps, 3);
    }
}

int main(int argc, char **argv)
{
    setvbuf(stdout, NULL, _IONBF, 0); /* a crash keeps what was said */
    asm_tests();
    fault_tests(argc > 1 && !strcmp(argv[1], "call"));
    printf("%s\n", failures ? "guest ARM: FAILED" : "guest ARM: ok");
    return failures != 0;
}
#else
#include <stdio.h>
int main(void)
{
    puts("guest ARM: 32-bit ARM only");
    return 0;
}
#endif
