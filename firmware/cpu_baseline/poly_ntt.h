#ifndef MLKEM_CPU_BASELINE_POLY_NTT_H
#define MLKEM_CPU_BASELINE_POLY_NTT_H

#include <stdint.h>

#define SW_POLY_N 256
#define SW_POLY_Q 3329

#ifdef __cplusplus
extern "C" {
#endif

/*
 * ML-KEM ring arithmetic in Z_3329[x]/(x^256 + 1).
 *
 * sw_ntt accepts coefficients in [0, 3328], transforms in place, and reduces
 * its bit-reversed NTT-domain output to centered representatives.
 * sw_basemul accepts two such NTT-domain arrays and produces their product
 * with one inverse Montgomery factor, R^-1, where R = 2^16.
 * sw_invntt accepts that product and includes the 1441 = R^2 / 128 (mod q)
 * final scaling. Its output is congruent to the ordinary polynomial product;
 * sw_canonicalize maps the resulting signed representatives into [0, 3328].
 * Consequently sw_invntt(sw_ntt(a)) alone equals R*a, not a, modulo q.
 *
 * sw_polymul accepts ordinary canonical inputs and returns canonical output.
 * It uses one 512-byte local work array. out may equal a, b, or both. The
 * input array(s) not aliased by out remain unchanged. sw_basemul also permits
 * out == a, out == b, or out == a == b. Partial overlap is not supported.
 * All arrays contain exactly SW_POLY_N int16_t coefficients.
 *
 * Arithmetic assumptions: 8-bit bytes, exact 16/32-bit integer types, and
 * arithmetic right shift of negative int32_t values, as provided by the
 * project's GCC RISC-V and host GCC targets. There is no signed overflow or
 * out-of-range signed narrowing in the documented input domains. Reduction
 * and butterfly loops have fixed bounds; no division/remainder is used.
 */
void sw_ntt(int16_t p[SW_POLY_N]);
void sw_basemul(int16_t out[SW_POLY_N], const int16_t a[SW_POLY_N],
                const int16_t b[SW_POLY_N]);
void sw_invntt(int16_t p[SW_POLY_N]);
void sw_canonicalize(int16_t p[SW_POLY_N]);
void sw_polymul(int16_t out[SW_POLY_N], const int16_t a[SW_POLY_N],
                const int16_t b[SW_POLY_N]);

#ifdef __cplusplus
}
#endif

#endif
