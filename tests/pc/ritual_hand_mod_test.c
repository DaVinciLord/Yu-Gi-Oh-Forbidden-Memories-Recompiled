/* Freestanding 32-bit test of the actual mod, including bridge consumption.
 * Run via tools/pc/test_ritual_hand_mod.py; no game/disc or libc needed. */
#include "../../user-mods/melhoria-dos-rituais/rules.c"

DuelCardRecord D_801A7AD8[DUEL_CARD_RECORD_COUNT];
DuelSideState D_800E9FF0[DUEL_SIDE_COUNT];
u8 D_8009B1D5;
u8 D_800907CC[12];
u8 D_800907D8[40];
s32 gDuel_adwCardStats[CARD_TABLE_COUNT];
u16 gDuel_awRitualData[10] = {665, 1, 2, 3, 362, 0};
static TablesRitualRequirement req[3];
static int mode, deactivated, accepted;

static int get_requirements(int id, TablesRitualRequirement *out, unsigned short *result) {
    int i;
    if (id != 665 || mode != 1) return 0;
    for (i = 0; i < 3; i++) out[i] = req[i];
    *result = 362;
    return 1;
}
static int get_recipe(int id, unsigned short *out) {
    int i;
    if (mode == 2) return 0;
    if (mode != 3) return -1;
    for (i = 0; i < 6; i++) out[i] = gDuel_awRitualData[i];
    out[1] = 4;
    return 1;
}
static s32 original(DuelRitualResult *out, s32 id) { (void)out; (void)id; return accepted; }
static void deactivate(DuelCardRecord *r) { deactivated++; r->flags = 0; }
static int type(int id) { return id == 665 ? CARD_TYPE_RITUAL : 0; }
static int level(int id) { (void)id; return 4; }
static int group(int id, int g) { return id == 2 && g == 1; }
static int base(int id) { return id == 6 ? 1 : id; }
static void stats(int id, int atk, int def) {
    gDuel_adwCardStats[id - 1] = atk / 10 | ((def / 10) << CARD_STAT_DEFENSE_SHIFT);
}
static void setup(int s) {
    int i, j;
    side = D_8009B1D5 = s;
    mode = 1; accepted = deactivated = 0;
    reset_bridge();
    o_check = original; o_deact = deactivate;
    custom_requirements = get_requirements; custom_recipe = get_recipe;
    card_type = type; card_level = level; in_group = group; base_id = base;
    for (i = 0; i < DUEL_CARD_RECORD_COUNT; i++) D_801A7AD8[i] = (DuelCardRecord){0};
    for (i = 0; i < 2; i++) for (j = 0; j < HAND_SIZE; j++) {
        D_800E9FF0[i].hand[j] = -1;
        D_800907CC[i * HAND_SIZE + j] = i * DUEL_CARD_SIDE_RECORD_COUNT + j;
    }
    for (i = 0; i < 40; i++) D_800907D8[i] = 255;
    for (i = 0; i < 3; i++) {
        req[i] = (TablesRitualRequirement){0};
        req[i].type = req[i].min_level = req[i].max_level = -1;
        req[i].max_attack = -1; req[i].max_defense = 2999;
        req[i].min_defense = 1000; req[i].defense_gt_attack = 1;
    }
    req[1].card = 1;
    stats(1, 700, 1300); stats(2, 500, 1000); stats(3, 1000, 2000);
    stats(4, 600, 1200); stats(6, 700, 1300); stats(362, 0, 3000);
}
static void field(int slot, int id) {
    int r = side * 15 + 5 + slot;
    D_801A7AD8[r].card_id = id;
    D_801A7AD8[r].flags = DUEL_CARD_FLAG_OCCUPIED;
    D_801A7AD8[r].object = (void *)(u32)(0x1000 + r * 32);
    D_800907D8[side * 20 + 10 + slot] = r;
}
static void hand(int slot, int id) {
    int r = hand_record(side, slot);
    D_801A7AD8[r].card_id = id;
    D_800E9FF0[side].hand[slot] = id;
}
#define CHECK(condition, code) do { if (!(condition)) return code; } while (0)
static int run(void) {
    DuelRitualResult out;
    int s, i, named;
    for (s = 0; s < 2; s++) {
        /* Named tribute overlaps the broad conditions, but is used once. */
        setup(s); field(0, 1); hand(0, 2); hand(1, 3);
        CHECK(ritual_check(0, 665) == 362 && !bridge_active, 1);
        out.field_0C = 99;
        CHECK(ritual_check(&out, 665) == 362 && bridge_active && out.field_0C == 0, 2);
        named = side * 15 + 5;
        CHECK(rec[1] == named && rec[0] != rec[2] && rec[0] != named && rec[2] != named, 3);
        for (i = 0; i < 3; i++) CHECK(out.tribute_objects[i] != 0, 4);
        for (i = 0; i < 3; i++) ritual_deactivate(&D_801A7AD8[named]);
        CHECK(deactivated == 1 && !bridge_active && D_801A7AD8[named].flags == 0, 5);
        CHECK(D_800E9FF0[side].hand[0] == -1 && D_800E9FF0[side].hand[1] == -1, 6);

        setup(s); field(0, 2); field(1, 1); hand(0, 3);
        CHECK(ritual_check(&out, 665) == 362, 7);
        for (i = 0; i < 3; i++) ritual_deactivate(&D_801A7AD8[side * 15 + 5]);
        CHECK(deactivated == 2 && D_800E9FF0[side].hand[0] == -1, 8);

        setup(s); hand(0, 1); hand(1, 2); hand(2, 3);
        CHECK(ritual_check(0, 665) == 0, 9); /* At least one on field. */
        setup(s); field(0, 1); hand(0, 2);
        CHECK(ritual_check(0, 665) == 0, 10); /* Never reuse a material. */
        setup(s); field(0, 1); hand(0, 2); hand(1, 3); stats(3, 1000, 3000);
        CHECK(ritual_check(0, 665) == 0, 11);
        stats(3, 2000, 2000);
        CHECK(ritual_check(0, 665) == 0, 12);
        stats(3, 500, 990);
        CHECK(ritual_check(0, 665) == 0, 13);
        stats(3, 500, 1000);
        CHECK(ritual_check(0, 665) == 362, 14);

        setup(s); field(0, 1); hand(0, 2); hand(1, 3); hand(2, 4);
        CHECK(ritual_check(0, 665) == 362 && rec[2] == hand_record(side, 2), 15);
        stats(362, 3000, 0); stats(3, 100, 2000);
        CHECK(ritual_check(0, 665) == 362 && rec[0] == hand_record(side, 1), 16);
        stats(362, 3000, 3000);
        CHECK(ritual_check(0, 665) == 362 && rec[0] == hand_record(side, 1), 17);

        /* All combined conditions are applied, including level and groups. */
        setup(s); field(0, 1); hand(0, 2); hand(1, 3);
        req[0].type = 0; req[0].fusion_group = 1; req[0].min_level = 4;
        req[0].max_level = 4; req[0].max_attack = 500;
        CHECK(ritual_check(0, 665) == 362, 18);
        req[0].min_level = 5;
        CHECK(ritual_check(0, 665) == 0, 19);

        /* Missing extension: keep the old original recipe path. */
        setup(s); custom_requirements = 0; custom_recipe = 0;
        field(0, 1); hand(0, 2); hand(1, 3);
        CHECK(ritual_check(0, 665) == 362, 20);
        setup(s); mode = 3; field(0, 4); hand(0, 2); hand(1, 3);
        CHECK(ritual_check(0, 665) == 362, 21);
        mode = 2;
        CHECK(ritual_check(0, 665) == 0, 22);
        accepted = 362;
        CHECK(ritual_check(&out, 665) == 362 && !bridge_active, 23);
        setup(s); field(0, 6); hand(0, 2); hand(1, 3);
        CHECK(ritual_check(0, 665) == 362, 24);
    }
    return 0;
}
void _start(void) {
    int result = run();
    __asm__ volatile ("int $0x80" : : "a"(1), "b"(result) : "memory");
    __builtin_unreachable();
}
