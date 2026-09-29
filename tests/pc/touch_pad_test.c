/* The on-screen controller's logic (src/pc/platform/touch_pad.c): when it
 * shows, what a finger presses where, and that a tap shorter than a pump
 * still counts once. */
#include "pc/platform/touch_pad.h"
#include <assert.h>
#include <stdio.h>

static void centre(TouchButton button, int *x, int *y)
{
    int bx, by, bw, bh;
    assert(TouchPad_Rect(button, &bx, &by, &bw, &bh));
    *x = bx + bw / 2;
    *y = by + bh / 2;
}

int main(void)
{
    int x, y, ux, uy, dx, dy;
    /* Automatic: hidden, and nothing is the pad's, until a touch. */
    TouchPad_SetMode(TOUCH_PAD_AUTO);
    TouchPad_Layout(2280, 1080, 0);
    assert(!TouchPad_Shown() && !TouchPad_Covers(100, 600) && !TouchPad_Rect(TOUCH_CROSS, &x, &y, &x, &y));
    assert(TouchPad_Finger(TOUCH_FINGER_DOWN, 1, 100, 600) && TouchPad_Shown());
    assert(TouchPad_Update() == 0); /* the touch that showed it pressed nothing */
    TouchPad_Finger(TOUCH_FINGER_UP, 1, 100, 600);

    /* A D-pad arrow, held across updates and let go. */
    centre(TOUCH_UP, &ux, &uy);
    assert(TouchPad_Covers(ux, uy) && !TouchPad_Covers(1140, 540));
    assert(TouchPad_Finger(TOUCH_FINGER_DOWN, 2, ux, uy));
    assert(TouchPad_Update() == TouchPad_Bit(TOUCH_UP) && TouchPad_Update() == TouchPad_Bit(TOUCH_UP));
    assert(TouchPad_Held(TOUCH_UP) && TouchPad_TakePresses() == TouchPad_Bit(TOUCH_UP) && !TouchPad_TakePresses());
    /* Sliding to the right arrow's side of the middle turns it into Right. */
    centre(TOUCH_RIGHT, &x, &y);
    TouchPad_Finger(TOUCH_FINGER_MOVE, 2, x, y);
    assert(TouchPad_Update() == TouchPad_Bit(TOUCH_RIGHT));
    /* Between Up and Right: both. */
    centre(TOUCH_DOWN, &dx, &dy);
    TouchPad_Finger(TOUCH_FINGER_MOVE, 2, x, uy);
    assert(TouchPad_Update() == (TouchPad_Bit(TOUCH_UP) | TouchPad_Bit(TOUCH_RIGHT)));
    TouchPad_Finger(TOUCH_FINGER_UP, 2, x, uy);
    assert(TouchPad_Update() == 0);

    /* A tap down and up between two updates is seen by one of them. */
    centre(TOUCH_CROSS, &x, &y);
    TouchPad_Finger(TOUCH_FINGER_DOWN, 3, x, y);
    TouchPad_Finger(TOUCH_FINGER_UP, 3, x, y);
    assert(TouchPad_Update() == TouchPad_Bit(TOUCH_CROSS) && TouchPad_Update() == 0);

    /* Two fingers: the D-pad and a face button together; a face finger
     * slides to the nearest button. */
    TouchPad_Finger(TOUCH_FINGER_DOWN, 4, dx, dy);
    TouchPad_Finger(TOUCH_FINGER_DOWN, 5, x, y);
    assert(TouchPad_Update() == (TouchPad_Bit(TOUCH_DOWN) | TouchPad_Bit(TOUCH_CROSS)));
    centre(TOUCH_CIRCLE, &x, &y);
    TouchPad_Finger(TOUCH_FINGER_MOVE, 5, x, y);
    assert(TouchPad_Update() == (TouchPad_Bit(TOUCH_DOWN) | TouchPad_Bit(TOUCH_CIRCLE)));
    TouchPad_Finger(TOUCH_FINGER_UP, 4, dx, dy);
    TouchPad_Finger(TOUCH_FINGER_UP, 5, x, y);
    TouchPad_Update();

    /* The small buttons, each its own bit; one the finger slides off lets go. */
    centre(TOUCH_START, &x, &y);
    TouchPad_Finger(TOUCH_FINGER_DOWN, 6, x, y);
    assert(TouchPad_Update() == 0x0008);
    TouchPad_Finger(TOUCH_FINGER_MOVE, 6, 1140, 540);
    assert(TouchPad_Update() == 0);
    TouchPad_Finger(TOUCH_FINGER_UP, 6, 1140, 540);
    centre(TOUCH_L1, &x, &y);
    TouchPad_Finger(TOUCH_FINGER_DOWN, 7, x, y);
    assert(TouchPad_Update() == 0x0400);

    /* A key hides it again, and lets go of what it held. */
    assert(TouchPad_OtherInput() && !TouchPad_Shown() && !TouchPad_Covers(x, y));
    assert(TouchPad_Update() == 0);
    TouchPad_Finger(TOUCH_FINGER_UP, 7, x, y);

    /* Show keeps it without a touch; Hide never takes one. */
    assert(TouchPad_SetMode(TOUCH_PAD_SHOW) && TouchPad_Shown() && !TouchPad_OtherInput() && TouchPad_Shown());
    assert(TouchPad_SetMode(TOUCH_PAD_HIDE) && !TouchPad_Shown());
    assert(!TouchPad_Finger(TOUCH_FINGER_DOWN, 8, 100, 600) && !TouchPad_Shown() && TouchPad_Update() == 0);
    puts("touch pad: showing, D-pad angles, face buttons, taps, fingers, hiding passed");
    return 0;
}
