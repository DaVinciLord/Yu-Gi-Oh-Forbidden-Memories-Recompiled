/* Android: libmain.so, the library SDL's Java shell loads and whose SDL_main
 * it runs, is only this loader. The game is libgame.so, linked at a fixed
 * base (MEMORIES_ANDROID_GAME_BASE, set by build_game32.py), and loaded here
 * into a range reserved at that very address, so it sits where it was
 * linked on every launch: the addresses a save state holds (return
 * addresses on the game stack, callbacks in guest RAM, the game's variables)
 * and the build's symbol tables (crash reports) mean the same thing from one
 * launch to the next, as they do for the desktop executables. The system
 * would otherwise load it at a different address each time.
 *
 * If the range cannot be had, the game is loaded where the system chooses
 * and told so (MEMORIES_ANDROID_LOAD_BIAS): it runs, but its save states
 * cannot be carried to another launch (notes/pc-build.md, "Android"). */
#ifdef __ANDROID__
#include "pc/compat/fs.h" /* setenv, as every unit that names a file or a variable */
#include <android/dlext.h>
#include <android/log.h>
#include <dlfcn.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>

#ifndef MEMORIES_ANDROID_GAME_BASE
#error "build_game32.py defines MEMORIES_ANDROID_GAME_BASE and MEMORIES_ANDROID_GAME_SPAN"
#endif

#define LOG_TAG "memories"

typedef int (*GameMain)(int argc, char **argv);

static void say(const char *text)
{
    __android_log_write(ANDROID_LOG_INFO, LOG_TAG, text);
}

/* libgame.so beside this library (the app's native library folder). */
static int game_path(char *out, size_t size)
{
    Dl_info info;
    const char *slash;
    if (!dladdr((void *)game_path, &info) || !info.dli_fname || !(slash = strrchr(info.dli_fname, '/'))) return -1;
    return snprintf(out, size, "%.*s/libgame.so", (int)(slash - info.dli_fname), info.dli_fname) < (int)size ? 0 : -1;
}

int SDL_main(int argc, char **argv)
{
    char path[1024], line[1200];
    void *base = (void *)(uintptr_t)MEMORIES_ANDROID_GAME_BASE, *reserved, *game = NULL;
    GameMain run;
    long bias = 0;
    if (game_path(path, sizeof(path))) snprintf(path, sizeof(path), "libgame.so");
    reserved = mmap(base, MEMORIES_ANDROID_GAME_SPAN, PROT_NONE, MAP_PRIVATE | MAP_ANONYMOUS | MAP_NORESERVE, -1, 0);
    if (reserved == base) {
        android_dlextinfo extinfo;
        memset(&extinfo, 0, sizeof(extinfo));
        extinfo.flags = ANDROID_DLEXT_RESERVED_ADDRESS;
        extinfo.reserved_addr = base;
        extinfo.reserved_size = MEMORIES_ANDROID_GAME_SPAN;
        game = android_dlopen_ext(path, RTLD_NOW, &extinfo);
        if (!game) {
            snprintf(line, sizeof(line), "memories-pc: loading %s at %p: %s", path, base, dlerror());
            say(line);
            munmap(reserved, MEMORIES_ANDROID_GAME_SPAN);
        }
    } else {
        snprintf(line, sizeof(line), "memories-pc: the game's address range at %p is taken (got %p)", base, reserved);
        say(line);
        if (reserved != MAP_FAILED) munmap(reserved, MEMORIES_ANDROID_GAME_SPAN);
    }
    if (!game && !(game = dlopen(path, RTLD_NOW))) {
        snprintf(line, sizeof(line), "memories-pc: cannot load %s: %s", path, dlerror());
        say(line);
        return 1;
    }
    run = (GameMain)dlsym(game, "Memories_AndroidMain");
    if (!run) {
        say("memories-pc: libgame.so has no Memories_AndroidMain");
        return 1;
    }
    {
        /* Where it went, against where it was linked: 0 when the
         * reservation held. */
        Dl_info info;
        if (dladdr((void *)run, &info)) bias = (long)((uintptr_t)info.dli_fbase - (uintptr_t)base);
    }
    snprintf(line, sizeof(line), "%ld", bias);
    setenv("MEMORIES_ANDROID_LOAD_BIAS", line, 1);
    /* When the port's main returns (a problem before the game started, as
     * a desktop program's would), the process ends with it, so the next
     * launch starts afresh instead of SDL's Java shell finding a finished
     * main in a live process. The game's own quit ends it with exit too. */
    exit(run(argc, argv));
}
#endif
