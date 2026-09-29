/* The on-screen controller's layout, fingers and bits (touch_pad.h). */
#include "touch_pad.h"
#include <math.h>
#include <string.h>

#define FINGERS 10

typedef enum { ZONE_NONE, ZONE_DPAD, ZONE_FACE, ZONE_BUTTON } Zone;
typedef struct {
    int used;
    uint64_t id;
    Zone zone;
    TouchButton button; /* ZONE_BUTTON's */
    uint16_t bits;
} Finger;

/* PS1 pad bits, as Platform_Pad reports them. */
static const uint16_t bits_of[TOUCH_BUTTONS] = {
    [TOUCH_UP] = 0x0010, [TOUCH_RIGHT] = 0x0020, [TOUCH_DOWN] = 0x0040, [TOUCH_LEFT] = 0x0080,
    [TOUCH_TRIANGLE] = 0x1000, [TOUCH_CIRCLE] = 0x2000, [TOUCH_CROSS] = 0x4000, [TOUCH_SQUARE] = 0x8000,
    [TOUCH_L2] = 0x0100, [TOUCH_R2] = 0x0200, [TOUCH_L1] = 0x0400, [TOUCH_R1] = 0x0800,
    [TOUCH_SELECT] = 0x0001, [TOUCH_START] = 0x0008};

static int mode, touched, width, height, top;
static int rects[TOUCH_BUTTONS][4];
static int unit, dpad_x, dpad_y, face_x, face_y;
static Finger fingers[FINGERS];
static uint16_t held, tapped, presses;

uint16_t TouchPad_Bit(TouchButton button) { return button < TOUCH_BUTTONS ? bits_of[button] : 0; }

int TouchPad_Shown(void)
{
    return width > 0 && height > 0 && (mode == TOUCH_PAD_SHOW || (mode == TOUCH_PAD_AUTO && touched));
}

static void place(TouchButton button, int x, int y, int w, int h)
{
    rects[button][0] = x;
    rects[button][1] = y;
    rects[button][2] = w;
    rects[button][3] = h;
}

/* A button is about a thumb's width: 13% of the window's short side. The
 * D-pad and the face buttons sit in the middle of the left and right sides
 * (where the 4:3 picture leaves black bars on a phone), the shoulders above
 * them, SELECT and START below. */
static void lay_out(void)
{
    int s = (width < height ? width : height) * 13 / 100, m = s * 35 / 100, bottom;
    unit = s;
    dpad_x = m + s * 3 / 2;
    face_x = width - m - s * 3 / 2;
    dpad_y = face_y = top + (height - top) * 56 / 100;
    place(TOUCH_UP, dpad_x - s / 2, dpad_y - s * 3 / 2, s, s);
    place(TOUCH_DOWN, dpad_x - s / 2, dpad_y + s / 2, s, s);
    place(TOUCH_LEFT, dpad_x - s * 3 / 2, dpad_y - s / 2, s, s);
    place(TOUCH_RIGHT, dpad_x + s / 2, dpad_y - s / 2, s, s);
    place(TOUCH_TRIANGLE, face_x - s / 2, face_y - s * 3 / 2, s, s);
    place(TOUCH_CROSS, face_x - s / 2, face_y + s / 2, s, s);
    place(TOUCH_SQUARE, face_x - s * 3 / 2, face_y - s / 2, s, s);
    place(TOUCH_CIRCLE, face_x + s / 2, face_y - s / 2, s, s);
    place(TOUCH_L2, m, top + m / 2, s, s);
    place(TOUCH_L1, m + s * 23 / 20, top + m / 2, s, s);
    place(TOUCH_R1, width - m - s * 43 / 20, top + m / 2, s, s);
    place(TOUCH_R2, width - m - s, top + m / 2, s, s);
    bottom = height - m / 2;
    place(TOUCH_SELECT, dpad_x - s, bottom - s * 3 / 5, s * 2, s / 2);
    place(TOUCH_START, face_x - s * 4 / 5, bottom - s * 4 / 5, s * 8 / 5, s * 4 / 5);
}

int TouchPad_Layout(int window_w, int window_h, int bar)
{
    if (window_w == width && window_h == height && bar == top) return 0;
    width = window_w;
    height = window_h;
    top = bar;
    lay_out();
    return TouchPad_Shown();
}

int TouchPad_Rect(TouchButton button, int *x, int *y, int *w, int *h)
{
    if (!TouchPad_Shown() || button >= TOUCH_BUTTONS) return 0;
    *x = rects[button][0];
    *y = rects[button][1];
    *w = rects[button][2];
    *h = rects[button][3];
    return 1;
}

int TouchPad_Held(TouchButton button) { return button < TOUCH_BUTTONS && (held & bits_of[button]) != 0; }

static long distance2(int x, int y, int cx, int cy) { return (long)(x - cx) * (x - cx) + (long)(y - cy) * (y - cy); }

