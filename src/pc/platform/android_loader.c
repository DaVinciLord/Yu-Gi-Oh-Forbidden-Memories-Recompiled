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
 * If the range cannot be had, the 64-bit game is not loaded at all (its
 * function addresses go into 4-byte guest slots: anywhere else it would run
 * broken), and the player is told so in a message box; the 32-bit one is
 * loaded where the system chooses and told so (MEMORIES_ANDROID_LOAD_BIAS):
 * it runs, but its save states cannot be carried to another launch
 * (notes/pc-build.md, "Android"). A failure ends the process: the app does
 * not just flash and close. */
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

/* What holds the part of [low, high) that the reservation could not have. */
static void say_occupants(uintptr_t low, uintptr_t high)
{
    char text[512], line[600];
    unsigned long start, end;
    FILE *maps = fopen("/proc/self/maps", "r");
    if (!maps) return;
    while (fgets(text, sizeof(text), maps))
        if (sscanf(text, "%lx-%lx", &start, &end) == 2 && start < high && end > low) {
            text[strcspn(text, "\n")] = 0;
            snprintf(line, sizeof(line), "memories-pc: occupied by %s", text);
            say(line);
        }
    fclose(maps);
}

/* A failure the player sees: the log, then SDL's message box (libSDL3.so,
 * which SDL's Java shell loaded before this library), then the process
 * ends, so the next launch starts afresh. */
static void fail(const char *text)
{
    typedef int (*ShowBox)(unsigned flags, const char *title, const char *message, void *window);
    void *sdl = dlopen("libSDL3.so", RTLD_NOW | RTLD_NOLOAD);
    ShowBox show = sdl ? (ShowBox)dlsym(sdl, "SDL_ShowSimpleMessageBox") : NULL;
    say(text);
    if (show) show(0x10u /* SDL_MESSAGEBOX_ERROR */, "YFM Re-Decomp", text, NULL);
    exit(1);
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
    /* MAP_FIXED_NOREPLACE: without it the address is a hint, which the
     * kernel may pass over even when the range is free (it did in a phone's
     * app process); kernels before 4.17 ignore the flag and take the hint. */
    reserved = mmap(base, MEMORIES_ANDROID_GAME_SPAN, PROT_NONE,
                    MAP_PRIVATE | MAP_ANONYMOUS | MAP_NORESERVE | MAP_FIXED_NOREPLACE, -1, 0);
    if (reserved == base) {
        android_dlextinfo extinfo;
        memset(&extinfo, 0, sizeof(extinfo));
        extinfo.flags = ANDROID_DLEXT_RESERVED_ADDRESS;
        extinfo.reserved_addr = base;
        extinfo.reserved_size = MEMORIES_ANDROID_GAME_SPAN;
        game = android_dlopen_ext(path, RTLD_NOW, &extinfo);
        if (!game) {
            snprintf(line, sizeof(line), "The game could not start: loading %s at %p failed: %s", path, base,
                     dlerror());
#if UINTPTR_MAX > 0xffffffffu
            fail(line);
#else
            say(line);
            munmap(reserved, MEMORIES_ANDROID_GAME_SPAN);
#endif
        }
    } else {
        snprintf(line, sizeof(line), "memories-pc: the game's address range at %p is taken (got %p)", base, reserved);
        say(line);
        if (reserved != MAP_FAILED) munmap(reserved, MEMORIES_ANDROID_GAME_SPAN);
        say_occupants((uintptr_t)base, (uintptr_t)base + MEMORIES_ANDROID_GAME_SPAN);
#if UINTPTR_MAX > 0xffffffffu
        /* Refused before anything of the game is loaded: elsewhere its
         * initialisers would run at an address it cannot work at. */
        snprintf(line, sizeof(line), "The game could not start: it needs the addresses %p-%p, which this phone "
                 "already uses for something else (the log lists what). Please report this, with the phone's "
                 "model and Android version.", base, (void *)((uintptr_t)base + MEMORIES_ANDROID_GAME_SPAN));
        fail(line);
#endif
    }
    if (!game && !(game = dlopen(path, RTLD_NOW))) {
        snprintf(line, sizeof(line), "The game could not start: cannot load %s: %s", path, dlerror());
        fail(line);
    }
    run = (GameMain)dlsym(game, "Memories_AndroidMain");
    if (!run) fail("The game could not start: libgame.so has no Memories_AndroidMain");
    {
        /* Where it went, against where it was linked: 0 when the
         * reservation held. */
        Dl_info info;
        if (dladdr((void *)run, &info)) bias = (long)((uintptr_t)info.dli_fbase - (uintptr_t)base);
    }
#if UINTPTR_MAX > 0xffffffffu
    /* 64-bit: the game's function addresses go into 4-byte guest slots, so
     * anywhere but its link address (below 4 GB) it would run broken. */
    if (bias) {
        snprintf(line, sizeof(line), "The game could not start: libgame.so was loaded %ld bytes from its link "
                 "address %p; the 64-bit game needs it there", bias, base);
        fail(line);
    }
#endif
    snprintf(line, sizeof(line), "%ld", bias);
    setenv("MEMORIES_ANDROID_LOAD_BIAS", line, 1);
    /* When the port's main returns (a problem before the game started, as
     * a desktop program's would), the process ends with it, so the next
     * launch starts afresh instead of SDL's Java shell finding a finished
     * main in a live process. The game's own quit ends it with exit too. */
    exit(run(argc, argv));
}
#endif
