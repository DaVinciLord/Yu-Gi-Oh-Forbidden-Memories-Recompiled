/* A PAL language pack's text as a listing with the US ids (pal_text.h).
 *
 * The decoding is tools/pc/text_listing.py's, and the listing the one the
 * Language research's extractor wrote (the same text, byte for byte, for
 * the five discs, but for the result pages and F8 1C): every string the tables reach, the jumps as labels, the
 * menus' labels renamed into names the story's text does not use, since
 * both end up in the US dialogue bank. What is ours here is knowledge, not
 * the game's: which letter each language's font draws on a placeholder
 * code, and which ids mean something else on the PAL discs. */
#include "pal_text.h"
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define BANK_SIZE 0x10000
#define FILE_TABLE 4                 /* each file's u16 id and u16 0 */
#define MENU_IDS 0x100
#define DESCRIPTION_IDS 0x100        /* table entries 0x100-0x3FF: US ids 0xD100-0xD3FF */
#define DIALOG_FIRST 0x400           /* table entries 0x400-0x4F9: US ids 0x500-0x5F9 */
#define DIALOG_LAST 0x4F9
#define NAME_IDS 0x360
#define NAMES_BEFORE_C 0x5800        /* file C sits at 0x801D5800 in the US names bank */
#define FREE_NAMES 0xF000            /* the menus' labels: names from here the dialogue does not use */
#define NUMBER_DELTA (0x801D5608u - 0x801BF88Cu)

/* Menu ids whose PAL string is another screen's (checked against the US
 * text with the English PAL disc): the debug menu with ENDING and LANGUAGE,
 * the PAL name keyboard's rows and prompt, the movie notice PAL has not,
 * and the ids US leaves empty. They keep the US string. So do the result
 * pages, 0x40-0x45: PAL lays them out with code of its own (its 0x40 and
 * 0x44 trade places, and no string names a total annihilation), which the
 * US screens cannot show right (phase 2). */
static const int keep_us[] = {0x06, 0x10, 0x18, 0x19, 0x40, 0x41, 0x42, 0x43, 0x44, 0x45, 0x50,
                              0xEE, 0xEF, 0xF0, 0xF1, 0xF3, 0xF7};

/* The PAL name buffers (file A offsets) and the US ones they stand for. */
static const struct { unsigned pal, us; } name_buffers[] = {{0xF800, 0x122B}, {0xF814, 0x1238}, {0xF848, 0x125A}};

/* Each language's font on the placeholder codes (Shift-JIS kanji in the
 * shared table): the letter, as read from the text. */
typedef struct { unsigned char code; uint16_t character; } Accent;
static const Accent french[] = {
    {0x24, 0xE9}, {0x2A, 0x27}, {0x37, 0x2D}, {0x3E, 0xE0}, {0x3F, 0x153}, {0x40, 0xE8}, {0x4C, 0xEA},
    {0x51, 0xC9}, {0x55, 0xF9}, {0x56, 0xEE}, {0x59, 0xF4}, {0x5A, 0x22}, {0x5B, 0xC8}, {0x5D, 0xE2},
    {0x61, 0xE7}, {0x64, 0x27}, {0x66, 0xB0}, {0x69, 0x153}, {0x6D, 0xC0}, {0x72, 0xEF}, {0x77, 0xFB},
    {0x81, 0xCA}, {0x82, 0xBB}, {0x83, 0xAB}, {0x8B, 0xC7}, {0x8E, 0xCA}, {0, 0}};
static const Accent german[] = {
    {0x2A, 0x27}, {0x37, 0x2D}, {0x3D, 0xE4}, {0x41, 0xFC}, {0x44, 0xF6}, {0x4F, 0xDF}, {0x5A, 0x22},
    {0x64, 0x27}, {0x6A, 0xC4}, {0x74, 0xDC}, {0x78, 0xD6}, {0, 0}};
static const Accent italian[] = {
    {0x24, 0xE9}, {0x2A, 0x27}, {0x37, 0x2D}, {0x3E, 0xE0}, {0x40, 0xE8}, {0x53, 0xF2}, {0x55, 0xF9},
    {0x57, 0xEC}, {0x5A, 0x22}, {0x5B, 0xC8}, {0x64, 0x27}, {0x6D, 0xC0}, {0x6F, 0xCC}, {0, 0}};
