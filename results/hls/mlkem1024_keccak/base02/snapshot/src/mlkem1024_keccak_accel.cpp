#include "mlkem1024_keccak_accel.h"

#ifndef KECCAK_IO_OPT
#define KECCAK_IO_OPT 1
#endif
#if KECCAK_IO_OPT != 0 && KECCAK_IO_OPT != 1
#error "KECCAK_IO_OPT must be 0 or 1"
#endif
namespace {

static const int KECCAK_LANES = 25;
static const int SHAKE128_RATE = 168;
static const int SHAKE256_RATE = 136;
static const uint64_t MAGIC = 0x4b344b4300000000ULL;

static const uint64_t ROUND_CONSTANTS[24] = {
    0x0000000000000001ULL, 0x0000000000008082ULL,
    0x800000000000808aULL, 0x8000000080008000ULL,
    0x000000000000808bULL, 0x0000000080000001ULL,
    0x8000000080008081ULL, 0x8000000000008009ULL,
    0x000000000000008aULL, 0x0000000000000088ULL,
    0x0000000080008009ULL, 0x000000008000000aULL,
    0x000000008000808bULL, 0x800000000000008bULL,
    0x8000000000008089ULL, 0x8000000000008003ULL,
    0x8000000000008002ULL, 0x8000000000000080ULL,
    0x000000000000800aULL, 0x800000008000000aULL,
    0x8000000080008081ULL, 0x8000000000008080ULL,
    0x0000000080000001ULL, 0x8000000080008008ULL
};

static const int ROTATION[25] = {
     0,  1, 62, 28, 27,
    36, 44,  6, 55, 20,
     3, 10, 43, 25, 39,
    41, 45, 15, 21,  8,
    18,   2, 61, 56, 14
};

static inline uint64_t rotl64(uint64_t x, int n) {
#pragma HLS INLINE
    if (n == 0) return x;
    return (x << n) | (x >> (64 - n));
}

static void keccak_f1600(uint64_t a[KECCAK_LANES]) {
#pragma HLS INLINE off
#pragma HLS ARRAY_PARTITION variable=a complete
ROUNDS:
    for (int round = 0; round < 24; ++round) {
#pragma HLS PIPELINE II=1
        uint64_t c[5];
        uint64_t d[5];
        uint64_t b[KECCAK_LANES];
#pragma HLS ARRAY_PARTITION variable=c complete
#pragma HLS ARRAY_PARTITION variable=d complete
#pragma HLS ARRAY_PARTITION variable=b complete

        // Theta.
        for (int x = 0; x < 5; ++x) {
#pragma HLS UNROLL
            c[x] = a[x] ^ a[x + 5] ^ a[x + 10] ^ a[x + 15] ^ a[x + 20];
        }
        for (int x = 0; x < 5; ++x) {
#pragma HLS UNROLL
            d[x] = c[(x + 4) % 5] ^ rotl64(c[(x + 1) % 5], 1);
        }
        for (int y = 0; y < 5; ++y) {
            for (int x = 0; x < 5; ++x) {
#pragma HLS UNROLL
                a[x + 5 * y] ^= d[x];
            }
        }

        // Rho and Pi.  The lane index is x + 5*y.
        for (int y = 0; y < 5; ++y) {
            for (int x = 0; x < 5; ++x) {
#pragma HLS UNROLL
                const int nx = y;
                const int ny = (2 * x + 3 * y) % 5;
                b[nx + 5 * ny] = rotl64(a[x + 5 * y], ROTATION[x + 5 * y]);
            }
        }

        // Chi.
        for (int y = 0; y < 5; ++y) {
            for (int x = 0; x < 5; ++x) {
#pragma HLS UNROLL
                a[x + 5 * y] = b[x + 5 * y] ^
                    ((~b[((x + 1) % 5) + 5 * y]) & b[((x + 2) % 5) + 5 * y]);
            }
        }

        // Iota.
        a[0] ^= ROUND_CONSTANTS[round];
    }
}

static inline void xor_byte(uint64_t state[KECCAK_LANES], int index, uint8_t value) {
#pragma HLS INLINE
    const int lane = index >> 3;
    const int shift = (index & 7) * 8;
    state[lane] ^= ((uint64_t)value) << shift;
}

static inline uint8_t get_byte(const uint64_t state[KECCAK_LANES], int index) {
#pragma HLS INLINE
    const int lane = index >> 3;
    const int shift = (index & 7) * 8;
    return (uint8_t)(state[lane] >> shift);
}

} // namespace

