/* Which folder Paths_UserDir picks when saves/ beside the game (where the
 * port keeps everything when it cannot make its own folder) holds saves.
 * Each case resolves in a child, since the answer is kept for the process.
 * The Linux folder stands in for Documents\My Games; the rule is the same. */
#define _POSIX_C_SOURCE 200809L
#include "pc/platform/paths.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "pc/compat/posix.h"
#include "scratch.h"
#ifndef _WIN32
#include <sys/wait.h>

static void touch(const char *path)
{
    FILE *file = fopen(path, "wb");
    assert(file && !fclose(file));
}

/* Paths_UserDir in a child whose working directory is `game`; 0 when it
 * named `expected`. */
static int resolves_to(const char *game, const char *expected)
{
    pid_t child = fork();
    int status;
    assert(child >= 0);
    if (!child) {
        if (chdir(game)) _exit(2);
        _exit(strcmp(Paths_UserDir(), expected) ? (fprintf(stderr, "got %s, wanted %s\n", Paths_UserDir(), expected), 1) : 0);
    }
    assert(waitpid(child, &status, 0) == child);
    return WIFEXITED(status) ? WEXITSTATUS(status) : -1;
}
#endif

int main(void)
{
#ifndef _WIN32
    char root[SCRATCH_MAX], data[SCRATCH_MAX + 16], folder[SCRATCH_MAX + 32], game[SCRATCH_MAX + 16],
        path[SCRATCH_MAX + 64];
    assert(scratch_dir(root, sizeof(root), "memories-user-dir"));
    snprintf(data, sizeof(data), "%s/data", root);
    snprintf(folder, sizeof(folder), "%s/YFM Re-Decomp", data);
    snprintf(game, sizeof(game), "%s/game", root);
    assert(!Paths_MakeDirs(folder) && !Paths_MakeDirs(game));
    assert(!unsetenv("MEMORIES_USER_DIR"));
    assert(!setenv("XDG_DATA_HOME", data, 1));

    /* Nothing beside the game: the folder. */
    assert(!resolves_to(game, folder));

    /* An older build's saves beside the game, the folder there but empty
     * (made later, or by something else): the saves win. */
    snprintf(path, sizeof(path), "%s/saves/saves", game);
    assert(!Paths_MakeDirs(path));
    snprintf(path, sizeof(path), "%s/saves/saves/slot03.sav", game);
    touch(path);
    assert(!resolves_to(game, "saves"));

    /* Only settings in the folder: still not saves. */
    snprintf(path, sizeof(path), "%s/settings.txt", folder);
    touch(path);
    assert(!resolves_to(game, "saves"));

    /* The memory card image older builds kept beside the game counts too. */
    snprintf(path, sizeof(path), "%s/saves/saves/slot03.sav", game);
    assert(!remove(path));
    snprintf(path, sizeof(path), "%s/saves/memcard1.mcd", game);
    touch(path);
    assert(!resolves_to(game, "saves"));

    /* Saves in the folder: the folder, whatever is beside the game. */
    snprintf(path, sizeof(path), "%s/saves", folder);
    assert(!Paths_MakeDirs(path));
    snprintf(path, sizeof(path), "%s/saves/slot01.sav", folder);
    touch(path);
    assert(!resolves_to(game, folder));
    puts("user dir: ok");
#else
    puts("user dir: skipped (Documents is the machine's own)");
#endif
    return 0;
}
