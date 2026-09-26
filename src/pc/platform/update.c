/* Versions, release choice, archives and installing (update.h). No window,
 * no network and no game state: the unit tests (tests/pc/update_test.c)
 * link this file alone with the JSON reader and zlib. */
#define _POSIX_C_SOURCE 200809L
#include "update.h"
#include "paths.h"
#include "pc/mods/json.h"
#include <ctype.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <zlib.h>
#include "pc/compat/posix.h"
#ifndef _WIN32
#include <dirent.h>
#endif

#define PATH_SIZE 1024
#define OLD_SUFFIX ".update-old"
#define NEW_SUFFIX ".update-new"

static void say(char *why, size_t size, const char *format, const char *detail)
{
    if (why && size) snprintf(why, size, format, detail ? detail : "");
}

/* --- versions -------------------------------------------------------- */

static int read_number(const char **text, long *out)
{
    const char *at = *text;
    long value = 0;
    if (!isdigit((unsigned char)*at)) return 0;
    if (*at == '0' && isdigit((unsigned char)at[1])) return 0; /* no leading zeros */
    while (isdigit((unsigned char)*at)) {
        if (value > 100000000L) return 0;
        value = value * 10 + (*at++ - '0');
    }
    *out = value;
    *text = at;
    return 1;
}

int Update_ParseVersion(const char *text, UpdateVersion *out)
{
    UpdateVersion version;
    const char *at = text;
    size_t length;
    if (!text) return 0;
    memset(&version, 0, sizeof(version));
    if (*at == 'v' || *at == 'V') at++;
    if (!read_number(&at, &version.major) || *at++ != '.' || !read_number(&at, &version.minor) ||
        *at++ != '.' || !read_number(&at, &version.patch))
        return 0;
    if (*at == '-') {
        at++;
        length = strlen(at);
        if (!length || length >= sizeof(version.pre)) return 0;
        for (size_t i = 0; i < length; i++) {
            char c = at[i];
            if (!isalnum((unsigned char)c) && c != '.' && c != '-') return 0;
            if (c == '.' && (i == 0 || at[i - 1] == '.' || i + 1 == length)) return 0;
        }
        memcpy(version.pre, at, length + 1);
    } else if (*at == '+') {
        /* Build metadata does not take part in the order. */
    } else if (*at) {
        return 0;
    }
    if (out) *out = version;
    return 1;
}

static int all_digits(const char *text, size_t length)
{
    for (size_t i = 0; i < length; i++)
        if (!isdigit((unsigned char)text[i])) return 0;
    return length > 0;
}

static int compare_pre(const char *a, const char *b)
{
    if (!*a || !*b) return !*a && !*b ? 0 : !*a ? 1 : -1; /* the release after its pre-releases */
    for (;;) {
        size_t la = strcspn(a, "."), lb = strcspn(b, ".");
        int na = all_digits(a, la), nb = all_digits(b, lb), order;
        if (na && nb) {
            order = la != lb ? (la < lb ? -1 : 1) : strncmp(a, b, la);
        } else if (na != nb) {
            order = na ? -1 : 1;
        } else {
            size_t shorter = la < lb ? la : lb;
            order = strncmp(a, b, shorter);
            if (!order && la != lb) order = la < lb ? -1 : 1;
        }
        if (order) return order < 0 ? -1 : 1;
        a += la;
        b += lb;
        if (!*a || !*b) return !*a && !*b ? 0 : !*a ? -1 : 1; /* fewer parts sort first */
        a++;
        b++;
    }
}

int Update_CompareVersions(const UpdateVersion *a, const UpdateVersion *b)
{
    if (a->major != b->major) return a->major < b->major ? -1 : 1;
    if (a->minor != b->minor) return a->minor < b->minor ? -1 : 1;
    if (a->patch != b->patch) return a->patch < b->patch ? -1 : 1;
    return compare_pre(a->pre, b->pre);
}

/* --- choosing a release ---------------------------------------------- */

static int ends_with(const char *text, const char *suffix)
{
    size_t lt = strlen(text), ls = strlen(suffix);
    return lt >= ls && !strcmp(text + lt - ls, suffix);
}

