#define _GNU_SOURCE
#include "pc/compat/fs.h"
#include "image.h"
#include "mips.h"
#include "pc/debug/crash.h"
#include "pc/debug/log.h"
#include "pc/debug/profile.h"
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#ifdef _WIN32
#include "pc/platform/win32.h"
#include <windows.h>
#else
#include <signal.h>
#include <sys/mman.h>
#include <ucontext.h>
#endif

_Static_assert(sizeof(void *) == 4, "the guest image model requires an ILP32 build");

/* The first 64 KiB. On the console that is kernel RAM, and retail code reaches
 * it through null pointers: CardList_CreateSlotTextBox clears a flag in
 * box->field_28 one call before that object exists, a read-modify-write of
 * address 8 that nothing notices. Hosts do not let a process map page zero,
 * so such an access faults; the handler then points the instruction's base
 * register at `low_memory` (the same pages guest RAM has at 0x80000000),
 * single-steps it, and puts the register back unless the instruction itself
 * replaced it. Each site is reported once. */
#ifndef _WIN32
static unsigned char *low_memory;
#else
/* Which 64 KiB pieces of the physical mirror Memories_GuestMap could map;
 * Windows holds the others (see there). */
static unsigned char low_piece_mapped[MEMORIES_GUEST_RAM_SIZE / 0x10000u];
#endif
#if defined(__i386__)
static struct {
    int active, reg; /* reg: the ModRM register number, 0 (EAX) to 7 (EDI) */
    uint32_t original, patched;
} low_fixup;
#endif
#ifndef _WIN32
/* Whether the retail scratchpad view (0x1F800000) is mapped; where it is
 * not, an access there takes the same register rebase as the first 64 KiB,
 * onto the port's view (image.h). Windows always maps it. */
static int scratchpad_retail_view;
#endif

static void report_low_access(uint32_t eip, uint32_t address)
{
    static uint32_t seen[32];
    static unsigned count;
    char text[128];
    unsigned i;
    int length;
    for (i = 0; i < count; i++) {
        if (seen[i] == eip) {
            return;
        }
    }
    if (count < sizeof(seen) / sizeof(seen[0])) {
        seen[count++] = eip;
    }
    if (address >= MEMORIES_GUEST_SCRATCHPAD_RETAIL)
        length = snprintf(text, sizeof(text), "memories-pc: scratchpad access through 0x%08x at eip 0x%08x goes to 0x%08x\n",
                          (unsigned)address, (unsigned)eip, (unsigned)(address | 0x80000000u));
    else
        length = snprintf(text, sizeof(text), "memories-pc: null-pointer access to 0x%04x at eip 0x%08x goes to kernel RAM, as on the console\n",
                          (unsigned)address, (unsigned)eip);
    (void)!write(2, text, (size_t)length);
}

#if defined(__i386__)
/* Which register (ModRM number) does the faulting instruction address memory
 * through? -1 for none. */
#define REGISTER_ESI 6
#define REGISTER_EDI 7
static int low_access_register(const unsigned char *code, uint32_t esi)
{
    unsigned modrm, base;
    while (*code == 0x66 || *code == 0xf2 || *code == 0xf3 || *code == 0x2e || *code == 0x36 || *code == 0x3e ||
           *code == 0x26) {
        code++;
    }
    if ((*code >= 0xa4 && *code <= 0xa7) || *code == 0xaa || *code == 0xab) { /* string moves and stores */
        if (*code != 0xaa && *code != 0xab && esi < 0x10000u) {
            return REGISTER_ESI;
        }
        return REGISTER_EDI;
    }
    code += *code == 0x0f ? 2 : 1;
    modrm = *code++;
    if (modrm >> 6 == 3 || ((modrm >> 6) == 0 && (modrm & 7) == 5)) {
        return -1; /* register operand, or an absolute address */
    }
    base = modrm & 7;
    if (base == 4) {
        unsigned sib = *code;
        base = sib & 7;
        if (base == 5 && modrm >> 6 == 0) {
            return -1;
        }
    }
    return (int)base;
}
#endif

