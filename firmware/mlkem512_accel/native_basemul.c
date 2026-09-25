#include "native_basemul.h"
#include "basemul_mmio.h"
#include "src/poly_k.h"

_Static_assert(sizeof(mlk_poly) == 256 * sizeof(int16_t), "Polynomial layout changed");
_Static_assert(sizeof(mlk_polyvec) == 2 * 256 * sizeof(int16_t), "Vector layout changed");
_Static_assert(sizeof(mlk_polyvec_mulcache) == 2 * 128 * sizeof(int16_t), "Cache layout changed");

int mlk_polyvec_basemul_acc_montgomery_cached_k2_native(
    int16_t *r, const int16_t *a, const int16_t *b, const int16_t *cache)
{
    int ret = mlkem512_basemul_mmio(r, (const int16_t (*)[256])a,
                                  (const int16_t (*)[256])b,
                                  (const int16_t (*)[128])cache);
    if (ret != 0) {
        /* Hardware failure must not silently fall back to portable software. */
        volatile uint32_t *dbg = (volatile uint32_t *)0x50000000u;
        dbg[1] = 0xacc00001u;
        dbg[0] = 0x4b415446u;
        for (;;) __asm__ volatile ("nop");
    }
    return MLK_NATIVE_FUNC_SUCCESS;
}
