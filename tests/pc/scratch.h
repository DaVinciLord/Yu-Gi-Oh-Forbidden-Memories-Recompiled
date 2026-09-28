#ifndef MEMORIES_TESTS_SCRATCH_H
#define MEMORIES_TESTS_SCRATCH_H
/* Scratch files and folders for the tests, in the system's temporary folder:
 * TMPDIR, else TEMP or TMP (Windows), else /tmp. A plain "/tmp" is \tmp on
 * the current drive on Windows, which a fresh machine or a CI runner does not
 * have (Wine maps it, which hid this).
 *
 * scratch_dir() makes memories-<kind>-p<pid>-XXXXXX and removes it again
 * when the test exits, fails an assert() or is interrupted. What a test
 * cannot remove itself (killed by a timeout, or a file it still holds open,
 * which Windows will not delete) is swept later: by the next scratch_dir()
 * of the same kind, and by pc_scratch_sweep, which CTest runs after the
 * tests (scratch_sweep_test.c). A sweep removes only our names whose
 * process is gone, and folders from before the process tag (the exact
 * memories-<kind>-XXXXXX of an earlier build) once they are a day old. */
#include <ctype.h>
#include <errno.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <time.h>
#ifdef _WIN32
#include <process.h>
#include "pc/compat/fs.h" /* UTF-8 opendir/stat/rmdir/remove/getenv/mkdtemp */
#else
#include <dirent.h>
#include <unistd.h>
#endif

#define SCRATCH_MAX 512
#define SCRATCH_ROOTS 16
#define SCRATCH_LEGACY_AGE (24 * 60 * 60)

static inline const char *scratch_base(void)
{
    const char *names[] = {"TMPDIR", "TEMP", "TMP"}, *base = NULL;
    size_t i;
    for (i = 0; i < sizeof(names) / sizeof(names[0]) && (!base || !*base); i++) base = getenv(names[i]);
    return base && *base ? base : "/tmp";
}

/* A mkstemp/mkdtemp template, for a test that manages the name itself. */
static inline void scratch_template(char *out, size_t size, const char *name)
{
    snprintf(out, size, "%s/%s-XXXXXX", scratch_base(), name);
}

static inline unsigned long scratch_pid(void)
{
#ifdef _WIN32
    return (unsigned long)_getpid();
#else
    return (unsigned long)getpid();
#endif
}

static inline int scratch_alive(unsigned long pid)
{
#ifdef _WIN32
    return Memories_ProcessAlive(pid);
#else
    if (!pid || pid > 0x7FFFFFFFul) return 1; /* not a process of ours: leave it */
    return !kill((pid_t)pid, 0) || errno == EPERM;
#endif
}

/* Remove a file or a whole tree. A missing path is fine. rmdir comes first,
 * so a link to a folder is unlinked rather than emptied. */
static inline void scratch_remove(const char *path, int depth)
{
    struct stat info;
    DIR *dir;
    struct dirent *entry;
    char child[2 * SCRATCH_MAX];
#ifdef _WIN32
    if (stat(path, &info)) return;
#else
    if (lstat(path, &info)) return;
#endif
    if (!S_ISDIR(info.st_mode)) {
        remove(path);
        return;
    }
    if (!rmdir(path) || depth > 32) return;
    dir = opendir(path);
    if (!dir) return;
    while ((entry = readdir(dir))) {
        if (!strcmp(entry->d_name, ".") || !strcmp(entry->d_name, "..")) continue;
        if (snprintf(child, sizeof(child), "%s/%s", path, entry->d_name) >= (int)sizeof(child)) continue;
        scratch_remove(child, depth + 1);
    }
    closedir(dir);
    rmdir(path);
}

typedef struct {
    char roots[SCRATCH_ROOTS][SCRATCH_MAX];
    int count, hooked;
} ScratchState;

static inline ScratchState *scratch_state(void)
{
    static ScratchState state;
    return &state;
}

static inline int scratch_exists(const char *path)
{
    struct stat info;
    return !stat(path, &info);
}

static inline void scratch_cleanup(void)
{
    ScratchState *state = scratch_state();
    int i, moved = 0;
    for (i = state->count - 1; i >= 0; i--) {
        scratch_remove(state->roots[i], 0);
        if (scratch_exists(state->roots[i]) && !moved) {
            /* The test may still be inside it (game_files_test chdirs in),
             * and Windows will not remove the current folder. */
            moved = 1;
#ifdef _WIN32
            {
                wchar_t *wide = Memories_Utf8ToWide(scratch_base());
                if (wide) _wchdir(wide);
                free(wide);
            }
#else
            if (chdir(scratch_base())) {}
#endif
            scratch_remove(state->roots[i], 0);
        }
    }
    state->count = 0;
}

