/* The updater's parts without a window or a network (src/pc/platform/update.h):
 * version order, choosing a release from GitHub's answer, SHA-256, both
 * archive kinds, and installing over a program folder. */
#define _POSIX_C_SOURCE 200809L
#include "pc/platform/update.h"
#include "pc/platform/paths.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <zlib.h>
#include "pc/compat/posix.h"
#include "scratch.h"

static char root[SCRATCH_MAX];

static void path_of(char *out, size_t size, const char *relative)
{
    snprintf(out, size, "%s/%s", root, relative);
}

static void write_text(const char *relative, const char *text)
{
    char path[1024], parent[1024], *slash;
    FILE *file;
    path_of(path, sizeof(path), relative);
    snprintf(parent, sizeof(parent), "%s", path);
    slash = strrchr(parent, '/');
    *slash = '\0';
    assert(!Paths_MakeDirs(parent));
    file = fopen(path, "wb");
    assert(file);
    fputs(text, file);
    assert(!fclose(file));
}

static int has_text(const char *relative, const char *text)
{
    char path[1024], got[4096];
    FILE *file;
    size_t length;
    path_of(path, sizeof(path), relative);
    if (!(file = fopen(path, "rb"))) return 0;
    length = fread(got, 1, sizeof(got) - 1, file);
    got[length] = '\0';
    fclose(file);
    return !strcmp(got, text);
}

static int present(const char *relative)
{
    char path[1024];
    struct stat info;
    path_of(path, sizeof(path), relative);
    return !stat(path, &info);
}

static int order(const char *a, const char *b)
{
    UpdateVersion va, vb;
    assert(Update_ParseVersion(a, &va));
    assert(Update_ParseVersion(b, &vb));
    return Update_CompareVersions(&va, &vb);
}

static void versions(void)
{
    static const char *const ascending[] = {
        "v0.0.9", "v0.1.0", "v0.1.1", "v0.2.0-alpha", "v0.2.0-alpha.1", "v0.2.0-alpha.beta", "v0.2.0-beta",
        "v0.2.0-beta.2", "v0.2.0-beta.11", "v0.2.0-preview.1", "v0.2.0-preview.2", "v0.2.0-preview.10",
        "v0.2.0-rc.1", "v0.2.0", "v0.10.0", "v1.0.0"};
    size_t i, j, count = sizeof(ascending) / sizeof(ascending[0]);
    UpdateVersion version;
    for (i = 0; i < count; i++)
        for (j = 0; j < count; j++) {
            int want = i < j ? -1 : i > j ? 1 : 0;
            assert(order(ascending[i], ascending[j]) == want);
        }
    assert(Update_ParseVersion("0.1.0", &version) && version.major == 0 && version.minor == 1);
    assert(Update_ParseVersion("v1.2.3+build.5", &version) && version.patch == 3 && !version.pre[0]);
    assert(!order("v1.2.3+a", "v1.2.3"));
    assert(Update_ParseVersion("v0.2.0-preview.1", &version) && !strcmp(version.pre, "preview.1"));
    assert(!Update_ParseVersion("", NULL));
    assert(!Update_ParseVersion("v1.2", NULL));
    assert(!Update_ParseVersion("v1.2.3.4", NULL));
    assert(!Update_ParseVersion("v01.2.3", NULL));
    assert(!Update_ParseVersion("v1.2.3-", NULL));
    assert(!Update_ParseVersion("v1.2.3-a..b", NULL));
    assert(!Update_ParseVersion("dev-0123456789ab", NULL));
    assert(!Update_ParseVersion("20260926-abcdef0", NULL));
    assert(!Update_ParseVersion(NULL, NULL));
}