/* Tables in the retail data image hold MIPS function addresses, and native
 * code calls through them. The build generates Memories_FunctionMap (guest
 * address -> native function, sorted); a call to such an address resumes in
 * the native function. The caller's return address and cdecl arguments are
 * already on the stack, so the redirect is transparent. Two ways lead here:
 * the indirect-branch thunks every unit is compiled to use (branch_thunks.c,
 * through guest_branch_target below), and, as the second net, the fault of
 * executing guest RAM, which is mapped without execute permission
 * (on_guest_exception, on_fault). Anything else is fatal.
 * Returns where to resume, or NULL. */
static int in_guest_ram(uint32_t address)
{
    return (address >= 0x10000u && address < MEMORIES_GUEST_RAM_SIZE) ||
           address - MEMORIES_GUEST_RAM < MEMORIES_GUEST_RAM_SIZE || address - 0xa0000000u < MEMORIES_GUEST_RAM_SIZE;
}

static void *guest_call_target(uint32_t address)
{
    size_t low = 0, high = Memories_FunctionMapCount;
    /* Through KSEG1 or the physical address, the console runs the same
     * code; the map and the overlay slots are keyed by KSEG0. */
    if (in_guest_ram(address)) {
        address = MEMORIES_GUEST_RAM | (address & (MEMORIES_GUEST_RAM_SIZE - 1u));
    }
    while (low < high) {
        size_t middle = (low + high) / 2;
        if (Memories_FunctionMap[middle].guest < address) {
            low = middle + 1;
        } else {
            high = middle;
        }
    }
    for (; low < Memories_FunctionMapCount && Memories_FunctionMap[low].guest == address; low++) {
        const MemoriesGuestFunction *entry = &Memories_FunctionMap[low];
        if (Memories_ModuleIsResident(entry->bank, entry->identifier)) {
            return (void *)(uintptr_t)entry->host;
        }
    }
    if (Memories_MipsInOverlay(address)) {
        /* A callback into a loaded overlay: run it interpreted. */
        Memories_MipsThunkTarget = address;
        return (void *)(uintptr_t)Memories_MipsThunk;
    }
    return NULL;
}

static void report_guest_fault(uint32_t address, uint32_t eip)
{
    char text[128];
    int length;
    if (eip == address) {
        length = snprintf(text, sizeof(text), "memories-pc: call into guest code at 0x%08x, which has no native function\n",
                          (unsigned)address);
    } else {
        length = snprintf(text, sizeof(text), "memories-pc: bad memory access at 0x%08x (eip 0x%08x)\n",
                          (unsigned)address, (unsigned)eip);
    }
    (void)!write(2, text, (size_t)length);
}

/* Memories_GuestBranchResolver: where an indirect call or jump the thunks
 * caught goes. Outside guest RAM and its mirrors (and below 0x10000, so that
 * a call through a null pointer still faults as one; on Windows also in the
 * pieces of the physical mirror that Windows holds, which are not guest
 * RAM), the address itself. A guest address with no native function is
 * never jumped to: with DEP off its MIPS bytes would run as x86 code. */
static void *guest_branch_target(unsigned address)
{
    char text[64];
    void *target;
    if (!in_guest_ram(address)) {
        return (void *)(uintptr_t)address;
    }
#ifdef _WIN32
    if (address < MEMORIES_GUEST_RAM_SIZE && !low_piece_mapped[address >> 16]) {
        return (void *)(uintptr_t)address;
    }
#endif
    if ((target = guest_call_target(address)) != NULL) {
        return target;
    }
    report_guest_fault(address, address);
    snprintf(text, sizeof(text), "0x%08x has no native function", address);
    Crash_ReportFatal("call into guest code", text);
    Profile_Flush();
    _exit(70);
}

/* The thunks let a host target through after one test of its address
 * bits (branch_thunks.c). The executable has a fixed base where that test
 * passes; were its code somewhere the test fails, calls would still work,
 * through the resolver, only slower: say so. */
static void check_code_address(void)
{
    if (!((uintptr_t)check_code_address & 0x5fe00000u)) {
        fprintf(stderr, "memories-pc: the executable's code (0x%08x) is where the branch thunks take the slow path\n",
                (unsigned)(uintptr_t)check_code_address);
    }
}

/* Guest RAM mapped executable (MEMORIES_TEST_EXEC_GUEST=1), as it is where
 * DEP is off: then only the thunks keep a guest call from running MIPS bytes,
 * which makes "the game works without DEP" testable on any machine. */
