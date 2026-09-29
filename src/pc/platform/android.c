/* Android: the thin layer the port needs there, as win32.c is Windows'
 * (notes/pc-build.md, "Android"). Everything else is the Linux code: the
 * guest image, the fault handler, the clock and the SDL window (sdl.c).
 *
 * The app is SDL's Java shell (org.libsdl.app.SDLActivity, packaged by
 * tools/pc/package_android.py). It loads libSDL3.so and libmain.so (the
 * loader, android_loader.c) and calls SDL_main on a thread of its own; that
 * loads this game, libgame.so, and runs Memories_AndroidMain, which sets up
 * what an app process differs in and runs the port's main.
 *
 * - The player's folder is the app's external files folder
 *   (/sdcard/Android/data/<package>/files): the disc image goes in its
 *   game/ folder (game_files.c), where the first run's file picker copies
 *   the one the player chooses (Platform_SelectDisc, below); adb can put it
 *   there too.
 * - stdout and stderr, where the port reports, go nowhere in an app: they
 *   are forwarded to the system log (adb logcat -s memories).
 * - No crash monitor process and no restart: both re-execute the program,
 *   and an app process is the zygote's, not a program of its own.
 * - No update check yet, and no desktop OpenGL (platform.h).
 * - SDL_main itself is the loader's (android_loader.c, libmain.so), which
 *   loads this game, libgame.so, at the address it was linked at and calls
 *   Memories_AndroidMain.
 * - The build's own files (buildid, commit, symbols/: save states and crash
 *   reports read them beside the executable) are APK assets under build/,
 *   unpacked into the app's internal files folder, program/, which becomes
 *   the program directory (MEMORIES_PROGRAM_DIR, paths.h). */
#ifdef __ANDROID__
#include "pc/compat/fs.h"
#include "platform.h"
#include "paths.h"
#include "game_files.h"
#include <SDL3/SDL.h>
#include <android/log.h>
#include <dirent.h>
#include <dlfcn.h>
#include <errno.h>
#include <sys/statvfs.h>
#include <fcntl.h>
#include <linux/ashmem.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/syscall.h>
#include <unistd.h>

#define LOG_TAG "memories"

#if __ANDROID_API__ < 30
int memories_memfd_create(const char *name, unsigned flags) /* android_compat.h */
{
    return (int)syscall(__NR_memfd_create, name, flags);
}
#endif

int memories_ashmem_create(const char *name, unsigned size) /* android_compat.h */
{
    char label[ASHMEM_NAME_LEN];
    int fd = open("/dev/ashmem", O_RDWR | O_CLOEXEC);
    if (fd < 0) return -1;
    snprintf(label, sizeof(label), "%s", name);
    if (ioctl(fd, ASHMEM_SET_NAME, label) || ioctl(fd, ASHMEM_SET_SIZE, (size_t)size)) {
        close(fd);
        return -1;
    }
    return fd;
}

int main(int argc, char **argv); /* src/pc/guest/main.c */

/* The game calls bzero (HOST_LIBC in build_game32.py); bionic has none. */
void bzero(void *at, size_t size)
{
    memset(at, 0, size);
}

int Platform_HasDesktopGL(void)
{
    return 0; /* GLES only: sdl.c's GL renderer is desktop GL */
}

/* --- the disc image, through the system's file picker ----------------- */

typedef struct Picked {
    SDL_AtomicInt done;
    char uri[2048];
    int result; /* 1 chosen, 0 cancelled, -1 the picker failed */
} Picked;

static void SDLCALL picked(void *userdata, const char *const *files, int filter)
{
    Picked *pick = userdata;
    (void)filter;
    if (!files) pick->result = -1;
    else if (files[0] && strlen(files[0]) < sizeof(pick->uri)) {
        snprintf(pick->uri, sizeof(pick->uri), "%s", files[0]);
        pick->result = 1;
    }
    SDL_SetAtomicInt(&pick->done, 1); /* on the Java thread: published last */
}

/* The chosen document, open: 1 when it holds the game's executable, as
 * game_files.c checks an image (SLUS_014.11 on a raw ISO 9660 image), before
 * anything is copied. */
