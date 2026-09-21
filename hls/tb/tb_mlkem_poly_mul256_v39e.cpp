#include <ap_int.h>
#include <cstdint>
#include <cstdio>

typedef ap_int<16> coeff_t;
static const int Q = 3329;

void mlkem_poly_mul256_v39e_true_one_dsp(
    const coeff_t a[256], const coeff_t b[256], coeff_t output[256]);

static int canonical(int64_t x) {
    x %= Q;
    return (int)(x < 0 ? x + Q : x);
}

// Independent O(N^2) oracle in Z_q[x]/(x^256+1).  It shares no NTT,
// BaseMul, Montgomery, K2-RED or packed-memory logic with the DUT.
static void naive_negacyclic(const coeff_t a[256], const coeff_t b[256],
                             int expected[256]) {
    int64_t accum[256] = {0};
    for (int i = 0; i < 256; ++i) {
        for (int j = 0; j < 256; ++j) {
            const int64_t product = (int64_t)(int)a[i] * (int)b[j];
            const int index = i + j;
            if (index < 256) accum[index] += product;
            else accum[index - 256] -= product;
        }
    }
    for (int i = 0; i < 256; ++i) expected[i] = canonical(accum[i]);
}

static int run_case(const char *name, const coeff_t a[256],
                    const coeff_t b[256]) {
    int expected[256];
    coeff_t actual[256];
    naive_negacyclic(a, b, expected);
    mlkem_poly_mul256_v39e_true_one_dsp(a, b, actual);

    int errors = 0;
    for (int i = 0; i < 256; ++i) {
        const int got = canonical((int)actual[i]);
        if (got != expected[i]) {
            if (errors < 8)
                std::printf("FAIL [%s] i=%d actual=%d expected=%d\n",
                            name, i, got, expected[i]);
            ++errors;
        }
        if ((int)actual[i] < 0 || (int)actual[i] >= Q) {
            if (errors < 8)
                std::printf("FAIL [%s] i=%d outside [0,q): %d\n",
                            name, i, (int)actual[i]);
            ++errors;
        }
    }
    if (!errors)
        std::printf("PASS [%s]: independent negacyclic oracle and canonical output\n", name);
    return errors;
}

int main() {
    coeff_t a[256], b[256];
    int errors = 0;

    for (int i = 0; i < 256; ++i) a[i] = b[i] = 0;
    a[255] = 1;
    b[1] = 1;
    errors += run_case("ring boundary x^255*x=-1", a, b);

    for (int i = 0; i < 256; ++i) {
        a[i] = (coeff_t)((17 * i * i + 31 * i + 7) % Q);
        b[i] = (coeff_t)((29 * i * i + 11 * i + 19) % Q);
    }
    errors += run_case("deterministic dense pair", a, b);

    uint32_t state = 0xc0dec0deu;
    for (int i = 0; i < 256; ++i) {
        state = state * 1664525u + 1013904223u;
        a[i] = (coeff_t)(state % Q);
        state = state * 1664525u + 1013904223u;
        b[i] = (coeff_t)(state % Q);
    }
    errors += run_case("deterministic pseudo-random pair", a, b);

    if (!errors) {
        std::printf("V39-E TRUE-ONE-DSP COMPLETE POLYMUL PASS\n");
        return 0;
    }
    std::printf("V39-E TRUE-ONE-DSP COMPLETE POLYMUL FAIL: %d errors\n",
                errors);
    return 1;
}