int Update_PickRelease(const char *json, const char *current, int prereleases, const char *skip,
                       const char *asset_suffix, UpdateRelease *out)
{
    char error[128];
    JsonDocument *document = json ? Json_Parse(json, error, sizeof(error)) : NULL;
    const JsonValue *root = document ? Json_Root(document) : NULL, *item, *best = NULL;
    UpdateVersion now, newest = {0}, skipped = {0};
    int have_skip = skip && *skip && Update_ParseVersion(skip, &skipped);
    if (!root || Json_TypeOf(root) != JSON_ARRAY || !Update_ParseVersion(current, &now)) {
        Json_Free(document);
        return -1;
    }
    for (item = Json_At(root, 0); item; item = Json_Next(item)) {
        const char *tag = Json_String(Json_Member(item, "tag_name"), NULL);
        UpdateVersion version;
        int pre;
        if (Json_TypeOf(item) != JSON_OBJECT || !tag || !Update_ParseVersion(tag, &version)) continue;
        if (Json_Bool(Json_Member(item, "draft"), 0)) continue;
        pre = Json_Bool(Json_Member(item, "prerelease"), 0) || version.pre[0];
        if (pre && !prereleases) continue;
        if (Update_CompareVersions(&version, &now) <= 0) continue;
        if (have_skip && !Update_CompareVersions(&version, &skipped)) continue;
        if (best && Update_CompareVersions(&version, &newest) <= 0) continue;
        best = item;
        newest = version;
    }
    if (best && out) {
        const JsonValue *assets = Json_Member(best, "assets"), *asset;
        const char *title = Json_String(Json_Member(best, "name"), NULL);
        memset(out, 0, sizeof(*out));
        snprintf(out->tag, sizeof(out->tag), "%s", Json_String(Json_Member(best, "tag_name"), ""));
        snprintf(out->title, sizeof(out->title), "%s", title && *title ? title : out->tag);
        snprintf(out->page, sizeof(out->page), "%s", Json_String(Json_Member(best, "html_url"), ""));
        out->prerelease = Json_Bool(Json_Member(best, "prerelease"), 0) || newest.pre[0];
        for (asset = Json_At(assets, 0); asset && asset_suffix; asset = Json_Next(asset)) {
            const char *name = Json_String(Json_Member(asset, "name"), "");
            const char *url = Json_String(Json_Member(asset, "browser_download_url"), "");
            if (!ends_with(name, asset_suffix) || !*url || strlen(url) >= sizeof(out->asset_url)) continue;
            snprintf(out->asset_name, sizeof(out->asset_name), "%s", name);
            snprintf(out->asset_url, sizeof(out->asset_url), "%s", url);
            out->asset_size = Json_Number(Json_Member(asset, "size"), 0);
            snprintf(out->digest, sizeof(out->digest), "%s", Json_String(Json_Member(asset, "digest"), ""));
            break;
        }
    }
    Json_Free(document);
    return best ? 1 : 0;
}

/* --- SHA-256 (FIPS 180-4) -------------------------------------------- */

typedef struct { uint32_t state[8]; uint64_t length; unsigned char block[64]; size_t used; } Sha256;

static uint32_t rotate(uint32_t x, int n) { return x >> n | x << (32 - n); }

static void sha256_block(Sha256 *sha, const unsigned char *data)
{
    static const uint32_t k[64] = {
        0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
        0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
        0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
        0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
        0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
        0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
        0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
        0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2};
    uint32_t w[64], s[8];
    int i;
    for (i = 0; i < 16; i++)
        w[i] = (uint32_t)data[i * 4] << 24 | (uint32_t)data[i * 4 + 1] << 16 | (uint32_t)data[i * 4 + 2] << 8 | data[i * 4 + 3];
    for (; i < 64; i++) {
        uint32_t s0 = rotate(w[i - 15], 7) ^ rotate(w[i - 15], 18) ^ (w[i - 15] >> 3);
        uint32_t s1 = rotate(w[i - 2], 17) ^ rotate(w[i - 2], 19) ^ (w[i - 2] >> 10);
        w[i] = w[i - 16] + s0 + w[i - 7] + s1;
    }
    memcpy(s, sha->state, sizeof(s));
    for (i = 0; i < 64; i++) {
        uint32_t t1 = s[7] + (rotate(s[4], 6) ^ rotate(s[4], 11) ^ rotate(s[4], 25)) + ((s[4] & s[5]) ^ (~s[4] & s[6])) + k[i] + w[i];
        uint32_t t2 = (rotate(s[0], 2) ^ rotate(s[0], 13) ^ rotate(s[0], 22)) + ((s[0] & s[1]) ^ (s[0] & s[2]) ^ (s[1] & s[2]));
        memmove(s + 1, s, 7 * sizeof(s[0]));
        s[4] += t1;
        s[0] = t1 + t2;
    }
    for (i = 0; i < 8; i++) sha->state[i] += s[i];
}