static int is_the_disc(FILE *file)
{
    unsigned char sector[2048];
    unsigned lba, size;
    return GameFiles_FindFile(file, "SLUS_014.11", &lba, &size) && size > 2048 && size < (4u << 20) &&
           GameFiles_ReadSector(file, lba, sector) && !memcmp(sector, "PS-X EXE", 8);
}

/* Copies the open document to `to` (through to.tmp): 1 when it was. */
static int copy_disc(FILE *from, Sint64 size, const char *to, char *why, size_t why_size)
{
    char temporary[1100];
    static unsigned char buffer[1 << 20];
    struct statvfs space;
    char folder[1024], *slash;
    FILE *out;
    Sint64 done = 0;
    int ok;
    snprintf(folder, sizeof(folder), "%s", to);
    if ((slash = strrchr(folder, '/')) != NULL) *slash = '\0';
    if (!statvfs(folder, &space) && (Sint64)space.f_bavail * (Sint64)space.f_frsize < size + (16 << 20)) {
        snprintf(why, why_size, "There is not enough free space for the disc image: it needs %lld MB, and %lld MB "
                 "are free.", (long long)(size >> 20), (long long)((Sint64)space.f_bavail * space.f_frsize >> 20));
        return 0;
    }
    snprintf(temporary, sizeof(temporary), "%s.tmp", to);
    if (!(out = fopen(temporary, "wb"))) {
        snprintf(why, why_size, "Could not write the disc image to %s: %s", folder, strerror(errno));
        return 0;
    }
    rewind(from);
    for (;;) {
        size_t got = fread(buffer, 1, sizeof(buffer), from);
        if (!got) break;
        if (fwrite(buffer, 1, got, out) != got) break;
        done += (Sint64)got;
        if (!(done & ((64 << 20) - 1))) fprintf(stderr, "memories-pc: copying the disc image: %lld of %lld MB\n",
                                                 (long long)(done >> 20), (long long)(size >> 20));
    }
    ok = !ferror(from) && !ferror(out) && (size <= 0 || done == size);
    if (fclose(out)) ok = 0;
    if (!ok || rename(temporary, to)) {
        snprintf(why, why_size, "Could not copy the disc image into %s (%s).", folder,
                 ok ? strerror(errno) : "a read or a write failed");
        remove(temporary);
        return 0;
    }
    fprintf(stderr, "memories-pc: disc image copied to %s (%lld MB)\n", to, (long long)(done >> 20));
    return 1;
}

/* First run (game_files.h): the picker offers the documents the system can
 * reach (Downloads, SD cards, cloud drives); the chosen image is checked
 * where it is and then copied into the app's game/ folder, since the right
 * to read a picked document does not outlast the app. A file that is not
 * the disc says so and the picker comes back, as on the desktop. */