static inline void scratch_signal(int number)
{
#ifndef _WIN32
    alarm(10); /* an abort from inside malloc would deadlock opendir: give up */
#endif
    scratch_cleanup();
    signal(number, SIG_DFL);
    raise(number);
}

/* Six letters or digits, and the end: mkdtemp's suffix. */
static inline int scratch_suffix(const char *text)
{
    int i;
    for (i = 0; i < 6; i++) if (!isalnum((unsigned char)text[i])) return 0;
    return !text[6];
}

/* memories-<kind>-p<pid>-XXXXXX, with <kind> equal to `name` when given. */
static inline int scratch_tagged(const char *entry, const char *name, unsigned long *pid)
{
    size_t length = strlen(entry), head;
    const char *tail, *digits;
    if (length < 9 + 3 + 7 || strncmp(entry, "memories-", 9)) return 0;
    tail = entry + length - 7;
    if (*tail != '-' || !scratch_suffix(tail + 1)) return 0;
    for (digits = tail; digits > entry && isdigit((unsigned char)digits[-1]); digits--) {}
    if (digits == tail || digits - entry < 11 || digits[-1] != 'p' || digits[-2] != '-') return 0;
    head = (size_t)(digits - 2 - entry);
    if (name && (strlen(name) != head || strncmp(entry, name, head))) return 0;
    *pid = strtoul(digits, NULL, 10);
    return 1;
}

static inline int scratch_legacy(const char *entry, const char *name)
{
    size_t length = strlen(name);
    return !strncmp(entry, name, length) && entry[length] == '-' && scratch_suffix(entry + length + 1);
}

static inline int scratch_registered(const char *path)
{
    ScratchState *state = scratch_state();
    int i;
    for (i = 0; i < state->count; i++) if (!strcmp(state->roots[i], path)) return 1;
    return 0;
}

/* Remove what earlier runs left in the temporary folder: every kind when
 * `name` is NULL, else that kind only. Returns how many were removed. */
static inline int scratch_sweep(const char *name)
{
    /* Every kind the tests have made, for the sweep of untagged leftovers. */
    static const char *const kinds[] = {
        "memories-audio", "memories-backend", "memories-card-identities", "memories-controls",
        "memories-decks", "memories-disc", "memories-fs", "memories-lifecycle", "memories-log",
        "memories-manager", "memories-mod-window", "memories-mods", "memories-rom", "memories-runtime",
        "memories-save-menu", "memories-save-slots", "memories-settings", "memories-texture-pack",
        "memories-window"};
    const char *base = scratch_base();
    char path[2 * SCRATCH_MAX];
    DIR *dir = opendir(base);
    struct dirent *entry;
    time_t now = time(NULL);
    int removed = 0;
    if (!dir) return 0;
    while ((entry = readdir(dir))) {
        unsigned long pid;
        size_t i;
        int stale = 0;
        if (strncmp(entry->d_name, "memories-", 9)) continue;
        if (snprintf(path, sizeof(path), "%s/%s", base, entry->d_name) >= (int)sizeof(path)) continue;
        if (scratch_tagged(entry->d_name, name, &pid)) {
            stale = !scratch_registered(path) && !scratch_alive(pid);
        } else {
            struct stat info;
            int legacy = name && scratch_legacy(entry->d_name, name);
            for (i = 0; !name && !legacy && i < sizeof(kinds) / sizeof(kinds[0]); i++)
                legacy = scratch_legacy(entry->d_name, kinds[i]);
            stale = legacy && !stat(path, &info) && now - info.st_mtime > SCRATCH_LEGACY_AGE;
        }
        if (stale) {
            scratch_remove(path, 0);
            removed += !scratch_exists(path);
        }
    }
    closedir(dir);
    return removed;
}

/* mkdtemp in the temporary folder, removed again however the test ends.
 * Returns `out`, or NULL. */
static inline char *scratch_dir(char *out, size_t size, const char *name)
{
    ScratchState *state = scratch_state();
    scratch_sweep(name);
    if (state->count >= SCRATCH_ROOTS) return NULL;
    if (snprintf(out, size, "%s/%s-p%lu-XXXXXX", scratch_base(), name, scratch_pid()) >= (int)size) return NULL;
    if (strlen(out) >= SCRATCH_MAX || !mkdtemp(out)) return NULL;
    strcpy(state->roots[state->count++], out);
    if (!state->hooked) {
        const int numbers[] = {SIGABRT, SIGINT, SIGTERM};
        size_t i;
        state->hooked = 1;
        atexit(scratch_cleanup);
        /* Only where the test has no handler of its own. */
        for (i = 0; i < sizeof(numbers) / sizeof(numbers[0]); i++) {
            void (*previous)(int) = signal(numbers[i], scratch_signal);
            if (previous != SIG_DFL && previous != SIG_ERR) signal(numbers[i], previous);
        }
    }
    return out;
}
#endif
