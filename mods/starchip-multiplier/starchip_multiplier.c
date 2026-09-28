/* Scales the end-of-duel StarChip prize through MEMORIES_EVENT_STARCHIP
 * (Mods_AwardStarchips). The results screen still draws the retail star
 * count; only the amount written into the save is multiplied. */
#include "pc/mods/modapi.h"

static const MemoriesModHost *host;

static void starchip(MemoriesModEvent *event)
{
    long long prize;
    int mult;

    if (event->phase != MEMORIES_BEFORE)
        return;
    mult = host->setting(host, "multiplier", 5);
    if (mult < 1)
        mult = 1;
    if (mult > 100)
        mult = 100;
    prize = (long long)event->a * mult;
    if (prize < 0)
        prize = 0;
    if (prize > 999999)
        prize = 999999;
    event->a = (int)prize;
}

int MemoriesModInit(const MemoriesModHost *from, MemoriesMod *mod)
{
    if (from->api < 6)
        return 0;
    host = from;
    mod->api = 6;
    return host->subscribe(host, MEMORIES_EVENT_STARCHIP, 0, starchip) != 0;
}