static const char releases[] =
    "[{\"tag_name\":\"v0.3.0\",\"draft\":true,\"prerelease\":false,\"assets\":[]},"
    " {\"tag_name\":\"v0.2.0-rc.1\",\"name\":\"Second release candidate\",\"draft\":false,\"prerelease\":false,"
    "  \"html_url\":\"https://example.invalid/rc1\",\"assets\":[]},"
    " {\"tag_name\":\"v0.2.0-preview.1\",\"name\":\"Preview\",\"draft\":false,\"prerelease\":true,"
    "  \"html_url\":\"https://example.invalid/p1\",\"assets\":[]},"
    " {\"tag_name\":\"v0.1.1\",\"name\":\"\",\"draft\":false,\"prerelease\":false,"
    "  \"html_url\":\"https://example.invalid/v0.1.1\",\"body\":\"caf\\u00e9 \\\"notes\\\" 1.5e3\","
    "  \"assets\":[{\"name\":\"yfm-redecomp-v0.1.1-windows.zip\",\"size\":2000,"
    "               \"browser_download_url\":\"https://example.invalid/w.zip\"},"
    "              {\"name\":\"yfm-redecomp-v0.1.1-linux.tar.gz\",\"size\":1234,\"digest\":\"sha256:ab\","
    "               \"browser_download_url\":\"https://example.invalid/l.tar.gz\",\"download_count\":7}]},"
    " {\"tag_name\":\"nightly\",\"draft\":false,\"prerelease\":false},"
    " {\"tag_name\":\"v0.1.0\",\"name\":\"First\",\"draft\":false,\"prerelease\":false,\"assets\":[]}]";

static void picking(void)
{
    UpdateRelease release;
    assert(Update_PickRelease(releases, "v0.1.0", 0, NULL, "-linux.tar.gz", &release) == 1);
    assert(!strcmp(release.tag, "v0.1.1") && !strcmp(release.title, "v0.1.1") && !release.prerelease);
    assert(!strcmp(release.page, "https://example.invalid/v0.1.1"));
    assert(!strcmp(release.asset_name, "yfm-redecomp-v0.1.1-linux.tar.gz"));
    assert(!strcmp(release.asset_url, "https://example.invalid/l.tar.gz"));
    assert(release.asset_size == 1234 && !strcmp(release.digest, "sha256:ab"));
    assert(Update_PickRelease(releases, "v0.1.0", 0, NULL, "-windows.zip", &release) == 1);
    assert(!strcmp(release.asset_url, "https://example.invalid/w.zip") && !release.digest[0]);
    /* A tag with a hyphen is a pre-release whatever GitHub's flag says;
     * rc sorts after preview; the draft never counts. */
    assert(Update_PickRelease(releases, "v0.1.0", 1, NULL, "-linux.tar.gz", &release) == 1);
    assert(!strcmp(release.tag, "v0.2.0-rc.1") && release.prerelease && !release.asset_name[0]);
    assert(!strcmp(release.title, "Second release candidate"));
    /* Skipped, current, and newer-than-everything. */
    assert(Update_PickRelease(releases, "v0.1.0", 0, "v0.1.1", "-linux.tar.gz", &release) == 0);
    assert(Update_PickRelease(releases, "v0.1.0", 1, "v0.2.0-rc.1", "-linux.tar.gz", &release) == 1);
    assert(!strcmp(release.tag, "v0.2.0-preview.1"));
    assert(Update_PickRelease(releases, "v0.1.1", 0, NULL, "-linux.tar.gz", &release) == 0);
    assert(Update_PickRelease(releases, "v0.2.0", 1, NULL, "-linux.tar.gz", &release) == 0);
    assert(Update_PickRelease(releases, "v0.2.0-preview.1", 1, NULL, "-linux.tar.gz", &release) == 1);
    assert(!strcmp(release.tag, "v0.2.0-rc.1"));
    /* Not an answer, or no version to compare with. */
    assert(Update_PickRelease("{\"message\":\"API rate limit exceeded\"}", "v0.1.0", 0, NULL, "x", &release) == -1);
    assert(Update_PickRelease("<html>", "v0.1.0", 0, NULL, "x", &release) == -1);
    assert(Update_PickRelease(releases, "", 0, NULL, "x", &release) == -1);
    assert(Update_PickRelease("[]", "v0.1.0", 0, NULL, "x", &release) == 0);
}

static void sha256(void)
{
    char path[1024], hex[65];
    write_text("abc.txt", "abc");
    path_of(path, sizeof(path), "abc.txt");
    assert(!Update_Sha256File(path, hex));
    assert(!strcmp(hex, "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"));
    write_text("abc.txt", "abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq");
    assert(!Update_Sha256File(path, hex));
    assert(!strcmp(hex, "248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1"));
    write_text("abc.txt", "");
    assert(!Update_Sha256File(path, hex));
    assert(!strcmp(hex, "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"));
}

/* --- archives made here ---------------------------------------------- */

