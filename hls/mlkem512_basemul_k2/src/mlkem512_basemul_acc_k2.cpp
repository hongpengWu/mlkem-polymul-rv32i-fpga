#include "mlkem512_basemul_acc_k2.h"

#include <cstdint>

namespace {

constexpr int kQ = 3329;
constexpr uint32_t kQInv = 62209; // q^(-1) mod 2^16

// This is the same Montgomery contract as mlk_montgomery_reduce(), kept
// local so the new HLS block has no source dependency on third_party/.
static int16_t montgomery_reduce(int32_t value) {
    const uint16_t low = static_cast<uint16_t>(value);
    const uint16_t inverse = static_cast<uint16_t>(
        (static_cast<uint32_t>(low) * kQInv) & 0xffffu);
    const int16_t t = static_cast<int16_t>(inverse);
    const int32_t lifted = value - static_cast<int32_t>(t) * kQ;
    return static_cast<int16_t>(lifted >> 16);
}

} // namespace

void mlkem512_basemul_acc_k2(
    const int16_t a[2][256], const int16_t b[2][256],
    const int16_t b_cache[2][128], int16_t result[256]) {
#pragma HLS INLINE off
#pragma HLS ARRAY_PARTITION variable=a complete dim=1
#pragma HLS ARRAY_PARTITION variable=b complete dim=1
#pragma HLS ARRAY_PARTITION variable=b_cache complete dim=1

    // One iteration handles one degree-2 NTT base case. The K=2 loop is
    // fully unrolled to expose the vector dot product to the scheduler.
    for (int i = 0; i < 128; ++i) {
#pragma HLS PIPELINE II=1
        int32_t even = 0;
        int32_t odd = 0;

        for (int k = 0; k < 2; ++k) {
#pragma HLS UNROLL
            const int16_t a_even = a[k][2 * i];
            const int16_t a_odd = a[k][2 * i + 1];
            const int16_t b_even = b[k][2 * i];
            const int16_t b_odd = b[k][2 * i + 1];
            const int16_t cached_odd = b_cache[k][i];

            even += static_cast<int32_t>(a_odd) * cached_odd;
            even += static_cast<int32_t>(a_even) * b_even;
            odd += static_cast<int32_t>(a_even) * b_odd;
            odd += static_cast<int32_t>(a_odd) * b_even;
        }

        result[2 * i] = montgomery_reduce(even);
        result[2 * i + 1] = montgomery_reduce(odd);
    }
}
