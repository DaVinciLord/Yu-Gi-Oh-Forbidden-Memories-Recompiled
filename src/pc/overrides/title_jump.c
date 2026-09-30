/* The retail game-over return sequence, called only between mode runners. */
#include "pc/platform/title_jump.h"
#include "pc/platform/title_screen.h"
#include "pc/platform/platform.h"
#include "types.h"
#include "game/display_object_core.h"
#include "game/fade.h"
#include "game/file_transfer.h"
#include "game/func_80035A64.h"
#include "game/main_modes.h"
#include "game/sound.h"
#include <stdio.h>

extern u8 D_8009B268, D_8009B26C, D_8009B26D;
extern int D_800E9DC0[];
void Psx_longjmp(int *env, int value);

void TitleJump_Execute(void)
{
    /* The credits are the one mode retail never leaves but by a console
     * reset: their presentation takes over what only the boot sets up (the
     * music buffer, the resident VRAM palettes; platform/title_jump.c), so
     * leaving them is a reset here too. */
    if ((D_8009B26C & 0x1F) == MAIN_MODE_CREDITS) {
        fprintf(stderr, "memories-pc: leaving the credits; restarting the game\n");
        Platform_RestartGame();
        fprintf(stderr, "memories-pc: the restart failed; back to the title screen instead\n");
    }
    fprintf(stderr, "memories-pc: back to the title screen from mode %u\n", D_8009B26C & 0x1F);
    File_WaitForTransfers();
    SD_BGMFadeOut();
    Fade_WaitOut();
    DisplayObject_Reset();
    func_80035A64();
    /* Out past MainMenu_DestroyFrontendMenu, if it is the title we leave. */
    TitleScreen_Closed();
    D_8009B268 = 1;
    D_8009B26D = 0;
    D_8009B26C = MAIN_MODE_MENU;
    Psx_longjmp(D_800E9DC0, 1);
}