static int guest_ram_executable(void)
{
    const char *value = getenv("MEMORIES_TEST_EXEC_GUEST");
    if (!value || !*value || !strcmp(value, "0")) return 0;
    fprintf(stderr, "memories-pc: guest RAM is mapped executable (MEMORIES_TEST_EXEC_GUEST)\n");
    return 1;
}

#ifdef _WIN32
static DWORD *context_register(CONTEXT *context, int number)
{
    switch (number) {
    case 0: return &context->Eax;
    case 1: return &context->Ecx;
    case 2: return &context->Edx;
    case 3: return &context->Ebx;
    case 4: return &context->Esp;
    case 5: return &context->Ebp;
    case 6: return &context->Esi;
    default: return &context->Edi;
    }
}

/* The common low access, a plain 32-bit MOV to or from [base + disp], is
 * done here through guest RAM instead of the rebase-and-single-step path:
 * 32-bit processes on 64-bit Windows can mishandle the trap when the
 * instruction's destination is its own base register. Returns 1 if done. */
static int emulate_low_mov(CONTEXT *context, uint32_t address)
{
    const unsigned char *code = (const unsigned char *)(uintptr_t)context->Eip;
    unsigned modrm, mod, reg, rm;
    uint32_t *guest;
    if ((code[0] != 0x8b && code[0] != 0x89) || address > MEMORIES_GUEST_RAM_SIZE - 4) {
        return 0;
    }
    modrm = code[1];
    mod = modrm >> 6;
    reg = (modrm >> 3) & 7;
    rm = modrm & 7;
    if (mod == 3 || rm == 4 || (mod == 0 && rm == 5)) {
        return 0; /* register operand, SIB byte or absolute address */
    }
    guest = (uint32_t *)(uintptr_t)(MEMORIES_GUEST_RAM + address);
    if (code[0] == 0x8b) {
        *context_register(context, (int)reg) = *guest;
    } else {
        *guest = *context_register(context, (int)reg);
    }
    context->Eip += 2u + (mod == 1 ? 1u : mod == 2 ? 4u : 0u);
    return 1;
}

/* First in line for every exception in the process: take the guest's own
 * faults, leave everything else to the next handler (win32.c reports what
 * the executable raised). */
static LONG CALLBACK on_guest_exception(EXCEPTION_POINTERS *pointers)
{
    const EXCEPTION_RECORD *record = pointers->ExceptionRecord;
    CONTEXT *context = pointers->ContextRecord;
    uint32_t address;
    void *target;
    Win32_UndoInterruptedFault(context); /* then handled as the faulting instruction's own */
    /* A 32-bit process on 64-bit Windows may see the trap as WoW64's own
     * STATUS_WX86_SINGLE_STEP. */
    if (record->ExceptionCode == EXCEPTION_SINGLE_STEP || record->ExceptionCode == 0x4000001eu) {
        DWORD *reg;
        if (!low_fixup.active) {
            return EXCEPTION_CONTINUE_SEARCH;
        }
        low_fixup.active = 0;
        reg = context_register(context, low_fixup.reg);
        if (*reg == low_fixup.patched) {
            *reg = low_fixup.original;
        }
        context->EFlags &= ~0x100; /* trap flag */
        return EXCEPTION_CONTINUE_EXECUTION;
    }
    if (record->ExceptionCode != EXCEPTION_ACCESS_VIOLATION || record->NumberParameters < 2) {
        return EXCEPTION_CONTINUE_SEARCH;
    }
    address = (uint32_t)record->ExceptionInformation[1];
    /* The first 64 KiB and the parts of the physical mirror Windows holds
     * (see Memories_GuestMap) are reached the same way: through guest RAM
     * at 0x80000000, which the same offsets address. */
    if (address < MEMORIES_GUEST_RAM_SIZE && context->Eip != address && !low_fixup.active) {
        int reg = low_access_register((const unsigned char *)(uintptr_t)context->Eip, context->Esi);
        if (reg >= 0 && *context_register(context, reg) < MEMORIES_GUEST_RAM_SIZE) {
            report_low_access(context->Eip, address);
            if (emulate_low_mov(context, address)) {
                return EXCEPTION_CONTINUE_EXECUTION;
            }
            low_fixup.active = 1;
            low_fixup.reg = reg;
            low_fixup.original = *context_register(context, reg);
            low_fixup.patched = low_fixup.original + MEMORIES_GUEST_RAM;
            *context_register(context, reg) = low_fixup.patched;
            context->EFlags |= 0x100;
            return EXCEPTION_CONTINUE_EXECUTION;
        }
    }
    if (context->Eip == address && (target = guest_call_target(address)) != NULL) {
        context->Eip = (DWORD)(uintptr_t)target;
        return EXCEPTION_CONTINUE_EXECUTION;
    }
    if (context->Eip == address || address < 0x10000u ||
        (address >= MEMORIES_GUEST_RAM && address < MEMORIES_GUEST_RAM + 0x00800000u)) {
        report_guest_fault(address, context->Eip);
    }
    return EXCEPTION_CONTINUE_SEARCH;
}