int Platform_SelectDisc(char *path, size_t size, char *why, size_t why_size)
{
    static const SDL_MessageBoxButtonData buttons[] = {
        {SDL_MESSAGEBOX_BUTTON_ESCAPEKEY_DEFAULT, 0, "Quit"},
        {SDL_MESSAGEBOX_BUTTON_RETURNKEY_DEFAULT, 1, "Choose disc image..."}
    };
    /* Any document: the system knows no type for a .bin, and the image is
     * checked by what it holds. */
    static const SDL_DialogFileFilter filters[] = {{"PlayStation disc image (.bin)", "*"}};
    const SDL_MessageBoxData welcome = {
        SDL_MESSAGEBOX_INFORMATION, NULL, "Welcome to Forbidden Memories Recompiled",
        "Choose your copy of Yu-Gi-Oh! Forbidden Memories to begin.\n\n"
        "Select the .bin file of your USA disc (SLUS-01411), the .bin of a .bin/.cue pair.\n\n"
        "The game copies it into its own folder (about 500 MB), so you can remove the file you chose afterwards.",
        2, buttons, NULL
    };
    char target[1024];
    int result = 0;
    if (!SDL_InitSubSystem(SDL_INIT_VIDEO)) {
        snprintf(why, why_size, "Could not open ROM setup: %s", SDL_GetError());
        return -1;
    }
    for (;;) {
        Picked pick;
        int button = 0;
        SDL_IOStream *stream;
        FILE *file;
        memset(&pick, 0, sizeof(pick));
        if (!SDL_ShowMessageBox(&welcome, &button)) {
            snprintf(why, why_size, "Could not open ROM setup: %s", SDL_GetError());
            result = -1;
            break;
        }
        if (button != 1) {
            result = 0;
            break;
        }
        SDL_ShowOpenFileDialog(picked, &pick, NULL, filters, 1, NULL, false);
        while (!SDL_GetAtomicInt(&pick.done)) {
            SDL_PumpEvents();
            SDL_Delay(10);
        }
        if (pick.result < 0) {
            snprintf(why, why_size, "Could not open the file picker: %s", SDL_GetError());
            result = -1;
            break;
        }
        if (!pick.result) continue; /* backed out of the picker: the welcome again */
        fprintf(stderr, "memories-pc: chosen: %s\n", pick.uri);
        stream = SDL_IOFromFile(pick.uri, "rb");
        file = stream ? SDL_GetPointerProperty(SDL_GetIOProperties(stream), SDL_PROP_IOSTREAM_STDIO_FILE_POINTER, NULL)
                      : NULL;
        if (!file || !is_the_disc(file)) {
            snprintf(why, why_size, "That file could not be read as a Forbidden Memories (USA, SLUS-01411) disc.\n\n"
                     "Choose the raw .bin file from your .bin/.cue pair, rather than the .cue file.");
            if (stream) SDL_CloseIO(stream);
            Platform_ShowError("Unable to use this ROM", why);
            continue;
        }
        if (Paths_User(target, sizeof(target), "game/rpg-yfm.bin") ||
            !copy_disc(file, SDL_GetIOSize(stream), target, why, why_size)) {
            SDL_CloseIO(stream);
            Platform_ShowError("Unable to use this ROM", why);
            continue;
        }
        SDL_CloseIO(stream);
        if (strlen(target) >= size) {
            snprintf(why, why_size, "The ROM path is too long.");
            result = -1;
            break;
        }
        snprintf(path, size, "%s", target);
        result = 1;
        break;
    }
    SDL_QuitSubSystem(SDL_INIT_VIDEO);
    return result;
}

/* The game's memory sits at fixed addresses up to 0xB0800000 (image.c).
 * A 32-bit process has 4 GB to place them in on a 64-bit kernel (phones
 * that still run 32-bit apps), and only 3 GB on a 32-bit kernel, where the
 * system's libraries already fill the top of it before the game runs. The
 * failed mapping is what counts; the process's own stack, which the
 * kernel puts at the top of that space, only tells which it was: past
 * 0xC0000000 there is room for 4 GB. (uname is no help: a 32-bit process
 * on a 64-bit x86 kernel is told "i686".) */
static int four_gigabytes(void)
{
    char line[512];
    FILE *maps = fopen("/proc/self/maps", "r");
    unsigned long start, end;
    int yes = -1;
    if (!maps) return -1;
    while (fgets(line, sizeof(line), maps)) {
        if (strstr(line, "[stack]") && sscanf(line, "%lx-%lx", &start, &end) == 2) {
            yes = end > 0xC0000000ul;
            break;
        }
    }
    fclose(maps);
    return yes;
}

int Platform_GuestMemoryHelp(char *why, size_t size)
{
    if (four_gigabytes() == 0) {
        fprintf(stderr, "memories-pc: this is a 32-bit kernel (3 GB for the app): the guest memory cannot be placed\n");
        snprintf(why, size, "This Android is 32-bit.\n\n"
                 "The game needs a 64-bit Android that can still run 32-bit apps: on a 32-bit system there is no "
                 "room for the memory the game runs in.");
    } else {
        snprintf(why, size, "The game could not reserve the memory it runs in at its fixed addresses on this "
                 "device.\n\nPlease report it with the app's log (adb logcat -s memories).");
    }
    return 1;
}

int Platform_RestartGame(void)
{
    fprintf(stderr, "memories-pc: restarting is not available on Android yet; close the app and open it again\n");
    return -1;
}

static int log_pipe[2];

