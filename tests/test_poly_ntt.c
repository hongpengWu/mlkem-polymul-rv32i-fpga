#include "poly_ntt.h"

#include <stdint.h>
#include <stdio.h>
#include <string.h>

static unsigned int cases;
static unsigned int checks;
static unsigned int errors;

static int16_t canonical(int64_t x)
{
    x %= SW_POLY_Q;
    return (int16_t)(x < 0 ? x + SW_POLY_Q : x);
}

/* Independent integer convolution; no NTT, twiddles or reduction helpers. */
static void oracle(int16_t out[SW_POLY_N], const int16_t a[SW_POLY_N],
                   const int16_t b[SW_POLY_N])
{
    int64_t accum[SW_POLY_N] = {0};
    unsigned int i, j;

    for (i = 0; i < SW_POLY_N; ++i) {
        for (j = 0; j < SW_POLY_N; ++j) {
            int64_t product = (int64_t)a[i] * b[j];
            unsigned int index = i + j;
            if (index < SW_POLY_N)
                accum[index] += product;
            else
                accum[index - SW_POLY_N] -= product;
        }
    }
    for (i = 0; i < SW_POLY_N; ++i)
        out[i] = canonical(accum[i]);
}

static void compare(const char *name, const char *variant,
                    const int16_t got[SW_POLY_N],
                    const int16_t expected[SW_POLY_N])
{
    unsigned int i;
    for (i = 0; i < SW_POLY_N; ++i) {
        ++checks;
        if (got[i] != expected[i] || got[i] < 0 || got[i] >= SW_POLY_Q) {
            if (errors < 12)
                printf("FAIL case=%s variant=%s i=%u got=%d expected=%d\n",
                       name, variant, i, (int)got[i], (int)expected[i]);
            ++errors;
        }
    }
}

static void run_case(const char *name, const int16_t a[SW_POLY_N],
                     const int16_t b[SW_POLY_N])
{
    int16_t expected[SW_POLY_N], out[SW_POLY_N];
    int16_t wa[SW_POLY_N], wb[SW_POLY_N];
    unsigned int i;

    ++cases;
    oracle(expected, a, b);
    sw_polymul(out, a, b);
    compare(name, "separate", out, expected);

    memcpy(wa, a, sizeof(wa));
    memcpy(wb, b, sizeof(wb));
    sw_polymul(wa, wa, wb);
    compare(name, "out=a", wa, expected);
    compare(name, "preserve-b", wb, b);

    memcpy(wa, a, sizeof(wa));
    memcpy(wb, b, sizeof(wb));
    sw_polymul(wb, wa, wb);
    compare(name, "out=b", wb, expected);
    compare(name, "preserve-a", wa, a);

    memcpy(wa, a, sizeof(wa));
    memcpy(wb, b, sizeof(wb));
    sw_ntt(wa);
    sw_ntt(wb);
    sw_basemul(wb, wa, wb);
    sw_invntt(wb);
    sw_canonicalize(wb);
    compare(name, "staged-out=b", wb, expected);

    /* The inverse has the reference algorithm's additional Montgomery R. */
    memcpy(wa, a, sizeof(wa));
    sw_ntt(wa);
    sw_invntt(wa);
    sw_canonicalize(wa);
    for (i = 0; i < SW_POLY_N; ++i)
        out[i] = canonical((int64_t)a[i] * 2285);
    compare(name, "roundtrip-R", wa, out);
}

static uint32_t next_random(uint32_t *state)
{
    *state = *state * UINT32_C(1664525) + UINT32_C(1013904223);
    return *state;
}

int main(void)
{
    int16_t a[SW_POLY_N] = {0}, b[SW_POLY_N] = {0};
    int16_t expected[SW_POLY_N], out[SW_POLY_N];
    uint32_t state = UINT32_C(0xc0dec0de);
    unsigned int i, trial;
    char name[40];

    run_case("all-zero", a, b);

    for (i = 0; i < SW_POLY_N; ++i)
        a[i] = (int16_t)i;
    b[0] = 1;
    run_case("multiplicative-identity", a, b);

    memset(a, 0, sizeof(a));
    memset(b, 0, sizeof(b));
    a[255] = 1;
    b[1] = 1;
    run_case("x255-times-x", a, b);

    for (i = 0; i < SW_POLY_N; ++i)
        a[i] = b[i] = SW_POLY_Q - 1;
    run_case("all-q-minus-one", a, b);

    for (i = 0; i < SW_POLY_N; ++i) {
        a[i] = (int16_t)((17 * i * i + 31 * i + 7) % SW_POLY_Q);
        b[i] = (int16_t)((29 * i * i + 11 * i + 19) % SW_POLY_Q);
    }
    run_case("deterministic-dense", a, b);

    /* Cover exact alias of both inputs; expected is independently squared. */
    oracle(expected, a, a);
    memcpy(out, a, sizeof(out));
    sw_polymul(out, out, out);
    compare("deterministic-square", "out=a=b", out, expected);
    memcpy(out, a, sizeof(out));
    sw_ntt(out);
    sw_basemul(out, out, out);
    sw_invntt(out);
    sw_canonicalize(out);
    compare("deterministic-square", "staged-out=a=b", out, expected);

    for (i = 0; i < SW_POLY_N; ++i) {
        a[i] = (int16_t)((i & 1) ? SW_POLY_Q - 1 : 0);
        b[i] = (int16_t)((i & 1) ? 1 : SW_POLY_Q - 1);
    }
    run_case("alternating-boundaries", a, b);

    /* First random pair is identical to the existing HLS/RTL core TB. */
    for (trial = 0; trial < 128; ++trial) {
        for (i = 0; i < SW_POLY_N; ++i) {
            a[i] = (int16_t)(next_random(&state) % SW_POLY_Q);
            b[i] = (int16_t)(next_random(&state) % SW_POLY_Q);
        }
        (void)snprintf(name, sizeof(name), "random-%u", trial);
        run_case(name, a, b);
    }

    /* Canonicalization also accepts every possible signed 16-bit value. */
    for (trial = 0; trial < 256; ++trial) {
        for (i = 0; i < SW_POLY_N; ++i) {
            int32_t value = (int32_t)(trial * SW_POLY_N + i) - 32768;
            out[i] = (int16_t)value;
            expected[i] = canonical(value);
        }
        sw_canonicalize(out);
        compare("all-int16-values", "canonicalize", out, expected);
    }

    if (errors) {
        printf("CPU_POLY_NTT_FAIL cases=%u coefficient_checks=%u errors=%u\n",
               cases, checks, errors);
        return 1;
    }
    printf("CPU_POLY_NTT_PASS cases=%u random_cases=128 coefficient_checks=%u "
           "seed=0xc0dec0de canonical_values=65536 aliases=separate/a/b/both\n",
           cases, checks);
    return 0;
}
