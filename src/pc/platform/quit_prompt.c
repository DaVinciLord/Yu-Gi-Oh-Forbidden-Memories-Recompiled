/* Confirm before quitting (quit_prompt.h). The question is the menu's
 * notice, so it takes the mouse, the keyboard and, through Menu_NoticePad,
 * a controller; the game runs on behind it with its input held. */
#include "pc/platform/quit_prompt.h"
#include "pc/platform/menu.h"
#include "pc/platform/settings.h"

static void chosen(int button, int *quit)
{
    if (button == 0) *quit = 1;
}

void QuitPrompt_Request(int *quit)
{
    static const char *const buttons[] = {"Quit", "Keep playing"};
    if (!Settings_Get(SET_CONFIRM_QUIT)) {
        *quit = 1;
        return;
    }
    /* Keep playing is focused and last, so Enter, Escape and Circle all
     * stay in the game: only a deliberate Quit ends it. */
    Menu_ShowNotice("Quit the game?", "Progress since your last save is lost.", buttons, 2, 1, chosen);
}
