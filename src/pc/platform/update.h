#ifndef MEMORIES_PC_UPDATE_H
#define MEMORIES_PC_UPDATE_H
/* Updates from the project's GitHub releases (notes/updates.md).
 *
 * This half is the part without a window or a network: version numbers,
 * choosing a release from the GitHub API's answer, unpacking a release
 * archive and putting its files over the program directory. update_net.c
 * fetches, update_runtime.c runs all of it on a thread of its own and asks
 * the player through a notice over the picture (Menu_ShowNotice). */
#include <stddef.h>

/* vMAJOR.MINOR.PATCH with an optional -PRE (v0.2.0, v0.2.0-preview.1). */
typedef struct {
    long major, minor, patch;
    char pre[64];
} UpdateVersion;

/* 1 when `text` is such a version (the leading v is optional), else 0. */
int Update_ParseVersion(const char *text, UpdateVersion *out);
/* Semantic versioning order: <0, 0, >0. A pre-release sorts before its
 * release; its dot-separated parts compare numerically when both are
 * numbers, else as text, and a number sorts before text. */
int Update_CompareVersions(const UpdateVersion *a, const UpdateVersion *b);

typedef struct {
    char tag[64];          /* v0.2.0 */
    char title[160];       /* the release's name, else its tag */
    char page[512];        /* the release's page on GitHub */
    char asset_name[256];  /* the archive for this system; empty if it has none */
    char asset_url[1024];
    long asset_size;       /* bytes; 0 if unknown */
    char digest[80];       /* "sha256:<hex>" when GitHub gave one */
    int prerelease;
} UpdateRelease;

/* The newest release in a GitHub /releases answer that is newer than
 * `current` and is not `skip` (NULL or "" for none). Drafts are never
 * chosen; pre-releases (GitHub's flag, or a tag with a hyphen) only when
 * `prereleases` is nonzero. The asset is the one whose name ends in
 * `asset_suffix`. 1: found, 0: none newer, -1: not a release list. */
int Update_PickRelease(const char *json, const char *current, int prereleases, const char *skip,
                       const char *asset_suffix, UpdateRelease *out);

/* SHA-256 of a file as 64 lower-case hex digits. 0 on success. */
int Update_Sha256File(const char *path, char hex[65]);

/* Unpack a release archive (.zip, or .tar.gz) into `directory`, which is
 * created. Only files and folders, each checked to stay inside `directory`
 * (Paths_Contained); anything else fails the whole archive. Every zip entry
 * is checked against its CRC-32, a .tar.gz against gzip's. 0 on success. */
int Update_Extract(const char *archive, const char *directory, char *why, size_t why_size);

/* The one folder an archive unpacked to (a release is yfm-redecomp-<v>/). */
int Update_StagedRoot(const char *directory, char *out, size_t size);

/* Whether `program` is an unpacked release folder, which Update_Install may
 * replace files in: the executable, buildid and LICENSE are there. */
int Update_IsPackagedInstall(const char *program, const char *executable);

/* Whether a file can be made in `program` (not Program Files, not a
 * read-only mount): tried with a probe file that is removed again. */
int Update_CanWrite(const char *program);

/* Put every file of the unpacked release `staged` over `program`, except
 * its game/ folder (the player's disc lives there). Files the release does
 * not have are left alone. All new files are copied beside their targets
 * first; only then is each target moved aside to <name>.update-old and the
 * new one moved in, so a failure leaves the old program as it was. A file
 * that cannot be removed yet (the running executable on Windows) is listed
 * in `cleanup_list` for Update_Cleanup at the next start. 0 on success. */
int Update_Install(const char *staged, const char *program, const char *cleanup_list, char *why, size_t why_size);
/* Remove the *.update-old files `cleanup_list` names; the list goes once
 * every one of them is gone. */
void Update_Cleanup(const char *cleanup_list);

/* Remove a folder and everything in it. */
void Update_RemoveTree(const char *path);

#endif
