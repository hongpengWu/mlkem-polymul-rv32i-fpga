#include <stdint.h>
#include <stdio.h>
#include <string.h>

extern void software_polymul(int16_t *, int16_t *);
static uint32_t seed = 1;
static unsigned random_coeff(void)
{
    seed = seed * 1664525u + 1013904223u;
    return seed % 3329;
}

int main(void)
{
    int16_t a[256], b[256];
    int64_t oracle[256];
    for (unsigned test = 0; test < 36; ++test) {
        memset(a, 0, sizeof a);
        memset(b, 0, sizeof b);
        memset(oracle, 0, sizeof oracle);
        for (unsigned i = 0; i < 256; ++i) {
            if (test == 1) a[i] = b[i] = 3328;
            if (test == 3) {
                a[i] = (17*i*i + 31*i + 7) % 3329;
                b[i] = (29*i*i + 11*i + 19) % 3329;
            }
            if (test >= 4) { a[i] = random_coeff(); b[i] = random_coeff(); }
        }
        if (test == 2) { a[255] = 1; b[1] = 1; }
        for (unsigned i = 0; i < 256; ++i)
            for (unsigned j = 0; j < 256; ++j) {
                unsigned k = i + j;
                int64_t p = (int64_t)a[i] * b[j];
                oracle[k & 255] += k < 256 ? p : -p;
            }
        software_polymul(a, b);
        for (unsigned i = 0; i < 256; ++i) {
            int expected = (int)((oracle[i] % 3329 + 3329) % 3329);
            if (a[i] != expected) {
                printf("FAIL test=%u coefficient=%u got=%d expected=%d\n", test, i, a[i], expected);
                return 1;
            }
        }
    }
    puts("HOST SOFTWARE PASS: 36 vectors, 9216 coefficients, independent negacyclic oracle");
    return 0;
}
