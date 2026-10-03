#include "darwin_image.h"
#ifdef __APPLE__
#include <mach-o/dyld.h>
#include <mach-o/loader.h>
#include <stddef.h>
#include <string.h>

int DarwinImage_TextRange(uintptr_t *first, uintptr_t *last)
{
    static uintptr_t cached_first, cached_last;
    static int initialized;
    if (!initialized) {
        const struct mach_header_64 *header = (const void *)_dyld_get_image_header(0);
        intptr_t slide = _dyld_get_image_vmaddr_slide(0);
        if (header && header->magic == MH_MAGIC_64) {
            const char *cursor = (const char *)(header + 1);
            const char *end = cursor + header->sizeofcmds;
            for (uint32_t i = 0; i < header->ncmds && cursor + sizeof(struct load_command) <= end; i++) {
                const struct load_command *command = (const void *)cursor;
                if (command->cmdsize < sizeof(*command) || (size_t)(end - cursor) < command->cmdsize) break;
                if (command->cmd == LC_SEGMENT_64 && command->cmdsize >= sizeof(struct segment_command_64)) {
                    const struct segment_command_64 *segment = (const void *)cursor;
                    if (!strncmp(segment->segname, "__TEXT", 16) && segment->nsects <=
                        (command->cmdsize - sizeof(*segment)) / sizeof(struct section_64)) {
                        const struct section_64 *section = (const void *)(segment + 1);
                        for (uint32_t j = 0; j < segment->nsects; j++, section++) {
                            if (!strncmp(section->sectname, "__text", 16) && section->size) {
                                cached_first = (uintptr_t)(section->addr + slide);
                                if (section->size <= UINTPTR_MAX - cached_first) cached_last = cached_first + section->size;
                            }
                        }
                    }
                }
                cursor += command->cmdsize;
            }
        }
        initialized = 1;
    }
    *first = cached_first; *last = cached_last;
    return cached_last > cached_first;
}
#endif
