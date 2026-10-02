/* The input recorder and player (recorder.h). */
#include "pc/compat/fs.h"
#include "recorder.h"
#include "pc/debug/monitor.h"
#include "pc/guest/state.h"
#include "pc/platform/platform.h"
#include "pc/sdk/display.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct {
    uint32_t index;
    uint16_t bits[2], fixed[2];
    uint8_t pad2;
} PadEvent;

#define PENDING_MAX 1024 /* changes between two safe points; a frame has a few VBlanks */

static enum { WAITING, RUNNING } phase;
static int recording, playing, started;
static unsigned start_vblank;        /* the VBlank count the indices count from */
static FILE *out;
static char out_path[600];
static unsigned states_every, last_state;
/* Recording: changes noted at the VBlank, written at the next safe point. */
static PadEvent pending[PENDING_MAX], last_written;
static volatile unsigned pending_count, dropped;
static int have_last;
/* Playing: the file's changes, in order. */
static PadEvent *script;
static size_t script_count, script_at;
static unsigned play_end;
static int play_has_end;
static volatile uint16_t played[2]; /* the bits given at the last VBlank played */

static void begin(void)
{
    started = 1;
    phase = RUNNING;
    start_vblank = Platform_VBlankCount();
}

static void read_script(const char *path)
{
    FILE *file = fopen(path, "r");
    char line[700];
    size_t room = 0;
    if (!file) {
        fprintf(stderr, "memories-pc: replay: cannot read %s; the pads stay idle\n", path);
        return;
    }
    while (fgets(line, sizeof(line), file)) {
        unsigned index, b1, f1, b2, f2, c2, frame;
        if (sscanf(line, "I %u %x %x %x %x %u", &index, &b1, &f1, &b2, &f2, &c2) == 6) {
            if (script_count == room) {
                PadEvent *grown;
                room = room ? room * 2 : 1024;
                grown = realloc(script, room * sizeof(*script));
                if (!grown) break;
                script = grown;
            }
            script[script_count].index = index;
            script[script_count].bits[0] = (uint16_t)b1;
            script[script_count].fixed[0] = (uint16_t)f1;
            script[script_count].bits[1] = (uint16_t)b2;
            script[script_count].fixed[1] = (uint16_t)f2;
            script[script_count].pad2 = (uint8_t)(c2 != 0);
            script_count++;
        } else if (sscanf(line, "E %u %u", &index, &frame) == 2) {
            play_end = index;
            play_has_end = 1;
        }
    }
    fclose(file);
    fprintf(stderr, "memories-pc: replay: %lu pad changes from %s%s\n", (unsigned long)script_count, path,
            play_has_end ? "" : " (no end: it runs on)");
}

/* What the run was made with: the facts every crash report starts with
 * (monitor.h) that decide what a replay sees, as "F key: value" lines. */
static void write_facts(void)
{
    static const char *const keys[] = {"build: ", "os: ", "settings: ", "mods: "};
    static char facts[4096];
    char *line, *next;
    size_t i;
    Monitor_Facts(facts, sizeof(facts));
    for (line = facts; line && *line; line = next) {
        next = strchr(line, '\n');
        if (next) *next++ = '\0';
        for (i = 0; i < sizeof(keys) / sizeof(keys[0]); i++) {
            if (!strncmp(line, keys[i], strlen(keys[i]))) fprintf(out, "F %s\n", line);
        }
    }
}

static void finish(void)
{
    if (!out) return;
    fprintf(out, "E %u %u\n", started ? Platform_VBlankCount() - start_vblank : 0, Memories_PresentedFrames());
    fclose(out);
    out = NULL;
}