static void tar_header(gzFile gz, const char *name, char type, long size, int mode)
{
    char header[512];
    unsigned sum = 0;
    int i;
    memset(header, 0, sizeof(header));
    snprintf(header, 100, "%s", name);
    snprintf(header + 100, 8, "%07o", mode);
    snprintf(header + 108, 8, "%07o", 0);
    snprintf(header + 116, 8, "%07o", 0);
    snprintf(header + 124, 12, "%011o", (unsigned)size);
    snprintf(header + 136, 12, "%011o", 0);
    memset(header + 148, ' ', 8);
    header[156] = type;
    memcpy(header + 257, "ustar", 6);
    memcpy(header + 263, "00", 2);
    for (i = 0; i < 512; i++) sum += (unsigned char)header[i];
    snprintf(header + 148, 8, "%06o", sum);
    assert(gzwrite(gz, header, 512) == 512);
}

static void tar_data(gzFile gz, const char *data, size_t size)
{
    char zero[512] = {0};
    if (size) assert(gzwrite(gz, data, (unsigned)size) == (int)size);
    if (size % 512) assert(gzwrite(gz, zero, (unsigned)(512 - size % 512)) == (int)(512 - size % 512));
}

static void tar_file(gzFile gz, const char *name, const char *text, int mode)
{
    tar_header(gz, name, '0', (long)strlen(text), mode);
    tar_data(gz, text, strlen(text));
}

static void make_tar(const char *relative, const char *evil)
{
    char path[1024], record[400], zero[1024] = {0};
    const char *deep = "pkg/sdk/examples/mods/a-rather-long-folder-name-for-a-mod/"
                       "another-long-folder-name/and-a-long-file-name-too.txt";
    gzFile gz;
    path_of(path, sizeof(path), relative);
    gz = gzopen(path, "wb");
    assert(gz);
    tar_header(gz, "pkg/", '5', 0, 0755);
    tar_file(gz, "pkg/memories-pc", "new program", 0755);
    tar_file(gz, "pkg/README.txt", "readme", 0644);
    /* A path over 100 bytes, as Python's tarfile writes it: a pax record. */
    snprintf(record, sizeof(record), "%3d path=%s\n", (int)(strlen(deep) + 10), deep);
    tar_header(gz, "pkg/PaxHeader", 'x', (long)strlen(record), 0644);
    tar_data(gz, record, strlen(record));
    tar_file(gz, "pkg/placeholder-name", "deep", 0644);
    if (evil) tar_file(gz, evil, "evil", 0644);
    assert(gzwrite(gz, zero, sizeof(zero)) == (int)sizeof(zero));
    assert(gzclose(gz) == Z_OK);
}

static void put16(FILE *file, unsigned value) { fputc((int)(value & 255), file); fputc((int)(value >> 8 & 255), file); }
static void put32(FILE *file, unsigned long value) { put16(file, (unsigned)(value & 0xffff)); put16(file, (unsigned)(value >> 16)); }

typedef struct { const char *name, *text; int deflated; } ZipEntry;

static void make_zip(const char *relative, const ZipEntry *entries, int count, int corrupt)
{
    char path[1024];
    unsigned char packed[4096];
    unsigned long offsets[8], sizes[8], crcs[8], directory;
    int methods[8], i;
    FILE *file;
    path_of(path, sizeof(path), relative);
    file = fopen(path, "wb");
    assert(file && count <= 8);
    for (i = 0; i < count; i++) {
        const char *text = entries[i].text;
        uLong length = (uLong)strlen(text);
        size_t stored = length;
        crcs[i] = crc32(crc32(0, Z_NULL, 0), (const Bytef *)text, (uInt)length);
        methods[i] = entries[i].deflated ? 8 : 0;
        if (entries[i].deflated) {
            z_stream stream;
            memset(&stream, 0, sizeof(stream));
            assert(deflateInit2(&stream, 9, Z_DEFLATED, -MAX_WBITS, 8, Z_DEFAULT_STRATEGY) == Z_OK);
            stream.next_in = (Bytef *)text;
            stream.avail_in = (uInt)length;
            stream.next_out = packed;
            stream.avail_out = sizeof(packed);
            assert(deflate(&stream, Z_FINISH) == Z_STREAM_END);
            stored = sizeof(packed) - stream.avail_out;
            deflateEnd(&stream);
        } else {
            memcpy(packed, text, length);
        }
        if (corrupt && i == count - 1) packed[0] ^= 1;
        sizes[i] = (unsigned long)stored;
        offsets[i] = (unsigned long)ftell(file);
        put32(file, 0x04034b50); put16(file, 20); put16(file, 0); put16(file, (unsigned)methods[i]);
        put16(file, 0); put16(file, 0); put32(file, crcs[i]); put32(file, sizes[i]); put32(file, length);
        put16(file, (unsigned)strlen(entries[i].name)); put16(file, 0);
        fputs(entries[i].name, file);
        fwrite(packed, 1, stored, file);
    }
    directory = (unsigned long)ftell(file);
    for (i = 0; i < count; i++) {
        put32(file, 0x02014b50); put16(file, 20); put16(file, 20); put16(file, 0); put16(file, (unsigned)methods[i]);
        put16(file, 0); put16(file, 0); put32(file, crcs[i]); put32(file, sizes[i]);
        put32(file, (unsigned long)strlen(entries[i].text)); put16(file, (unsigned)strlen(entries[i].name));
        put16(file, 0); put16(file, 0); put16(file, 0); put16(file, 0); put32(file, 0); put32(file, offsets[i]);
        fputs(entries[i].name, file);
    }
    put32(file, 0x06054b50); put16(file, 0); put16(file, 0); put16(file, (unsigned)count); put16(file, (unsigned)count);
    put32(file, (unsigned long)ftell(file) - directory); put32(file, directory); put16(file, 0);
    assert(!fclose(file));
}