/* The Linux layout as far as Windows allows: one pagefile-backed section
 * holds guest RAM and is viewed at 0x80000000 and 0xA0000000. The physical
 * mirror (0x10000..0x200000) competes with what Windows puts there before
 * the program starts (process parameters, locale tables, the WoW64 stack),
 * so it is mapped in 64 KiB pieces where the address space is free; an
 * access to a piece Windows holds faults and goes through guest RAM
 * instead (on_guest_exception). Such accesses into pages Windows has
 * mapped readable would not fault; the sites that fault are reported. */
static DWORD view_access = FILE_MAP_ALL_ACCESS;

static int view_at(HANDLE section, uint32_t address, size_t length, DWORD offset)
{
    void *wanted = (void *)(uintptr_t)address;
    if (MapViewOfFileEx(section, view_access, 0, offset, length, wanted) != wanted) {
        fprintf(stderr, "cannot map guest memory at 0x%08x (error %lu)\n", (unsigned)address,
                GetLastError());
        return -1;
    }
    return 0;
}

/* Calls into guest code go through the branch thunks: the game works
 * without DEP. DEP is a second safety net, turned on here where Windows
 * lets a program: with it, a call that escaped the thunks faults into
 * on_guest_exception instead of running MIPS bytes. The game is a 32-bit
 * process, which follows the system's DEP policy (only 64-bit processes
 * always have DEP): under OptIn, the default, the executable's --nxcompat
 * turns it on; under OptOut with the program excepted, SetProcessDEPPolicy
 * does; under AlwaysOff nothing can. */
static void ask_for_dep(void)
{
    DWORD flags = 0;
    BOOL permanent = FALSE;
    if (GetProcessDEPPolicy(GetCurrentProcess(), &flags, &permanent) && (flags & PROCESS_DEP_ENABLE)) return;
    SetProcessDEPPolicy(PROCESS_DEP_ENABLE);
}

int Memories_GuestMap(void)
{
    HANDLE section;
    int result, executable = guest_ram_executable();
    ask_for_dep();
    Memories_GuestBranchResolver = guest_branch_target;
    check_code_address();
    if (executable) view_access = FILE_MAP_ALL_ACCESS | FILE_MAP_EXECUTE;
    /* Guest RAM, then 64 KiB (the view granularity) for the scratchpad. */
    section = CreateFileMappingA(INVALID_HANDLE_VALUE, NULL, executable ? PAGE_EXECUTE_READWRITE : PAGE_READWRITE, 0,
                                 MEMORIES_GUEST_RAM_SIZE + 0x10000u, NULL);
    AddVectoredExceptionHandler(1, on_guest_exception);
    if (section == NULL) {
        fprintf(stderr, "guest RAM: CreateFileMapping failed (error %lu)\n", GetLastError());
        return -1;
    }
    /* The mirror first: tested on Windows 11, a view below 0x200000 fails
     * with ERROR_INVALID_ADDRESS once the high views exist. */
    {
        uint32_t piece, held = 0;
        for (piece = 0x10000u; piece < MEMORIES_GUEST_RAM_SIZE; piece += 0x10000u) {
            if (MapViewOfFileEx(section, view_access, 0, piece, 0x10000u, (void *)(uintptr_t)piece) == NULL) {
                held += 0x10000u;
            } else {
                low_piece_mapped[piece >> 16] = 1;
            }
        }
        if (held) {
            fprintf(stderr, "memories-pc: %u KiB of the physical RAM mirror are taken by Windows; accesses there fault into guest RAM\n",
                    (unsigned)(held / 1024));
        }
    }
    /* The scratchpad's two views (image.h); Windows leaves 0x1F800000 free. */
    result = view_at(section, MEMORIES_GUEST_RAM, MEMORIES_GUEST_RAM_SIZE, 0) ||
             view_at(section, 0xa0000000u, MEMORIES_GUEST_RAM_SIZE, 0) ||
             view_at(section, MEMORIES_GUEST_SCRATCHPAD, 0x10000u, MEMORIES_GUEST_RAM_SIZE) ||
             view_at(section, MEMORIES_GUEST_SCRATCHPAD_RETAIL, 0x10000u, MEMORIES_GUEST_RAM_SIZE);
    /* The views keep the section alive. */
    CloseHandle(section);
    return result ? -1 : 0;
}
#else
static int view_protection = PROT_READ | PROT_WRITE;

