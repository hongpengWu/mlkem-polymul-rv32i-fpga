#include "basemul_mmio.h"
#define MMIO ((volatile uint32_t *)0x50001000u)
#define CONTROL (0x1000u / 4u)
#define STATUS (0x1004u / 4u)

static void load(unsigned offset, const int16_t *p, unsigned count)
{
    for (unsigned i = 0; i < count; i += 2)
        MMIO[offset / 4u + i / 2u] = (uint16_t)p[i] | ((uint32_t)(uint16_t)p[i+1] << 16);
}

int mlkem512_basemul_mmio(int16_t r[256], const int16_t a[2][256],
                         const int16_t b[2][256], const int16_t cache[2][128])
{
    if (MMIO[STATUS] & 1u) return -1;
    MMIO[CONTROL] = 6u;
    load(0x000, a[0], 256); load(0x200, a[1], 256);
    load(0x400, b[0], 256); load(0x600, b[1], 256);
    load(0x800, cache[0], 128); load(0x900, cache[1], 128);
    MMIO[CONTROL] = 1u;
    for (unsigned i = 0; i < 10000; ++i) {
        uint32_t status = MMIO[STATUS];
        if (status & 4u) return -1;
        if ((status & 3u) == 2u) {
            for (unsigned j = 0; j < 128; ++j) {
                uint32_t word = MMIO[0xa00u / 4u + j];
                r[2*j] = (int16_t)(uint16_t)word;
                r[2*j+1] = (int16_t)(uint16_t)(word >> 16);
            }
            return 0;
        }
    }
    return -1;
}