static void *forward_log(void *unused)
{
    char buffer[1024];
    size_t used = 0;
    ssize_t got;
    (void)unused;
    while ((got = read(log_pipe[0], buffer + used, sizeof(buffer) - 1 - used)) > 0) {
        char *line = buffer, *end;
        used += (size_t)got;
        buffer[used] = '\0';
        while ((end = memchr(line, '\n', used - (size_t)(line - buffer))) != NULL) {
            *end = '\0';
            __android_log_write(ANDROID_LOG_INFO, LOG_TAG, line);
            line = end + 1;
        }
        used -= (size_t)(line - buffer);
        memmove(buffer, line, used);
        if (used == sizeof(buffer) - 1) { /* a line longer than the buffer: in pieces */
            buffer[used] = '\0';
            __android_log_write(ANDROID_LOG_INFO, LOG_TAG, buffer);
            used = 0;
        }
    }
    return NULL;
}

static void log_to_logcat(void)
{
    pthread_t thread;
    if (pipe(log_pipe)) return;
    setvbuf(stdout, NULL, _IOLBF, 0);
    setvbuf(stderr, NULL, _IONBF, 0);
    dup2(log_pipe[1], STDOUT_FILENO);
    dup2(log_pipe[1], STDERR_FILENO);
    if (pthread_create(&thread, NULL, forward_log, NULL) == 0) pthread_detach(thread);
}

/* An app gets no environment of its own: environment.txt in the player's
 * folder, NAME=value per line, stands in for the MEMORIES_* variables the
 * desktop builds read (tracing, scripted input, frame dumps). For testing;
 * adb can put the file there. */
static void read_environment(const char *folder)
{
    char path[1024], line[1024];
    FILE *file;
    snprintf(path, sizeof(path), "%s/environment.txt", folder);
    if (!(file = fopen(path, "r"))) return;
    while (fgets(line, sizeof(line), file)) {
        char *equals = strchr(line, '=');
        line[strcspn(line, "\r\n")] = '\0';
        if (!equals || equals == line || line[0] == '#') continue;
        *equals = '\0';
        setenv(line, equals + 1, 1);
        fprintf(stderr, "memories-pc: environment.txt: %s=%s\n", line, equals + 1);
    }
    fclose(file);
}

/* An APK asset (a path under assets/) copied to `to`; 1 when it was. */
static int copy_asset(const char *asset, const char *to)
{
    size_t size = 0;
    void *data = SDL_LoadFile(asset, &size); /* relative: the internal folder, then the assets */
    char temporary[1100];
    FILE *file;
    int written;
    if (!data) return 0;
    snprintf(temporary, sizeof(temporary), "%s.tmp", to);
    written = (file = fopen(temporary, "wb")) != NULL && fwrite(data, 1, size, file) == size;
    if (file && fclose(file)) written = 0;
    SDL_free(data);
    if (!written || rename(temporary, to)) {
        remove(temporary);
        return 0;
    }
    return 1;
}

/* The build's files out of the APK into <internal>/program, when this build
 * has not unpacked them yet (its buildid differs). Symbol tables of earlier
 * builds stay: a state saved by one of them is carried over by name
 * (state.c). The asset paths (build/...) are not the unpacked ones, since
 * SDL looks in the internal folder before the assets. */
static void unpack_program(void)
{
    const char *internal = SDL_GetAndroidInternalStoragePath();
    char directory[900], path[1100], asset[200], id[32] = "", have[32] = "";
    size_t size = 0;
    char *text;
    FILE *file;
    int ok;
    if (!internal || !*internal) return;
    snprintf(directory, sizeof(directory), "%s/program", internal);
    if ((text = SDL_LoadFile("build/buildid", &size)) != NULL) {
        snprintf(id, sizeof(id), "%.*s", (int)(size < sizeof(id) ? size : sizeof(id) - 1), text);
        id[strcspn(id, "\r\n")] = '\0';
        SDL_free(text);
    }
    snprintf(path, sizeof(path), "%s/buildid", directory);
    if ((file = fopen(path, "r")) != NULL) {
        if (fgets(have, sizeof(have), file)) have[strcspn(have, "\r\n")] = '\0';
        fclose(file);
    }
    if (!id[0]) {
        fprintf(stderr, "memories-pc: the APK has no build/buildid; save states cannot tell builds apart\n");
    } else if (strcmp(id, have)) {
        snprintf(path, sizeof(path), "%s/symbols", directory);
        Paths_MakeDirs(path);
        snprintf(asset, sizeof(asset), "build/symbols/%s.txt", id);
        snprintf(path, sizeof(path), "%s/symbols/%s.txt", directory, id);
        ok = copy_asset(asset, path);
        snprintf(path, sizeof(path), "%s/commit", directory);
        copy_asset("build/commit", path);
        snprintf(path, sizeof(path), "%s/buildid", directory);
        ok = ok && copy_asset("build/buildid", path); /* last: it marks the rest as there */
        fprintf(stderr, "memories-pc: build %s %s %s\n", id, ok ? "unpacked into" : "could not be unpacked into",
                directory);
    }
    setenv("MEMORIES_PROGRAM_DIR", directory, 0);
}