static int map_at(uint32_t address, size_t length, int fd, off_t offset)
{
    void *wanted = (void *)(uintptr_t)address;
    int flags = MAP_FIXED_NOREPLACE | (fd < 0 ? MAP_PRIVATE | MAP_ANONYMOUS : MAP_SHARED);
    if (mmap(wanted, length, fd < 0 ? PROT_READ | PROT_WRITE : view_protection, flags, fd, offset) != wanted) {
        fprintf(stderr, "cannot map guest memory at 0x%08x\n", (unsigned)address);
        return -1;
    }
    return 0;
}

#if defined(__i386__)
/* ModRM/SIB register numbers to gregs[]. */
static const int register_slot[8] = {REG_EAX, REG_ECX, REG_EDX, REG_EBX, REG_ESP, REG_EBP, REG_ESI, REG_EDI};

static void on_step(int number, siginfo_t *info, void *context)
{
    ucontext_t *user = context;
    greg_t *reg;
    (void)number; (void)info;
    if (low_fixup.active) {
        low_fixup.active = 0;
        reg = &user->uc_mcontext.gregs[register_slot[low_fixup.reg]];
        if ((uint32_t)*reg == low_fixup.patched) {
            *reg = (greg_t)low_fixup.original;
        }
    } else {
        struct sigaction action;
        memset(&action, 0, sizeof(action));
        action.sa_handler = SIG_DFL;
        sigaction(SIGTRAP, &action, NULL);
        raise(SIGTRAP);
        return;
    }
    user->uc_mcontext.gregs[REG_EFL] &= ~0x100; /* trap flag */
}

static void on_fault(int number, siginfo_t *info, void *context)
{
    ucontext_t *user = context;
    uint32_t address = (uint32_t)(uintptr_t)info->si_addr;
    uint32_t eip = (uint32_t)user->uc_mcontext.gregs[REG_EIP];
    void *target;
    /* The first 64 KiB go through the low_memory view of guest RAM; the
     * retail scratchpad view, where it could not be mapped, through the
     * port's (image.h). Both are the same register rebase. */
    if (eip != address && !low_fixup.active &&
        ((address < 0x10000u && low_memory) ||
         (!scratchpad_retail_view && address - MEMORIES_GUEST_SCRATCHPAD_RETAIL < 0x1000u))) {
        int low = address < 0x10000u;
        int reg = low_access_register((const unsigned char *)(uintptr_t)eip, (uint32_t)user->uc_mcontext.gregs[REG_ESI]);
        uint32_t base = reg >= 0 ? (uint32_t)user->uc_mcontext.gregs[register_slot[reg]] : 0;
        if (reg >= 0 && (low ? base < 0x10000u : base - MEMORIES_GUEST_SCRATCHPAD_RETAIL < 0x1000u)) {
            report_low_access(eip, address);
            low_fixup.active = 1;
            low_fixup.reg = reg;
            low_fixup.original = base;
            low_fixup.patched = base + (low ? (uint32_t)(uintptr_t)low_memory : 0x80000000u);
            user->uc_mcontext.gregs[register_slot[reg]] = (greg_t)low_fixup.patched;
            user->uc_mcontext.gregs[REG_EFL] |= 0x100;
            return;
        }
    }
    if (eip == address && (target = guest_call_target(address)) != NULL) {
        user->uc_mcontext.gregs[REG_EIP] = (greg_t)(uintptr_t)target;
        return;
    }
    report_guest_fault(address, eip);
    Crash_HandleSignal(number, info, context);
}
#elif defined(__arm__)
/* 32-bit ARM (A32), for the two faults the i386 handler above takes.
 *
 * A low or retail-scratchpad access: ARM has no single-step trap, so the
 * instruction runs once out of line instead. The handler moves its base
 * register (Rn, bits 16-19 in every A32 load/store class) up by 0x80000000,
 * onto the same RAM in KSEG0 (the first 64 KiB of guest RAM, or the port's
 * scratchpad view), and resumes in a stub: the instruction itself, then
 * `sub Rn, Rn, #0x80000000` (which also undoes the move after a writeback),
 * then a jump back behind the original. When the instruction loads Rn, the
 * loaded value stands and there is no `sub`. Not handled, and fatal as
 * before: Thumb code (the game and the port are built as A32; Thumb is the
 * system libraries'), a base that is the PC, a store of the base register
 * itself, and a register offset that is the base register again. The stub
 * is one page for the process: the game takes these faults on its one
 * thread.
 *
 * A call into guest code: the target of a guest address, as on i386. LR
 * holds the caller's return address already, and R0-R3 the arguments. A
 * target with bit 0 set is Thumb code, which the CPSR's T bit selects. */