static const Accent spanish[] = {
    {0x24, 0xE9}, {0x36, 0xA1}, {0x37, 0x2D}, {0x3F, 0xE1}, {0x41, 0xFC}, {0x42, 0xED}, {0x43, 0xF3},
    {0x4A, 0xBF}, {0x4D, 0xF1}, {0x51, 0xC9}, {0x52, 0xFA}, {0x5A, 0x22}, {0x64, 0x27}, {0x66, 0xBA},
    {0x68, 0xCD}, {0x69, 0xC1}, {0x71, 0xBA}, {0x7A, 0xD3}, {0x7C, 0xAA}, {0x84, 0xD1}, {0x86, 0xDA}, {0, 0}};
static const Accent *const accents[PAL_LANGUAGES] = {NULL, french, german, italian, spanish};

/* The Shift-JIS the tables use, as the character the US listing spells it
 * with (the full-width forms as ASCII). 0 for none. */
static uint32_t sjis_character(unsigned sjis)
{
    static const struct { uint16_t sjis; uint16_t character; } symbols[] = {
        {0x8140, ' '}, {0x8143, ','}, {0x8144, '.'}, {0x8145, 0xB7}, {0x8146, ':'}, {0x8147, ';'},
        {0x8148, '?'}, {0x8149, '!'}, {0x815E, '/'}, {0x8166, '\''}, {0x8168, '"'}, {0x8169, '('},
        {0x816A, ')'}, {0x816D, '['}, {0x816E, ']'}, {0x8173, 0xAB}, {0x8174, 0xBB}, {0x817B, '+'},
        {0x817C, '-'}, {0x8183, '<'}, {0x8184, '>'}, {0x8189, 0x2642}, {0x818A, 0x2640}, {0x8190, '$'},
        {0x8193, '%'}, {0x8194, '#'}, {0x8195, '&'}, {0x8196, '*'}, {0x81A8, 0x2192}, {0x81A9, 0x2190},
        {0x81BC, 0x2282}, {0x81BD, 0x2283}, {0x83BF, 0x3B1}};
    size_t i;
    if (sjis >= 0x824F && sjis <= 0x8258) return '0' + (sjis - 0x824F);
    if (sjis >= 0x8260 && sjis <= 0x8279) return 'A' + (sjis - 0x8260);
    if (sjis >= 0x8281 && sjis <= 0x829A) return 'a' + (sjis - 0x8281);
    for (i = 0; i < sizeof(symbols) / sizeof(symbols[0]); i++) {
        if (symbols[i].sjis == sjis) return symbols[i].character;
    }
    return 0;
}

/* --- decoding --------------------------------------------------------------- */

enum { OP_GLYPH = 1, OP_NL, OP_END, OP_CODE };
#define MAX_TARGETS 8

typedef struct {
    unsigned char kind, length, target_count;
    uint16_t value;             /* a glyph's code */
    char text[48];              /* a code's words */
    uint16_t targets[MAX_TARGETS];
} Op;

typedef struct {
    const char *name;
    const unsigned char *memory;           /* BANK_SIZE bytes */
    int ids[0x10000];                      /* id -> offset, -1 for none */
    unsigned char buffer[BANK_SIZE];       /* offsets the game writes (never decoded) */
    int op_at[BANK_SIZE];                  /* offset -> index in ops, -1 */
    Op *ops;
    int op_count, op_room;
    unsigned char target[BANK_SIZE], start[BANK_SIZE];
    int failed;
} Bank;

typedef struct {
    int *items;
    int count, room;
} Stack;

static int push(Stack *stack, int value)
{
    if (stack->count == stack->room) {
        int room = stack->room ? stack->room * 2 : 256;
        int *items = realloc(stack->items, (size_t)room * sizeof(*items));
        if (!items) return 0;
        stack->items = items;
        stack->room = room;
    }
    stack->items[stack->count++] = value;
    return 1;
}