void Recorder_Init(void)
{
    const char *record = getenv("MEMORIES_RECORD"), *play = getenv("MEMORIES_PLAY");
    const char *state = getenv("MEMORIES_LOAD_STATE"), *every = getenv("MEMORIES_RECORD_STATES");
    if (play && *play) {
        playing = 1;
        read_script(play);
    }
    if (record && *record) {
        snprintf(out_path, sizeof(out_path), "%s", record);
        out = fopen(record, "w");
        if (!out) {
            fprintf(stderr, "memories-pc: record: cannot write %s\n", record);
        } else {
            recording = 1;
            fprintf(out, "yfm-recording 1\nbuild %08x\n", (unsigned)Memories_StateBuildId());
            if (state && *state) fprintf(out, "start state %s\n", state);
            else fprintf(out, "start boot\n");
            write_facts();
            fflush(out);
            atexit(finish);
        }
        states_every = every ? (unsigned)strtoul(every, NULL, 10) : 0;
    }
    if (!recording && !playing) return;
    /* From boot the indices are the VBlank count; from a state they start
     * once the state is in (Recorder_Point). */
    if (state && *state) phase = WAITING;
    else begin();
}

void Recorder_Pads(uint16_t bits[2], uint16_t fixed[2], int *pad2_connected)
{
    unsigned index;
    if (!recording && !playing) return;
    if (phase != RUNNING) {
        if (playing) bits[0] = bits[1] = fixed[0] = fixed[1] = 0, *pad2_connected = 0;
        return;
    }
    index = Platform_VBlankCount() - start_vblank;
    if (playing) {
        while (script_at < script_count && script[script_at].index <= index) script_at++;
        if (script_at) {
            const PadEvent *event = &script[script_at - 1];
            bits[0] = event->bits[0];
            bits[1] = event->bits[1];
            fixed[0] = event->fixed[0];
            fixed[1] = event->fixed[1];
            *pad2_connected = event->pad2;
        } else {
            bits[0] = bits[1] = fixed[0] = fixed[1] = 0;
            *pad2_connected = 0;
        }
        played[0] = bits[0];
        played[1] = bits[1];
    }
    if (recording) {
        PadEvent event;
        event.index = index;
        event.bits[0] = bits[0];
        event.bits[1] = bits[1];
        event.fixed[0] = fixed[0];
        event.fixed[1] = fixed[1];
        event.pad2 = (uint8_t)(*pad2_connected != 0);
        if (pending_count < PENDING_MAX) pending[pending_count++] = event;
        else dropped++;
    }
}

uint16_t Recorder_HostPad(int port, uint16_t live)
{
    return playing ? played[port & 1] : live;
}

void Recorder_Point(unsigned frame)
{
    unsigned index, i;
    if (!recording && !playing) return;
    if (phase == WAITING) {
        if (!Memories_StateStartupDone()) return;
        begin();
    }
    index = Platform_VBlankCount() - start_vblank;
    if (recording && out) {
        for (i = 0; i < pending_count; i++) {
            const PadEvent *event = &pending[i];
            if (have_last && !memcmp(event->bits, last_written.bits, sizeof(event->bits)) &&
                !memcmp(event->fixed, last_written.fixed, sizeof(event->fixed)) && event->pad2 == last_written.pad2) {
                continue;
            }
            fprintf(out, "I %u %04x %04x %04x %04x %u\n", event->index, event->bits[0], event->fixed[0],
                    event->bits[1], event->fixed[1], event->pad2);
            last_written = *event;
            have_last = 1;
        }
        pending_count = 0;
        if (dropped) {
            fprintf(stderr, "memories-pc: record: %u VBlanks of input were dropped (too many between two frames)\n",
                    dropped);
            dropped = 0;
        }
        fprintf(out, "H %u %u %016llx\n", index, frame, Memories_VramHash());
        if (states_every && index - last_state >= states_every) {
            char path[700];
            snprintf(path, sizeof(path), "%s.%u.state", out_path, index);
            if (!Memories_StateSaveHere(path)) {
                fprintf(out, "S %u %u %s\n", index, frame, path);
                last_state = index;
            }
        }
        fflush(out);
    }
    if (playing && play_has_end && index >= play_end) {
        fprintf(stderr, "memories-pc: replay: the recording ends at VBlank %u; done\n", play_end);
        playing = 0;
        Platform_RequestQuit();
    }
}