static void archives(void)
{
    char archive[1024], out[1024], why[256], staged[1024];
    static const ZipEntry good[] = {
        {"pkg/", "", 0},
        {"pkg/memories-pc.exe", "windows program", 0},
        {"pkg/mods/a/mod.json", "{\"id\": \"a\", \"text\": \"a longer text that deflate squeezes, squeezes, squeezes\"}", 1},
        {"pkg/empty.txt", "", 1}};
    static const ZipEntry evil[] = {{"pkg/ok.txt", "ok", 0}, {"pkg/../../evil.txt", "evil", 0}};

    make_tar("a.tar.gz", NULL);
    path_of(archive, sizeof(archive), "a.tar.gz");
    path_of(out, sizeof(out), "tar-out");
    assert(!Update_Extract(archive, out, why, sizeof(why)));
    assert(has_text("tar-out/pkg/memories-pc", "new program"));
    assert(has_text("tar-out/pkg/README.txt", "readme"));
    assert(has_text("tar-out/pkg/sdk/examples/mods/a-rather-long-folder-name-for-a-mod/another-long-folder-name/"
                    "and-a-long-file-name-too.txt", "deep"));
    assert(!present("tar-out/pkg/placeholder-name"));
#ifndef _WIN32
    {
        struct stat info;
        path_of(archive, sizeof(archive), "tar-out/pkg/memories-pc");
        assert(!stat(archive, &info) && (info.st_mode & 0100));
        path_of(archive, sizeof(archive), "tar-out/pkg/README.txt");
        assert(!stat(archive, &info) && !(info.st_mode & 0100));
    }
#endif
    assert(!Update_StagedRoot(out, staged, sizeof(staged)));
    assert(strstr(staged, "tar-out/pkg"));

    make_tar("evil.tar.gz", "pkg/../../evil.txt");
    path_of(archive, sizeof(archive), "evil.tar.gz");
    path_of(out, sizeof(out), "evil-tar");
    assert(Update_Extract(archive, out, why, sizeof(why)) && strstr(why, "outside"));
    assert(!present("evil.txt"));

    /* A truncated .tar.gz fails on gzip's own check. */
    {
        FILE *file;
        long size;
        char *data;
        path_of(archive, sizeof(archive), "a.tar.gz");
        file = fopen(archive, "rb");
        fseek(file, 0, SEEK_END);
        size = ftell(file);
        rewind(file);
        data = malloc((size_t)size);
        assert(fread(data, 1, (size_t)size, file) == (size_t)size);
        fclose(file);
        path_of(archive, sizeof(archive), "short.tar.gz");
        file = fopen(archive, "wb");
        fwrite(data, 1, (size_t)size - 6, file);
        fclose(file);
        free(data);
        path_of(out, sizeof(out), "short-out");
        assert(Update_Extract(archive, out, why, sizeof(why)));
    }

    make_zip("a.zip", good, 4, 0);
    path_of(archive, sizeof(archive), "a.zip");
    path_of(out, sizeof(out), "zip-out");
    assert(!Update_Extract(archive, out, why, sizeof(why)));
    assert(has_text("zip-out/pkg/memories-pc.exe", "windows program"));
    assert(has_text("zip-out/pkg/mods/a/mod.json", good[2].text));
    assert(has_text("zip-out/pkg/empty.txt", ""));

    make_zip("bad.zip", good, 3, 1);
    path_of(archive, sizeof(archive), "bad.zip");
    path_of(out, sizeof(out), "bad-out");
    assert(Update_Extract(archive, out, why, sizeof(why)));

    make_zip("evil.zip", evil, 2, 0);
    path_of(archive, sizeof(archive), "evil.zip");
    path_of(out, sizeof(out), "evil-zip");
    assert(Update_Extract(archive, out, why, sizeof(why)) && strstr(why, "outside"));
    assert(!present("evil.txt"));
}