/* Reading past the bank ends the bank's decoding (as the extractor's
 * DecodeError does). */
static int byte_at(const Bank *bank, int at, int *failed)
{
    if (at < 0 || at >= BANK_SIZE) {
        *failed = 1;
        return 0;
    }
    return bank->memory[at];
}

static int word_at(const Bank *bank, int at, int *failed)
{
    return byte_at(bank, at, failed) | byte_at(bank, at + 1, failed) << 8;
}

/* Up to `most` u16 targets at `at`: a table ends where its first target, or
 * another string, begins. */
static int jump_table(const Bank *bank, int at, int most, uint16_t *table)
{
    int count = 0, end = at + 2 * most, i;
    for (i = 0; i < most; i++) {
        int here = at + 2 * i, target;
        if (here >= end || here + 1 >= BANK_SIZE || bank->start[here] || bank->start[here + 1]) break;
        target = bank->memory[here] | bank->memory[here + 1] << 8;
        table[count++] = (uint16_t)target;
        if (target && at < target && target < end) end = target;
    }
    return count;
}

static void words(Op *op, const char *format, ...)
{
    va_list args;
    va_start(args, format);
    vsnprintf(op->text, sizeof(op->text), format, args);
    va_end(args);
}

static void operands(Op *op, const Bank *bank, int at, int count, int *failed)
{
    int i;
    for (i = 0; i < count; i++) {
        size_t used = strlen(op->text);
        snprintf(op->text + used, sizeof(op->text) - used, " %02X", byte_at(bank, at + i, failed));
    }
}

/* F8 and its operands: whether the stream goes on. */
static int decode_secondary(const Bank *bank, int at, Op *op, int *failed)
{
    static const signed char counts[0x2B] = {
        1, 1, 1, 5, 1, 2, 2, 1 /* 07: a byte in the PAL */, 0, 0, 1, 1, 1, 6, 2, -1, -1, 1, 0, 0, 1, 1, 0, -1, -1,
        1, 0,
        0 /* 1B: PAL's player name */, 1, 1, 1, 1, 1, 2, 1, -1, -1, 0, -1, 2, 2, 0, 0};
    int index = byte_at(bank, at + 1, failed), count;
    op->kind = OP_CODE;
    if (index == 0x0F) {
        count = 1 + ((byte_at(bank, at + 2, failed) & 0x3F) ? 2 : 0);
    } else if (index == 0x10) {
        count = 2 + ((byte_at(bank, at + 3, failed) & 0x80) ? 2 : 0);
    } else if (index == 0x17 || index == 0x18) {
        op->target_count = (unsigned char)jump_table(bank, at + 2, 4, op->targets);
        op->length = (unsigned char)(2 + 2 * op->target_count);
        words(op, "f8 %02X", index);
        return 0;
    } else if (index < (int)sizeof(counts) && counts[index] >= 0) {
        count = counts[index];
    } else {
        *failed = 1;
        return 0;
    }
    if (index == 0x27 || index == 0x28) {
        op->targets[0] = (uint16_t)word_at(bank, at + 2, failed);
        op->target_count = 1;
        op->length = 4;
        words(op, "f8 %02X", index);
        return index != 0x28;
    }
    op->length = (unsigned char)(2 + count);
    words(op, "f8 %02X", index);
    operands(op, bank, at + 2, count, failed);
    /* The PAL's F8 07 takes a byte (EU 0x80038190: that times 8 pixels); the
     * US one, which the port runs, a u16. The byte goes as its low half:
     * TextBox_BuildStep reads it as the PAL does with a language on. */
    if (index == 0x07) {
        size_t used = strlen(op->text);
        snprintf(op->text + used, sizeof(op->text) - used, " 00");
    }
    /* F8 00 03, the PAL's own (EU 0x80037B3C): the card's type as a label,
     * which the magic cards' rows and bar show. The US code has no kind 3
     * (it would draw the dragon's icon); its rows draw that label from kind
     * 1, the first guardian star's, as the US [0007] and [0051] do. */
    if (index == 0x00 && byte_at(bank, at + 2, failed) == 0x03) words(op, "f8 00 01");
    return index != 0x2A;
}