static void sha256_init(Sha256 *sha)
{
    static const uint32_t start[8] = {0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
                                      0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19};
    memset(sha, 0, sizeof(*sha));
    memcpy(sha->state, start, sizeof(start));
}

static void sha256_add(Sha256 *sha, const unsigned char *data, size_t size)
{
    sha->length += size;
    while (size) {
        size_t take = 64 - sha->used < size ? 64 - sha->used : size;
        memcpy(sha->block + sha->used, data, take);
        sha->used += take;
        data += take;
        size -= take;
        if (sha->used == 64) {
            sha256_block(sha, sha->block);
            sha->used = 0;
        }
    }
}

static void sha256_hex(Sha256 *sha, char hex[65])
{
    uint64_t bits = sha->length * 8;
    unsigned char pad = 0x80, zero = 0, size[8];
    int i;
    for (i = 0; i < 8; i++) size[i] = (unsigned char)(bits >> (56 - i * 8));
    sha256_add(sha, &pad, 1);
    while (sha->used != 56) sha256_add(sha, &zero, 1);
    sha256_add(sha, size, 8);
    for (i = 0; i < 32; i++) sprintf(hex + i * 2, "%02x", (unsigned)(sha->state[i / 4] >> (24 - (i % 4) * 8) & 0xff));
    hex[64] = '\0';
}

int Update_Sha256File(const char *path, char hex[65])
{
    unsigned char buffer[65536];
    FILE *file = fopen(path, "rb");
    Sha256 sha;
    size_t got;
    int failed;
    if (!file) return -1;
    sha256_init(&sha);
    while ((got = fread(buffer, 1, sizeof(buffer), file)) > 0) sha256_add(&sha, buffer, got);
    failed = ferror(file);
    fclose(file);
    if (failed) return -1;
    sha256_hex(&sha, hex);
    return 0;
}

/* --- archives -------------------------------------------------------- */

/* Where an entry goes: `directory`/`name`, once `name` is known to stay
 * inside. A trailing slash (a folder entry) is dropped first. */
static int entry_path(const char *directory, const char *name, char *out, size_t size, int *is_folder)
{
    char relative[PATH_SIZE];
    size_t length = strlen(name);
    *is_folder = 0;
    if (length >= sizeof(relative)) return -1;
    memcpy(relative, name, length + 1);
    while (length && relative[length - 1] == '/') {
        relative[--length] = '\0';
        *is_folder = 1;
    }
    if (!Paths_Contained(relative)) return -1;
    if ((size_t)snprintf(out, size, "%s/%s", directory, relative) >= size) return -1;
    return 0;
}

static int make_parent(const char *path)
{
    char parent[PATH_SIZE];
    char *slash;
    snprintf(parent, sizeof(parent), "%s", path);
    slash = strrchr(parent, '/');
    if (!slash) return 0;
    *slash = '\0';
    return Paths_MakeDirs(parent);
}

static void set_executable(const char *path, int executable)
{
#ifndef _WIN32
    chmod(path, executable ? 0755 : 0644);
#else
    (void)path;
    (void)executable;
#endif
}

static unsigned read16(const unsigned char *at) { return (unsigned)at[0] | (unsigned)at[1] << 8; }
static uint32_t read32(const unsigned char *at)
{
    return (uint32_t)at[0] | (uint32_t)at[1] << 8 | (uint32_t)at[2] << 16 | (uint32_t)at[3] << 24;
}

