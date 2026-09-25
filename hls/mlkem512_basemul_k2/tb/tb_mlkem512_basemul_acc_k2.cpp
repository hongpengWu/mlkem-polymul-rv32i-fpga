#include "mlkem512_basemul_acc_k2.h"

#include <cstdint>
#include <cstdio>
#include <random>

namespace {

constexpr int kQ = 3329;
constexpr uint32_t kQInv = 62209;
constexpr int16_t kZetas[64] = {
    -1103, 430,
    555, 843, -1251, 871, 1550, 105, 422, 587,
    177, -235, -291, -460, 1574, 1653, -246, 778,
    1159, -147, -777, 1483, -602, 1119, -1590, 644,
    -872, 349, 418, 329, -156, -75, 817, 1097,
    603, 610, 1322, -1285, -1465, 384, -1215, -136,
    1218, -1335, -874, 220, -1187, -1659, -1185, -1530,
    -1278, 794, -1510, -854, -870, 478, -108, -308,
    996, 991, 958, -1460, 1522, 1628,
};

static int16_t montgomery_reduce_reference(int32_t value) {
    const uint16_t low = static_cast<uint16_t>(value);
    const uint16_t inverse = static_cast<uint16_t>(
        (static_cast<uint32_t>(low) * kQInv) & 0xffffu);
    const int16_t t = static_cast<int16_t>(inverse);
    const int32_t lifted = value - static_cast<int32_t>(t) * kQ;
    return static_cast<int16_t>(lifted >> 16);
}

static int canonical(int32_t value) {
    value %= kQ;
    return value < 0 ? value + kQ : value;
}

// Independent cache construction, intentionally kept in the testbench.
static void make_cache(const int16_t b[2][256], int16_t cache[2][128]) {
    for (int k = 0; k < 2; ++k) {
        for (int i = 0; i < 64; ++i) {
            const int16_t zeta = kZetas[i];
            cache[k][2 * i] = montgomery_reduce_reference(
                static_cast<int32_t>(b[k][4 * i + 1]) * zeta);
            cache[k][2 * i + 1] = montgomery_reduce_reference(
                static_cast<int32_t>(b[k][4 * i + 3]) * (-zeta));
        }
    }
}

// Independent direct BaseCaseMultiply oracle. It reconstructs each degree-2
// product from b and the zeta table instead of reusing the cached accumulation
// expression in the DUT. Comparison is modulo q because signed lazy
// representatives may differ by a multiple of q.
static void direct_reference(const int16_t a[2][256],
                             const int16_t b[2][256],
                             int16_t expected[256]) {
    for (int i = 0; i < 128; ++i) {
        const int block = i >> 1;
        const int offset = 4 * block + ((i & 1) ? 2 : 0);
        const int16_t zeta = (i & 1) ? static_cast<int16_t>(-kZetas[block])
                                    : kZetas[block];
        int32_t even = 0;
        int32_t odd = 0;
        for (int k = 0; k < 2; ++k) {
            const int16_t a0 = a[k][offset];
            const int16_t a1 = a[k][offset + 1];
            const int16_t b0 = b[k][offset];
            const int16_t b1 = b[k][offset + 1];
            even += montgomery_reduce_reference(
                static_cast<int32_t>(a0) * b0);
            even += montgomery_reduce_reference(
                static_cast<int32_t>(zeta) *
                montgomery_reduce_reference(static_cast<int32_t>(a1) * b1));
            odd += montgomery_reduce_reference(
                static_cast<int32_t>(a0) * b1);
            odd += montgomery_reduce_reference(
                static_cast<int32_t>(a1) * b0);
        }
        expected[2 * i] = static_cast<int16_t>(canonical(even));
        expected[2 * i + 1] = static_cast<int16_t>(canonical(odd));
    }
}

static int run_case(const char *name, const int16_t a[2][256],
                    const int16_t b[2][256]) {
    int16_t cache[2][128] = {};
    int16_t expected[256] = {};
    int16_t actual[256] = {};
    make_cache(b, cache);
    direct_reference(a, b, expected);
    mlkem512_basemul_acc_k2(a, b, cache, actual);

    int errors = 0;
    for (int i = 0; i < 256; ++i) {
        if (canonical(actual[i]) != canonical(expected[i])) {
            if (errors < 4) {
                std::printf("FAIL [%s] i=%d actual=%d expected=%d (mod q: %d/%d)\n",
                            name, i, static_cast<int>(actual[i]),
                            static_cast<int>(expected[i]), canonical(actual[i]),
                            canonical(expected[i]));
            }
            ++errors;
        }
    }
    if (!errors) {
        std::printf("PASS [%s]\n", name);
    }
    return errors;
}

} // namespace

int main() {
    int16_t a[2][256] = {};
    int16_t b[2][256] = {};
    int errors = 0;

    errors += run_case("all zero", a, b);

    for (int k = 0; k < 2; ++k) {
        for (int i = 0; i < 256; ++i) {
            a[k][i] = static_cast<int16_t>((37 * i + 19 * k) % 4096);
            b[k][i] = static_cast<int16_t>((23 * i * i + 11 * i + 7 * k) % kQ);
        }
    }
    errors += run_case("canonical deterministic", a, b);

    for (int k = 0; k < 2; ++k) {
        for (int i = 0; i < 256; ++i) {
            a[k][i] = static_cast<int16_t>((i & 1) ? 0 : 4095);
            b[k][i] = static_cast<int16_t>((i & 1) ? -(8 * kQ - 1)
                                                   : (8 * kQ - 1));
        }
    }
    errors += run_case("signed lazy boundary", a, b);

    std::mt19937 rng(0x512BACEu);
    for (int test = 0; test < 100; ++test) {
        for (int k = 0; k < 2; ++k) {
            for (int i = 0; i < 256; ++i) {
                a[k][i] = static_cast<int16_t>(rng() % 4096u);
                b[k][i] = static_cast<int16_t>((rng() % (16 * kQ - 1u)) -
                                                (8 * kQ - 1));
            }
        }
        char name[64];
        std::snprintf(name, sizeof(name), "random-%03d", test);
        errors += run_case(name, a, b);
    }

    if (errors == 0) {
        std::printf("MLKEM512 BASEMUL K2 C-SIM PASS cases=103\n");
        return 0;
    }
    std::printf("MLKEM512 BASEMUL K2 C-SIM FAIL errors=%d\n", errors);
    return 1;
}
