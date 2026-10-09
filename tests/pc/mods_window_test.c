/* Real loader/settings, fake font and restart: verify staged UI behavior. */
#define main original_mods_test
#include "pc/compat/fs.h"
#include "mods_test.c"
#undef main
#include "pc/platform/mods_window.h"
#include "pc/mods/overlap.h"
static int restarts;
int Menu_Scale(void) { return 1; }
int Menu_TextWidthScaled(const char *s, int scale) { return (int)strlen(s) * 7 * scale; }
/* What a draw wrote, while `capture` is on: each string, its color and
 * the middle of its line (in the canvas it was drawn on). */
static int capture;
static char drawn[16384];
static int drawn_y(const char *part)
{
    const char *at = strstr(drawn, part), *line;
    if (!at) return -1;
    for (line = at; line > drawn && line[-1] != '\n'; line--) {
    }
    return atoi(line);
}
void Menu_DrawTextScaled(MenuCanvas *c, int x, int y, const char *s, uint32_t color, int scale)
{
    (void)c;
    (void)x;
    (void)scale;
    if (capture && strlen(drawn) + strlen(s) + 32 < sizeof(drawn))
        snprintf(drawn + strlen(drawn), sizeof(drawn) - strlen(drawn), "%d %06x %s\n", y, (unsigned)color, s);
}
static void draw(int w, int h)
{
    MenuCanvas canvas = {0};
    canvas.width = canvas.stride = w;
    canvas.height = h;
    canvas.pixels = calloc((size_t)w * h, 4);
    assert(canvas.pixels);
    drawn[0] = 0;
    capture = 1;
    ModsWindow_Draw(&canvas);
    capture = 0;
    free(canvas.pixels);
}
static char opened[1024];
int Platform_OpenFolder(const char *path)
{
    snprintf(opened, sizeof(opened), "%s", path);
    return 0;
}
int Platform_RestartGame(void)
{
    restarts++;
    return -1;
}
static int input(MenuEventType type, int x, int y, MenuKey key, const char *text)
{
    MenuEvent e = {0};
    e.type = type;
    e.x = x;
    e.y = y;
    e.button = 1;
    e.key = key;
    if (text)
        snprintf(e.text, sizeof(e.text), "%s", text);
    return ModsWindow_Event(&e);
}
static int click(int x, int y) { return input(MENU_EVENT_BUTTON_DOWN, x, y, MENU_KEY_OTHER, NULL); }
/* menu.h's UTF-8 cuts: never inside a character. */
static void test_text_cuts(void)
{
    const char *word = "Portugu\xC3\xAAs"; /* "Português": ê is bytes 7-8 */
    char cut[16];
    assert(Menu_TextBack(word, 9) == 7);
    assert(Menu_TextBack(word, 7) == 6);
    assert(Menu_TextBack(word, 0) == 0);
    assert(Menu_TextFit(word, 8) == 7);
    assert(Menu_TextFit(word, 9) == 9);
    {
        /* Ends before `length`: a buffer that long, as a caller's is (gcc
         * reads the string literal's 11 bytes as out of bounds for 50). */
        static const char padded[64] = "Portugu\xC3\xAAs";
        assert(Menu_TextFit(padded, 50) == 10);
    }
    memcpy(cut, word, 8); /* "Portugu" and the first byte of ê */
    cut[8] = '\0';
    Menu_TextTrim(cut);
    assert(strcmp(cut, "Portugu") == 0);
    snprintf(cut, sizeof(cut), "%s", word);
    Menu_TextTrim(cut);
    assert(strcmp(cut, word) == 0);
    snprintf(cut, sizeof(cut), "a\xE2\x80");  /* a cut-short U+2014 */
    Menu_TextTrim(cut);
    assert(strcmp(cut, "a") == 0);
}
int main(void)
{
    char path[1024];
    int w, h;
    test_text_cuts();
    assert(scratch_dir(root, sizeof(root), "memories-mod-window"));
    make_dir("mods");
    for (int i = 0; i < 80; i++) {
        snprintf(path, sizeof(path), "mods/mod%02d", i);
        make_dir(path);
        snprintf(path, sizeof(path), "mods/mod%02d/mod.json", i);
        if (i == 2 || i == 3) { /* six fusion pairs both set: overlaps; mod03's first by its setting "on" */
            char json[2048] = "{\"settings\":[{\"key\":\"on\",\"type\":\"bool\",\"default\":1}],\"fusions\":[";
            for (int j = 0; j < 6; j++)
                snprintf(json + strlen(json), sizeof(json) - strlen(json), "%s{\"with\":[%d,%d],\"result\":%d%s}",
                         j ? "," : "", 100 + j, 200 + j, i, i == 3 && !j ? ",\"setting\":\"on\"" : "");
            strcat(json, "]}");
            write_text(path, json);
        } else if (i == 1) { /* more settings than the details show at once */
            char json[2048] = "{\"settings\":[";
            for (int j = 0; j < 12; j++)
                snprintf(json + strlen(json), sizeof(json) - strlen(json), "%s{\"key\":\"s%d\",\"type\":\"bool\"}",
                         j ? "," : "", j);
            strcat(json, "]}");
            write_text(path, json);
        } else
            write_text(path, i ? "{}"
                               : "{\"restart\":true,\"settings\":[{\"key\":\"speed\",\"label\":\"Speed\",\"default\":5,"
                                 "\"min\":0,\"max\":10}]}");
    }
    snprintf(path, sizeof(path), "%s/mods", root);
    setenv("MEMORIES_MODS_DIR", path, 1);
    snprintf(path, sizeof(path), "%s/settings.txt", root);
    setenv("MEMORIES_SETTINGS", path, 1);
    setenv("MEMORIES_USER_DIR", root, 1);
    Settings_Load();
    Mods_Load();
    assert(Mods_Count() == 80);
    assert(find("mod00") == 0);
    ModsWindow_Init();
    ModsWindow_Size(&w, &h);
    assert(w == 920 && h == 640);
    click(32, 160);
    assert(!Mods_Enabled(0)); /* staged */
    click(800, 610);
    assert(!restarts && !Mods_Enabled(0)); /* restart warning */
    click(680, 610);
    assert(!restarts); /* cancel warning */
    click(800, 610);
    click(800, 610);
    assert(restarts == 1 && Mods_Enabled(0));
    ModsWindow_Init();
    click(620, 238); /* settings tab */
    click(800, 357);
    input(MENU_EVENT_MOTION, 878, 357, MENU_KEY_OTHER, NULL);
    input(MENU_EVENT_BUTTON_UP, 878, 357, MENU_KEY_OTHER, NULL);
    assert(Mods_OptionValue(0, 0) == 5); /* slider edits are staged */
    click(800, 610);
    click(800, 610);
    assert(Mods_OptionValue(0, 0) == 10);
    click(790, 80); /* save Default profile */
    click(800, 165); /* disable */
    click(800, 610);
    click(800, 610);
    assert(!Mods_Enabled(0));
    click(860, 80);
    assert(!Mods_Enabled(0)); /* loading a profile is staged too */
    click(800, 610);
    click(800, 610);
    assert(Mods_Enabled(0) && Mods_OptionValue(0, 0) == 10);
    ModsWindow_Init();
    {
        /* Twelve settings scroll: by wheel, then by dragging the scrollbar. */
        int many = find("mod01");
        MenuEvent wheel = {0};
        wheel.type = MENU_EVENT_WHEEL;
        wheel.x = 600;
        wheel.y = 450;
        click(100, 142 + many * 58 + 20);
        click(620, 238);
        wheel.wheel = -1;
        for (int i = 0; i < 20; i++)
            ModsWindow_Event(&wheel);
        click(858, 505); /* the last setting's + */
        click(800, 610);
        assert(Mods_OptionValue(many, 11) == 1 && Mods_OptionValue(many, 0) == 0);
        wheel.wheel = 1;
        for (int i = 0; i < 20; i++)
            ModsWindow_Event(&wheel);
        click(889, 310);
        input(MENU_EVENT_MOTION, 889, 600, MENU_KEY_OTHER, NULL);
        input(MENU_EVENT_BUTTON_UP, 889, 600, MENU_KEY_OTHER, NULL);
        click(858, 505);
        click(800, 610);
        assert(Mods_OptionValue(many, 11) == 0 && Mods_OptionValue(many, 0) == 0);
    }
    ModsWindow_Init();
    click(50, 80);
    input(MENU_EVENT_TEXT, 0, 0, MENU_KEY_OTHER, "mod79");
    click(32, 160);
    click(800, 610);
    assert(Mods_Enabled(find("mod79"))); /* search actually filters */
    ModsWindow_Init();
    click(32, 160);
    assert(!input(MENU_EVENT_KEY_DOWN, 0, 0, MENU_KEY_ESCAPE, NULL));
    assert(input(MENU_EVENT_KEY_DOWN, 0, 0, MENU_KEY_ENTER, NULL)); /* explicit discard */
    assert(Mods_Enabled(0));
    ModsWindow_Init();
    click(50, 80); /* a focused search field does not hold the window open */
    assert(ModsWindow_RequestClose());
    ModsWindow_Init();
    click(32, 160);
    assert(!ModsWindow_RequestClose()); /* unsaved changes: asks first */
    assert(ModsWindow_RequestClose());  /* the second close discards */
    {
        MenuEvent motion = {0};
        motion.type = MENU_EVENT_MOTION;
        assert(!ModsWindow_Redraws(&motion)); /* plain pointer motion draws nothing */
    }
    ModsWindow_Init();
    click(550, 600); /* Open mods folder: the folder new mods are installed in */
    assert(!strcmp(opened, getenv("MEMORIES_MODS_DIR")));
    {
        /* What two enabled mods both change: in the header, and by kind in
         * the Compatibility tab, the first few lines, then the rest on a
         * press. The load order staged in the window decides who wins. */
        int more;
        ModsWindow_Init();
        click(32, 142 + 2 * 58 + 20); /* mod02 and mod03, staged */
        click(32, 142 + 3 * 58 + 20);
        click(800, 238); /* Compatibility */
        draw(920, 640);
        assert(strstr(drawn, "/  6 overlaps")); /* with the warnings when the line has room */
        assert(strstr(drawn, "Fusions: 6 (6 warnings)"));
        assert(strstr(drawn, "f4bd6a Fusion #100 + #200 (mod02, mod03): mod03 wins (later in load order)") ||
               strstr(drawn, "(mod02, mod03): mod03 wins (later in load order)"));
        assert(strstr(drawn, "...and 2 more: show them") && !strstr(drawn, "#105 + #205"));
        more = drawn_y("...and 2 more");
        click(600, 142 + 124 + more);
        draw(920, 640);
        assert(strstr(drawn, "#105 + #205") && strstr(drawn, "Show fewer"));
        click(100, 142 + 2 * 58 + 20); /* mod02 selected, and loaded after mod03 */
        click(856 + 14, 186 + 13);
        draw(920, 640);
        assert(strstr(drawn, "(mod03, mod02): mod02 wins (later in load order)"));
        click(32, 142 + 3 * 58 + 20); /* one of them off: nothing in common */
        draw(920, 640);
        assert(!strstr(drawn, "overlap") && strstr(drawn, "Enable this mod"));
        {
            /* A setting staged in the window, before Apply, switches mod03's
             * first fusion off: one overlap fewer. */
            int both[MODS_MAX] = {0}, off = 0, on = 1;
            const int *staged[MODS_MAX] = {0};
            both[2] = both[3] = 1;
            staged[3] = &on;
            assert(Mods_OverlapCount(Mods_Overlaps(both, NULL, staged)) == 6);
            staged[3] = &off;
            assert(Mods_OverlapCount(Mods_Overlaps(both, NULL, staged)) == 5);
            assert(Mods_OverlapCount(Mods_Overlaps(both, NULL, NULL)) == 6); /* saved: its default, on */
        }
    }
    ModsWindow_Init();
    ModsWindow_Resize(720, 480);
    ModsWindow_Size(&w, &h);
    assert(w == 720 && h == 480);
    MenuCanvas canvas = {0};
    canvas.width = w;
    canvas.height = h;
    canvas.stride = w;
    canvas.pixels = calloc((size_t)w * h, 4);
    assert(canvas.pixels);
    ModsWindow_Draw(&canvas);
    free(canvas.pixels);
    return 0;
}
