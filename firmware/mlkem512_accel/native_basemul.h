#ifndef PICO_BASEMUL_NATIVE_H
#define PICO_BASEMUL_NATIVE_H
/* Force-include ONLY for upstream poly_k.c in the accelerator build.
 * The vendored portable sources and the software baseline stay unchanged. */
#include <stdint.h>
#include "mlkem_config.h"
#if MLK_CONFIG_PARAMETER_SET != 512
#error "The current MMIO core supports ML-KEM-512 only"
#endif
#define MLK_USE_NATIVE_POLYVEC_BASEMUL_ACC_MONTGOMERY_CACHED
#define MLK_NATIVE_FUNC_SUCCESS 0
int mlk_polyvec_basemul_acc_montgomery_cached_k2_native(
    int16_t *r, const int16_t *a, const int16_t *b, const int16_t *cache);
#endif
