/* languages/pt-br.txt, Game > Language's Brazilian Portuguese (language.h):
 * the listing compiler (src/pc/text/listing.c) reads all of it without a
 * word to say, in letters the port can draw (glyphs.h: the retail font, and
 * the accented letters it adds); and no symbol the fan patch redrew as an
 * accented letter is left as the symbol (notes/translation.md, "Português
 * (Brasil)"), but where the game means the symbol: the name grid, its
 * arrows and the movie counter. */
#include "pc/text/listing.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static const uint32_t bases[TEXT_BANK_COUNT] = {0x801B0000u, 0x801C0000u, 0x801D0000u};
static int reports;

/* The retail glyphs past ASCII (glyphs.c's table), and the letters pt-BR
 * writes with a mark and the º of Jono 2º, each an added glyph from 0x100
 * on. */
static const uint32_t added[] = {0xAB,   0xBB,   0xB7,   0x3B1,  0x3B2,  0x3B3,  0x2190, 0x2192, 0x2640, 0x2642,
                                 0x2282, 0x2283, 0xC0,   0xC1,   0xC2,   0xC3,   0xC7,   0xC9,   0xCA,   0xCD,
                                 0xD3,   0xD4,   0xD5,   0xDA,   0xDC,   0xE0,   0xE1,   0xE2,   0xE3,   0xE7,
                                 0xE9,   0xEA,   0xED,   0xF3,   0xF4,   0xF5,   0xFA,   0xFC,   0xBA};

static int encode(uint32_t character)
{
    size_t i;
    if (character >= 0x20 && character < 0x7F) return (int)(character - 0x20);
    for (i = 0; i < sizeof(added) / sizeof(added[0]); i++) {
        if (added[i] == character) return 0x100 + (int)i;
    }
    return -1;
}

static void report(void *context, int line, const char *message)
{
    (void)context;
    fprintf(stderr, "pt-br.txt line %d: %s\n", line, message);
    reports++;
}

static char *read_pack(size_t *length)
{
    FILE *file = fopen(LANGUAGE_PACK, "rb");
    char *text;
    long size;
    assert(file);
    assert(!fseek(file, 0, SEEK_END) && (size = ftell(file)) > 0 && !fseek(file, 0, SEEK_SET));
    text = malloc((size_t)size + 1);
    assert(text && fread(text, 1, (size_t)size, file) == (size_t)size);
    fclose(file);
    text[size] = '\0';
    *length = (size_t)size;
    return text;
}

static const unsigned char *string(const TextUnit *unit, unsigned id)
{
    int i;
    for (i = 0; i < unit->string_count; i++) {
        if (unit->strings[i].id == id) return unit->data + unit->strings[i].offset;
    }
    return NULL;
}

/* The strings where the game means the symbols themselves. */
static int keeps_symbols(const char *item)
{
    return !strncmp(item, "[00F2]", 6) || !strncmp(item, "[00F3]", 6) || !strncmp(item, "[00F8]", 6);
}

/* A symbol of the fan font's accented letters outside a {code}, a comment
 * or those strings; the line it is on, or 0. */
static int leftover_symbol(const char *text)
{
    const char *line = text, *item = "";
    int number = 1, in_bank = 0;
    while (*line) {
        const char *end = strchr(line, '\n'), *c;
        int code = 0;
        if (!end) end = line + strlen(line);
        if (line[0] == '@') in_bank = 1;
        if (line[0] == '[') item = line;
        if (in_bank && line[0] != '[' && !keeps_symbols(item)) {
            for (c = line; c < end; c++) {
                if (*c == '{') code = 1;
                else if (*c == '}') code = 0;
                else if (!code && strchr("#$%&*+;<>", *c)) return number;
                else if (!code && !strncmp(c, "\xE2\x8A\x82", 3)) return number;   /* ⊂, the fan's É */
                else if (!code && !strncmp(c, "\xCE\xB1", 2)) return number;       /* α, the fan's ç */
            }
        }
        line = *end ? end + 1 : end;
        number++;
    }
    return 0;
}

int main(void)
{
    size_t length;
    char *text = read_pack(&length);
    TextUnit *unit = TextListing_Compile(text, length, bases, NULL, 0, encode, report, NULL);
    const unsigned char *name;

    assert(unit && reports == 0);
    assert(unit->string_count > 1800);
    /* Card 1's name, Dragão B. de Olhos Azuis: the ã an added glyph (F1 and
     * its low byte), after "Drag". */
    name = string(unit, 0x8001);
    assert(name && name[0] == encode('D') && name[3] == encode('g'));
    assert(name[4] == 0xF1 && name[5] == encode(0xE3) - 0x100);
    assert(leftover_symbol(text) == 0);
    TextListing_Free(unit);
    free(text);
    puts("pt-br.txt: compiles, every letter drawable, no fan-font symbol left");
    return 0;
}
