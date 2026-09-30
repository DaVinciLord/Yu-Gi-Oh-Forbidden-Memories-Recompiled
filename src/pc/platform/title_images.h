#ifndef MEMORIES_PC_PLATFORM_TITLE_IMAGES_H
#define MEMORIES_PC_PLATFORM_TITLE_IMAGES_H
/* The title's pictures of a mod's own (title_images.c): the background and
 * the logo, copyright and PUSH START BUTTON, each a PNG drawn instead of the
 * game's. */
#include "title_config.h"

enum { TITLE_IMAGE_BACKGROUND, TITLE_IMAGE_LOGO, TITLE_IMAGE_COPYRIGHT, TITLE_IMAGE_PROMPT, TITLE_IMAGES };

/* Made from `config` and put in VRAM, once the title's own pictures are
 * there (MainMenu_InitFrontendMenu); one that cannot be read is reported
 * on the console and the game's own picture shows. */
void TitleImages_Prepare(const TitleConfig *config);
/* Whether picture `which` is the mod's this time, and its size in the
 * game's pixels. */
int TitleImages_Ready(int which, int *width, int *height);
/* Draws it at x, y (its top left, in the game's 320 x 240) in colour r, g,
 * b (128 each as it is) into ordering table `ot` at `depth`. */
void TitleImages_Draw(int which, void *ot, int depth, int x, int y, int r, int g, int b);
#endif
