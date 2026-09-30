/* Included after the bridge state and hand_record helpers in rules.c. */
static int matches_requirement(int id, const TablesRitualRequirement *q) {
    int stats, atk, def;
    if (id <= 0 || id > CARD_TABLE_COUNT) return 0;
    if (card_type && card_type(id) >= CARD_TYPE_MAGIC) return 0;
    stats = gDuel_adwCardStats[id - 1];
    atk = (stats & CARD_STAT_VALUE_MASK) * CARD_STAT_SCALE;
    def = ((stats >> CARD_STAT_DEFENSE_SHIFT) & CARD_STAT_VALUE_MASK) * CARD_STAT_SCALE;
    if (q->card && id != q->card && (!base_id || base_id(id) != q->card)) return 0;
    if (q->type >= 0 && (!card_type || card_type(id) != q->type)) return 0;
    if (q->fusion_group && (!in_group || !in_group(id, q->fusion_group))) return 0;
    if (atk < q->min_attack || def < q->min_defense) return 0;
    if (q->max_attack >= 0 && atk > q->max_attack) return 0;
    if (q->max_defense >= 0 && def > q->max_defense) return 0;
    if (q->min_level >= 0 && (!card_level || card_level(id) < q->min_level)) return 0;
    if (q->max_level >= 0 && (!card_level || card_level(id) > q->max_level)) return 0;
    return !q->defense_gt_attack || def > atk;
}

static int specificity(const TablesRitualRequirement *q) {
    return (q->card ? 100 : 0) + (q->type >= 0) + !!q->fusion_group +
        !!q->min_attack + !!q->min_defense + (q->max_attack >= 0) +
        (q->max_defense >= 0) + (q->min_level >= 0) + (q->max_level >= 0) +
        !!q->defense_gt_attack;
}

/* Exhaustive assignment protects named-card slots and overlapping groups.
 * Use as many field materials as possible; then use the same printed-stat
 * economy as the field-only selector in the game. */
static int locate_requirements(const TablesRitualRequirement q[3]) {
    int cr[10], cw[10], cs[10], count = 0;
    int best[3] = {-1, -1, -1}, order[3] = {0, 1, 2};
    int a, b, c, i, j, n, r, stats, prefer_def;
    int best_hand = 4;
    for (i = 0; i < 3; i++)
        for (j = i + 1; j < 3; j++)
            if (specificity(&q[order[j]]) > specificity(&q[order[i]])) {
                n = order[i]; order[i] = order[j]; order[j] = n;
            }
    for (i = 0; i < DUEL_FIELD_ROW_SIZE; i++) {
        r = side * DUEL_CARD_SIDE_RECORD_COUNT + DUEL_FIELD_ROW_SIZE + i;
        if ((D_801A7AD8[r].flags & DUEL_CARD_FLAG_OCCUPIED) && D_801A7AD8[r].object) {
            cr[count] = r; cw[count] = 1; cs[count++] = i;
        }
    }
    for (i = 0; i < HAND_SIZE; i++) {
        r = hand_record(side, i);
        if (D_800E9FF0[side].hand[i] >= 0 && valid_record(r)) {
            cr[count] = r; cw[count] = 2; cs[count++] = i;
        }
    }
    stats = gDuel_adwCardStats[recipe_result - 1];
    prefer_def = ((stats >> CARD_STAT_DEFENSE_SHIFT) & CARD_STAT_VALUE_MASK) > (stats & CARD_STAT_VALUE_MASK);
    for (a = 0; a < count; a++) for (b = 0; b < count; b++) for (c = 0; c < count; c++) {
        int selected[3] = {a, b, c};
        int hands, better;
        if (cr[a] == cr[b] || cr[a] == cr[c] || cr[b] == cr[c]) continue;
        hands = (cw[a] == 2) + (cw[b] == 2) + (cw[c] == 2);
        if (hands == 3 || hands > best_hand) continue;
        for (i = 0; i < 3; i++)
            if (!matches_requirement(D_801A7AD8[cr[selected[i]]].card_id, &q[i])) break;
        if (i != 3) continue;
        better = best[0] < 0 || hands < best_hand;
        for (i = 0; i < 3 && !better; i++) {
            int x = selected[order[i]], y = best[order[i]];
            int xs = gDuel_adwCardStats[D_801A7AD8[cr[x]].card_id - 1];
            int ys = gDuel_adwCardStats[D_801A7AD8[cr[y]].card_id - 1];
            int xa = xs & CARD_STAT_VALUE_MASK, ya = ys & CARD_STAT_VALUE_MASK;
            int xd = (xs >> CARD_STAT_DEFENSE_SHIFT) & CARD_STAT_VALUE_MASK;
            int yd = (ys >> CARD_STAT_DEFENSE_SHIFT) & CARD_STAT_VALUE_MASK;
            int px = prefer_def ? xd : xa, py = prefer_def ? yd : ya;
            int sx = prefer_def ? xa : xd, sy = prefer_def ? ya : yd;
            if (px != py) { better = px < py; break; }
            if (sx != sy) { better = sx < sy; break; }
            if (x != y) { better = x < y; break; }
        }
        if (better) { best[0] = a; best[1] = b; best[2] = c; best_hand = hands; }
    }
    if (best[0] < 0) return 0;
    for (i = 0; i < 3; i++) {
        n = best[i]; where[i] = cw[n]; slot[i] = cs[n]; rec[i] = cr[n];
        obj[i] = (unsigned)(u32)D_801A7AD8[rec[i]].object;
    }
    return 1;
}