static Op *add_op(Bank *bank, int at)
{
    if (bank->op_count == bank->op_room) {
        int room = bank->op_room ? bank->op_room * 2 : 4096;
        Op *ops = realloc(bank->ops, (size_t)room * sizeof(*ops));
        if (!ops) return NULL;
        bank->ops = ops;
        bank->op_room = room;
    }
    bank->op_at[at] = bank->op_count;
    return &bank->ops[bank->op_count++];
}

/* Every op reachable from the bank's strings. Nonzero if it decoded. */
static int decode_bank(Bank *bank)
{
    Stack work = {0}, deferred = {0};
    signed char *setups = malloc(BANK_SIZE); /* choice setups: offset -> number of choices, -1 */
    int failed = 0, offset, id;
    if (!setups) return 0;
    memset(setups, -1, BANK_SIZE);
    for (offset = 0; offset < BANK_SIZE; offset++) bank->op_at[offset] = -1;
    for (id = 0; id < 0x10000; id++) {
        if (bank->ids[id] > 0 && bank->ids[id] < BANK_SIZE) bank->start[bank->ids[id]] = 1;
    }
    for (offset = 1; offset < BANK_SIZE && !failed; offset++) {
        if (bank->start[offset] && !push(&work, offset)) failed = 1;
    }
    while (!failed && (work.count || deferred.count)) {
        int at, entry, choices = -1;
        if (!work.count) {
            /* Paths that met a choice jump before any setup: its setup is
             * the nearest one before it, now that everything else is read. */
            int progress = 0, i, n = deferred.count, *waiting = deferred.items;
            deferred.items = NULL;
            deferred.count = deferred.room = 0;
            for (i = 0; i < n && !failed; i++) {
                int before = 0, s;
                for (s = 0; s < waiting[i]; s++) before |= setups[s] >= 0;
                if (before) {
                    failed = !push(&work, waiting[i]);
                    progress = 1;
                } else {
                    failed = !push(&deferred, waiting[i]);
                }
            }
            free(waiting);
            if (!progress) failed = 1;
            continue;
        }
        at = entry = work.items[--work.count];
        while (!failed && bank->op_at[at] < 0) {
            int op = byte_at(bank, at, &failed), here = at, follow = 1, i;
            Op item;
            if (bank->buffer[at]) break;
            memset(&item, 0, sizeof(item));
            if (op < 0xF0) {
                item.kind = OP_GLYPH, item.length = 1, item.value = (uint16_t)op;
            } else if (op <= 0xF5) {
                item.kind = OP_GLYPH, item.length = 2;
                item.value = (uint16_t)(((op - 0xF0) << 8) | byte_at(bank, at + 1, &failed));
            } else if (op == 0xF6) {
                item.kind = OP_CODE, item.length = 3;
                words(&item, "fx %02X %02X", byte_at(bank, at + 1, &failed), byte_at(bank, at + 2, &failed));
            } else if (op == 0xF7) {
                /* Some states read operands of their own once they start. */
                int state = byte_at(bank, at + 1, &failed), count = 0;
                switch (state & 0x1F) {
                case 0x05: count = (word_at(bank, at + 2, &failed) & 0x8000) ? 5 : 2; break;
                case 0x0B: count = 6; break;
                case 0x0F: case 0x10: count = 2; break;
                }
                item.kind = OP_CODE, item.length = (unsigned char)(2 + count);
                words(&item, "state %02X", state);
                operands(&item, bank, at + 2, count, &failed);
            } else if (op == 0xF8) {
                follow = decode_secondary(bank, at, &item, &failed);
                if (byte_at(bank, at + 1, &failed) == 0x1B) {
                    /* PAL: the player's name, no operand */
                    item.length = 2;
                    words(&item, "f8 1B");
                    follow = 1;
                }
            } else if (op == 0xF9) {
                int command = word_at(bank, at + 1, &failed);
                item.kind = OP_CODE;
                if (command & 0x4000) {
                    item.length = 3;
                    words(&item, "set %04X", command);
                } else {
                    item.length = 5;
                    words(&item, "if %04X", command);
                    item.targets[0] = (uint16_t)word_at(bank, at + 3, &failed);
                    item.target_count = 1;
                }
            } else if (op == 0xFA) {
                item.kind = OP_CODE, item.length = 1;
                words(&item, "page");
            } else if (op == 0xFB) {
                int control = byte_at(bank, at + 1, &failed), length = 2;
                item.kind = OP_CODE;
                words(&item, "%s %02X", control & 0x80 ? "choose" : "choice", control);
                if (control & 0x08) {
                    operands(&item, bank, at + 2, 1, &failed);
                    length = 3;
                }
                if (control & 0x80) {
                    if (choices < 0) {
                        int s;
                        for (s = at - 1; s >= 0 && setups[s] < 0; s--) {}
                        if (s < 0) {
                            failed = !push(&deferred, entry);
                            break;
                        }
                        choices = setups[s];
                    }
                    item.target_count = (unsigned char)jump_table(bank, at + length, choices, item.targets);
                    item.length = (unsigned char)(length + 2 * item.target_count);
                    follow = 0;
                } else {
                    choices = control & 7;
                    setups[here] = (signed char)choices;
                    item.length = (unsigned char)length;
                }
            } else if (op == 0xFC || op == 0xFD) {
                item.kind = OP_CODE, item.length = 3;
                words(&item, op == 0xFC ? "call" : "jump");
                item.targets[0] = (uint16_t)word_at(bank, at + 1, &failed);
                item.target_count = 1;
                follow = op == 0xFC;
            } else if (op == 0xFE) {
                item.kind = OP_NL, item.length = 1;
            } else {
                item.kind = OP_END, item.length = 1;
                follow = 0;
            }
            if (failed) break;
            for (i = here + 1; i < here + item.length; i++) {
                if (i >= BANK_SIZE || bank->op_at[i] >= 0 || bank->start[i]) failed = 1;
            }
            if (failed) break;
            {
                Op *added = add_op(bank, here);
                if (!added) {
                    failed = 1;
                    break;
                }
                *added = item;
            }
            for (i = 0; i < item.target_count; i++) {
                int target = item.targets[i];
                if (!target) continue; /* a null entry, never taken */
                bank->target[target] = 1;
                if (bank->op_at[target] < 0 && !push(&work, target)) failed = 1;
            }
            if (!follow) break;
            at = here + item.length;
        }
    }
    for (offset = 0; offset < BANK_SIZE && !failed; offset++) {
        if (bank->target[offset] && !bank->buffer[offset] && bank->op_at[offset] < 0) failed = 1;
    }
    free(work.items);
    free(deferred.items);
    free(setups);
    return !failed;
}