/* One zip entry from `offset` (its local header) into `path`. */
static int zip_entry(FILE *zip, long offset, unsigned method, uint32_t packed, uint32_t size, uint32_t crc,
                     const char *path)
{
    unsigned char header[30], in[65536], out[65536];
    FILE *file;
    z_stream stream;
    uint32_t left = packed, sum = (uint32_t)crc32(0, Z_NULL, 0), written = 0;
    int result = 0, status = Z_OK;
    if (method != 0 && method != 8) return -1;
    if (fseek(zip, offset, SEEK_SET) || fread(header, 1, 30, zip) != 30 || read32(header) != 0x04034b50) return -1;
    if (fseek(zip, offset + 30 + (long)read16(header + 26) + (long)read16(header + 28), SEEK_SET)) return -1;
    if (!(file = fopen(path, "wb"))) return -1;
    memset(&stream, 0, sizeof(stream));
    if (method == 8 && inflateInit2(&stream, -MAX_WBITS) != Z_OK) { fclose(file); return -1; }
    while (!result && (left || (method == 8 && status != Z_STREAM_END))) {
        size_t want = left < sizeof(in) ? left : sizeof(in), got = want ? fread(in, 1, want, zip) : 0;
        if (want && got != want) { result = -1; break; }
        left -= (uint32_t)got;
        if (method == 0) {
            sum = (uint32_t)crc32(sum, in, (uInt)got);
            written += (uint32_t)got;
            if (fwrite(in, 1, got, file) != got) result = -1;
            continue;
        }
        stream.next_in = in;
        stream.avail_in = (uInt)got;
        do {
            size_t have;
            stream.next_out = out;
            stream.avail_out = sizeof(out);
            status = inflate(&stream, Z_NO_FLUSH);
            if (status != Z_OK && status != Z_STREAM_END && !(status == Z_BUF_ERROR && !got)) { result = -1; break; }
            have = sizeof(out) - stream.avail_out;
            sum = (uint32_t)crc32(sum, out, (uInt)have);
            written += (uint32_t)have;
            if (fwrite(out, 1, have, file) != have) { result = -1; break; }
        } while (stream.avail_out == 0 && status != Z_STREAM_END);
        if (!got && status != Z_STREAM_END) result = -1; /* ran out of input */
    }
    if (method == 8) inflateEnd(&stream);
    if (fclose(file)) result = -1;
    if (!result && (sum != crc || written != size)) result = -1;
    return result;
}

static int extract_zip(const char *archive, const char *directory, char *why, size_t why_size)
{
    FILE *zip = fopen(archive, "rb");
    unsigned char tail[65557], *end = NULL, entry[46];
    long length, start, at;
    size_t got;
    unsigned count, i;
    if (!zip) { say(why, why_size, "Could not open the downloaded archive.%s", NULL); return -1; }
    fseek(zip, 0, SEEK_END);
    length = ftell(zip);
    start = length > (long)sizeof(tail) ? length - (long)sizeof(tail) : 0;
    fseek(zip, start, SEEK_SET);
    got = fread(tail, 1, sizeof(tail), zip);
    for (long back = (long)got - 22; back >= 0 && !end; back--)
        if (read32(tail + back) == 0x06054b50) end = tail + back;
    if (!end) { fclose(zip); say(why, why_size, "The downloaded archive is not a complete zip file.%s", NULL); return -1; }
    count = read16(end + 10);
    at = (long)read32(end + 16);
    for (i = 0; i < count; i++) {
        char name[PATH_SIZE], path[PATH_SIZE];
        unsigned name_length, extra, comment;
        int folder;
        long next;
        if (fseek(zip, at, SEEK_SET) || fread(entry, 1, 46, zip) != 46 || read32(entry) != 0x02014b50) break;
        name_length = read16(entry + 28);
        extra = read16(entry + 30);
        comment = read16(entry + 32);
        next = at + 46 + (long)name_length + (long)extra + (long)comment;
        if (name_length >= sizeof(name) || fread(name, 1, name_length, zip) != name_length) break;
        name[name_length] = '\0';
        if (read16(entry + 8) & 1) break; /* encrypted */
        if (entry_path(directory, name, path, sizeof(path), &folder)) {
            fclose(zip);
            say(why, why_size, "The archive names a file outside its folder: %s", name);
            return -1;
        }
        if (folder) {
            if (Paths_MakeDirs(path)) break;
        } else if (make_parent(path) ||
                   zip_entry(zip, (long)read32(entry + 42), read16(entry + 10), read32(entry + 20),
                             read32(entry + 24), read32(entry + 16), path)) {
            fclose(zip);
            say(why, why_size, "Could not unpack %s from the downloaded archive.", name);
            return -1;
        }
        at = next;
    }
    fclose(zip);
    if (i != count) { say(why, why_size, "The downloaded archive is damaged.%s", NULL); return -1; }
    return 0;
}

