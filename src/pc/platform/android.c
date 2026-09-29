/* Android: the thin layer the port needs there, as win32.c is Windows'
 * (notes/pc-build.md, "Android"). Everything else is the Linux code: the
 * guest image, the fault handler, the clock and the SDL window (sdl.c).
 *
 * The app is SDL's Java shell (org.libsdl.app.SDLActivity, packaged by
 * tools/pc/package_android.py). It loads libSDL3.so and libmain.so, this
 * game, and calls SDL_main on a thread of its own; SDL_main sets up what an
 * app process differs in and runs the port's main.
 *
 * - The player's folder is the app's external files folder
 *   (/sdcard/Android/data/<package>/files): the disc image goes in its
 *   game/ folder, as beside the desktop executable (game_files.c), and adb
 *   can put it there.
 * - stdout and stderr, where the port reports, go nowhere in an app: they
 *   are forwarded to the system log (adb logcat -s memories).
 * - No crash monitor process and no restart: both re-execute the program,
 *   and an app process is the zygote's, not a program of its own.
 * - No update check yet, and no desktop OpenGL (platform.h). */
#ifdef __ANDROID__
#include "platform.h"
#include <SDL3/SDL.h>
#include <android/log.h>
#include <dlfcn.h>
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

int SDL_main(int argc, char **argv)
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
    /* The window is resizable, which SDL takes for "any orientation";
     * the game is a landscape picture. */
    SDL_SetHint(SDL_HINT_ORIENTATIONS, "LandscapeLeft LandscapeRight");
    setenv("MEMORIES_NO_MONITOR", "1", 0);
    setenv("MEMORIES_NO_UPDATE_CHECK", "1", 0);
    {
        /* Where the system loaded this library: crash addresses minus this
         * are the offsets llvm-symbolizer and the build's symbols take. */
        Dl_info info;
        fprintf(stderr, "memories-pc: Android, user folder %s, libmain.so at %p\n",
                getenv("MEMORIES_USER_DIR") ? getenv("MEMORIES_USER_DIR") : "?",
                dladdr((void *)SDL_main, &info) ? info.dli_fbase : NULL);
    }
    return main(1, args);
}
#endif
