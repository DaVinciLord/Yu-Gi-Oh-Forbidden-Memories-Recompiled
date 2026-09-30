"""Run the actual ritual hand mod with synthetic 32-bit game records."""
import pathlib
import subprocess
import tempfile
import errno


def execute(executable):
    try:
        return subprocess.run([executable]).returncode
    except OSError as problem:
        if problem.errno != errno.ENOEXEC:
            raise
    # Some hosts disable 32-bit Linux execution. An optional emulator keeps
    # the test on the real 32-bit layouts rather than changing the headers.
    from elftools.elf.elffile import ELFFile
    from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_INTR
    from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_EBX, UC_X86_REG_ESP
    emulator = Uc(UC_ARCH_X86, UC_MODE_32)
    with open(executable, "rb") as handle:
        elf = ELFFile(handle)
        segments = [s for s in elf.iter_segments() if s["p_type"] == "PT_LOAD"]
        start = min(s["p_vaddr"] for s in segments) & ~4095
        end = (max(s["p_vaddr"] + s["p_memsz"] for s in segments) + 4095) & ~4095
        emulator.mem_map(start, end - start)
        for segment in segments:
            emulator.mem_write(segment["p_vaddr"], segment.data())
        entry = elf["e_entry"]
    emulator.mem_map(0x70000000, 0x100000)
    emulator.reg_write(UC_X86_REG_ESP, 0x700ff000)
    result = []

    def interrupt(machine, number, data):
        if number != 0x80 or machine.reg_read(UC_X86_REG_EAX) != 1:
            raise RuntimeError("Unexpected syscall in freestanding test")
        result.append(machine.reg_read(UC_X86_REG_EBX))
        machine.emu_stop()

    emulator.hook_add(UC_HOOK_INTR, interrupt)
    emulator.emu_start(entry, 0, count=10_000_000)
    if not result:
        raise RuntimeError("Test did not finish within the instruction budget")
    return result[0]

ROOT = pathlib.Path(__file__).resolve().parents[2]
compiler_headers = subprocess.check_output(
    ["gcc", "-m32", "-print-file-name=include"], text=True).strip()
with tempfile.TemporaryDirectory() as tmp:
    executable = str(pathlib.Path(tmp) / "ritual_hand_test")
    subprocess.run([
        "gcc", "-m32", "-std=gnu11", "-O2", "-nostdlib", "-static",
        "-fno-pie", "-no-pie", "-ffreestanding", "-nostdinc", "-ffunction-sections",
        "-fdata-sections", "-w", "-Wl,--gc-sections", "-DMEMORIES_PC",
        "-D_LANGUAGE_C", "-DLANGUAGE_C", "-isystem", str(ROOT / "src/pc/mods/sdk"),
        "-isystem", compiler_headers,
        "-I", str(ROOT / "src"), str(ROOT / "tests/pc/ritual_hand_mod_test.c"),
        "-o", executable,
    ], check=True)
    result = execute(executable)
    if result:
        raise SystemExit(f"Ritual hand mod case {result} failed")
    print("Ritual hand mod: 24 checks on each side passed (48 total)")
