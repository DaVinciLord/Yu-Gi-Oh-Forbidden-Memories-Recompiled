#ifndef MEMORIES_NAME_TRACE_H
#define MEMORIES_NAME_TRACE_H
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
extern unsigned Memories_PresentedFrames(void);
#define NAME_TRACE(...) do { if (getenv("MEMORIES_TRACE_NAME")) printf(__VA_ARGS__); } while (0)
#endif
