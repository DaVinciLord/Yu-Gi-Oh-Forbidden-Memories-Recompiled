/* Headless loader diagnostic only; no MIPS or native game execution. */
#include "types.h"
#include "pc/guest/translated_image.h"
#include "pc/platform/game_files.h"
#include <stdio.h>
#include <stdlib.h>
int main(int argc, char **argv)
{
    MemoriesMemory *memory;
    unsigned char *image;
    size_t size = 0;
    u32 entry = 0;
    int result;
    if (argc != 2) { fprintf(stderr, "usage: memories-native-loader <USA-disc.bin>\n"); return 2; }
    image = GameFiles_ReadExecutable(argv[1], &size);
    if (!image) { fputs("Cannot read SLUS_014.11 from this disc\n", stderr); return 1; }
    memory = calloc(1, sizeof(*memory));
    result = Memories_LoadTranslatedExe(memory, image, size, &entry);
    if (!result) {
        printf("SLUS_014.11 loaded: %zu executable bytes, entry 0x%08x\n", size, entry);
        printf("Native RAM: %p; entry resolves to %p\n", (void *)memory->ram,
               Memories_Resolve(memory, entry, 4, 4));
        puts("Loader milestone passed; game execution is not implemented");
    } else fputs("Invalid PS-X EXE or allocation failure\n", stderr);
    free(memory);
    free(image);
    return result ? 1 : 0;
}