/* --- writing -------------------------------------------------------------- */

typedef struct {
    char *text;
    size_t length, room;
    int failed;
} Out;

static void add(Out *out, const char *text)
{
    size_t n = strlen(text);
    if (out->failed) return;
    if (out->length + n + 1 > out->room) {
        size_t room = out->room ? out->room : 1 << 18;
        char *bigger;
        while (out->length + n + 1 > room) room *= 2;
        bigger = realloc(out->text, room);
        if (!bigger) {
            out->failed = 1;
            return;
        }
        out->text = bigger;
        out->room = room;
    }
    memcpy(out->text + out->length, text, n + 1);
    out->length += n;
}

static void addf(Out *out, const char *format, ...)
{
    char text[128];
    va_list args;
    va_start(args, format);
    vsnprintf(text, sizeof(text), format, args);
    va_end(args);
    add(out, text);
}

static void add_character(Out *out, uint32_t c)
{
    char text[5] = {0};
    if (c < 0x80) {
        text[0] = (char)c;
    } else if (c < 0x800) {
        text[0] = (char)(0xC0 | c >> 6), text[1] = (char)(0x80 | (c & 0x3F));
    } else {
        text[0] = (char)(0xE0 | c >> 12), text[1] = (char)(0x80 | (c >> 6 & 0x3F)), text[2] = (char)(0x80 | (c & 0x3F));
    }
    add(out, text);
}