/* A button's rectangle, a little larger to aim at. */
static int in_button(TouchButton button, int x, int y)
{
    int grow = unit * 15 / 100;
    return x >= rects[button][0] - grow && y >= rects[button][1] - grow &&
           x < rects[button][0] + rects[button][2] + grow && y < rects[button][1] + rects[button][3] + grow;
}

static Zone zone_at(int x, int y, TouchButton *button)
{
    TouchButton b;
    long reach = (long)unit * unit * 4; /* two buttons from the middle */
    if (distance2(x, y, dpad_x, dpad_y) <= reach) return ZONE_DPAD;
    if (distance2(x, y, face_x, face_y) <= reach) return ZONE_FACE;
    for (b = TOUCH_L1; b < TOUCH_BUTTONS; b++) {
        if (in_button(b, x, y)) {
            *button = b;
            return ZONE_BUTTON;
        }
    }
    return ZONE_NONE;
}

/* What a finger of its zone presses at x, y. The D-pad goes by the angle
 * from its middle, so the diagonals between two arrows press both; the
 * face buttons by the nearest one. */
static uint16_t press_at(const Finger *finger, int x, int y)
{
    int dx = x - dpad_x, dy = y - dpad_y, i, nearest = -1;
    long best = 0;
    double length, c, s;
    static const TouchButton face[] = {TOUCH_TRIANGLE, TOUCH_CIRCLE, TOUCH_CROSS, TOUCH_SQUARE};
    uint16_t out = 0;
    switch (finger->zone) {
    case ZONE_DPAD:
        length = sqrt((double)dx * dx + (double)dy * dy);
        if (length < unit * 0.3) return 0; /* the middle presses nothing */
        c = dx / length;
        s = dy / length;
        if (c > 0.383) out |= bits_of[TOUCH_RIGHT]; /* 67.5 degrees each way */
        if (c < -0.383) out |= bits_of[TOUCH_LEFT];
        if (s > 0.383) out |= bits_of[TOUCH_DOWN];
        if (s < -0.383) out |= bits_of[TOUCH_UP];
        return out;
    case ZONE_FACE:
        if (distance2(x, y, face_x, face_y) > (long)unit * unit * 9) return 0; /* slid well away */
        for (i = 0; i < 4; i++) {
            const int *r = rects[face[i]];
            long d = distance2(x, y, r[0] + r[2] / 2, r[1] + r[3] / 2);
            if (nearest < 0 || d < best) {
                nearest = i;
                best = d;
            }
        }
        return bits_of[face[nearest]];
    case ZONE_BUTTON:
        return in_button(finger->button, x, y) ? bits_of[finger->button] : 0;
    default:
        return 0;
    }
}

static int refresh(void)
{
    uint16_t now = 0;
    int i;
    for (i = 0; i < FINGERS; i++) {
        if (fingers[i].used) now |= fingers[i].bits;
    }
    presses |= now & ~held;
    tapped |= now & ~held;
    if (now == held) return 0;
    held = now;
    return 1;
}

static void release_all(void)
{
    memset(fingers, 0, sizeof(fingers));
    refresh();
}

int TouchPad_SetMode(int wanted)
{
    int was = TouchPad_Shown();
    if (wanted == mode) return 0;
    mode = wanted;
    if (!TouchPad_Shown()) release_all();
    return was != TouchPad_Shown();
}

int TouchPad_OtherInput(void)
{
    if (mode != TOUCH_PAD_AUTO || !touched) return 0;
    touched = 0;
    release_all();
    return 1;
}

int TouchPad_Covers(int x, int y)
{
    TouchButton button;
    return TouchPad_Shown() && zone_at(x, y, &button) != ZONE_NONE;
}

int TouchPad_Finger(int kind, uint64_t id, int x, int y)
{
    Finger *finger = NULL;
    int i;
    for (i = 0; i < FINGERS; i++) {
        if (fingers[i].used && fingers[i].id == id) finger = &fingers[i];
    }
    if (kind == TOUCH_FINGER_DOWN) {
        TouchButton button = TOUCH_UP;
        Zone zone;
        if (mode == TOUCH_PAD_HIDE) return 0;
        if (!TouchPad_Shown()) {
            touched = 1; /* the first touch shows the pad; it presses nothing */
            return 1;
        }
        zone = zone_at(x, y, &button);
        if (zone == ZONE_NONE || finger) return 0;
        for (i = 0; i < FINGERS && !finger; i++) {
            if (!fingers[i].used) finger = &fingers[i];
        }
        if (!finger) return 0;
        finger->used = 1;
        finger->id = id;
        finger->zone = zone;
        finger->button = button;
        finger->bits = press_at(finger, x, y);
        return refresh();
    }
    if (!finger) return 0;
    if (kind == TOUCH_FINGER_MOVE) {
        finger->bits = press_at(finger, x, y);
    } else {
        memset(finger, 0, sizeof(*finger));
    }
    return refresh();
}

uint16_t TouchPad_Update(void)
{
    uint16_t out = held | tapped;
    tapped = 0;
    return out;
}

uint16_t TouchPad_TakePresses(void)
{
    uint16_t out = presses;
    presses = 0;
    return out;
}
