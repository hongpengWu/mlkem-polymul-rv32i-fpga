#ifndef MLKEM1024_KECCAK_ACCEL_H
#define MLKEM1024_KECCAK_ACCEL_H

#include <stdint.h>

// Packed little-endian BRAM words; the future CPU bridge owns arbitration.
// H(ek) needs 1568 bytes and J(z || c) needs 1600 bytes in ML-KEM-1024.
static const int KECCAK_MAX_INPUT_BYTES = 2048;
static const int KECCAK_MAX_OUTPUT_BYTES = 4096;
static const int KECCAK_INPUT_WORDS = KECCAK_MAX_INPUT_BYTES / 4;
static const int KECCAK_OUTPUT_WORDS = KECCAK_MAX_OUTPUT_BYTES / 4;
static const int KECCAK_CONTEXT_WORDS = 26;

// mode = 0: SHAKE128, mode = 1: SHAKE256, mode = 2: SHA3-256,
// mode = 3: SHA3-512.
// command 0 HASH: initialize, absorb, finalize and squeeze; retain SHAKE state.
// command 1 SQUEEZE: continue SHAKE, input_len=0, same mode as context.
// command 2 CLEAR: input_len=output_len=0, clear all context words.
// SHA3 requires output_len=32/64 and clears context. SHAKE permits length 0.
// context[0..24] are lanes x+5*y. Word 25 stores magic 0x4b344b43 in
// high32, mode in bits16..23, cursor 0..rate in low16; other bits must be zero.
// Returns 0, -1 (parameters) or -2 (context). Invalid calls modify nothing.
// Output high bytes of a partial final word are zero; later words untouched.
// Buffers must not alias. Timing depends on public command/mode/lengths.
int mlkem1024_keccak_accel(
    const uint32_t input[KECCAK_INPUT_WORDS],
    uint32_t input_len,
    uint32_t output[KECCAK_OUTPUT_WORDS],
    uint32_t output_len,
    uint8_t mode,
    uint8_t command,
    uint64_t context[KECCAK_CONTEXT_WORDS]);

#endif
