#include "pc/guest/state_io.h"
#include <assert.h>
#include <errno.h>
#include <string.h>

int main(void)
{
    uint32_t number = 0x12345678, length;
    uint8_t flags[2] = {7, 9}, image[42], zero[16] = {0};
    MemoriesStateField fields[] = {{&number, sizeof(number)}, {flags, sizeof(flags)}, {NULL, 0}};
    MemoriesState save = {0, tmpfile(), NULL, 0};
    MemoriesState load = {1, NULL, image, sizeof(image)};
    size_t size;
    assert(save.file);
    Memories_StateWrite(&save, zero, sizeof(zero));
    assert(!Memories_StateChunk(&save, "fixture", fields, 3));
    assert(!ferror(save.file) && ftell(save.file) == sizeof(image));
    rewind(save.file);
    assert(fread(image, 1, sizeof(image), save.file) == sizeof(image));
    fclose(save.file);
    number = 0;
    memset(flags, 0, sizeof(flags));
    assert(Memories_StateLoading(&load));
    assert(Memories_StateChunk(&load, "fixture", fields, 3));
    assert(number == 0x12345678 && flags[0] == 7 && flags[1] == 9);
    assert(Memories_StateFindChunk(&load, "fixture", &size) == image + 36 && size == 6);
    number = 42;
    load.image_size--;
    assert(!Memories_StateChunk(&load, "fixture", fields, 3) && number == 42);
    load.image_size++;
    length = 5;
    memcpy(image + 32, &length, 4);
    assert(!Memories_StateChunk(&load, "fixture", fields, 3) && number == 42);
    length = UINT32_MAX;
    memcpy(image + 32, &length, 4);
    assert(!Memories_StateFindChunk(&load, "fixture", &size));
    load.image_size = 15;
    assert(!Memories_StateFindChunk(&load, "fixture", &size));
    assert(!Memories_StateLoading(NULL));
    assert(!Memories_StateChunk(NULL, "fixture", fields, 3) && errno == EINVAL);
    fields[0].size = SIZE_MAX;
    assert(!Memories_StateChunk(&load, "fixture", fields, 3) && errno == EINVAL);
    puts("State chunks: round trip, field ordering, truncation, layout mismatch and overflow passed");
    return 0;
}
