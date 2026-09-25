#include "poly_ntt.h"

#include <limits.h>

_Static_assert(CHAR_BIT == 8 && INT16_MAX == 32767 && INT32_MAX == 2147483647,
               "This implementation requires exact 16/32-bit integer types");
_Static_assert((-1 >> 1) == -1, "This implementation requires arithmetic shift");

/*
 * Same Montgomery-domain twiddle constants as the existing HLS source:
 * third_party/mlkem-native/mlkem/src/zetas.inc.
 * They represent R * 17^bitrev7(i) mod 3329, R = 2^16, in centered form.
 * The software uses ordinary arrays and seven in-place butterfly stages;
 * it does not reproduce the hardware stream or packed-memory architecture.
 */
static const int16_t zetas[128] = {
    -1044, -758, -359, -1517, 1493, 1422, 287, 202,
    -171, 622, 1577, 182, 962, -1202, -1474, 1468,
    573, -1325, 264, 383, -829, 1458, -1602, -130,
    -681, 1017, 732, 608, -1542, 411, -205, -1571,
    1223, 652, -552, 1015, -1293, 1491, -282, -1544,
    516, -8, -320, -666, -1618, -1162, 126, 1469,
    -853, -90, -271, 830, 107, -1421, -247, -951,
    -398, 961, -1508, -725, 448, -1065, 677, -1275,
    -1103, 430, 555, 843, -1251, 871, 1550, 105,
    422, 587, 177, -235, -291, -460, 1574, 1653,
    -246, 778, 1159, -147, -777, 1483, -602, 1119,
    -1590, 644, -872, 349, 418, 329, -156, -75,
    817, 1097, 603, 610, 1322, -1285, -1465, 384,
    -1215, -136, 1218, -1335, -874, 220, -1187, -1659,
    -1185, -1530, -1278, 794, -1510, -854, -870, 478,
    -108, -308, 996, 991, 958, -1460, 1522, 1628
};

/* Return a * R^-1 mod q. 62209 = q^-1 mod 2^16. */
static inline int16_t montgomery_reduce(int32_t a)
{
    /* Unsigned wrap is intentional; form the signed low word explicitly. */
    int32_t t = (int32_t)(((uint32_t)a * UINT32_C(62209)) & UINT32_C(65535));
    t = (t ^ 32768) - 32768;
    return (int16_t)((a - t * SW_POLY_Q) >> 16);
}

/* Valid for every signed 16-bit input and the butterfly sums used below. */
static inline int16_t barrett_reduce(int32_t a)
{
    const int32_t v = 20159; /* round(2^26 / q) */
    int32_t t = (v * a + (INT32_C(1) << 25)) >> 26;
    return (int16_t)(a - t * SW_POLY_Q);
}

static inline int16_t fqmul(int16_t a, int16_t b)
{
    return montgomery_reduce((int32_t)a * (int32_t)b);
}

void sw_ntt(int16_t p[SW_POLY_N])
{
    unsigned int len, start, j;
    unsigned int k = 1;

    for (len = 128; len >= 2; len >>= 1) {
        for (start = 0; start < SW_POLY_N; start += 2 * len) {
            const int16_t zeta = zetas[k++];
            for (j = start; j < start + len; ++j) {
                const int16_t t = fqmul(zeta, p[j + len]);
                const int16_t u = p[j];
                p[j + len] = (int16_t)((int32_t)u - t);
                p[j] = (int16_t)((int32_t)u + t);
            }
        }
    }
    /* Center once after the lazy stages, bounding all BaseMul operands. */
    for (j = 0; j < SW_POLY_N; ++j)
        p[j] = barrett_reduce(p[j]);
}

static inline void basemul_pair(int16_t out[2], const int16_t a[2],
                               const int16_t b[2], int16_t zeta)
{
    /* Read the pair before storing, so exact in-place aliases are valid. */
    const int16_t a0 = a[0], a1 = a[1];
    const int16_t b0 = b[0], b1 = b[1];
    const int16_t r0 = (int16_t)((int32_t)fqmul(fqmul(a1, b1), zeta)
                              + fqmul(a0, b0));
    const int16_t r1 = (int16_t)((int32_t)fqmul(a0, b1) + fqmul(a1, b0));
    out[0] = r0;
    out[1] = r1;
}

void sw_basemul(int16_t out[SW_POLY_N], const int16_t a[SW_POLY_N],
                const int16_t b[SW_POLY_N])
{
    unsigned int i;
    for (i = 0; i < SW_POLY_N / 4; ++i) {
        basemul_pair(out + 4 * i, a + 4 * i, b + 4 * i, zetas[64 + i]);
        basemul_pair(out + 4 * i + 2, a + 4 * i + 2, b + 4 * i + 2,
                     (int16_t)-zetas[64 + i]);
    }
}

void sw_invntt(int16_t p[SW_POLY_N])
{
    unsigned int len, start, j;
    unsigned int k = 127;

    for (len = 2; len <= 128; len <<= 1) {
        for (start = 0; start < SW_POLY_N; start += 2 * len) {
            const int16_t zeta = zetas[k--];
            for (j = start; j < start + len; ++j) {
                const int16_t u = p[j];
                const int16_t v = p[j + len];
                p[j] = barrett_reduce((int32_t)u + v);
                p[j + len] = fqmul(zeta, (int16_t)((int32_t)v - u));
            }
        }
    }
    /* R^2 / 128: cancels BaseMul's R^-1 and the inverse's factor 128. */
    for (j = 0; j < SW_POLY_N; ++j)
        p[j] = fqmul(p[j], 1441);
}

void sw_canonicalize(int16_t p[SW_POLY_N])
{
    unsigned int i;
    for (i = 0; i < SW_POLY_N; ++i) {
        int32_t x = barrett_reduce(p[i]);
        x += (x >> 31) & SW_POLY_Q;
        p[i] = (int16_t)x;
    }
}

void sw_polymul(int16_t out[SW_POLY_N], const int16_t a[SW_POLY_N],
                const int16_t b[SW_POLY_N])
{
    int16_t btmp[SW_POLY_N];
    unsigned int i;

    for (i = 0; i < SW_POLY_N; ++i) {
        btmp[i] = b[i];
        out[i] = a[i];
    }
    sw_ntt(out);
    sw_ntt(btmp);
    sw_basemul(out, out, btmp);
    sw_invntt(out);
    sw_canonicalize(out);
}
