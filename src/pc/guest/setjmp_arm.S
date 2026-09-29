/* 32-bit ARM (A32) counterpart of setjmp_i386.S. The game's jmp_buf is the
 * Psy-Q int[12] at a fixed guest address: R4-R11, SP and LR take 40 of its
 * 48 bytes. The callee-saved VFP registers (D8-D15, 64 bytes) do not fit;
 * they go to a small table here, keyed by the buffer's address (the game has
 * one buffer; a fifth one would take the first slot over). The build
 * assembles this for ARM targets only (tools/pc/build_game32.py). */
    .syntax unified
    .arm
    .text

#define SLOTS 4
#define SLOT_SIZE 72 /* the buffer's address, a pad word, D8-D15 */

/* r0: the buffer. Leaves the buffer's slot in r1 (NULL when `find_only` and
 * there is none) and changes r2, r3. */
.macro FIND_SLOT find_only
    ldr r1, 9f
8:  add r1, pc, r1
    mov r2, #SLOTS
1:  ldr r3, [r1]
    cmp r3, r0
    beq 3f
    .if \find_only == 0
    cmp r3, #0
    beq 3f
    .endif
    add r1, r1, #SLOT_SIZE
    subs r2, r2, #1
    bne 1b
    .if \find_only == 0
    sub r1, r1, #(SLOT_SIZE * SLOTS)
    .else
    mov r1, #0
    .endif
    b 3f
9:  .word psx_vfp_slots - (8b + 8)
3:
.endm

    .globl Psx_setjmp
    .type Psx_setjmp, %function
    .p2align 2
Psx_setjmp:
    stm r0, {r4-r11}
    str sp, [r0, #32]
    str lr, [r0, #36]
#if defined(__ARM_FP)
    FIND_SLOT 0
    str r0, [r1]
    add r1, r1, #8
    vstmia r1, {d8-d15}
#endif
    mov r0, #0
    bx lr
    .size Psx_setjmp, . - Psx_setjmp

    .globl Psx_longjmp
    .type Psx_longjmp, %function
    .p2align 2
Psx_longjmp:
    mov r12, r1
    cmp r12, #0
    moveq r12, #1
#if defined(__ARM_FP)
    FIND_SLOT 1
    cmp r1, #0
    addne r1, r1, #8
    vldmiane r1, {d8-d15}
#endif
    ldm r0, {r4-r11}
    ldr sp, [r0, #32]
    ldr lr, [r0, #36]
    mov r0, r12
    bx lr
    .size Psx_longjmp, . - Psx_longjmp

    .bss
    .p2align 3
psx_vfp_slots:
    .space SLOT_SIZE * SLOTS
    .section .note.GNU-stack, "", %progbits
