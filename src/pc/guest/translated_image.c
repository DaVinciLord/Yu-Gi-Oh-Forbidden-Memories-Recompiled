#include "../../types.h"
#include "translated_image.h"
#include <string.h>

int Memories_LoadTranslatedExe(MemoriesMemory *memory, const uint8_t *data,
                              size_t length, uint32_t *entry)
{
    u32 address, size, pc;
    void *destination;
    if (!memory || !data || !entry || length < 0x800 || memcmp(data, "PS-X EXE", 8)) return -1;
    address = Memories_ReadLE32(data + 0x18);
    size = Memories_ReadLE32(data + 0x1c);
    pc = Memories_ReadLE32(data + 0x10);
    /* Match the existing runtime's KSEG0 image range and reserved kernel RAM.
     * Also require an aligned entry inside initialized text/data. */
    if (address < 0x80010000u || address >= 0x80200000u || size < 4 ||
        size > length - 0x800 || size > 0x80200000u - address ||
        pc < address || pc - address > size - 4 || (pc & 3u)) return -1;
    destination = Memories_Resolve(memory, address, size, 4);
    if (!destination) return -1;
    memcpy(destination, data + 0x800, size);
    *entry = pc;
    return 0;
}
