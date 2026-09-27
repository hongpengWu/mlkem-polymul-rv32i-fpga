#ifndef PICO_MLKEM_FIPS202_HW_H
#define PICO_MLKEM_FIPS202_HW_H
#include "src/common.h"
#include "keccak_mmio.h"

#define SHAKE128_RATE 168
#define SHAKE256_RATE 136
#define SHA3_256_RATE 136
#define SHA3_512_RATE 72
#define SHA3_256_HASHBYTES 32
#define SHA3_512_HASHBYTES 64
/* Preserve the portable baseline's serial noise-sampling call selection. */
#define FIPS202_X4_DEFAULT_IMPLEMENTATION

/* ML-KEM provider, not a general unbounded FIPS 202 streaming interface.
 * XOF inputs are at most 34 bytes (rho || indices). Owning that input avoids
 * retaining a caller's expired stack pointer, while merging absorb and the
 * first squeeze into one hardware HASH command. Each context owns its state.
 * Single-shot inputs <=2048 bytes and outputs <=4096 bytes. Byte-aligned
 * input/output pointers are supported; the library's no-alias contract applies.
 * The scratch buffers are shared: this bare-metal provider is non-reentrant.
 */
typedef struct {
    keccak_context hardware;
    uint8_t pending[34];
    uint32_t pending_len;
    uint32_t phase;
} MLK_ALIGN mlk_shake128ctx;

#define mlk_shake128_init MLK_NAMESPACE(shake128_init)
#define mlk_shake128_absorb_once MLK_NAMESPACE(shake128_absorb_once)
#define mlk_shake128_squeezeblocks MLK_NAMESPACE(shake128_squeezeblocks)
#define mlk_shake128_release MLK_NAMESPACE(shake128_release)
#define mlk_shake256 MLK_NAMESPACE(shake256)
#define mlk_sha3_256 MLK_NAMESPACE(sha3_256)
#define mlk_sha3_512 MLK_NAMESPACE(sha3_512)
void mlk_shake128_init(mlk_shake128ctx *state);
void mlk_shake128_absorb_once(mlk_shake128ctx *state, const uint8_t *input, size_t inlen);
void mlk_shake128_squeezeblocks(uint8_t *output, size_t nblocks, mlk_shake128ctx *state);
void mlk_shake128_release(mlk_shake128ctx *state);
void mlk_shake256(uint8_t *output, size_t outlen, const uint8_t *input, size_t inlen);
void mlk_sha3_256(uint8_t *output, const uint8_t *input, size_t inlen);
void mlk_sha3_512(uint8_t *output, const uint8_t *input, size_t inlen);
#endif