static long octal(const char *field, size_t size)
{
    long value = 0;
    size_t i = 0;
    while (i < size && (field[i] == ' ' || field[i] == '\0')) i++;
    for (; i < size && field[i] >= '0' && field[i] <= '7'; i++) value = value * 8 + (field[i] - '0');
    return value;
}

/* A pax extended header's "path" record, if it has one. */
static void pax_path(const char *records, size_t size, char *path, size_t path_size)
{
    size_t at = 0;
    while (at < size) {
        char *end;
        long length = strtol(records + at, &end, 10);
        const char *key;
        if (length <= 0 || at + (size_t)length > size || *end != ' ') return;
        key = end + 1;
        if (!strncmp(key, "path=", 5)) {
            size_t value = (size_t)(records + at + length - 1 - (key + 5)); /* without the newline */
            if (value < path_size) {
                memcpy(path, key + 5, value);
                path[value] = '\0';
            }
        }
        at += (size_t)length;
    }
}

/* A .tar.gz read in order. zlib's gzread is not used: some versions give
 * no error for a stream cut off before gzip's CRC-32 and length, which is
 * what an interrupted download looks like. */
typedef struct {
    FILE *file;
    z_stream stream;
    unsigned char in[65536];
    int ended;
} Gz;

static int gz_open(Gz *gz, const char *path)
{
    memset(gz, 0, sizeof(*gz));
    if (!(gz->file = fopen(path, "rb"))) return -1;
    if (inflateInit2(&gz->stream, 15 + 16) != Z_OK) { fclose(gz->file); return -1; }
    return 0;
}

static void gz_close(Gz *gz)
{
    inflateEnd(&gz->stream);
    fclose(gz->file);
}

/* Exactly `size` bytes, or -1; NULL `buffer` skips them. */
static int gz_read(Gz *gz, void *buffer, size_t size)
{
    unsigned char scratch[4096];
    while (size) {
        size_t take = buffer ? size : size < sizeof(scratch) ? size : sizeof(scratch);
        int status;
        if (gz->ended) return -1;
        gz->stream.next_out = buffer ? buffer : scratch;
        gz->stream.avail_out = (uInt)take;
        while (gz->stream.avail_out && !gz->ended) {
            if (!gz->stream.avail_in) {
                size_t got = fread(gz->in, 1, sizeof(gz->in), gz->file);
                if (!got) return -1; /* cut off */
                gz->stream.next_in = gz->in;
                gz->stream.avail_in = (uInt)got;
            }
            status = inflate(&gz->stream, Z_NO_FLUSH);
            if (status == Z_STREAM_END) gz->ended = 1;
            else if (status != Z_OK && !(status == Z_BUF_ERROR && !gz->stream.avail_in)) return -1;
        }
        if (gz->stream.avail_out) return -1;
        if (buffer) buffer = (unsigned char *)buffer + take;
        size -= take;
    }
    return 0;
}

/* Read to the end of the gzip stream, which checks its CRC-32 and length. */
static int gz_finish(Gz *gz)
{
    unsigned char scratch[4096];
    while (!gz->ended) {
        int status;
        gz->stream.next_out = scratch;
        gz->stream.avail_out = sizeof(scratch);
        if (!gz->stream.avail_in) {
            size_t got = fread(gz->in, 1, sizeof(gz->in), gz->file);
            if (!got) return -1;
            gz->stream.next_in = gz->in;
            gz->stream.avail_in = (uInt)got;
        }
        status = inflate(&gz->stream, Z_NO_FLUSH);
        if (status == Z_STREAM_END) gz->ended = 1;
        else if (status != Z_OK && !(status == Z_BUF_ERROR && !gz->stream.avail_in)) return -1;
    }
    return 0;
}