/* The last line gets `text`; a new line starts with `text`. */
#define LINE(out, text) (add((out), "\n"), add((out), (text)))

static int is_name_buffer(unsigned offset, unsigned *us)
{
    size_t i;
    for (i = 0; i < sizeof(name_buffers) / sizeof(name_buffers[0]); i++) {
        if (name_buffers[i].pal == offset) {
            if (us) *us = name_buffers[i].us;
            return 1;
        }
    }
    return 0;
}

/* A code's words as the US text has them. */
static void us_code(const Op *op, char *text, size_t size)
{
    unsigned b[5];
    if (!strcmp(op->text, "f8 1B")) {
        snprintf(text, size, "call L125A");
        return;
    }
    if (!strncmp(op->text, "f8 03 ", 6) &&
        sscanf(op->text + 6, "%x %x %x %x %x", &b[0], &b[1], &b[2], &b[3], &b[4]) == 5) {
        uint32_t address = b[0] | b[1] << 8 | b[2] << 16 | (uint32_t)b[3] << 24;
        if (address >= 0x801BF800u && address < 0x801C0000u) {
            address += NUMBER_DELTA;
            snprintf(text, size, "f8 03 %02X %02X %02X %02X %02X", address & 0xFF, address >> 8 & 0xFF,
                     address >> 16 & 0xFF, address >> 24, b[4]);
            return;
        }
    }
    snprintf(text, size, "%s", op->text);
}

static void write_bank(Out *out, Bank *bank, const char *out_bank, const uint32_t *glyphs, const uint16_t *rename,
                       int *problems)
{
    int offset, inside = 0, previous_end = -1, is_menus = !strcmp(bank->name, "menus"), id, id_count = 0;
    /* The bank's ids in order, to name each string's. */
    static uint16_t ids[0x10000];
    for (id = 0; id < 0x10000; id++) {
        if (bank->ids[id] >= 0) ids[id_count++] = (uint16_t)id;
    }
    addf(out, "\n@bank %s", out_bank);
    LINE(out, "");
    for (offset = 0; offset < BANK_SIZE; offset++) {
        const Op *op = bank->op_at[offset] >= 0 ? &bank->ops[bank->op_at[offset]] : NULL;
        int header = bank->start[offset], marker = bank->target[offset] && !header, i;
        unsigned name = is_menus && rename[offset] ? rename[offset] : (unsigned)offset;
        if (!op && !(header && bank->buffer[offset])) continue;
        if (header || marker || (previous_end >= 0 && offset != previous_end)) {
            if (inside) add(out, "{cont}");
            if (header) {
                int first = 1;
                LINE(out, "[");
                for (i = 0; i < id_count; i++) {
                    if (bank->ids[ids[i]] != offset) continue;
                    addf(out, first ? "%04X" : " %04X", ids[i]);
                    first = 0;
                }
                add(out, "]");
                if (bank->buffer[offset]) {
                    /* a buffer the game writes: keep the US one */
                    LINE(out, "{buffer}");
                    LINE(out, "");
                    inside = 0;
                    previous_end = -1;
                    continue;
                }
                if (bank->target[offset]) addf(out, "  {:L%04X}", name);
            } else {
                addf(out, "\n{:L%04X}", name);
            }
            LINE(out, "");
            inside = 1;
        }
        if (op->kind == OP_GLYPH) {
            uint32_t character = op->value < 0x100 ? glyphs[op->value] : 0;
            if (!character) {
                addf(out, "{g %X}", op->value);
                if (problems) ++*problems;
            } else if (character == ' ' &&
                       (offset + 1 >= BANK_SIZE || bank->op_at[offset + 1] < 0 ||
                        bank->ops[bank->op_at[offset + 1]].kind == OP_NL ||
                        bank->ops[bank->op_at[offset + 1]].kind == OP_END)) {
                add(out, "{sp}");
            } else {
                add_character(out, character);
            }
        } else if (op->kind == OP_NL) {
            int next = offset + 1;
            if (next >= BANK_SIZE || bank->start[next] || bank->target[next] || bank->op_at[next] < 0) add(out, "{nl}");
            else LINE(out, "");
        } else if (op->kind == OP_END) {
            add(out, "{end}");
            LINE(out, "");
            inside = 0;
        } else {
            char text[64];
            int k;
            us_code(op, text, sizeof(text));
            /* F8 1C: the 2P results' command the US text never uses; the
             * US engine reads it as a glyph of the added font (phase 2). */
            if (strncmp(text, "f8 1C", 5)) {
                add(out, "{");
                add(out, text);
                for (k = 0; k < op->target_count; k++) {
                    unsigned target = op->targets[k], us;
                    if (!target) add(out, " 0");
                    else if (bank->buffer[target] && is_menus && is_name_buffer(target, &us)) addf(out, " L%04X", us);
                    else if (bank->buffer[target]) {
                        addf(out, " L%04X", target);
                        if (problems) ++*problems;
                    } else addf(out, " L%04X", is_menus && rename[target] ? rename[target] : target);
                }
                add(out, "}");
            }
            if (!strcmp(op->text, "jump") || !strncmp(op->text, "choose", 6) || !strncmp(op->text, "f8 17", 5) ||
                !strncmp(op->text, "f8 18", 5) || !strcmp(op->text, "f8 28")) {
                LINE(out, "");
                inside = 0;
            }
        }
        previous_end = offset + op->length;
    }
    LINE(out, "");
}

