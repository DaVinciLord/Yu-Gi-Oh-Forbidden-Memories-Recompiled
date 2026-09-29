#include "pc/platform/quit_prompt.h"
#include "pc/platform/menu.h"
#include "pc/platform/settings.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

static int confirm = 1, notices;
static void (*notice_chosen)(int button, int *quit);

int Settings_Get(SettingId id)
{
    assert(id == SET_CONFIRM_QUIT);
    return confirm;
}
void Menu_ShowNotice(const char *title, const char *text, const char *const *buttons, int count, int focus,
                     void (*chosen)(int button, int *quit))
{
    (void)text;
    /* Quit, then Keep playing: focused and last, which Enter, Escape and
     * Circle press. */
    assert(!strcmp(title, "Quit the game?") && count == 2 && !strcmp(buttons[0], "Quit") &&
           !strcmp(buttons[1], "Keep playing") && focus == 1 && chosen);
    notices++;
    notice_chosen = chosen;
}

int main(void)
{
    int quit = 0;
    QuitPrompt_Request(&quit);
    assert(!quit && notices == 1);
    notice_chosen(1, &quit);
    assert(!quit);
    /* Asked again, it asks again; Quit ends the game. */
    QuitPrompt_Request(&quit);
    QuitPrompt_Request(&quit);
    assert(!quit && notices == 3);
    notice_chosen(0, &quit);
    assert(quit);
    /* Confirm before quitting off: straight out, no notice. */
    confirm = 0;
    quit = 0;
    QuitPrompt_Request(&quit);
    assert(quit && notices == 3);
    puts("quit prompt: asks, keeps playing, quits and skips the question when off passed");
    return 0;
}