static int extract_tar_gz(const char *archive, const char *directory, char *why, size_t why_size)
{
    Gz *gz = malloc(sizeof(Gz));
    char header[512], long_name[PATH_SIZE] = "";
    int result = -1;
    if (!gz || gz_open(gz, archive)) {
        free(gz);
        say(why, why_size, "Could not open the downloaded archive.%s", NULL);
        return -1;
    }
    for (;;) {
        char name[PATH_SIZE], path[PATH_SIZE];
        long size, mode;
        char type;
        int folder, blank = 1;
        if (gz_read(gz, header, sizeof(header))) break;
        for (int i = 0; i < 512 && blank; i++) blank = !header[i];
        if (blank) { result = 0; break; } /* the end-of-archive blocks */
        size = octal(header + 124, 12);
        mode = octal(header + 100, 8);
        type = header[156];
        if (size < 0 || size > 0x7fffffffL) break;
        if (type == 'x' || type == 'L') {
            char *records = malloc((size_t)size + 1);
            long padded = (size + 511) & ~511L;
            if (!records || padded > 16 * 1024 * 1024) { free(records); break; }
            if (gz_read(gz, records, (size_t)size) || gz_read(gz, NULL, (size_t)(padded - size))) {
                free(records);
                break;
            }
            records[size] = '\0';
            if (type == 'x') pax_path(records, (size_t)size, long_name, sizeof(long_name));
            else snprintf(long_name, sizeof(long_name), "%s", records);
            free(records);
            continue;
        }
        if (type == 'g') { /* global pax header: nothing needed from it */
            if (gz_read(gz, NULL, (size_t)((size + 511) & ~511L))) break;
            continue;
        }
        if (long_name[0]) {
            snprintf(name, sizeof(name), "%s", long_name);
            long_name[0] = '\0';
        } else if (!memcmp(header + 257, "ustar", 5) && header[345]) {
            snprintf(name, sizeof(name), "%.155s/%.100s", header + 345, header);
        } else {
            snprintf(name, sizeof(name), "%.100s", header);
        }
        if (type != '0' && type != '\0' && type != '5') {
            say(why, why_size, "The archive holds something other than files and folders: %s", name);
            gz_close(gz);
            free(gz);
            return -1;
        }
        if (entry_path(directory, name, path, sizeof(path), &folder)) {
            say(why, why_size, "The archive names a file outside its folder: %s", name);
            gz_close(gz);
            free(gz);
            return -1;
        }
        if (type == '5' || folder) {
            if (Paths_MakeDirs(path)) break;
            continue;
        }
        {
            FILE *file;
            char buffer[65536];
            long left = size;
            if (make_parent(path) || !(file = fopen(path, "wb"))) break;
            while (left > 0) {
                size_t take = left < (long)sizeof(buffer) ? (size_t)left : sizeof(buffer);
                if (gz_read(gz, buffer, take) || fwrite(buffer, 1, take, file) != take) { left = -1; break; }
                left -= (long)take;
            }
            if (fclose(file)) left = -1;
            if (left < 0) break;
            set_executable(path, (mode & 0111) != 0);
            if (size % 512 && gz_read(gz, NULL, (size_t)(512 - size % 512))) break;
        }
    }
    /* gzip checks its CRC-32 and length at the end of the stream: read on
     * to there so a damaged or cut-off download cannot pass. */
    if (!result && gz_finish(gz)) result = -1;
    gz_close(gz);
    free(gz);
    if (result) say(why, why_size, "The downloaded archive is damaged.%s", NULL);
    return result;
}

int Update_Extract(const char *archive, const char *directory, char *why, size_t why_size)
{
    if (Paths_MakeDirs(directory)) {
        say(why, why_size, "Could not create %s.", directory);
        return -1;
    }
    if (ends_with(archive, ".zip")) return extract_zip(archive, directory, why, why_size);
    if (ends_with(archive, ".tar.gz") || ends_with(archive, ".tgz")) return extract_tar_gz(archive, directory, why, why_size);
    say(why, why_size, "Unknown archive type: %s", archive);
    return -1;
}

/* --- installing ------------------------------------------------------ */

static int is_folder(const char *path)
{
    struct stat info;
    return !stat(path, &info) && S_ISDIR(info.st_mode);
}

static int exists(const char *path)
{
    struct stat info;
    return !stat(path, &info);
}

int Update_StagedRoot(const char *directory, char *out, size_t size)
{
    DIR *dir = opendir(directory);
    struct dirent *entry;
    int found = 0;
    if (!dir) return -1;
    while ((entry = readdir(dir))) {
        char path[PATH_SIZE];
        if (entry->d_name[0] == '.') continue;
        if ((size_t)snprintf(path, sizeof(path), "%s/%s", directory, entry->d_name) >= sizeof(path)) continue;
        if (!is_folder(path)) { found = 2; break; }
        if (found++) break;
        snprintf(out, size, "%s", path);
    }
    closedir(dir);
    return found == 1 ? 0 : -1;
}

