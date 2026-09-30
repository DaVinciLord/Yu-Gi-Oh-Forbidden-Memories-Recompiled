/* The two roots the port reads and writes through (paths.h). Both are
 * resolved once and cached: the program directory from /proc/self/exe, the
 * user directory from MEMORIES_USER_DIR, else portable.txt beside the
 * executable (portable mode), else the platform's own convention for a
 * game's files. */
#define _POSIX_C_SOURCE 200809L
#include "paths.h"
#include <ctype.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <shlobj.h> /* SHGetFolderPathW */
#endif
#include "pc/compat/posix.h" /* mkdir, and readlink of /proc/self/exe, on Windows */
#include <sys/stat.h>

#define PATH_MAX_ 1024
#define APP_NAME "YFM Re-Decomp"
#define OLD_APP_NAME "YFM ReDecomp" /* what builds before 2026-09-22 called it */

static char user_dir[PATH_MAX_];
static char program_dir[PATH_MAX_];

/* A folder made, or already there. When it is not, errno and the last error
 * are mkdir's (Paths_WriteError), not those of the check after it. */
static int make_dir(const char *path)
{
    int error;
#ifdef _WIN32
    DWORD code;
    unsigned long dos;
#endif
    if (!mkdir(path, 0777)) return 0;
    error = errno;
#ifdef _WIN32
    code = GetLastError();
    dos = _doserrno;
#endif
    if (!access(path, X_OK)) return 0;
    errno = error;
#ifdef _WIN32
    _doserrno = dos;
    SetLastError(code);
#endif
    return -1;
}

int Paths_MakeDirs(const char *path)
{
    char work[PATH_MAX_];
    size_t length = strlen(path), i;
    if (length >= sizeof(work)) return -1;
    memcpy(work, path, length + 1);
    while (length > 1 && work[length - 1] == '/') work[--length] = '\0';
    for (i = 1; i < length; i++) {
        if (work[i] != '/') continue;
        work[i] = '\0';
        if (make_dir(work)) return -1;
        work[i] = '/';
    }
    if (make_dir(work)) return -1;
    return 0;
}

/* Everything above the last separator of a path. */
static void directory_of(char *path)
{
    char *slash = strrchr(path, '/');
    if (slash) *slash = '\0';
    else path[0] = '\0';
}

const char *Paths_ProgramDir(void)
{
    ssize_t length;
    if (program_dir[0]) return program_dir;
    length = readlink("/proc/self/exe", program_dir, sizeof(program_dir) - 1);
    if (length > 0 && (size_t)length < sizeof(program_dir)) {
        program_dir[length] = '\0';
        directory_of(program_dir);
    }
    if (!program_dir[0]) snprintf(program_dir, sizeof(program_dir), ".");
    return program_dir;
}

/* Portable mode: a file named portable.txt beside the executable (what it
 * holds does not matter) keeps the player's files beside it too, in a
 * folder of their own -- mods/ beside the executable is the release's. */
static int portable(char *out, size_t size)
{
    char marker[PATH_MAX_];
    int n;
    if (Paths_Program(marker, sizeof(marker), "portable.txt") || access(marker, F_OK)) return 0;
    n = snprintf(out, size, "%s/user", Paths_ProgramDir());
    if (n < 0 || (size_t)n >= size) {
        out[0] = '\0';
        return 0;
    }
    fprintf(stderr, "memories-pc: %s found; the player's files go to %s\n", marker, out);
    return 1;
}

