#ifndef MEMORIES_PC_MODS_PALETTE_RAMPS_H
#define MEMORIES_PC_MODS_PALETTE_RAMPS_H

/* Applies all manifest-defined text palette ramps after the boot upload. */
void PaletteRamps_ApplyManifest(const unsigned short *original);

/* A named, added ramp's CLUT. Names are qualified as "mod-id:name".
 * Returns zero when the requested name was not declared. */
unsigned short PaletteRamps_Clut(const char *name);

#endif
