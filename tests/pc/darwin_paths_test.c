/* Run as separate processes because path roots are intentionally cached. */
#include "pc/platform/paths.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
int main(int argc, char **argv)
{
    assert(argc == 3);
    assert(!strcmp(Paths_ProgramDir(), argv[1]));
    assert(!strcmp(Paths_UserDir(), argv[2]));
    puts("Darwin executable and user paths passed");
}