int Update_IsPackagedInstall(const char *program, const char *executable)
{
    static const char *const marks[] = {"buildid", "LICENSE"};
    char path[PATH_SIZE];
    snprintf(path, sizeof(path), "%s/%s", program, executable);
    if (!exists(path)) return 0;
    for (size_t i = 0; i < sizeof(marks) / sizeof(marks[0]); i++) {
        snprintf(path, sizeof(path), "%s/%s", program, marks[i]);
        if (!exists(path)) return 0;
    }
    return 1;
}

typedef struct { char **items; int count, capacity; } List;

static int list_add(List *list, const char *text)
{
    if (list->count == list->capacity) {
        int capacity = list->capacity ? list->capacity * 2 : 64;
        char **grown = realloc(list->items, (size_t)capacity * sizeof(*grown));
        if (!grown) return -1;
        list->items = grown;
        list->capacity = capacity;
    }
    if (!(list->items[list->count] = malloc(strlen(text) + 1))) return -1;
    strcpy(list->items[list->count++], text);
    return 0;
}

static void list_free(List *list)
{
    for (int i = 0; i < list->count; i++) free(list->items[i]);
    free(list->items);
    memset(list, 0, sizeof(*list));
}

/* Every file under `root`/`relative`, as paths relative to `root`. */
static int collect(const char *root, const char *relative, List *files)
{
    char path[PATH_SIZE];
    DIR *dir;
    struct dirent *entry;
    int result = 0;
    snprintf(path, sizeof(path), "%s%s%s", root, *relative ? "/" : "", relative);
    if (!(dir = opendir(path))) return -1;
    while (!result && (entry = readdir(dir))) {
        char child[PATH_SIZE], full[PATH_SIZE];
        if (!strcmp(entry->d_name, ".") || !strcmp(entry->d_name, "..")) continue;
        if ((size_t)snprintf(child, sizeof(child), "%s%s%s", relative, *relative ? "/" : "", entry->d_name) >= sizeof(child) ||
            (size_t)snprintf(full, sizeof(full), "%s/%s", root, child) >= sizeof(full)) {
            result = -1;
            break;
        }
        if (!*relative && !strcmp(entry->d_name, "game")) continue; /* the player's disc image */
        if (is_folder(full)) result = collect(root, child, files);
        else result = list_add(files, child);
    }
    closedir(dir);
    return result;
}

static int copy_file(const char *from, const char *to)
{
    char buffer[65536];
    FILE *in = fopen(from, "rb"), *out;
    size_t got;
    int failed = 0;
    struct stat info;
    if (!in) return -1;
    if (!(out = fopen(to, "wb"))) { fclose(in); return -1; }
    while ((got = fread(buffer, 1, sizeof(buffer), in)) > 0)
        if (fwrite(buffer, 1, got, out) != got) { failed = 1; break; }
    if (ferror(in)) failed = 1;
    fclose(in);
    if (fflush(out) || fsync(fileno(out))) failed = 1;
    if (fclose(out)) failed = 1;
    if (!failed && !stat(from, &info)) set_executable(to, (info.st_mode & 0111) != 0);
    if (failed) remove(to);
    return failed ? -1 : 0;
}

int Update_CanWrite(const char *program)
{
    char probe[PATH_SIZE];
    FILE *file;
    if ((size_t)snprintf(probe, sizeof(probe), "%s/.update-probe", program) >= sizeof(probe)) return 0;
    if (!(file = fopen(probe, "wb"))) return 0;
    fclose(file);
    remove(probe);
    return 1;
}