const char *Paths_UserDir(void)
{
    const char *named = getenv("MEMORIES_USER_DIR");
    if (user_dir[0]) return user_dir;
    if (named && *named) {
        snprintf(user_dir, sizeof(user_dir), "%s", named);
    } else if (portable(user_dir, sizeof(user_dir))) {
        /* user/ beside the executable */
    } else {
        char root[PATH_MAX_ - 32] = ""; /* room for the folder name after it */
#ifdef _WIN32
        /* Documents\My Games is where Windows games have put their files
         * since the Games for Windows era; the player can find and back it
         * up without being told where to look. Ask the shell where Documents
         * is, since OneDrive and the folder's Location tab both move it. */
        wchar_t documents[MAX_PATH];
        char *utf8 = NULL;
        const char *profile = getenv("USERPROFILE");
        if (SHGetFolderPathW(NULL, CSIDL_PERSONAL, NULL, 0, documents) == S_OK)
            utf8 = Memories_WideToUtf8(documents);
        if (utf8) {
            snprintf(root, sizeof(root), "%s/My Games", utf8);
            free(utf8);
        }
        else
            snprintf(root, sizeof(root), "%s/Documents/My Games", profile && *profile ? profile : ".");
#else
        const char *home = getenv("HOME"), *xdg = getenv("XDG_DATA_HOME");
        if (xdg && *xdg == '/') snprintf(root, sizeof(root), "%s", xdg);
        else if (home && *home) snprintf(root, sizeof(root), "%s/.local/share", home);
#endif
        if (root[0]) {
            char old[PATH_MAX_];
            snprintf(user_dir, sizeof(user_dir), "%s/" APP_NAME, root);
            snprintf(old, sizeof(old), "%s/" OLD_APP_NAME, root);
            /* Bring the old folder along under the new name, once. */
            if (access(user_dir, F_OK) && !access(old, F_OK) && !rename(old, user_dir))
                fprintf(stderr, "memories-pc: moved %s to %s\n", old, user_dir);
        } else {
            snprintf(user_dir, sizeof(user_dir), "saves");
        }
    }
    /* A root that cannot be made is not worth carrying: fall back beside the
     * game, which is where the port kept everything before. */
    if (Paths_MakeDirs(user_dir)) {
        fprintf(stderr, "memories-pc: cannot create %s; using ./saves\n", user_dir);
        snprintf(user_dir, sizeof(user_dir), "saves");
        Paths_MakeDirs(user_dir);
    }
    return user_dir;
}

static int join(char *out, size_t size, const char *root, const char *relative, int create)
{
    int n = snprintf(out, size, "%s/%s", root, relative);
    if (n < 0 || (size_t)n >= size) return -1;
    if (create) {
        char parent[PATH_MAX_];
        if ((size_t)n >= sizeof(parent)) return -1;
        memcpy(parent, out, (size_t)n + 1);
        directory_of(parent);
        if (parent[0] && Paths_MakeDirs(parent)) return -1;
    }
    return 0;
}

int Paths_User(char *out, size_t size, const char *relative)
{
    return join(out, size, Paths_UserDir(), relative, 1);
}

int Paths_Program(char *out, size_t size, const char *relative)
{
    return join(out, size, Paths_ProgramDir(), relative, 0);
}

int Paths_Contained(const char *relative)
{
    const char *at = relative;
    if (!relative || !*relative || *relative == '/' || *relative == '\\') return 0;
    if (relative[0] && relative[1] == ':') return 0; /* a drive letter */
    for (;;) {
        size_t length = strcspn(at, "/");
        if (strchr(at, '\\')) return 0;
        if (!length) return 0; /* an empty component: "a//b" or a trailing slash */
        if (length == 1 && at[0] == '.') return 0;
        if (length == 2 && at[0] == '.' && at[1] == '.') return 0;
        if (!at[length]) return 1;
        at += length + 1;
    }
}

static void carry(const char *from, const char *relative)
{
    char destination[PATH_MAX_];
    char buffer[65536];
    FILE *in, *out;
    size_t got;
    if (access(from, R_OK)) return;
    if (Paths_User(destination, sizeof(destination), relative)) return;
    if (!access(destination, F_OK)) return; /* already carried, or newer */
    in = fopen(from, "rb");
    if (!in) return;
    out = fopen(destination, "wb");
    if (!out) { fclose(in); return; }
    while ((got = fread(buffer, 1, sizeof(buffer), in)) > 0) {
        if (fwrite(buffer, 1, got, out) != got) break;
    }
    fclose(in);
    if (fclose(out)) remove(destination);
    else fprintf(stderr, "memories-pc: carried %s to %s\n", from, destination);
}

void Paths_MigrateLegacySaves(void)
{
    static const char *files[] = {"settings.txt", "controls.txt", "memcard1.mcd", "memcard2.mcd"};
    char legacy[PATH_MAX_];
    unsigned i;
    for (i = 0; i < sizeof(files) / sizeof(files[0]); i++) {
        snprintf(legacy, sizeof(legacy), "saves/%s", files[i]);
        carry(legacy, files[i]);
    }
}

void Paths_WriteBegin(void)
{
    errno = 0;
#ifdef _WIN32
    _doserrno = 0;
    SetLastError(0);
#endif
}

#ifdef _WIN32
/* Whether a full path lies in the Documents folder, where an antivirus's
 * ransomware protection and Windows' Controlled folder access guard it. */
static int in_documents(const wchar_t *path)
{
    wchar_t documents[MAX_PATH];
    size_t n;
    if (SHGetFolderPathW(NULL, CSIDL_PERSONAL, NULL, 0, documents) != S_OK) return 0;
    n = wcslen(documents);
    while (n && documents[n - 1] == L'\\') n--;
    return n && !_wcsnicmp(path, documents, n) && (path[n] == L'\\' || !path[n]);
}

