#include "pc/compat/pgxp.h"
#include "pc/compat/gte.h"
#include <assert.h>

int main(void)
{
    uint32_t packet[] = {0x04ffffff, 0x20000000, 0x0014000a, 0x00140014, 0x001e000a};
    uint32_t address = ((uint32_t)(uintptr_t)packet & 0x00ffffffu) + 8;
    float a[] = {10.25f, 20.5f, 100.0f}, b[] = {10.75f, 20.5f, 120.0f};
    float x, y, w;
    Pgxp_Active = 1;
    Pgxp_Project(packet[2], a[0], a[1], a[2]);
    Pgxp_Project(packet[2], b[0], b[1], b[2]);
    assert(!Pgxp_Find(packet[2], &x, &y, &w)); /* ambiguous by value */
    Pgxp_Stored(packet[2], a);
    Pgxp_AddPrim(packet);
    assert(Pgxp_FindAt(address, packet[2], &x, &y, &w) == 1 && x == a[0]);

    /* The same packet buffer is reused for a primitive without GTE stores.
     * An unchanged rounded word must not inherit the previous projection. */
    Pgxp_AddPrim(packet);
    assert(Pgxp_FindAt(address, packet[2], &x, &y, &w) == 0);
    Pgxp_Stored(packet[2], a);
    Pgxp_Stored(packet[2], b);
    Pgxp_AddPrim(packet);
    assert(Pgxp_FindAt(address, packet[2], &x, &y, &w) == -1);
    Pgxp_Stored(packet[2], a);
    Pgxp_AddPrim(packet);
    Pgxp_NextFrame();
    assert(Pgxp_FindAt(address, packet[2], &x, &y, &w) == 1);
    Pgxp_NextFrame();
    assert(Pgxp_FindAt(address, packet[2], &x, &y, &w) == 0);

    /* Close to the camera: R11 = R33 = 0.5 put the vertex at view x -150.5,
     * z 160.5, which the GTE truncates to IR1 = -151 and SZ3 = 160 before
     * it divides. The word is -284, the vertex really at -281.3: outside the
     * (-1, +2) window, but that is the truncation, so the precise position
     * is kept. */
    Memories_GteReset();
    Memories_GteWriteControl(0, 0x0800);
    Memories_GteWriteControl(2, 0x1000);
    Memories_GteWriteControl(4, 0x0800);
    Memories_GteWriteControl(26, 300);
    Memories_GteWriteData(0, (uint16_t)-301);
    Memories_GteWriteData(1, 321);
    Memories_GteCommand(0x0180001); /* RTPS, sf */
    assert((int16_t)Memories_GteReadData(14) == -284);
    assert(Memories_GtePrecise(2, &x, &y, &w) && x > -281.32f && x < -281.30f && w == 160.5f);

    /* A view x IR1 saturates is not the word's vertex: rejected. */
    Memories_GteWriteControl(0, 0x7fff);
    Memories_GteWriteData(0, 0x7fff);
    Memories_GteCommand(0x0180001);
    assert(!Memories_GtePrecise(2, &x, &y, &w));
    return 0;
}
