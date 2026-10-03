#include "pc/platform/darwin_image.h"
#include <assert.h>
#include <stdio.h>
int main(void)
{
    uintptr_t first, last, again_first, again_last;
    assert(DarwinImage_TextRange(&first, &last));
    assert(first > UINT32_MAX && last > first);
    assert((uintptr_t)main >= first && (uintptr_t)main < last);
    assert((uintptr_t)DarwinImage_TextRange >= first && (uintptr_t)DarwinImage_TextRange < last);
    assert(DarwinImage_TextRange(&again_first, &again_last));
    assert(first == again_first && last == again_last);
    printf("Real Mach-O text range includes native code: 0x%lx..0x%lx\n", (unsigned long)first, (unsigned long)last);
}