/* The executable's file name, which the player allows in those settings. */
static void program_name(char *out, size_t size)
{
    wchar_t module[MAX_PATH];
    DWORD length = GetModuleFileNameW(NULL, module, MAX_PATH);
    const wchar_t *base = module;
    char *utf8;
    snprintf(out, size, "memories-pc.exe");
    if (!length || length >= MAX_PATH) return;
    if (wcsrchr(module, L'\\')) base = wcsrchr(module, L'\\') + 1;
    utf8 = Memories_WideToUtf8(base);
    if (utf8 && *utf8) snprintf(out, size, "%s", utf8);
    free(utf8);
}
#endif

/* Paths_WriteError and Paths_WriteReason: the reason, after the path when
 * `with_path` is set. */
static const char *describe(char *out, size_t size, const char *path, int with_path)
{
    int error = errno;
    char reason[512] = "", *shown = NULL, program[128] = "";
    size_t length;
    int hint = 0;
#ifdef _WIN32
    /* What the system said: the last error of the call that failed, or the
     * one the C runtime kept (_wfopen, fwrite and fclose go through it).
     * ERROR_ALREADY_EXISTS is what a successful CREATE_ALWAYS over an old
     * partial file leaves behind, not a failure. */
    DWORD last = GetLastError(), code = last;
    unsigned long dos = _doserrno;
    wchar_t *wide;
    if (!code || code == ERROR_ALREADY_EXISTS) code = (DWORD)dos;
    if (code == ERROR_ALREADY_EXISTS) code = 0;
    if (code) {
        wchar_t *message = NULL;
        if (FormatMessageW(FORMAT_MESSAGE_ALLOCATE_BUFFER | FORMAT_MESSAGE_FROM_SYSTEM | FORMAT_MESSAGE_IGNORE_INSERTS,
                           NULL, code, 0, (LPWSTR)&message, 0, NULL) && message) {
            char *utf8 = Memories_WideToUtf8(message);
            if (utf8) snprintf(reason, sizeof(reason), "%s", utf8);
            free(utf8);
        }
        if (message) LocalFree(message);
        if (!reason[0]) snprintf(reason, sizeof(reason), "Windows error %lu", (unsigned long)code);
    }
    /* The whole path, as Explorer shows it. */
    wide = Memories_Utf8ToWide(path);
    if (wide) {
        DWORD needed = GetFullPathNameW(wide, 0, NULL, NULL);
        wchar_t *full = needed ? malloc((size_t)needed * sizeof(*full)) : NULL;
        if (full && GetFullPathNameW(wide, needed, full, NULL) < needed) {
            shown = Memories_WideToUtf8(full);
            hint = code == ERROR_ACCESS_DENIED && in_documents(full);
        }
        free(full);
        free(wide);
    }
    if (hint) program_name(program, sizeof(program));
    /* Left as found, so a second description of the same failure agrees. */
    SetLastError(last);
    _doserrno = dos;
#endif
    if (!reason[0]) snprintf(reason, sizeof(reason), "%s", error ? strerror(error) : "the system gave no reason");
    length = strlen(reason);
    while (length && (isspace((unsigned char)reason[length - 1]) || reason[length - 1] == '.')) reason[--length] = '\0';
    snprintf(out, size, "%s%s%s%s%s%s", with_path ? (shown ? shown : path) : "", with_path ? ": " : "", reason,
             hint ? " (an antivirus \"ransomware protection\" or Windows \"Controlled folder access\" may be blocking "
                    "the Documents folder; allow " : "",
             hint ? program : "", hint ? " there)." : ".");
    free(shown);
#ifdef _WIN32
    SetLastError(last); /* free() may have changed it */
#endif
    errno = error;
    return out;
}

const char *Paths_WriteError(char *out, size_t size, const char *path) { return describe(out, size, path, 1); }
const char *Paths_WriteReason(char *out, size_t size, const char *path) { return describe(out, size, path, 0); }

int Paths_UserDirWritable(char *why, size_t size)
{
    char path[PATH_MAX_];
    FILE *file;
    if (size) why[0] = '\0';
    if (Paths_User(path, sizeof(path), "write-test.tmp")) {
        snprintf(why, size, "the path is too long.");
        return 0;
    }
    Paths_WriteBegin();
    file = fopen(path, "wb");
    if (!file) {
        Paths_WriteReason(why, size, path);
        return 0;
    }
    if (fclose(file)) {
        Paths_WriteReason(why, size, path);
        remove(path);
        return 0;
    }
    remove(path);
    return 1;
}