#define CPSR_THUMB 0x20u
#define A32_NOP 0xe320f000u
#define A32_LDR_PC_PC_MINUS_4 0xe51ff004u
#define A32_SUB_2_31 0xe2400102u /* sub Rd, Rn, #0x80000000 (0x02 rotated right by 2) */

static uint32_t *fixup_stub;

static void map_fixup_stub(void)
{
    void *page = mmap(NULL, 4096, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    fixup_stub = page == MAP_FAILED ? NULL : page;
}

/* The base register of an A32 load or store, or -1 for anything else. Sets
 * *loads_base when the access loads that register, *stores_base when it
 * stores it; -1 too for a register offset through the base register. */
static int a32_access(uint32_t code, int *loads_base, int *stores_base)
{
    unsigned rn = (code >> 16) & 15, rt = (code >> 12) & 15, rm = code & 15, load = (code >> 20) & 1;
    if (code >> 28 == 0xf) return -1; /* the unconditional space: no loads or stores that fault here */
    switch ((code >> 25) & 7) {
    case 3: /* LDR/STR/LDRB/STRB, register offset */
        if (code & 0x10) return -1; /* media instructions */
        if (rm == rn) return -1;
        /* fall through */
    case 2: /* LDR/STR/LDRB/STRB, immediate offset */
        *loads_base = load && rt == rn;
        *stores_base = !load && rt == rn;
        return (int)rn;
    case 0: /* LDRH/STRH/LDRSB/LDRSH/LDRD/STRD: bits 7 and 4 set, bits 6-5 not 00 */
        if ((code & 0x90) != 0x90 || !(code & 0x60)) return -1;
        if (!(code & (1u << 22)) && rm == rn) return -1;
        if (!load && (code & 0x40)) { /* LDRD (bits 6-5 10), STRD (11): Rt and Rt+1 */
            int pair = rt == rn || rt + 1 == rn;
            *loads_base = !(code & 0x20) && pair;
            *stores_base = (code & 0x20) && pair;
        } else {
            *loads_base = load && rt == rn;
            *stores_base = !load && rt == rn;
        }
        return (int)rn;
    case 4: /* LDM/STM */
        *loads_base = load && ((code >> rn) & 1);
        *stores_base = !load && ((code >> rn) & 1);
        return (int)rn;
    case 6: /* LDC/STC: VLDR/VSTR/VLDM/VSTM, into VFP registers */
        if ((code & 0x0fe00000u) == 0x0c400000u) return -1; /* MCRR/MRRC: no memory */
        return (int)rn;
    default:
        return -1;
    }
}

/* Returns 1 when the access will run from the stub. */
static int run_rebased(ucontext_t *user, uint32_t address)
{
    unsigned long *registers = &user->uc_mcontext.arm_r0; /* R0-R15 in order */
    uint32_t pc = (uint32_t)user->uc_mcontext.arm_pc, code, base;
    int rn, loads_base = 0, stores_base = 0, low = address < 0x10000u;
    if (!fixup_stub || (user->uc_mcontext.arm_cpsr & CPSR_THUMB)) return 0;
    code = *(const uint32_t *)(uintptr_t)pc;
    rn = a32_access(code, &loads_base, &stores_base);
    if (rn < 0 || rn == 15 || stores_base) return 0;
    base = (uint32_t)registers[rn];
    if (low ? base >= 0x10000u : base - MEMORIES_GUEST_SCRATCHPAD_RETAIL >= 0x1000u) return 0;
    report_low_access(pc, address);
    if (mprotect(fixup_stub, 4096, PROT_READ | PROT_WRITE)) return 0;
    fixup_stub[0] = code;
    fixup_stub[1] = loads_base ? A32_NOP : A32_SUB_2_31 | (uint32_t)rn << 16 | (uint32_t)rn << 12;
    fixup_stub[2] = A32_LDR_PC_PC_MINUS_4;
    fixup_stub[3] = pc + 4u;
    if (mprotect(fixup_stub, 4096, PROT_READ | PROT_EXEC)) return 0;
    __builtin___clear_cache((char *)fixup_stub, (char *)(fixup_stub + 4));
    registers[rn] = base + 0x80000000u;
    user->uc_mcontext.arm_pc = (unsigned long)(uintptr_t)fixup_stub;
    return 1;
}

static void on_fault(int number, siginfo_t *info, void *context)
{
    ucontext_t *user = context;
    uint32_t address = (uint32_t)(uintptr_t)info->si_addr;
    uint32_t pc = (uint32_t)user->uc_mcontext.arm_pc;
    void *target;
    if (pc != address && ((address < 0x10000u) ||
                          (!scratchpad_retail_view && address - MEMORIES_GUEST_SCRATCHPAD_RETAIL < 0x1000u))) {
        if (run_rebased(user, address)) return;
    }
    if (pc == address && !(user->uc_mcontext.arm_cpsr & CPSR_THUMB) && (target = guest_call_target(address)) != NULL) {
        uint32_t resume = (uint32_t)(uintptr_t)target;
        user->uc_mcontext.arm_pc = resume & ~1u;
        user->uc_mcontext.arm_cpsr = (user->uc_mcontext.arm_cpsr & ~CPSR_THUMB) | (resume & 1u ? CPSR_THUMB : 0u);
        return;
    }
    report_guest_fault(address, pc);
    Crash_HandleSignal(number, info, context);
}
#else
#error "image.c: no fault handler for this architecture"
#endif

int Memories_GuestMap(void)
{
    struct sigaction action;
    int fd, result;
    if (guest_ram_executable()) view_protection |= PROT_EXEC;
    Memories_GuestBranchResolver = guest_branch_target;
    check_code_address();
    memset(&action, 0, sizeof(action));
    action.sa_sigaction = on_fault;
    action.sa_flags = SA_SIGINFO | SA_ONSTACK;
    sigaction(SIGSEGV, &action, NULL);
#if defined(__i386__)
    action.sa_sigaction = on_step;
    sigaction(SIGTRAP, &action, NULL);
#else
    map_fixup_stub();
#endif
    fd = memfd_create("memories-ram", 0);
    /* Guest RAM, then a page for the scratchpad. */
    if (fd >= 0 && ftruncate(fd, MEMORIES_GUEST_RAM_SIZE + 0x1000) != 0) {
        close(fd);
        fd = -1;
    }
#ifdef __ANDROID__
    /* Before memfd (Linux 3.17): the ashmem device (android.c). */
    if (fd < 0) fd = memories_ashmem_create("memories-ram", MEMORIES_GUEST_RAM_SIZE + 0x1000);
#endif
    if (fd < 0) {
        perror("guest RAM");
        return -1;
    }
    result = map_at(MEMORIES_GUEST_RAM, MEMORIES_GUEST_RAM_SIZE, fd, 0) ||
             map_at(0xa0000000u, MEMORIES_GUEST_RAM_SIZE, fd, 0) ||
             map_at(0x00010000u, MEMORIES_GUEST_RAM_SIZE - 0x10000u, fd, 0x10000) ||
             map_at(MEMORIES_GUEST_SCRATCHPAD, 0x1000, fd, MEMORIES_GUEST_RAM_SIZE);
    /* The retail view where the host allows it (image.h). */
    if (!result) {
        void *wanted = (void *)(uintptr_t)MEMORIES_GUEST_SCRATCHPAD_RETAIL;
        void *got = mmap(wanted, 0x1000, view_protection, MAP_FIXED_NOREPLACE | MAP_SHARED, fd, MEMORIES_GUEST_RAM_SIZE);
        scratchpad_retail_view = got == wanted;
        if (got != MAP_FAILED && got != wanted) munmap(got, 0x1000); /* taken as a hint */
        if (!scratchpad_retail_view) {
            fprintf(stderr, "memories-pc: 0x%08x is taken here; the scratchpad is reached at 0x%08x\n",
                    MEMORIES_GUEST_SCRATCHPAD_RETAIL, MEMORIES_GUEST_SCRATCHPAD);
        }
    }
    low_memory = mmap(NULL, 0x10000, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
    if (low_memory == MAP_FAILED) {
        low_memory = NULL;
    }
    close(fd);
    return result ? -1 : 0;
}
#endif /* _WIN32 */

static uint32_t le32(const unsigned char *bytes)
{
    return bytes[0] | ((uint32_t)bytes[1] << 8) | ((uint32_t)bytes[2] << 16) |
           ((uint32_t)bytes[3] << 24);
}

int Memories_GuestLoadExeData(const unsigned char *data, size_t length, const char *name)
{
    uint32_t address, size;
    if (length < 0x800 || memcmp(data, "PS-X EXE", 8) != 0) {
        fprintf(stderr, "%s: not a readable PS-X executable\n", name);
        return -1;
    }
    address = le32(data + 0x18);
    size = le32(data + 0x1c);
    if (address < MEMORIES_GUEST_RAM + 0x10000u || size > MEMORIES_GUEST_RAM_SIZE ||
        address - MEMORIES_GUEST_RAM > MEMORIES_GUEST_RAM_SIZE - size || size > length - 0x800) {
        fprintf(stderr, "%s: image does not fit guest RAM or is truncated\n", name);
        return -1;
    }
    memcpy((void *)(uintptr_t)address, data + 0x800, size);
    return 0;
}

int Memories_GuestLoadExe(const char *path)
{
    unsigned char *data;
    long length;
    int result;
    FILE *file = fopen(path, "rb");
    if (!file || fseek(file, 0, SEEK_END) || (length = ftell(file)) < 0 || fseek(file, 0, SEEK_SET) ||
        !(data = malloc(length ? (size_t)length : 1))) {
        fprintf(stderr, "%s: not a readable PS-X executable\n", path);
        if (file) fclose(file);
        return -1;
    }
    if (fread(data, 1, (size_t)length, file) != (size_t)length) length = 0;
    fclose(file);
    result = Memories_GuestLoadExeData(data, (size_t)length, path);
    free(data);
    return result;
}

typedef struct StubCount { const char *name; unsigned count; } StubCount;
static StubCount stub_calls[512];
static unsigned stub_call_count;

static int compare_stub_counts(const void *left, const void *right)
{
    const StubCount *a = left, *b = right;
    return a->count < b->count ? 1 : a->count > b->count ? -1 : strcmp(a->name, b->name);
}

static void print_stub_summary(void)
{
    unsigned at;
    qsort(stub_calls, stub_call_count, sizeof(stub_calls[0]), compare_stub_counts);
    for (at = 0; at < stub_call_count; at++) {
        LOG(LOG_STUB, "%s: %u calls", stub_calls[at].name, stub_calls[at].count);
    }
    Log_Drain();
}

void Memories_Unimplemented(const char *name)
{
    static int registered;
    const char *break_name = getenv("MEMORIES_STUB_BREAK");
    unsigned i;
#ifdef _WIN32
    if (break_name && !strcmp(break_name, name)) DebugBreak();
#else
    if (break_name && !strcmp(break_name, name)) raise(SIGTRAP);
#endif
    /* Survey aid only: results after the first line are not meaningful,
     * because the missing routine returned garbage. */
    if (getenv("MEMORIES_STUB_TRACE")) {
        for (i = 0; i < stub_call_count && strcmp(stub_calls[i].name, name); i++) {}
        if (i == stub_call_count && stub_call_count < sizeof(stub_calls) / sizeof(stub_calls[0])) {
            stub_calls[stub_call_count].name = name;
            stub_calls[stub_call_count++].count = 0;
        }
        if (i < stub_call_count) stub_calls[i].count++;
        if (!registered) {
            registered = 1;
            Log_Enable(LOG_STUB, 1);
            atexit(print_stub_summary);
        }
        LOG(LOG_STUB, "%s", name);
        return;
    }
    fflush(stdout);
    Crash_ReportFatal("unimplemented routine", name);
    Profile_Flush();
    _exit(70); /* not exit(): atexit handlers could re-enter game code */
}
