/* The mod-model hooks (src/pc/cards/models.h) for tests that link the mod
 * system or the drive model without the card tables: no mod models. */
#include "pc/cards/models.h"

int Models_DiscSector(int lba, void *out)
{
    (void)lba;
    (void)out;
    return 0;
}

unsigned Models_Signature(void) { return 0; }
