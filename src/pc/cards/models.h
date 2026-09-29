#ifndef MEMORIES_PC_CARDS_MODELS_H
#define MEMORIES_PC_CARDS_MODELS_H
/* A card's 3D model from a mod (notes/model-replacement.md).
 *
 * A mod's "models" list gives a card a MODEL.MRG record of its own ("file")
 * and settings the model is drawn with ("scale", "tint", "speed"). The card
 * keeps the model id the game already gives it (Cards_ModelId), because the
 * battle code indexes the card tables by that id; only the record the loader
 * fetches changes. Each record is served from sectors past the end of the
 * disc and every virtual file (Models_DiscSector), so the game's own loader
 * runs every phase of it, the voices included, as for a record on the disc.
 *
 * The loader is given a model id, not a card, so whoever knows the card says
 * which one is about to be loaded into a model slot (Models_SetSlotCard):
 * the battle presentation, for both of its slots, and the Library. A slot
 * loads the card's record only when the model id it is asked for is still
 * that card's. The 3D Monsters mod reads records itself, through
 * Models_RecordLba. */
#include <stdint.h>
#include "psyq/libgte.h"

typedef struct MemoriesState MemoriesState;

/* At startup, after Cards_Build: every applied mod's "models". */
void Models_Build(void);

/* Whether `card` has a record of its own from a mod. */
int Models_HasRecord(int card);
/* The first absolute sector of the record `card` is drawn with: its mod's
 * record, else its model's on the disc (effective MODEL.MRG), or -1 when it
 * has neither. */
int Models_RecordLba(int card);

/* The card whose look (record and settings) `card` is drawn with: itself
 * when a mod's "models" names it, else its model's card (Cards_ModelId). Two
 * cards with the same look can share one loaded model. */
int Models_Look(int card);

/* The card about to be loaded into model slot 0 or 1 (0: none). */
void Models_SetSlotCard(int slot, int card);
/* Model_LoadMonsterMerge: the sector offset from MODEL.MRG's start to load
 * slot `slot`'s record from, when the card set for it has a record of its
 * own and `model` (a zero-based model id) is still that card's. Returns 1
 * and sets *offset then; 0 leaves the disc's record to the game. Also
 * chooses the settings the slot is drawn with. */
int Models_SlotRecord(int slot, int model, int *offset);
/* The card whose settings slot `slot` is drawn with: set by
 * Models_SlotRecord for the game's loads, or by the 3D Monsters mod around
 * each of its monsters. Its "tint" and "speed" apply; its "yaw" and "scale"
 * only with bit 24 set in `card`, as the game's slots have it (the mod
 * turns and sizes each monster itself). Returns what it replaces, to be
 * given back. */
int Models_UseCard(int slot, int card);



/* The settings of `card` (100: as the disc has it). */
int Models_Scale(int card);   /* size, percent */
int Models_Speed(int card);   /* animation speed, percent */
/* The tint as 0xRRGGBB, a factor per channel where 0xFF is 1. */
uint32_t Models_Tint(int card);
/* Its "yaw": a turn about its up axis, 4096 to a turn (0: as it is). */
int Models_Yaw(int card);
/* Turn a model's root matrix by the card's "yaw", about the model's own up
 * axis (the matrix times the turn); the translation is left alone. */
void Models_Turn(int card, MATRIX *m);

/* What the draw and the animation of slot `slot` do with its card's
 * settings: whether the model is turned or sized, the turn and size of the
 * body's anchor for the draw (func_800540B4), the animation step, and the
 * primitive templates' colour words. */
int Models_SlotShaped(int slot);
/* Whether the card slot `slot` is drawn with has a mod's record. */
int Models_SlotOwnRecord(int slot);
void Models_ShapeSlotRoot(int slot, MATRIX *m);
int Models_SlotStep(int slot, int step);
uint32_t Models_SlotTint(int slot, uint32_t colour);
int Models_SlotTinted(int slot);

/* The drive model's source for the sectors past the disc: 1 with `out` (2048
 * bytes) filled when `lba` is one of a record's. Interrupt context. */
int Models_DiscSector(int lba, void *out);
/* What the records and settings are, for the save-state profile. */
unsigned Models_Signature(void);
void Models_State(MemoriesState *state);

#endif
