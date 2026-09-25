#ifndef MLKEM512_BASEMUL_ACC_K2_H
#define MLKEM512_BASEMUL_ACC_K2_H

#include <cstdint>

// ML-KEM-512 portable-library boundary:
//   a       : two NTT-domain polynomials, coefficients a[k][n]
//   b       : two NTT-domain polynomials, coefficients b[k][n]
//   b_cache : mulcache of b, coefficients b_cache[k][i]
//   result  : the K=2 vector BaseMul result, still in NTT domain
//
// No NTT, inverse NTT, 1441 scaling, compression, or canonical Barrett
// reduction is performed by this function.
void mlkem512_basemul_acc_k2(
    const int16_t a[2][256], const int16_t b[2][256],
    const int16_t b_cache[2][128], int16_t result[256]);

#endif
