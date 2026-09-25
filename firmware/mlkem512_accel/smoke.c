#include "basemul_mmio.h"
#include "smoke_inputs.h"
#define DBG ((volatile uint32_t *)0x50000000u)
#define MMIO ((volatile uint32_t *)0x50001000u)
static uint32_t cycles(void) { uint32_t v; __asm__ volatile("rdcycle %0" : "=r"(v) :: "memory"); return v; }

void kat_main(void)
{
    int16_t result[256];
    DBG[0] = 0x41434352u;
    for (unsigned c = 0; c < 3; ++c) {
        uint32_t start = cycles();
        int ret = mlkem512_basemul_mmio(result, smoke_inputs[c].a,
                                       smoke_inputs[c].b, smoke_inputs[c].cache);
        uint32_t elapsed = cycles() - start;
        if (ret) { DBG[0] = 0x41434346u; for (;;) {} }
        DBG[1] = c; DBG[4] = elapsed;
        DBG[5] = MMIO[0x1008/4]; DBG[6] = MMIO[0x100c/4]; DBG[7] = MMIO[0x1010/4];
        for (unsigned j = 0; j < 128; ++j) {
            DBG[2] = j;
            DBG[3] = (uint16_t)result[2*j] | ((uint32_t)(uint16_t)result[2*j+1] << 16);
            DBG[15] = c * 128 + j + 1;
        }
    }
    DBG[0] = 0x41434350u;
}