int Update_Install(const char *staged, const char *program, const char *cleanup_list, char *why, size_t why_size)
{
    List files = {0};
    int *moved = NULL, copied = 0, done = 0, failed = 0, i;

    /* Can this folder be written at all? (Program Files, a read-only mount.) */
    if (!Update_CanWrite(program)) {
        say(why, why_size, "The game's folder cannot be written to: %s", program);
        return -1;
    }
    if (collect(staged, "", &files) || !files.count || !(moved = calloc((size_t)files.count, sizeof(*moved)))) {
        list_free(&files);
        say(why, why_size, "Could not read the unpacked update.%s", NULL);
        return -1;
    }
    for (i = 0; i < files.count; i++) {
        size_t length = strlen(files.items[i]) + 1 + strlen(OLD_SUFFIX);
        if (strlen(program) + length >= PATH_SIZE || strlen(staged) + length >= PATH_SIZE) {
            say(why, why_size, "A path in the update is too long: %s", files.items[i]);
            free(moved);
            list_free(&files);
            return -1;
        }
    }
    /* 1: every new file beside its target, as <name>.update-new. */
    for (copied = 0; copied < files.count; copied++) {
        char from[PATH_SIZE], to[PATH_SIZE];
        snprintf(from, sizeof(from), "%s/%s", staged, files.items[copied]);
        snprintf(to, sizeof(to), "%s/%s" NEW_SUFFIX, program, files.items[copied]);
        if (make_parent(to) || copy_file(from, to)) {
            say(why, why_size, "Could not write %s.", to);
            failed = 1;
            break;
        }
    }
    /* 2: each old file aside, the new one in. */
    for (done = 0; !failed && done < files.count; done++) {
        char target[PATH_SIZE], old[PATH_SIZE + 16], fresh[PATH_SIZE + 16];
        snprintf(target, sizeof(target), "%s/%s", program, files.items[done]);
        snprintf(old, sizeof(old), "%s" OLD_SUFFIX, target);
        snprintf(fresh, sizeof(fresh), "%s" NEW_SUFFIX, target);
        remove(old);
        if (exists(target)) {
            if (rename(target, old)) {
                say(why, why_size, "Could not replace %s (is it open in another program?)", target);
                failed = 1;
                break;
            }
            moved[done] = 1;
        }
        if (rename(fresh, target)) {
            if (moved[done]) rename(old, target);
            say(why, why_size, "Could not replace %s.", target);
            failed = 1;
            break;
        }
    }
    if (failed) {
        /* Put back what step 2 had changed, and clear away the copies. */
        for (i = 0; i < done; i++) {
            char target[PATH_SIZE], old[PATH_SIZE + 16];
            snprintf(target, sizeof(target), "%s/%s", program, files.items[i]);
            snprintf(old, sizeof(old), "%s" OLD_SUFFIX, target);
            if (moved[i]) rename(old, target);
            else remove(target);
        }
        for (i = 0; i < files.count; i++) {
            char fresh[PATH_SIZE];
            snprintf(fresh, sizeof(fresh), "%s/%s" NEW_SUFFIX, program, files.items[i]);
            remove(fresh);
        }
    } else {
        /* The old files go now if they can; the running executable (on
         * Windows) and anything else still open waits for the next start. */
        FILE *list = NULL;
        for (i = 0; i < files.count; i++) {
            char old[PATH_SIZE];
            if (!moved[i]) continue;
            snprintf(old, sizeof(old), "%s/%s" OLD_SUFFIX, program, files.items[i]);
            if (!remove(old) || !cleanup_list) continue;
            if (!list && make_parent(cleanup_list) == 0) list = fopen(cleanup_list, "a");
            if (list) fprintf(list, "%s\n", old);
        }
        if (list) fclose(list);
    }
    free(moved);
    list_free(&files);
    return failed ? -1 : 0;
}

void Update_Cleanup(const char *cleanup_list)
{
    FILE *file = fopen(cleanup_list, "r");
    List left = {0};
    char line[PATH_SIZE];
    if (!file) return;
    while (fgets(line, sizeof(line), file)) {
        line[strcspn(line, "\r\n")] = '\0';
        if (!*line || !ends_with(line, OLD_SUFFIX)) continue; /* never anything else */
        if (remove(line) && errno != ENOENT && exists(line)) list_add(&left, line);
    }
    fclose(file);
    if (!left.count) {
        remove(cleanup_list);
    } else if ((file = fopen(cleanup_list, "w"))) {
        for (int i = 0; i < left.count; i++) fprintf(file, "%s\n", left.items[i]);
        fclose(file);
    }
    list_free(&left);
}

void Update_RemoveTree(const char *path)
{
    DIR *dir;
    struct dirent *entry;
    if (!is_folder(path)) { remove(path); return; }
    if ((dir = opendir(path))) {
        while ((entry = readdir(dir))) {
            char child[PATH_SIZE];
            if (!strcmp(entry->d_name, ".") || !strcmp(entry->d_name, "..")) continue;
            if ((size_t)snprintf(child, sizeof(child), "%s/%s", path, entry->d_name) < sizeof(child))
                Update_RemoveTree(child);
        }
        closedir(dir);
    }
    rmdir(path);
}
