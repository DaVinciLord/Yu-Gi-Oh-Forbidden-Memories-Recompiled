#ifndef MEMORIES_PC_QUIT_PROMPT_H
#define MEMORIES_PC_QUIT_PROMPT_H

/* Every way out of the game the player asks for (Esc, File > Exit, the
 * window's close button or Alt+F4) comes here. With File >
 * Confirm before quitting (SET_CONFIRM_QUIT, on by default) the menu's
 * notice asks first (asked again, it is shown again); otherwise, or on
 * Quit, *quit is set as before. Main thread only. */
void QuitPrompt_Request(int *quit);

#endif