static unsigned u16(const unsigned char *bytes) { return bytes[0] | bytes[1] << 8; }

char *PalText_Listing(const PalTextPack *pack, int language, size_t *length, int *problems)
{
    static const char *const names[PAL_LANGUAGES] = {"EN", "FR", "DE", "IT", "ES"};
    Bank *banks[4];
    const char *out_banks[4] = {"dialog", "dialog", "descriptions", "names"};
    unsigned char *menus_memory = NULL, *dialog_memory = NULL, *names_memory = NULL;
    uint32_t glyphs[0x100];
    uint16_t *rename = NULL;
    Out out = {0};
    int i, index, code;
    if (problems) *problems = 0;
    if (language < 0 || language >= PAL_LANGUAGES) return NULL;
    memset(banks, 0, sizeof(banks));
    for (i = 0; i < 4; i++) {
        banks[i] = calloc(1, sizeof(Bank));
        if (!banks[i]) goto done;
        memset(banks[i]->ids, -1, sizeof(banks[i]->ids));
    }
    menus_memory = malloc(BANK_SIZE);
    dialog_memory = calloc(1, BANK_SIZE);
    names_memory = calloc(1, BANK_SIZE);
    rename = calloc(BANK_SIZE, sizeof(*rename));
    if (!menus_memory || !dialog_memory || !names_memory || !rename) goto done;
    /* Past file A, 0xFF: the Italian last card text runs past its end (in
     * RAM it runs on into what follows); this ends it. */
    memset(menus_memory, 0xFF, BANK_SIZE);
    memcpy(menus_memory, pack->a, PAL_FILE_A_SIZE);
    memcpy(dialog_memory, pack->b, PAL_FILE_B_SIZE);
    memcpy(names_memory + NAMES_BEFORE_C, pack->c, PAL_FILE_C_SIZE);

    /* The glyphs: each language's letters, else the table's Shift-JIS. */
    memset(glyphs, 0, sizeof(glyphs));
    glyphs[0] = ' ';
    for (code = 1; code < 0xF0; code++) {
        unsigned sjis = u16(pack->glyphs + code * 4);
        const Accent *accent;
        if (!sjis) continue;
        glyphs[code] = sjis_character(sjis);
        for (accent = accents[language]; accent && accent->code; accent++) {
            if (accent->code == code) glyphs[code] = accent->character;
        }
    }

    banks[0]->name = "menus", banks[0]->memory = menus_memory;
    banks[1]->name = "dialog", banks[1]->memory = dialog_memory;
    banks[2]->name = "descriptions", banks[2]->memory = menus_memory;
    banks[3]->name = "names", banks[3]->memory = names_memory;
    for (index = 0; index < MENU_IDS; index++) banks[0]->ids[index] = (int)u16(pack->a + FILE_TABLE + index * 2);
    for (i = 0; i < (int)(sizeof(keep_us) / sizeof(keep_us[0])); i++) banks[0]->ids[keep_us[i]] = 0;
    for (index = DIALOG_FIRST; index <= DIALOG_LAST; index++) {
        banks[1]->ids[index + 0x100] = (int)u16(pack->a + FILE_TABLE + index * 2);
    }
    for (index = DESCRIPTION_IDS; index < DIALOG_FIRST; index++) {
        banks[2]->ids[0xD000 + index] = (int)u16(pack->a + FILE_TABLE + index * 2);
    }
    for (index = 0; index < NAME_IDS; index++) banks[3]->ids[0x8000 + index] = (int)u16(pack->c + FILE_TABLE + index * 2);
    /* An offset of 0 is no string. */
    for (i = 0; i < 4; i++) {
        for (index = 0; index < 0x10000; index++) {
            if (banks[i]->ids[index] == 0) banks[i]->ids[index] = -1;
        }
    }
    /* Buffers: offsets past file A's data, and the name buffers. */
    for (i = 0; i < 4; i += 2) {
        for (index = 0; index < 0x10000; index++) {
            if (banks[i]->ids[index] >= (int)PAL_FILE_A_SIZE) banks[i]->buffer[banks[i]->ids[index]] = 1;
        }
    }
    for (i = 0; i < (int)(sizeof(name_buffers) / sizeof(name_buffers[0])); i++) banks[0]->buffer[name_buffers[i].pal] = 1;

    for (i = 0; i < 4; i++) {
        if (!decode_bank(banks[i])) {
            /* The bank is left out; the US text stands. */
            banks[i]->op_count = 0;
            memset(banks[i]->op_at, -1, sizeof(banks[i]->op_at));
            memset(banks[i]->target, 0, sizeof(banks[i]->target));
            if (problems) ++*problems;
        }
    }
    /* The menus' labels, renamed to names the dialogue does not use. */
    {
        unsigned char *used = calloc(1, BANK_SIZE);
        int next = FREE_NAMES;
        if (!used) goto done;
        for (index = 0; index < BANK_SIZE; index++) used[index] = banks[1]->target[index];
        for (index = 0; index < 0x10000; index++) {
            if (banks[1]->ids[index] >= 0) used[banks[1]->ids[index]] = 1;
        }
        for (index = 0; index < BANK_SIZE; index++) {
            if (!banks[0]->target[index]) continue;
            while (next < BANK_SIZE && used[next]) next++;
            if (next < BANK_SIZE) rename[index] = (uint16_t)next++;
        }
        free(used);
    }

    add(&out, "# Yu-Gi-Oh! Forbidden Memories text listing (notes/translation.md).");
    addf(&out, "\n# Extracted from the PAL disc's own text (%s), US string ids.", names[language]);
    LINE(&out, "");
    for (i = 0; i < 4; i++) write_bank(&out, banks[i], out_banks[i], glyphs, rename, problems);
    add(&out, "\n");

done:
    for (i = 0; i < 4; i++) {
        if (banks[i]) free(banks[i]->ops);
        free(banks[i]);
    }
    free(menus_memory);
    free(dialog_memory);
    free(names_memory);
    free(rename);
    if (out.failed || !out.text) {
        free(out.text);
        return NULL;
    }
    if (length) *length = out.length;
    return out.text;
}

int PalText_Advance(uint32_t character, int *shift)
{
    *shift = 0;
    switch (character) {
    case ' ': return -1;
    case '\'': *shift = -3; return -6;
    /* The PAL moves its own letter a pixel left; the US letters are drawn
     * where its ink is (its centre within a quarter pixel), which is the
     * same pixel for f, i and l. The PAL's full stop and comma sit a pixel
     * further right in their cell than the US ones, so these stay put. */
    case 'f': case 'i': case 'l': *shift = -1; return -2;
    case '.': case ',': return -2;
    default: return 0;
    }
}

int PalText_PastWidth(int *width, int step, int cell, int limit)
{
    *width += step;
    return limit * 8 < *width + cell;
}
