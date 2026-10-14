#ifndef MLKEM1024_KECCAK_MMIO_H
#define MLKEM1024_KECCAK_MMIO_H
#include <stdint.h>

#define KECCAK_MMIO_BASE 0x50010000u
#define KECCAK_CONTEXT_WORDS32 52u
#define KECCAK_SHAKE128 0u
#define KECCAK_SHAKE256 1u
#define KECCAK_SHA3_256 2u
#define KECCAK_SHA3_512 3u
#define KECCAK_HASH 0u
#define KECCAK_SQUEEZE 1u
#define KECCAK_CLEAR 2u
#define KECCAK_DRIVER_TIMEOUT (-3)
#define KECCAK_DRIVER_ARGUMENT (-4)

typedef struct { uint32_t words[KECCAK_CONTEXT_WORDS32]; } keccak_context;
typedef struct {
    uint32_t starts, busy_cycles, buffer_writes, buffer_reads, flags;
} keccak_metrics;

/* Packed little-endian words. The final input word must be allocated even
 * when input_len is not a multiple of four. Output capacity rounds up too.
 * Each context can be interleaved with other callers: state is restored
 * before and saved after every hardware command. No software hash fallback.
 * Returns the HLS result (0/-1/-2), or a bounded-poll/driver error (-3/-4).
 * The caller's output remains untouched when the hardware returns an error.
 */
int keccak_mmio_run(keccak_context *context, uint32_t *output,
                   const uint32_t *input, uint32_t input_len,
                   uint32_t output_len, uint32_t mode, uint32_t command,
                   keccak_metrics *metrics);
#endif
