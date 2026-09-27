/* The rewind ring (src/pc/guest/rewind.h): what goes in comes back byte for
 * byte, whatever the sizes, across eviction and after branching. */
#include "pc/guest/rewind.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define CHECK(condition)                                                          \
    do {                                                                          \
        if (!(condition)) {                                                       \
            fprintf(stderr, "%s:%d: check failed: %s\n", __FILE__, __LINE__, #condition); \
            exit(1);                                                              \
        }                                                                         \
    } while (0)

#define IMAGES 40
#define LARGEST 70000

static uint8_t images[IMAGES][LARGEST];
static size_t sizes[IMAGES];
static uint32_t seed = 12345;

static uint32_t next_random(void)
{
    seed = seed * 1103515245u + 12345u;
    return seed >> 8;
}

/* Each image is the one before with a few changed spans; sizes wander,
 * odd ones included, so both shorter and longer neighbours occur. */
static void make_images(void)
{
    int k, n;
    sizes[0] = 50001;
    for (size_t i = 0; i < sizes[0]; i++) images[0][i] = (uint8_t)(i % 7 == 0 ? next_random() : 0);
    for (k = 1; k < IMAGES; k++) {
        size_t size = 40000 + next_random() % (LARGEST - 40000);
        memcpy(images[k], images[k - 1], LARGEST);
        if (k % 5 == 0) size = sizes[k - 1]; /* now and then the same size */
        if (k == 7) size = 40003;            /* a sharp shrink */
        if (k == 8) size = LARGEST;          /* and a growth to the most */
        memset(images[k] + size, 0, LARGEST - size);
        for (n = 0; n < 6; n++) {
            size_t at = next_random() % size, length = 1 + next_random() % 300;
            if (at + length > size) length = size - at;
            for (size_t i = 0; i < length; i++) images[k][at + i] = (uint8_t)next_random();
        }
        images[k][size - 1] = (uint8_t)(k | 1); /* the last byte always counts */
        sizes[k] = size;
    }
}

static void expect(const RewindRing *ring, int k)
{
    size_t size = 0;
    const uint8_t *latest = Rewind_Latest(ring, &size);
    CHECK(latest != NULL);
    CHECK(size == sizes[k]);
    CHECK(!memcmp(latest, images[k], size));
    /* Past the image, up to what the ring allocated, all zero. */
    for (size_t i = size; i < ring->capacity; i++) CHECK(latest[i] == 0);
}

static void round_trip(void)
{
    RewindRing ring;
    int k;
    Rewind_Init(&ring, (size_t)1 << 30, 1000);
    CHECK(Rewind_Latest(&ring, NULL) == NULL);
    CHECK(!Rewind_Back(&ring));
    for (k = 0; k < IMAGES; k++) {
        CHECK(Rewind_Push(&ring, images[k], sizes[k]) == 0);
        expect(&ring, k);
    }
    CHECK(ring.count == IMAGES - 1);
    /* Differences are much smaller than the images. */
    CHECK(ring.used < (size_t)(IMAGES - 1) * 40000 / 4);
    for (k = IMAGES - 2; k >= 0; k--) {
        CHECK(Rewind_Back(&ring));
        expect(&ring, k);
    }
    CHECK(!Rewind_Back(&ring));
    expect(&ring, 0);
    Rewind_Clear(&ring);
    CHECK(Rewind_Latest(&ring, NULL) == NULL && ring.used == 0);
}

static void eviction(void)
{
    RewindRing ring;
    int k, oldest;
    /* By count. */
    Rewind_Init(&ring, (size_t)1 << 30, 10);
    for (k = 0; k < IMAGES; k++) CHECK(Rewind_Push(&ring, images[k], sizes[k]) == 0);
    CHECK(ring.count == 10);
    for (k = IMAGES - 2; Rewind_Back(&ring); k--) expect(&ring, k);
    CHECK(k == IMAGES - 12);
    expect(&ring, IMAGES - 11);
    Rewind_Clear(&ring);
    /* By bytes: a budget of a few differences. */
    Rewind_Init(&ring, 4000, 1000);
    for (k = 0; k < IMAGES; k++) {
        CHECK(Rewind_Push(&ring, images[k], sizes[k]) == 0);
        CHECK(ring.used <= 4000 || ring.count == 1);
    }
    CHECK(ring.count >= 1 && ring.count < IMAGES - 1);
    oldest = IMAGES - 1 - (int)ring.count;
    for (k = IMAGES - 2; Rewind_Back(&ring); k--) expect(&ring, k);
    expect(&ring, oldest);
    CHECK(ring.used == 0);
    Rewind_Clear(&ring);
}

/* Back a few, then on from there: the ring follows the new line. */
static void branch(void)
{
    RewindRing ring;
    int k;
    Rewind_Init(&ring, (size_t)1 << 30, 1000);
    for (k = 0; k < 20; k++) CHECK(Rewind_Push(&ring, images[k], sizes[k]) == 0);
    for (k = 0; k < 5; k++) CHECK(Rewind_Back(&ring));
    expect(&ring, 14);
    CHECK(Rewind_Push(&ring, images[30], sizes[30]) == 0);
    CHECK(Rewind_Push(&ring, images[31], sizes[31]) == 0);
    expect(&ring, 31);
    CHECK(Rewind_Back(&ring));
    expect(&ring, 30);
    CHECK(Rewind_Back(&ring));
    expect(&ring, 14);
    CHECK(Rewind_Back(&ring));
    expect(&ring, 13);
    /* Emptied, then used again. */
    while (Rewind_Back(&ring)) {
    }
    expect(&ring, 0);
    CHECK(Rewind_Push(&ring, images[5], sizes[5]) == 0);
    CHECK(Rewind_Back(&ring));
    expect(&ring, 0);
    Rewind_Clear(&ring);
    CHECK(Rewind_Push(&ring, images[3], sizes[3]) == 0);
    expect(&ring, 3);
    CHECK(!Rewind_Back(&ring));
    Rewind_Clear(&ring);
}

/* Identical images cost a header and nothing else. */
static void unchanged(void)
{
    RewindRing ring;
    Rewind_Init(&ring, (size_t)1 << 30, 100);
    CHECK(Rewind_Push(&ring, images[2], sizes[2]) == 0);
    CHECK(Rewind_Push(&ring, images[2], sizes[2]) == 0);
    CHECK(ring.count == 1 && ring.used == 8);
    CHECK(Rewind_Back(&ring));
    expect(&ring, 2);
    Rewind_Clear(&ring);
}

/* Changes spread as thinly as can be, and a wholly new image: the encoding
 * stays within its buffer (the sanitizers watch) and still round-trips. */
static void scattered(void)
{
    static uint8_t first[30001], second[30001], third[30001];
    RewindRing ring;
    size_t i;
    for (i = 0; i < sizeof(first); i++) first[i] = (uint8_t)next_random();
    memcpy(second, first, sizeof(first));
    memcpy(third, first, sizeof(first));
    for (i = 0; i + 4 <= sizeof(second); i += 8) second[i] ^= 0x5a;  /* every other word */
    for (i = 0; i + 4 <= sizeof(third); i += 12) third[i] ^= 0xa5;   /* every third word */
    Rewind_Init(&ring, (size_t)1 << 30, 100);
    CHECK(Rewind_Push(&ring, first, sizeof(first)) == 0);
    CHECK(Rewind_Push(&ring, second, sizeof(second)) == 0);
    CHECK(Rewind_Push(&ring, third, sizeof(third)) == 0);
    for (i = 0; i < sizeof(first); i++) first[i] = (uint8_t)next_random();
    CHECK(Rewind_Push(&ring, first, 29999) == 0);
    CHECK(Rewind_Back(&ring));
    CHECK(ring.latest_size == sizeof(third) && !memcmp(ring.latest, third, sizeof(third)));
    CHECK(Rewind_Back(&ring));
    CHECK(ring.latest_size == sizeof(second) && !memcmp(ring.latest, second, sizeof(second)));
    Rewind_Clear(&ring);
}

int main(void)
{
    make_images();
    round_trip();
    eviction();
    branch();
    unchanged();
    scattered();
    puts("rewind ring: ok");
    return 0;
}
