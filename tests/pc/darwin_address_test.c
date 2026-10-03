/* Diagnostic only: never replace an existing virtual-memory mapping. */
#include "types.h"
#include "port_ptr.h"
#include <mach/mach.h>
#include <mach/mach_vm.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>

struct GuestSlot { u8 *G32 data; s32 count; };
_Static_assert(sizeof(void *) == 8, "native LP64 required");
_Static_assert(sizeof(((struct GuestSlot *)0)->data) == 4, "guest pointer width");
_Static_assert(offsetof(struct GuestSlot, count) == 4, "guest member offset");
_Static_assert(sizeof(struct GuestSlot) == 8, "guest structure size");
_Static_assert(sizeof(PSXLONG) == 4, "Psy-Q long width");

int main(void)
{
    const u32 addresses[] = {0x10000u, 0x1f800000u, 0x80000000u, 0xa0000000u};
    unsigned i, blocked = 0;
    mach_vm_address_t owned = 0, collision;
    kern_return_t result;
    if (mach_vm_allocate(mach_task_self(), &owned, vm_page_size, VM_FLAGS_ANYWHERE) != KERN_SUCCESS) return 1;
    *(volatile u32 *)(uintptr_t)owned = 0x12345678u;
    collision = owned;
    result = mach_vm_allocate(mach_task_self(), &collision, vm_page_size, VM_FLAGS_FIXED);
    if (result == KERN_SUCCESS || *(volatile u32 *)(uintptr_t)owned != 0x12345678u) return 1;
    if (mach_vm_deallocate(mach_task_self(), owned, vm_page_size) != KERN_SUCCESS) return 1;
    puts("Reservation collision preserves existing memory");
    /* VM_FLAGS_FIXED fails on a collision; VM_FLAGS_OVERWRITE is forbidden.
     * These pages are diagnostic reservations, not shared RAM aliases. */
    for (i = 0; i < sizeof(addresses) / sizeof(addresses[0]); ++i) {
        mach_vm_address_t address = addresses[i];
        kern_return_t result = mach_vm_allocate(mach_task_self(), &address,
                                               vm_page_size, VM_FLAGS_FIXED);
        printf("reserve 0x%08x: %s (%d)\n", addresses[i], mach_error_string(result), result);
        if (result == KERN_SUCCESS) {
            if (address != addresses[i]) return 1;
            if (mach_vm_deallocate(mach_task_self(), address, vm_page_size) != KERN_SUCCESS) return 1;
        } else if (result == KERN_NO_SPACE || result == KERN_INVALID_ADDRESS) {
            blocked++;
        } else {
            return 1;
        }
    }
    puts("G32 width, offsets and PSXLONG passed");
    if (blocked) {
        puts("Fixed guest addresses unavailable; runtime milestone NOT passed");
        return 77;
    }
    puts("Reservations available; shared aliases and callbacks still unverified");
    return 0;
}
