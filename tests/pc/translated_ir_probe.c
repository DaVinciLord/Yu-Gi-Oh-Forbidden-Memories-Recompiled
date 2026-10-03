#include "types.h"
#include <stdint.h>
typedef void (*Callback)(int);
struct Record { u8 *G32 bytes; Callback G32 callback; };
extern struct Record pinned_record;
u8 read_stream(struct Record *record) { return *record->bytes++; }
void write_stream(struct Record *record, u8 value) { record->bytes[2] = value; }
u8 *get_stream(struct Record *record) { return record->bytes; }
void set_stream(struct Record *record, u8 *native) { record->bytes = native; }
u8 *guest_cast(u32 guest) { return (u8 *)(uintptr_t)guest; }
u32 native_cast(u8 *native) { return (u32)(uintptr_t)native; }
u8 read_absolute(void) { return *(u8 *)(uintptr_t)0x8009B363u; }
u8 read_pinned(void) { return *pinned_record.bytes; }
void invoke(struct Record *record, int value) { CALL32(Callback, record->callback)(value); }
/* Exercise native atomic operands whose addresses may still be guest tokens. */
u32 atomic_read(u32 *address) { return __atomic_load_n(address, __ATOMIC_ACQUIRE); }
void atomic_write(u32 *address, u32 value) { __atomic_store_n(address, value, __ATOMIC_RELEASE); }
u32 atomic_add(u32 *address) { return __atomic_fetch_add(address, 3, __ATOMIC_SEQ_CST); }
int atomic_exchange(u32 *address, u32 *expected, u32 desired)
{
    return __atomic_compare_exchange_n(address, expected, desired, 0,
                                       __ATOMIC_SEQ_CST, __ATOMIC_SEQ_CST);
}
struct WidePair { u64 first, second; };
u64 sum_pair(struct WidePair pair) { return pair.first + pair.second; }
/* Compiler-emitted fortified calls are native boundaries too. */
void *checked_copy(void *out, const void *in, u32 length)
{
    return __builtin___memcpy_chk(out, in, length, 4);
}
void *checked_set(void *out, int value, u32 length)
{
    return __builtin___memset_chk(out, value, length, 4);
}
int checked_format(char *out, const char *string)
{
    return __builtin___snprintf_chk(out, 8, 0, 8, "%s%d", string, 12);
}
extern Callback G32 callback_table[2];
void invoke_guest_table(int value) { callback_table[1](value); }
/* Known-symbol casts are folded to ptrtoint constant expressions by Clang. */
extern void constant_callback(int);
void store_constant_callback(u8 *object) { *(u32 *)(object + 0x4c) = (u32)(uintptr_t)constant_callback; }