static void installing(void)
{
    char staged[1024], program[1024], cleanup[1024], why[256];
    write_text("program/memories-pc", "old program");
    write_text("program/buildid", "old id");
    write_text("program/LICENSE", "license");
    write_text("program/game/SLUS.bin", "the player's disc");
    write_text("program/mods/players-own.txt", "keep me");
    write_text("program/mods/bundled/mod.json", "old mod");
    write_text("program/symbols/old.txt", "old symbols");

    write_text("stage/pkg/memories-pc", "new program");
    write_text("stage/pkg/buildid", "new id");
    write_text("stage/pkg/LICENSE", "license");
    write_text("stage/pkg/game/README.txt", "put your disc here");
    write_text("stage/pkg/mods/bundled/mod.json", "new mod");
    write_text("stage/pkg/sdk/include/modapi.h", "header");
    write_text("stage/pkg/symbols/new.txt", "new symbols");

    path_of(staged, sizeof(staged), "stage/pkg");
    path_of(program, sizeof(program), "program");
    path_of(cleanup, sizeof(cleanup), "user/updates/cleanup.txt");
    assert(Update_IsPackagedInstall(program, "memories-pc"));
    assert(Update_IsPackagedInstall(staged, "memories-pc"));
    assert(!Update_IsPackagedInstall(staged, "memories-pc.exe"));
    assert(!Update_Install(staged, program, cleanup, why, sizeof(why)));
    assert(has_text("program/memories-pc", "new program"));
    assert(has_text("program/buildid", "new id"));
    assert(has_text("program/mods/bundled/mod.json", "new mod"));
    assert(has_text("program/sdk/include/modapi.h", "header"));
    assert(has_text("program/symbols/new.txt", "new symbols"));
    /* What the release does not carry stays; game/ is never touched. */
    assert(has_text("program/symbols/old.txt", "old symbols"));
    assert(has_text("program/mods/players-own.txt", "keep me"));
    assert(has_text("program/game/SLUS.bin", "the player's disc"));
    assert(!present("program/game/README.txt"));
    /* Nothing left over: these files were not open, so they went at once. */
    assert(!present("program/memories-pc.update-old") && !present("program/memories-pc.update-new"));
    assert(!present("program/mods/bundled/mod.json.update-old"));

    /* The next start removes what could not go (a running .exe on Windows);
     * the list names only *.update-old files, and nothing else is removed. */
    write_text("program/memories-pc.exe.update-old", "was running");
    write_text("program/keep.txt", "not an old file");
    {
        char line[2100], old[1024], keep[1024];
        FILE *file;
        path_of(old, sizeof(old), "program/memories-pc.exe.update-old");
        path_of(keep, sizeof(keep), "program/keep.txt");
        write_text("user/updates/cleanup.txt", "");
        file = fopen(cleanup, "w");
        assert(file);
        snprintf(line, sizeof(line), "%s\n%s\n", old, keep);
        fputs(line, file);
        fclose(file);
    }
    Update_Cleanup(cleanup);
    assert(!present("program/memories-pc.exe.update-old"));
    assert(has_text("program/keep.txt", "not an old file"));
    assert(!present("user/updates/cleanup.txt"));

    /* A staged folder that cannot be read leaves the program as it was. */
    path_of(staged, sizeof(staged), "stage/missing");
    assert(Update_Install(staged, program, cleanup, why, sizeof(why)));
    assert(has_text("program/memories-pc", "new program"));
    assert(!present("program/memories-pc.update-new"));
}

int main(void)
{
    char *made;
    scratch_template(root, sizeof(root), "memories-update");
    made = mkdtemp(root);
    assert(made);
    versions();
    picking();
    sha256();
    archives();
    installing();
    Update_RemoveTree(root);
    assert(!present(""));
    puts("update: ok");
    return 0;
}