int mlkem1024_keccak_accel(
    const uint32_t input[KECCAK_INPUT_WORDS],
    uint32_t input_len,
    uint32_t output[KECCAK_OUTPUT_WORDS],
    uint32_t output_len,
    uint8_t mode, uint8_t command, uint64_t context[KECCAK_CONTEXT_WORDS]) {
#pragma HLS INTERFACE mode=bram port=input depth=512
#pragma HLS INTERFACE mode=bram port=output depth=1024
#pragma HLS INTERFACE mode=bram port=context depth=26
#pragma HLS INTERFACE mode=s_axilite port=input_len bundle=control
#pragma HLS INTERFACE mode=s_axilite port=output_len bundle=control
#pragma HLS INTERFACE mode=s_axilite port=mode bundle=control
#pragma HLS INTERFACE mode=s_axilite port=command bundle=control
#pragma HLS INTERFACE mode=s_axilite port=return bundle=control
#pragma HLS ALLOCATION instances=keccak_f1600 limit=1 function

    if (input_len > KECCAK_MAX_INPUT_BYTES || output_len > KECCAK_MAX_OUTPUT_BYTES ||
        mode > 3 || command > 2) return -1;
    if (command == 2) {
        if (input_len != 0 || output_len != 0) return -1;
CLEAR_CONTEXT:
        for (int i = 0; i < KECCAK_CONTEXT_WORDS; ++i) {
#pragma HLS PIPELINE II=1
            context[i] = 0;
        }
        return 0;
    }
    if (command == 1 && (input_len != 0 || mode >= 2)) return -1;
    if ((mode == 2 && output_len != 32) || (mode == 3 && output_len != 64)) return -1;
    const unsigned rate = mode == 0 ? SHAKE128_RATE : (mode == 3 ? 72 : SHAKE256_RATE);
    const uint8_t domain = mode < 2 ? 0x1f : 0x06;
    unsigned cursor = 0;
    if (command == 1) {
        const uint64_t meta = context[25];
        cursor = (unsigned)(meta & 0xffffU);
        if ((meta >> 32) != (MAGIC >> 32) || ((meta >> 16) & 0xffU) != mode ||
            (meta & 0xff000000ULL) != 0 || cursor > rate) return -2;
        if (output_len == 0) return 0;
    }
    uint64_t state[KECCAK_LANES];
#pragma HLS ARRAY_PARTITION variable=state complete
LOAD_CONTEXT:
    for (int i = 0; i < KECCAK_LANES; ++i) {
#pragma HLS PIPELINE II=1
        state[i] = command == 1 ? context[i] : 0;
    }
    if (command == 0) {
#if KECCAK_IO_OPT
        // Rate blocks are aligned to packed words. Mask final input bytes.
        unsigned base = 0;
ABSORB_BLOCKS:
        while (base < input_len) {
#pragma HLS LOOP_TRIPCOUNT min=0 max=29
            const unsigned bytes = input_len-base < rate ? input_len-base : rate;
            const unsigned words = (bytes+3) >> 2;
ABSORB_WORDS:
            for (unsigned j = 0; j < words; ++j) {
#pragma HLS PIPELINE II=2
#pragma HLS LOOP_TRIPCOUNT min=0 max=42
                uint32_t v = input[(base >> 2)+j];
                const unsigned left = bytes-(j << 2);
                if (left < 4) v &= 0xffffffffU >> ((4-left)*8);
                state[j >> 1] ^= (uint64_t)v << ((j & 1)*32);
            }
            base += bytes;
            cursor = bytes;
            if (bytes == rate) { keccak_f1600(state); cursor = 0; }
        }
#else
ABSORB_BYTES:
        for (uint32_t i = 0; i < input_len; ++i) {
            xor_byte(state, i % rate, (uint8_t)(input[i >> 2] >> ((i & 3)*8)));
            if ((i+1) % rate == 0) keccak_f1600(state);
        }
        cursor = input_len % rate;
#endif
        xor_byte(state, cursor, domain);
        xor_byte(state, rate-1, 0x80);
        keccak_f1600(state);
        cursor = 0;
    }
#if KECCAK_IO_OPT
    // Up to one packed word per step, preserving arbitrary continuation
    // offsets across lane and rate boundaries. No variable division.
    uint32_t pending = 0;
    unsigned filled = 0, written = 0;
SQUEEZE_WORDS:
    while (written < output_len) {
#pragma HLS LOOP_TRIPCOUNT min=0 max=1030
        if (cursor == rate) { keccak_f1600(state); cursor = 0; }
        unsigned take = 4-filled;
        if (take > output_len-written) take = output_len-written;
        if (take > rate-cursor) take = rate-cursor;
        const unsigned lane = cursor >> 3;
        const unsigned shift = (cursor & 7)*8;
        uint64_t data = state[lane] >> shift;
        if ((cursor & 7)+take > 8) data |= state[lane+1] << (64-shift);
        uint32_t word = (uint32_t)data;
        if (take < 4) word &= 0xffffffffU >> ((4-take)*8);
        pending |= word << (filled*8);
        cursor += take;
        written += take;
        filled += take;
        if (filled == 4 || written == output_len) {
            output[(written-1) >> 2] = pending;
            pending = 0; filled = 0;
        }
    }
#else
    uint32_t pending = 0;
SQUEEZE_BYTES:
    for (uint32_t i = 0; i < output_len; ++i) {
        if (cursor == rate) { keccak_f1600(state); cursor = 0; }
        pending |= (uint32_t)get_byte(state, cursor++) << ((i & 3)*8);
        if ((i & 3) == 3 || i+1 == output_len) {
            output[i >> 2] = pending; pending = 0;
        }
    }
#endif
SAVE_CONTEXT:
    for (int i = 0; i < KECCAK_LANES; ++i) {
#pragma HLS PIPELINE II=1
        context[i] = mode < 2 ? state[i] : 0;
    }
    context[25] = mode < 2 ? MAGIC | ((uint64_t)mode << 16) | cursor : 0;
    return 0;
}
