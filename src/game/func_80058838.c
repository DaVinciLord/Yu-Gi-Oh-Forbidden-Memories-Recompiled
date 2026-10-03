#include "../types.h"
#include "func_80058938.h"
#include "model.h"
#ifdef MEMORIES_TRANSLATED
#include <stdarg.h>
#endif

void Model_QueueTintRequestForParts(
    s32 a0, s32 a1, ModelTintColor a2, ModelTintColor a3, s32 a4, ...)
{
    u8 bits[8];
#ifdef MEMORIES_TRANSLATED
    va_list arguments;
#else
    u8 *arguments;
#endif
    s32 value;
    s32 byte_index;
    s32 i;
    u8 *cursor;

    i = 7;
    cursor = bits + 7;
    for (; i >= 0; i--)
        *cursor-- = 0;
#ifdef MEMORIES_TRANSLATED
    va_start(arguments, a4);
#else
    arguments = (u8 *)&a4 + 4;
#endif
    while (1) {
#ifdef MEMORIES_TRANSLATED
        value = va_arg(arguments, s32);
#else
        arguments += 4;
        value = *(s32 *)(arguments - 4);
#endif
        if (value < 0)
            break;
        byte_index = value >> 3;
        bits[byte_index] |= 1 << (value - byte_index * 8);
    }
#ifdef MEMORIES_TRANSLATED
    va_end(arguments);
#endif
    a2.b3 = a1 & 127;
    Model_QueueTintRequest(a0, a1 & 128, a2, a3, a4, bits);
}
