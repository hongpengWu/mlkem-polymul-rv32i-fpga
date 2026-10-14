#include "fips202x4_hw.h"
#include "src/verify.h"
#include "kat_protocol.h"

/* Single CPU caller; shared packing buffers keep the 4-way XOF stack small.
 * No software Keccak implementation is linked. CPU-owned intermediates are
 * wiped with the maintained library's zeroization primitive after use.
 * Accelerator BRAM erasure is not provided by this integration revision.
 */
static uint32_t packed_input[512];
static uint32_t packed_output[1024];

static void fail_closed(uint32_t reason)
{
    mlk_zeroize(packed_input, sizeof(packed_input));
    mlk_zeroize(packed_output, sizeof(packed_output));
    KAT_DEBUG_ERROR = 0x4b450000u | reason;
    KAT_DEBUG_STATUS = KAT_STATUS_FAIL;
    KAT_DEBUG_EVENT = KAT_EVENT_DONE;
    for (;;) __asm__ volatile("nop");
}

static void hardware_call(keccak_context *context, uint8_t *output,
    size_t outlen, const uint8_t *input, size_t inlen,
    uint32_t mode, uint32_t command)
{
    if (inlen > 2048u || outlen > 4096u || (inlen && !input) || (outlen && !output))
        fail_closed(1);
    const size_t input_words = (inlen + 3u)/4u;
    const size_t output_words = (outlen + 3u)/4u;
    for (size_t i = 0; i < input_words; ++i) {
        uint32_t word = 0;
        for (size_t byte = 0; byte < 4 && 4*i+byte < inlen; ++byte)
            word |= (uint32_t)input[4*i+byte] << (8*byte);
        packed_input[i] = word;
    }
    keccak_metrics metrics;
    const int result = keccak_mmio_run(context, packed_output, packed_input,
        (uint32_t)inlen, (uint32_t)outlen, mode, command, &metrics);
    if (result || (metrics.flags & 7u) != 2u) {
        mlk_zeroize(context, sizeof(*context));
        fail_closed(result ? (0x100u | ((uint32_t)(-result) & 255u)) : 2u);
    }
    for (size_t i = 0; i < outlen; ++i)
        output[i] = (uint8_t)(packed_output[i/4] >> (8*(i%4)));
    mlk_zeroize(packed_input, 4*input_words);
    mlk_zeroize(packed_output, 4*output_words);
}

static void one_shot(uint8_t *output, size_t outlen,
                     const uint8_t *input, size_t inlen, uint32_t mode)
{
    keccak_context context;
    mlk_zeroize(&context, sizeof(context));
    hardware_call(&context, output, outlen, input, inlen, mode, KECCAK_HASH);
    mlk_zeroize(&context, sizeof(context));
}

void mlk_shake128_init(mlk_shake128ctx *state)
{
    mlk_zeroize(state, sizeof(*state));
}

void mlk_shake128_absorb_once(mlk_shake128ctx *state, const uint8_t *input, size_t inlen)
{
    if (state->phase != 0 || inlen > sizeof(state->pending) || (inlen && !input))
        fail_closed(3);
    for (size_t i = 0; i < inlen; ++i) state->pending[i] = input[i];
    state->pending_len = (uint32_t)inlen;
    state->phase = 1;
}

void mlk_shake128_squeezeblocks(uint8_t *output, size_t nblocks, mlk_shake128ctx *state)
{
    if ((state->phase != 1 && state->phase != 2) || nblocks > 4096u/SHAKE128_RATE)
        fail_closed(4);
    if (!nblocks) return;
    const uint32_t first = state->phase == 1;
    hardware_call(&state->hardware, output, nblocks*SHAKE128_RATE,
        state->pending, first ? state->pending_len : 0u,
        KECCAK_SHAKE128, first ? KECCAK_HASH : KECCAK_SQUEEZE);
    mlk_zeroize(state->pending, sizeof(state->pending));
    state->pending_len = 0;
    state->phase = 2;
}

void mlk_shake128_release(mlk_shake128ctx *state)
{
    mlk_zeroize(state, sizeof(*state));
}

void mlk_shake256(uint8_t *output, size_t outlen, const uint8_t *input, size_t inlen)
{
    one_shot(output, outlen, input, inlen, KECCAK_SHAKE256);
}

void mlk_sha3_256(uint8_t *output, const uint8_t *input, size_t inlen)
{
    one_shot(output, SHA3_256_HASHBYTES, input, inlen, KECCAK_SHA3_256);
}

void mlk_sha3_512(uint8_t *output, const uint8_t *input, size_t inlen)
{
    one_shot(output, SHA3_512_HASHBYTES, input, inlen, KECCAK_SHA3_512);
}

void mlk_shake128x4_init(mlk_shake128x4ctx *state)
{
    for (unsigned lane = 0; lane < 4; ++lane) mlk_shake128_init(&state->lane[lane]);
}

void mlk_shake128x4_absorb_once(mlk_shake128x4ctx *state, const uint8_t *in0,
    const uint8_t *in1, const uint8_t *in2, const uint8_t *in3, size_t inlen)
{
    const uint8_t *inputs[4] = {in0, in1, in2, in3};
    for (unsigned lane = 0; lane < 4; ++lane)
        mlk_shake128_absorb_once(&state->lane[lane], inputs[lane], inlen);
}

void mlk_shake128x4_squeezeblocks(uint8_t *out0, uint8_t *out1, uint8_t *out2,
    uint8_t *out3, size_t nblocks, mlk_shake128x4ctx *state)
{
    uint8_t *outputs[4] = {out0, out1, out2, out3};
    for (unsigned lane = 0; lane < 4; ++lane)
        mlk_shake128_squeezeblocks(outputs[lane], nblocks, &state->lane[lane]);
}

void mlk_shake128x4_release(mlk_shake128x4ctx *state)
{
    mlk_zeroize(state, sizeof(*state));
}

void mlk_shake256x4(uint8_t *out0, uint8_t *out1, uint8_t *out2, uint8_t *out3,
    size_t outlen, const uint8_t *in0, const uint8_t *in1,
    const uint8_t *in2, const uint8_t *in3, size_t inlen)
{
    uint8_t *outputs[4] = {out0, out1, out2, out3};
    const uint8_t *inputs[4] = {in0, in1, in2, in3};
    for (unsigned lane = 0; lane < 4; ++lane)
        mlk_shake256(outputs[lane], outlen, inputs[lane], inlen);
}
