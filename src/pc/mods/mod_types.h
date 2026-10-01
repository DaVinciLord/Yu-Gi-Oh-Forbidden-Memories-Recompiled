#ifndef MEMORIES_MOD_TYPES_H
#define MEMORIES_MOD_TYPES_H
#define MEMORIES_MOD_API 9
/* API 3: before hooks may alter arguments/result, or set handled to replace
 * the operation (including cancellation). Highest priority runs first;
 * equal priorities follow registration/load order. After hooks observe the
 * operation result. Input runs from VBlank (possibly interrupt context):
 * no allocation, file I/O or registration there. Keep all callbacks short. */
enum { MEMORIES_BEFORE, MEMORIES_AFTER };
enum {
    MEMORIES_EVENT_INPUT, MEMORIES_EVENT_DAMAGE, MEMORIES_EVENT_REWARD,
    MEMORIES_EVENT_FUSION, MEMORIES_EVENT_EFFECT, MEMORIES_EVENT_AI,
    MEMORIES_EVENT_SCENE, MEMORIES_EVENT_SAVE, MEMORIES_EVENT_LOAD,
    MEMORIES_EVENT_SETTINGS, MEMORIES_EVENT_EQUIP,
    /* API 4, after only: the save slot menu saved the running game (a slot,
     * from 0; b the slot's token, save_slots.h; c the save's sequence), or
     * loaded it (the same). What a mod keeps per save goes in its own file
     * named after the token (open_data), so each slot has its own. */
    MEMORIES_EVENT_SLOT_SAVE, MEMORIES_EVENT_SLOT_LOAD,
    /* API 6: end-of-duel StarChip prize about to be added to the save
     * (Mods_AwardStarchips). a is the retail prize (rank tier + 1); edit it
     * to change the award, or handle to skip adding. After observes result
     * as the amount actually credited. On-screen star icons stay retail. */
    MEMORIES_EVENT_STARCHIP,
    /* API 9: an item of the title's menus chosen (notes/modding.md, "The
     * title's menus"): a the item (0-10 the game's entries, as
     * MainMenuSelection; 11 on the mods' buttons, host->menu_item names
     * it), b the menu (0 the first, 1 the second), c the item's "value".
     * Before: set handled to do something else instead, and result to a
     * choice (MainMenuSelection, or a number of the mod's own that its
     * MEMORIES_EVENT_SCENE takes) to slide the menu out and leave the title
     * with it; result stays -1 to stay. After observes. An item whose
     * action is "event" does nothing but this. */
    MEMORIES_EVENT_MENU,
    MEMORIES_EVENT_COUNT
};
typedef struct {
    unsigned type, phase;
    int a, b, c, result, handled;
} MemoriesModEvent;
typedef void (*MemoriesModCallback)(MemoriesModEvent *event);

#endif