/* The loader could not put the game where it was linked (android_loader.c):
 * the addresses in a state saved now would not hold in the next launch, nor
 * those of the states saved before in this one. States then go to a folder
 * of this launch alone, emptied at the start. */
static void check_load_bias(void)
{
    const char *bias = getenv("MEMORIES_ANDROID_LOAD_BIAS");
    const char *cache = SDL_GetAndroidCachePath();
    char directory[900], path[1100];
    DIR *folder;
    struct dirent *entry;
    if (!bias || !strcmp(bias, "0") || !cache) return;
    snprintf(directory, sizeof(directory), "%s/states-this-launch", cache);
    if ((folder = opendir(directory)) != NULL) {
        while ((entry = readdir(folder)) != NULL) {
            if (entry->d_name[0] == '.') continue;
            snprintf(path, sizeof(path), "%s/%s", directory, entry->d_name);
            remove(path);
        }
        closedir(folder);
    }
    Paths_MakeDirs(directory);
    setenv("MEMORIES_STATE_DIR", directory, 1);
    fprintf(stderr, "memories-pc: the game is loaded %s bytes from its link address; save states are kept for "
                    "this launch only (%s)\n", bias, directory);
}

/* Called by the loader (android_loader.c) in place of SDL_main. */
int Memories_AndroidMain(int argc, char **argv)
{
    static char name[] = "memories-pc";
    char *args[] = {name, NULL};
    const char *files = SDL_GetAndroidExternalStoragePath();
    (void)argc;
    (void)argv;
    log_to_logcat();
    if (files && *files) {
        setenv("MEMORIES_USER_DIR", files, 0);
        read_environment(files);
    } else {
        fprintf(stderr, "memories-pc: no external files folder (%s)\n", SDL_GetError());
    }
    unpack_program();
    check_load_bias();
    /* The window is resizable, which SDL takes for "any orientation";
     * the game is a landscape picture. */
    SDL_SetHint(SDL_HINT_ORIENTATIONS, "LandscapeLeft LandscapeRight");
    /* Back is the game's to answer (sdl.c: menus, notices, then the quit
     * question), not the system's, which would end the activity at once. */
    SDL_SetHint(SDL_HINT_ANDROID_TRAP_BACK_BUTTON, "1");
    /* The whole screen, without the status and navigation bars (SDL makes
     * a fullscreen window immersive). */
    setenv("MEMORIES_FULLSCREEN", "1", 0);
    setenv("MEMORIES_NO_MONITOR", "1", 0);
    setenv("MEMORIES_NO_UPDATE_CHECK", "1", 0);
    {
        /* Where the game is: its link address when the loader's range held
         * (load bias 0), so crash addresses are the build's symbols' own. */
        Dl_info info;
        fprintf(stderr, "memories-pc: Android, user folder %s, libgame.so at %p (load bias %s)\n",
                getenv("MEMORIES_USER_DIR") ? getenv("MEMORIES_USER_DIR") : "?",
                dladdr((void *)Memories_AndroidMain, &info) ? info.dli_fbase : NULL,
                getenv("MEMORIES_ANDROID_LOAD_BIAS") ? getenv("MEMORIES_ANDROID_LOAD_BIAS") : "?");
    }
    return main(1, args);
}
#endif
