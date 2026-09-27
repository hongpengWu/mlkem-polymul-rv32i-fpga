#ifndef PICO_MLKEM_FIPS202X4_HW_H
#define PICO_MLKEM_FIPS202X4_HW_H
#include "fips202_hw.h"
typedef struct { mlk_shake128ctx lane[4]; } MLK_ALIGN mlk_shake128x4ctx;
#define mlk_shake128x4_init MLK_NAMESPACE(shake128x4_init)
#define mlk_shake128x4_absorb_once MLK_NAMESPACE(shake128x4_absorb_once)
#define mlk_shake128x4_squeezeblocks MLK_NAMESPACE(shake128x4_squeezeblocks)
#define mlk_shake128x4_release MLK_NAMESPACE(shake128x4_release)
#define mlk_shake256x4 MLK_NAMESPACE(shake256x4)
void mlk_shake128x4_init(mlk_shake128x4ctx *state);
void mlk_shake128x4_absorb_once(mlk_shake128x4ctx *state, const uint8_t *in0,
    const uint8_t *in1, const uint8_t *in2, const uint8_t *in3, size_t inlen);
void mlk_shake128x4_squeezeblocks(uint8_t *out0, uint8_t *out1, uint8_t *out2,
    uint8_t *out3, size_t nblocks, mlk_shake128x4ctx *state);
void mlk_shake128x4_release(mlk_shake128x4ctx *state);
void mlk_shake256x4(uint8_t *out0, uint8_t *out1, uint8_t *out2, uint8_t *out3,
    size_t outlen, const uint8_t *in0, const uint8_t *in1,
    const uint8_t *in2, const uint8_t *in3, size_t inlen);
#endif
