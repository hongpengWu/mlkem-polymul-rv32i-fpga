#ifndef MLKEM512_BASEMUL_MMIO_H
#define MLKEM512_BASEMUL_MMIO_H
#include <stdint.h>
/* NTT-domain K=2 cached BaseMul. Returns 0 on success, -1 on error/timeout.
 * Prototype bring-up driver; accelerator BRAM is NOT scrubbed after use. */
int mlkem512_basemul_mmio(int16_t r[256], const int16_t a[2][256],
                         const int16_t b[2][256], const int16_t cache[2][128]);
#endif
