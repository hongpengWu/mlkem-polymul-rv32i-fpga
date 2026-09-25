# ML-KEM-512 phase profile

145/145 pinned official ML-KEM-512 records; complete profiling suite.

Configuration: rv32im_fast, 64 KiB RAM; profiling firmware is separate from the retained baseline.

Raw rdcycle API interval, empty bracket retained without subtraction; seed decapsulation includes key expansion. Exclusive phases, including Other/unclassified, partition this exact interval.

Inclusive cycles include nested phases and overlap; never sum them or interpret their sum as a runtime share.

Per-case delta versus the identical original rv32im_fast official record. It includes marker execution and compiler/code-layout perturbation; it is not a pure marker cost. Profiled cycles are diagnostic, not a new performance baseline.

## Instrumentation and compiler overhead

| API / return | N | Baseline cycles | Profiled cycles | Delta cycles | Delta % | Same M counts |
|---|---:|---:|---:|---:|---:|---:|
| keyGen / 0 | 25 | 131,735,099 | 131,909,377 | +174,278 | +0.132% | 25/25 |
| encapsulation / 0 | 50 | 279,054,831 | 279,472,699 | +417,868 | +0.150% | 50/50 |
| decapsulation / 0 | 20 | 138,754,785 | 138,956,685 | +201,900 | +0.146% | 20/20 |
| decapsulationSeed / 0 | 10 | 121,320,854 | 121,490,714 | +169,860 | +0.140% | 10/10 |
| encapsulationKeyCheck / -4 | 10 | 1,289,430 | 1,295,320 | +5,890 | +0.457% | 10/10 |
| encapsulationKeyCheck / 0 | 10 | 1,289,320 | 1,295,210 | +5,890 | +0.457% | 10/10 |
| decapsulationKeyCheck / -5 | 10 | 9,414,520 | 9,423,300 | +8,780 | +0.093% | 10/10 |
| decapsulationKeyCheck / 0 | 10 | 9,414,410 | 9,423,190 | +8,780 | +0.093% | 10/10 |

## keyGen / return 0

Exclusive categories partition the API interval; their shares sum to 100% before rounding.

| Category | Exclusive cycles | Exclusive share |
|---|---:|---:|
| Other | 6,625 | 0.0050% |
| api_control | 14,175 | 0.0107% |
| basemul_acc | 1,718,000 | 1.3024% |
| compression | 0 | 0.0000% |
| decompression | 0 | 0.0000% |
| encoding | 1,308,400 | 0.9919% |
| explicit_reduce_convert | 4,218,400 | 3.1980% |
| intt | 0 | 0.0000% |
| keccak_permutation | 106,441,455 | 80.6929% |
| kpke_control | 85,975 | 0.0652% |
| matrix_control | 42,924 | 0.0325% |
| memory_copy | 235,800 | 0.1788% |
| mulcache | 563,400 | 0.4271% |
| noise_cbd | 1,566,000 | 1.1872% |
| noise_control | 33,775 | 0.0256% |
| ntt | 10,244,900 | 7.7666% |
| poly_add_sub | 513,400 | 0.3892% |
| rejection_sampling | 2,351,218 | 1.7824% |
| sha_sponge | 1,251,455 | 0.9487% |
| zeroize | 1,313,475 | 0.9957% |

Inclusive values below overlap and must not be added.

| Phase | Category | Calls | Exclusive cycles | Exclusive share | Inclusive cycles |
|---|---|---:|---:|---:|---:|
| 0: unclassified | unclassified | 0 | 6,625 | 0.0050% | 6,625 |
| 1: kem_keypair_derand | api_control | 25 | 14,175 | 0.0107% | 131,902,752 |
| 2: kem_enc_derand | api_control | 0 | 0 | 0.0000% | 0 |
| 3: kem_dec | api_control | 0 | 0 | 0.0000% | 0 |
| 4: kem_check_pk | api_control | 0 | 0 | 0.0000% | 0 |
| 5: kem_check_sk | api_control | 0 | 0 | 0.0000% | 0 |
| 6: indcpa_keypair_derand | kpke_control | 25 | 85,975 | 0.0652% | 108,200,127 |
| 7: indcpa_enc | kpke_control | 0 | 0 | 0.0000% | 0 |
| 8: indcpa_dec | kpke_control | 0 | 0 | 0.0000% | 0 |
| 9: gen_matrix | matrix_control | 25 | 42,924 | 0.0325% | 51,702,752 |
| 10: rej_uniform | rejection_sampling | 112 | 2,351,218 | 1.7824% | 2,351,218 |
| 11: poly_getnoise_eta1_4x | noise_control | 25 | 33,775 | 0.0256% | 33,206,225 |
| 12: poly_getnoise_eta2 | noise_control | 0 | 0 | 0.0000% | 0 |
| 13: poly_getnoise_eta1122_4x | noise_control | 0 | 0 | 0.0000% | 0 |
| 14: poly_cbd2 | noise_cbd | 0 | 0 | 0.0000% | 0 |
| 15: poly_cbd3 | noise_cbd | 100 | 1,566,000 | 1.1872% | 1,566,000 |
| 16: keccakf1600_permute | keccak_permutation | 687 | 106,441,455 | 80.6929% | 106,441,455 |
| 17: shake128_absorb_once | sha_sponge | 0 | 0 | 0.0000% | 0 |
| 18: shake128_squeezeblocks | sha_sponge | 0 | 0 | 0.0000% | 0 |
| 19: shake256 | sha_sponge | 100 | 351,100 | 0.2662% | 31,452,600 |
| 20: sha3_256 | sha_sponge | 25 | 266,575 | 0.2021% | 23,533,150 |
| 21: sha3_512 | sha_sponge | 25 | 55,925 | 0.0424% | 3,955,125 |
| 22: shake128x4_absorb_once | sha_sponge | 25 | 156,375 | 0.1185% | 156,375 |
| 23: shake128x4_squeezeblocks | sha_sponge | 28 | 421,480 | 0.3195% | 48,760,810 |
| 24: shake256x4 | sha_sponge | 0 | 0 | 0.0000% | 0 |
| 25: poly_ntt | ntt | 100 | 10,244,900 | 7.7666% | 10,244,900 |
| 26: poly_invntt_tomont | intt | 0 | 0 | 0.0000% | 0 |
| 27: polyvec_basemul_acc_montgomery_cached | basemul_acc | 50 | 1,718,000 | 1.3024% | 1,718,000 |
| 28: poly_mulcache_compute | mulcache | 50 | 563,400 | 0.4271% | 563,400 |
| 29: poly_reduce | explicit_reduce_convert | 100 | 3,307,200 | 2.5072% | 3,307,200 |
| 30: poly_tomont | explicit_reduce_convert | 50 | 911,200 | 0.6908% | 911,200 |
| 31: poly_add | poly_add_sub | 50 | 513,400 | 0.3892% | 513,400 |
| 32: poly_sub | poly_add_sub | 0 | 0 | 0.0000% | 0 |
| 33: poly_compress_d4 | compression | 0 | 0 | 0.0000% | 0 |
| 34: poly_compress_d10 | compression | 0 | 0 | 0.0000% | 0 |
| 35: poly_decompress_d4 | decompression | 0 | 0 | 0.0000% | 0 |
| 36: poly_decompress_d10 | decompression | 0 | 0 | 0.0000% | 0 |
| 37: poly_tobytes | encoding | 100 | 1,308,400 | 0.9919% | 1,308,400 |
| 38: poly_frombytes | encoding | 0 | 0 | 0.0000% | 0 |
| 39: poly_frommsg | encoding | 0 | 0 | 0.0000% | 0 |
| 40: poly_tomsg | encoding | 0 | 0 | 0.0000% | 0 |
| 41: zeroize | zeroize | 450 | 1,313,475 | 0.9957% | 1,313,475 |
| 42: memcpy | memory_copy | 300 | 235,800 | 0.1788% | 235,800 |

## encapsulation / return 0

Exclusive categories partition the API interval; their shares sum to 100% before rounding.

| Category | Exclusive cycles | Exclusive share |
|---|---:|---:|
| Other | 15,950 | 0.0057% |
| api_control | 482,450 | 0.1726% |
| basemul_acc | 5,154,000 | 1.8442% |
| compression | 2,436,200 | 0.8717% |
| decompression | 0 | 0.0000% |
| encoding | 3,825,800 | 1.3689% |
| explicit_reduce_convert | 8,268,000 | 2.9584% |
| intt | 26,607,150 | 9.5205% |
| keccak_permutation | 203,896,490 | 72.9576% |
| kpke_control | 197,400 | 0.0706% |
| matrix_control | 84,729 | 0.0303% |
| memory_copy | 193,200 | 0.0691% |
| mulcache | 1,126,800 | 0.4032% |
| noise_cbd | 3,737,400 | 1.3373% |
| noise_control | 97,900 | 0.0350% |
| ntt | 10,244,900 | 3.6658% |
| poly_add_sub | 2,053,600 | 0.7348% |
| rejection_sampling | 4,697,540 | 1.6809% |
| sha_sponge | 2,581,740 | 0.9238% |
| zeroize | 3,771,450 | 1.3495% |

Inclusive values below overlap and must not be added.

| Phase | Category | Calls | Exclusive cycles | Exclusive share | Inclusive cycles |
|---|---|---:|---:|---:|---:|
| 0: unclassified | unclassified | 0 | 15,950 | 0.0057% | 15,950 |
| 1: kem_keypair_derand | api_control | 0 | 0 | 0.0000% | 0 |
| 2: kem_enc_derand | api_control | 50 | 52,550 | 0.0188% | 279,456,749 |
| 3: kem_dec | api_control | 0 | 0 | 0.0000% | 0 |
| 4: kem_check_pk | api_control | 50 | 429,900 | 0.1538% | 6,463,600 |
| 5: kem_check_sk | api_control | 0 | 0 | 0.0000% | 0 |
| 6: indcpa_keypair_derand | kpke_control | 0 | 0 | 0.0000% | 0 |
| 7: indcpa_enc | kpke_control | 50 | 197,400 | 0.0706% | 217,876,399 |
| 8: indcpa_dec | kpke_control | 0 | 0 | 0.0000% | 0 |
| 9: gen_matrix | matrix_control | 50 | 84,729 | 0.0303% | 102,149,149 |
| 10: rej_uniform | rejection_sampling | 216 | 4,697,540 | 1.6809% | 4,697,540 |
| 11: poly_getnoise_eta1_4x | noise_control | 0 | 0 | 0.0000% | 0 |
| 12: poly_getnoise_eta2 | noise_control | 50 | 23,450 | 0.0084% | 8,759,350 |
| 13: poly_getnoise_eta1122_4x | noise_control | 50 | 74,450 | 0.0266% | 50,740,650 |
| 14: poly_cbd2 | noise_cbd | 150 | 2,171,400 | 0.7770% | 2,171,400 |
| 15: poly_cbd3 | noise_cbd | 100 | 1,566,000 | 0.5603% | 1,566,000 |
| 16: keccakf1600_permute | keccak_permutation | 1,316 | 203,896,490 | 72.9576% | 203,896,490 |
| 17: shake128_absorb_once | sha_sponge | 0 | 0 | 0.0000% | 0 |
| 18: shake128_squeezeblocks | sha_sponge | 0 | 0 | 0.0000% | 0 |
| 19: shake256 | sha_sponge | 250 | 778,150 | 0.2784% | 55,291,050 |
| 20: sha3_256 | sha_sponge | 50 | 533,150 | 0.1908% | 47,066,300 |
| 21: sha3_512 | sha_sponge | 50 | 125,600 | 0.0449% | 7,924,000 |
| 22: shake128x4_absorb_once | sha_sponge | 50 | 312,750 | 0.1119% | 312,750 |
| 23: shake128x4_squeezeblocks | sha_sponge | 54 | 832,090 | 0.2977% | 96,271,280 |
| 24: shake256x4 | sha_sponge | 0 | 0 | 0.0000% | 0 |
| 25: poly_ntt | ntt | 100 | 10,244,900 | 3.6658% | 10,244,900 |
| 26: poly_invntt_tomont | intt | 150 | 26,607,150 | 9.5205% | 26,607,150 |
| 27: polyvec_basemul_acc_montgomery_cached | basemul_acc | 150 | 5,154,000 | 1.8442% | 5,154,000 |
| 28: poly_mulcache_compute | mulcache | 100 | 1,126,800 | 0.4032% | 1,126,800 |
| 29: poly_reduce | explicit_reduce_convert | 250 | 8,268,000 | 2.9584% | 8,268,000 |
| 30: poly_tomont | explicit_reduce_convert | 0 | 0 | 0.0000% | 0 |
| 31: poly_add | poly_add_sub | 200 | 2,053,600 | 0.7348% | 2,053,600 |
| 32: poly_sub | poly_add_sub | 0 | 0 | 0.0000% | 0 |
| 33: poly_compress_d4 | compression | 50 | 487,000 | 0.1743% | 487,000 |
| 34: poly_compress_d10 | compression | 100 | 1,949,200 | 0.6975% | 1,949,200 |
| 35: poly_decompress_d4 | decompression | 0 | 0 | 0.0000% | 0 |
| 36: poly_decompress_d10 | decompression | 0 | 0 | 0.0000% | 0 |
| 37: poly_tobytes | encoding | 100 | 1,308,400 | 0.4682% | 1,308,400 |
| 38: poly_frombytes | encoding | 200 | 2,004,000 | 0.7171% | 2,004,000 |
| 39: poly_frommsg | encoding | 50 | 513,400 | 0.1837% | 513,400 |
| 40: poly_tomsg | encoding | 0 | 0 | 0.0000% | 0 |
| 41: zeroize | zeroize | 1,400 | 3,771,450 | 1.3495% | 3,771,450 |
| 42: memcpy | memory_copy | 600 | 193,200 | 0.0691% | 193,200 |

## decapsulation / return 0

Exclusive categories partition the API interval; their shares sum to 100% before rounding.

| Category | Exclusive cycles | Exclusive share |
|---|---:|---:|
| Other | 6,140 | 0.0044% |
| api_control | 238,180 | 0.1714% |
| basemul_acc | 2,748,800 | 1.9782% |
| compression | 974,480 | 0.7013% |
| decompression | 839,760 | 0.6043% |
| encoding | 1,262,480 | 0.9085% |
| explicit_reduce_convert | 2,645,760 | 1.9040% |
| intt | 14,190,480 | 10.2122% |
| keccak_permutation | 99,159,700 | 71.3602% |
| kpke_control | 114,140 | 0.0821% |
| matrix_control | 33,280 | 0.0239% |
| memory_copy | 190,440 | 0.1370% |
| mulcache | 901,440 | 0.6487% |
| noise_cbd | 1,494,960 | 1.0758% |
| noise_control | 39,160 | 0.0282% |
| ntt | 8,195,920 | 5.8982% |
| poly_add_sub | 1,026,800 | 0.7389% |
| rejection_sampling | 1,876,025 | 1.3501% |
| sha_sponge | 1,238,360 | 0.8912% |
| zeroize | 1,780,380 | 1.2812% |

Inclusive values below overlap and must not be added.

| Phase | Category | Calls | Exclusive cycles | Exclusive share | Inclusive cycles |
|---|---|---:|---:|---:|---:|
| 0: unclassified | unclassified | 0 | 6,140 | 0.0044% | 6,140 |
| 1: kem_keypair_derand | api_control | 0 | 0 | 0.0000% | 0 |
| 2: kem_enc_derand | api_control | 0 | 0 | 0.0000% | 0 |
| 3: kem_dec | api_control | 20 | 227,620 | 0.1638% | 138,950,545 |
| 4: kem_check_pk | api_control | 0 | 0 | 0.0000% | 0 |
| 5: kem_check_sk | api_control | 20 | 10,560 | 0.0076% | 18,842,540 |
| 6: indcpa_keypair_derand | kpke_control | 0 | 0 | 0.0000% | 0 |
| 7: indcpa_enc | kpke_control | 20 | 78,960 | 0.0568% | 86,146,685 |
| 8: indcpa_dec | kpke_control | 20 | 35,180 | 0.0253% | 11,517,020 |
| 9: gen_matrix | matrix_control | 20 | 33,280 | 0.0239% | 39,855,785 |
| 10: rej_uniform | rejection_sampling | 80 | 1,876,025 | 1.3501% | 1,876,025 |
| 11: poly_getnoise_eta1_4x | noise_control | 0 | 0 | 0.0000% | 0 |
| 12: poly_getnoise_eta2 | noise_control | 20 | 9,380 | 0.0068% | 3,503,740 |
| 13: poly_getnoise_eta1122_4x | noise_control | 20 | 29,780 | 0.0214% | 20,296,260 |
| 14: poly_cbd2 | noise_cbd | 60 | 868,560 | 0.6251% | 868,560 |
| 15: poly_cbd3 | noise_cbd | 40 | 626,400 | 0.4508% | 626,400 |
| 16: keccakf1600_permute | keccak_permutation | 640 | 99,159,700 | 71.3602% | 99,159,700 |
| 17: shake128_absorb_once | sha_sponge | 0 | 0 | 0.0000% | 0 |
| 18: shake128_squeezeblocks | sha_sponge | 0 | 0 | 0.0000% | 0 |
| 19: shake256 | sha_sponge | 120 | 525,620 | 0.3783% | 40,946,200 |
| 20: sha3_256 | sha_sponge | 20 | 213,260 | 0.1535% | 18,826,520 |
| 21: sha3_512 | sha_sponge | 20 | 50,240 | 0.0362% | 3,169,600 |
| 22: shake128x4_absorb_once | sha_sponge | 20 | 125,100 | 0.0900% | 125,100 |
| 23: shake128x4_squeezeblocks | sha_sponge | 20 | 324,140 | 0.2333% | 37,508,240 |
| 24: shake256x4 | sha_sponge | 0 | 0 | 0.0000% | 0 |
| 25: poly_ntt | ntt | 80 | 8,195,920 | 5.8982% | 8,195,920 |
| 26: poly_invntt_tomont | intt | 80 | 14,190,480 | 10.2122% | 14,190,480 |
| 27: polyvec_basemul_acc_montgomery_cached | basemul_acc | 80 | 2,748,800 | 1.9782% | 2,748,800 |
| 28: poly_mulcache_compute | mulcache | 80 | 901,440 | 0.6487% | 901,440 |
| 29: poly_reduce | explicit_reduce_convert | 80 | 2,645,760 | 1.9040% | 2,645,760 |
| 30: poly_tomont | explicit_reduce_convert | 0 | 0 | 0.0000% | 0 |
| 31: poly_add | poly_add_sub | 80 | 821,440 | 0.5911% | 821,440 |
| 32: poly_sub | poly_add_sub | 20 | 205,360 | 0.1478% | 205,360 |
| 33: poly_compress_d4 | compression | 20 | 194,800 | 0.1402% | 194,800 |
| 34: poly_compress_d10 | compression | 40 | 779,680 | 0.5611% | 779,680 |
| 35: poly_decompress_d4 | decompression | 20 | 210,640 | 0.1516% | 210,640 |
| 36: poly_decompress_d10 | decompression | 40 | 629,120 | 0.4527% | 629,120 |
| 37: poly_tobytes | encoding | 0 | 0 | 0.0000% | 0 |
| 38: poly_frombytes | encoding | 80 | 801,600 | 0.5769% | 801,600 |
| 39: poly_frommsg | encoding | 20 | 205,360 | 0.1478% | 205,360 |
| 40: poly_tomsg | encoding | 20 | 255,520 | 0.1839% | 255,520 |
| 41: zeroize | zeroize | 680 | 1,780,380 | 1.2812% | 1,780,380 |
| 42: memcpy | memory_copy | 260 | 190,440 | 0.1370% | 190,440 |

## decapsulationSeed / return 0

Exclusive categories partition the API interval; their shares sum to 100% before rounding.

| Category | Exclusive cycles | Exclusive share |
|---|---:|---:|
| Other | 5,090 | 0.0042% |
| api_control | 124,760 | 0.1027% |
| basemul_acc | 2,061,600 | 1.6969% |
| compression | 487,240 | 0.4011% |
| decompression | 419,880 | 0.3456% |
| encoding | 1,154,600 | 0.9504% |
| explicit_reduce_convert | 3,010,240 | 2.4778% |
| intt | 7,095,240 | 5.8402% |
| keccak_permutation | 91,412,750 | 75.2426% |
| kpke_control | 91,460 | 0.0753% |
| matrix_control | 33,350 | 0.0275% |
| memory_copy | 189,540 | 0.1560% |
| mulcache | 676,080 | 0.5565% |
| noise_cbd | 1,373,880 | 1.1309% |
| noise_control | 33,090 | 0.0272% |
| ntt | 8,195,920 | 6.7461% |
| poly_add_sub | 718,760 | 0.5916% |
| rejection_sampling | 1,878,414 | 1.5461% |
| sha_sponge | 1,113,240 | 0.9163% |
| zeroize | 1,415,580 | 1.1652% |

Inclusive values below overlap and must not be added.

| Phase | Category | Calls | Exclusive cycles | Exclusive share | Inclusive cycles |
|---|---|---:|---:|---:|---:|
| 0: unclassified | unclassified | 0 | 5,090 | 0.0042% | 5,090 |
| 1: kem_keypair_derand | api_control | 10 | 5,670 | 0.0047% | 52,009,157 |
| 2: kem_enc_derand | api_control | 0 | 0 | 0.0000% | 0 |
| 3: kem_dec | api_control | 10 | 113,810 | 0.0937% | 69,476,467 |
| 4: kem_check_pk | api_control | 0 | 0 | 0.0000% | 0 |
| 5: kem_check_sk | api_control | 10 | 5,280 | 0.0043% | 9,421,270 |
| 6: indcpa_keypair_derand | kpke_control | 10 | 34,390 | 0.0283% | 42,528,107 |
| 7: indcpa_enc | kpke_control | 10 | 39,480 | 0.0325% | 43,074,537 |
| 8: indcpa_dec | kpke_control | 10 | 17,590 | 0.0145% | 5,758,510 |
| 9: gen_matrix | matrix_control | 20 | 33,350 | 0.0275% | 39,858,244 |
| 10: rej_uniform | rejection_sampling | 80 | 1,878,414 | 1.5461% | 1,878,414 |
| 11: poly_getnoise_eta1_4x | noise_control | 10 | 13,510 | 0.0111% | 13,282,490 |
| 12: poly_getnoise_eta2 | noise_control | 10 | 4,690 | 0.0039% | 1,751,870 |
| 13: poly_getnoise_eta1122_4x | noise_control | 10 | 14,890 | 0.0123% | 10,148,130 |
| 14: poly_cbd2 | noise_cbd | 30 | 434,280 | 0.3575% | 434,280 |
| 15: poly_cbd3 | noise_cbd | 60 | 939,600 | 0.7734% | 939,600 |
| 16: keccakf1600_permute | keccak_permutation | 590 | 91,412,750 | 75.2426% | 91,412,750 |
| 17: shake128_absorb_once | sha_sponge | 0 | 0 | 0.0000% | 0 |
| 18: shake128_squeezeblocks | sha_sponge | 0 | 0 | 0.0000% | 0 |
| 19: shake256 | sha_sponge | 100 | 403,250 | 0.3319% | 33,054,140 |
| 20: sha3_256 | sha_sponge | 20 | 213,260 | 0.1755% | 18,826,520 |
| 21: sha3_512 | sha_sponge | 20 | 47,490 | 0.0391% | 3,166,850 |
| 22: shake128x4_absorb_once | sha_sponge | 20 | 125,100 | 0.1030% | 125,100 |
| 23: shake128x4_squeezeblocks | sha_sponge | 20 | 324,140 | 0.2668% | 37,508,240 |
| 24: shake256x4 | sha_sponge | 0 | 0 | 0.0000% | 0 |
| 25: poly_ntt | ntt | 80 | 8,195,920 | 6.7461% | 8,195,920 |
| 26: poly_invntt_tomont | intt | 40 | 7,095,240 | 5.8402% | 7,095,240 |
| 27: polyvec_basemul_acc_montgomery_cached | basemul_acc | 60 | 2,061,600 | 1.6969% | 2,061,600 |
| 28: poly_mulcache_compute | mulcache | 60 | 676,080 | 0.5565% | 676,080 |
| 29: poly_reduce | explicit_reduce_convert | 80 | 2,645,760 | 2.1777% | 2,645,760 |
| 30: poly_tomont | explicit_reduce_convert | 20 | 364,480 | 0.3000% | 364,480 |
| 31: poly_add | poly_add_sub | 60 | 616,080 | 0.5071% | 616,080 |
| 32: poly_sub | poly_add_sub | 10 | 102,680 | 0.0845% | 102,680 |
| 33: poly_compress_d4 | compression | 10 | 97,400 | 0.0802% | 97,400 |
| 34: poly_compress_d10 | compression | 20 | 389,840 | 0.3209% | 389,840 |
| 35: poly_decompress_d4 | decompression | 10 | 105,320 | 0.0867% | 105,320 |
| 36: poly_decompress_d10 | decompression | 20 | 314,560 | 0.2589% | 314,560 |
| 37: poly_tobytes | encoding | 40 | 523,360 | 0.4308% | 523,360 |
| 38: poly_frombytes | encoding | 40 | 400,800 | 0.3299% | 400,800 |
| 39: poly_frommsg | encoding | 10 | 102,680 | 0.0845% | 102,680 |
| 40: poly_tomsg | encoding | 10 | 127,760 | 0.1052% | 127,760 |
| 41: zeroize | zeroize | 520 | 1,415,580 | 1.1652% | 1,415,580 |
| 42: memcpy | memory_copy | 250 | 189,540 | 0.1560% | 189,540 |

## encapsulationKeyCheck / return -4

Exclusive categories partition the API interval; their shares sum to 100% before rounding.

| Category | Exclusive cycles | Exclusive share |
|---|---:|---:|
| Other | 2,490 | 0.1922% |
| api_control | 86,090 | 6.6462% |
| basemul_acc | 0 | 0.0000% |
| compression | 0 | 0.0000% |
| decompression | 0 | 0.0000% |
| encoding | 462,080 | 35.6730% |
| explicit_reduce_convert | 661,440 | 51.0638% |
| intt | 0 | 0.0000% |
| keccak_permutation | 0 | 0.0000% |
| kpke_control | 0 | 0.0000% |
| matrix_control | 0 | 0.0000% |
| memory_copy | 0 | 0.0000% |
| mulcache | 0 | 0.0000% |
| noise_cbd | 0 | 0.0000% |
| noise_control | 0 | 0.0000% |
| ntt | 0 | 0.0000% |
| poly_add_sub | 0 | 0.0000% |
| rejection_sampling | 0 | 0.0000% |
| sha_sponge | 0 | 0.0000% |
| zeroize | 83,220 | 6.4247% |

Inclusive values below overlap and must not be added.

| Phase | Category | Calls | Exclusive cycles | Exclusive share | Inclusive cycles |
|---|---|---:|---:|---:|---:|
| 0: unclassified | unclassified | 0 | 2,490 | 0.1922% | 2,490 |
| 1: kem_keypair_derand | api_control | 0 | 0 | 0.0000% | 0 |
| 2: kem_enc_derand | api_control | 0 | 0 | 0.0000% | 0 |
| 3: kem_dec | api_control | 0 | 0 | 0.0000% | 0 |
| 4: kem_check_pk | api_control | 10 | 86,090 | 6.6462% | 1,292,830 |
| 5: kem_check_sk | api_control | 0 | 0 | 0.0000% | 0 |
| 6: indcpa_keypair_derand | kpke_control | 0 | 0 | 0.0000% | 0 |
| 7: indcpa_enc | kpke_control | 0 | 0 | 0.0000% | 0 |
| 8: indcpa_dec | kpke_control | 0 | 0 | 0.0000% | 0 |
| 9: gen_matrix | matrix_control | 0 | 0 | 0.0000% | 0 |
| 10: rej_uniform | rejection_sampling | 0 | 0 | 0.0000% | 0 |
| 11: poly_getnoise_eta1_4x | noise_control | 0 | 0 | 0.0000% | 0 |
| 12: poly_getnoise_eta2 | noise_control | 0 | 0 | 0.0000% | 0 |
| 13: poly_getnoise_eta1122_4x | noise_control | 0 | 0 | 0.0000% | 0 |
| 14: poly_cbd2 | noise_cbd | 0 | 0 | 0.0000% | 0 |
| 15: poly_cbd3 | noise_cbd | 0 | 0 | 0.0000% | 0 |
| 16: keccakf1600_permute | keccak_permutation | 0 | 0 | 0.0000% | 0 |
| 17: shake128_absorb_once | sha_sponge | 0 | 0 | 0.0000% | 0 |
| 18: shake128_squeezeblocks | sha_sponge | 0 | 0 | 0.0000% | 0 |
| 19: shake256 | sha_sponge | 0 | 0 | 0.0000% | 0 |
| 20: sha3_256 | sha_sponge | 0 | 0 | 0.0000% | 0 |
| 21: sha3_512 | sha_sponge | 0 | 0 | 0.0000% | 0 |
| 22: shake128x4_absorb_once | sha_sponge | 0 | 0 | 0.0000% | 0 |
| 23: shake128x4_squeezeblocks | sha_sponge | 0 | 0 | 0.0000% | 0 |
| 24: shake256x4 | sha_sponge | 0 | 0 | 0.0000% | 0 |
| 25: poly_ntt | ntt | 0 | 0 | 0.0000% | 0 |
| 26: poly_invntt_tomont | intt | 0 | 0 | 0.0000% | 0 |
| 27: polyvec_basemul_acc_montgomery_cached | basemul_acc | 0 | 0 | 0.0000% | 0 |
| 28: poly_mulcache_compute | mulcache | 0 | 0 | 0.0000% | 0 |
| 29: poly_reduce | explicit_reduce_convert | 20 | 661,440 | 51.0638% | 661,440 |
| 30: poly_tomont | explicit_reduce_convert | 0 | 0 | 0.0000% | 0 |
| 31: poly_add | poly_add_sub | 0 | 0 | 0.0000% | 0 |
| 32: poly_sub | poly_add_sub | 0 | 0 | 0.0000% | 0 |
| 33: poly_compress_d4 | compression | 0 | 0 | 0.0000% | 0 |
| 34: poly_compress_d10 | compression | 0 | 0 | 0.0000% | 0 |
| 35: poly_decompress_d4 | decompression | 0 | 0 | 0.0000% | 0 |
| 36: poly_decompress_d10 | decompression | 0 | 0 | 0.0000% | 0 |
| 37: poly_tobytes | encoding | 20 | 261,680 | 20.2020% | 261,680 |
| 38: poly_frombytes | encoding | 20 | 200,400 | 15.4711% | 200,400 |
| 39: poly_frommsg | encoding | 0 | 0 | 0.0000% | 0 |
| 40: poly_tomsg | encoding | 0 | 0 | 0.0000% | 0 |
| 41: zeroize | zeroize | 20 | 83,220 | 6.4247% | 83,220 |
| 42: memcpy | memory_copy | 0 | 0 | 0.0000% | 0 |

## encapsulationKeyCheck / return 0

Exclusive categories partition the API interval; their shares sum to 100% before rounding.

| Category | Exclusive cycles | Exclusive share |
|---|---:|---:|
| Other | 2,490 | 0.1922% |
| api_control | 85,980 | 6.6383% |
| basemul_acc | 0 | 0.0000% |
| compression | 0 | 0.0000% |
| decompression | 0 | 0.0000% |
| encoding | 462,080 | 35.6761% |
| explicit_reduce_convert | 661,440 | 51.0682% |
| intt | 0 | 0.0000% |
| keccak_permutation | 0 | 0.0000% |
| kpke_control | 0 | 0.0000% |
| matrix_control | 0 | 0.0000% |
| memory_copy | 0 | 0.0000% |
| mulcache | 0 | 0.0000% |
| noise_cbd | 0 | 0.0000% |
| noise_control | 0 | 0.0000% |
| ntt | 0 | 0.0000% |
| poly_add_sub | 0 | 0.0000% |
| rejection_sampling | 0 | 0.0000% |
| sha_sponge | 0 | 0.0000% |
| zeroize | 83,220 | 6.4252% |

Inclusive values below overlap and must not be added.

| Phase | Category | Calls | Exclusive cycles | Exclusive share | Inclusive cycles |
|---|---|---:|---:|---:|---:|
| 0: unclassified | unclassified | 0 | 2,490 | 0.1922% | 2,490 |
| 1: kem_keypair_derand | api_control | 0 | 0 | 0.0000% | 0 |
| 2: kem_enc_derand | api_control | 0 | 0 | 0.0000% | 0 |
| 3: kem_dec | api_control | 0 | 0 | 0.0000% | 0 |
| 4: kem_check_pk | api_control | 10 | 85,980 | 6.6383% | 1,292,720 |
| 5: kem_check_sk | api_control | 0 | 0 | 0.0000% | 0 |
| 6: indcpa_keypair_derand | kpke_control | 0 | 0 | 0.0000% | 0 |
| 7: indcpa_enc | kpke_control | 0 | 0 | 0.0000% | 0 |
| 8: indcpa_dec | kpke_control | 0 | 0 | 0.0000% | 0 |
| 9: gen_matrix | matrix_control | 0 | 0 | 0.0000% | 0 |
| 10: rej_uniform | rejection_sampling | 0 | 0 | 0.0000% | 0 |
| 11: poly_getnoise_eta1_4x | noise_control | 0 | 0 | 0.0000% | 0 |
| 12: poly_getnoise_eta2 | noise_control | 0 | 0 | 0.0000% | 0 |
| 13: poly_getnoise_eta1122_4x | noise_control | 0 | 0 | 0.0000% | 0 |
| 14: poly_cbd2 | noise_cbd | 0 | 0 | 0.0000% | 0 |
| 15: poly_cbd3 | noise_cbd | 0 | 0 | 0.0000% | 0 |
| 16: keccakf1600_permute | keccak_permutation | 0 | 0 | 0.0000% | 0 |
| 17: shake128_absorb_once | sha_sponge | 0 | 0 | 0.0000% | 0 |
| 18: shake128_squeezeblocks | sha_sponge | 0 | 0 | 0.0000% | 0 |
| 19: shake256 | sha_sponge | 0 | 0 | 0.0000% | 0 |
| 20: sha3_256 | sha_sponge | 0 | 0 | 0.0000% | 0 |
| 21: sha3_512 | sha_sponge | 0 | 0 | 0.0000% | 0 |
| 22: shake128x4_absorb_once | sha_sponge | 0 | 0 | 0.0000% | 0 |
| 23: shake128x4_squeezeblocks | sha_sponge | 0 | 0 | 0.0000% | 0 |
| 24: shake256x4 | sha_sponge | 0 | 0 | 0.0000% | 0 |
| 25: poly_ntt | ntt | 0 | 0 | 0.0000% | 0 |
| 26: poly_invntt_tomont | intt | 0 | 0 | 0.0000% | 0 |
| 27: polyvec_basemul_acc_montgomery_cached | basemul_acc | 0 | 0 | 0.0000% | 0 |
| 28: poly_mulcache_compute | mulcache | 0 | 0 | 0.0000% | 0 |
| 29: poly_reduce | explicit_reduce_convert | 20 | 661,440 | 51.0682% | 661,440 |
| 30: poly_tomont | explicit_reduce_convert | 0 | 0 | 0.0000% | 0 |
| 31: poly_add | poly_add_sub | 0 | 0 | 0.0000% | 0 |
| 32: poly_sub | poly_add_sub | 0 | 0 | 0.0000% | 0 |
| 33: poly_compress_d4 | compression | 0 | 0 | 0.0000% | 0 |
| 34: poly_compress_d10 | compression | 0 | 0 | 0.0000% | 0 |
| 35: poly_decompress_d4 | decompression | 0 | 0 | 0.0000% | 0 |
| 36: poly_decompress_d10 | decompression | 0 | 0 | 0.0000% | 0 |
| 37: poly_tobytes | encoding | 20 | 261,680 | 20.2037% | 261,680 |
| 38: poly_frombytes | encoding | 20 | 200,400 | 15.4724% | 200,400 |
| 39: poly_frommsg | encoding | 0 | 0 | 0.0000% | 0 |
| 40: poly_tomsg | encoding | 0 | 0 | 0.0000% | 0 |
| 41: zeroize | zeroize | 20 | 83,220 | 6.4252% | 83,220 |
| 42: memcpy | memory_copy | 0 | 0 | 0.0000% | 0 |

## decapsulationKeyCheck / return -5

Exclusive categories partition the API interval; their shares sum to 100% before rounding.

| Category | Exclusive cycles | Exclusive share |
|---|---:|---:|
| Other | 1,920 | 0.0204% |
| api_control | 5,390 | 0.0572% |
| basemul_acc | 0 | 0.0000% |
| compression | 0 | 0.0000% |
| decompression | 0 | 0.0000% |
| encoding | 0 | 0.0000% |
| explicit_reduce_convert | 0 | 0.0000% |
| intt | 0 | 0.0000% |
| keccak_permutation | 9,296,340 | 98.6527% |
| kpke_control | 0 | 0.0000% |
| matrix_control | 0 | 0.0000% |
| memory_copy | 0 | 0.0000% |
| mulcache | 0 | 0.0000% |
| noise_cbd | 0 | 0.0000% |
| noise_control | 0 | 0.0000% |
| ntt | 0 | 0.0000% |
| poly_add_sub | 0 | 0.0000% |
| rejection_sampling | 0 | 0.0000% |
| sha_sponge | 106,630 | 1.1316% |
| zeroize | 13,020 | 0.1382% |

Inclusive values below overlap and must not be added.

| Phase | Category | Calls | Exclusive cycles | Exclusive share | Inclusive cycles |
|---|---|---:|---:|---:|---:|
| 0: unclassified | unclassified | 0 | 1,920 | 0.0204% | 1,920 |
| 1: kem_keypair_derand | api_control | 0 | 0 | 0.0000% | 0 |
| 2: kem_enc_derand | api_control | 0 | 0 | 0.0000% | 0 |
| 3: kem_dec | api_control | 0 | 0 | 0.0000% | 0 |
| 4: kem_check_pk | api_control | 0 | 0 | 0.0000% | 0 |
| 5: kem_check_sk | api_control | 10 | 5,390 | 0.0572% | 9,421,380 |
| 6: indcpa_keypair_derand | kpke_control | 0 | 0 | 0.0000% | 0 |
| 7: indcpa_enc | kpke_control | 0 | 0 | 0.0000% | 0 |
| 8: indcpa_dec | kpke_control | 0 | 0 | 0.0000% | 0 |
| 9: gen_matrix | matrix_control | 0 | 0 | 0.0000% | 0 |
| 10: rej_uniform | rejection_sampling | 0 | 0 | 0.0000% | 0 |
| 11: poly_getnoise_eta1_4x | noise_control | 0 | 0 | 0.0000% | 0 |
| 12: poly_getnoise_eta2 | noise_control | 0 | 0 | 0.0000% | 0 |
| 13: poly_getnoise_eta1122_4x | noise_control | 0 | 0 | 0.0000% | 0 |
| 14: poly_cbd2 | noise_cbd | 0 | 0 | 0.0000% | 0 |
| 15: poly_cbd3 | noise_cbd | 0 | 0 | 0.0000% | 0 |
| 16: keccakf1600_permute | keccak_permutation | 60 | 9,296,340 | 98.6527% | 9,296,340 |
| 17: shake128_absorb_once | sha_sponge | 0 | 0 | 0.0000% | 0 |
| 18: shake128_squeezeblocks | sha_sponge | 0 | 0 | 0.0000% | 0 |
| 19: shake256 | sha_sponge | 0 | 0 | 0.0000% | 0 |
| 20: sha3_256 | sha_sponge | 10 | 106,630 | 1.1316% | 9,413,260 |
| 21: sha3_512 | sha_sponge | 0 | 0 | 0.0000% | 0 |
| 22: shake128x4_absorb_once | sha_sponge | 0 | 0 | 0.0000% | 0 |
| 23: shake128x4_squeezeblocks | sha_sponge | 0 | 0 | 0.0000% | 0 |
| 24: shake256x4 | sha_sponge | 0 | 0 | 0.0000% | 0 |
| 25: poly_ntt | ntt | 0 | 0 | 0.0000% | 0 |
| 26: poly_invntt_tomont | intt | 0 | 0 | 0.0000% | 0 |
| 27: polyvec_basemul_acc_montgomery_cached | basemul_acc | 0 | 0 | 0.0000% | 0 |
| 28: poly_mulcache_compute | mulcache | 0 | 0 | 0.0000% | 0 |
| 29: poly_reduce | explicit_reduce_convert | 0 | 0 | 0.0000% | 0 |
| 30: poly_tomont | explicit_reduce_convert | 0 | 0 | 0.0000% | 0 |
| 31: poly_add | poly_add_sub | 0 | 0 | 0.0000% | 0 |
| 32: poly_sub | poly_add_sub | 0 | 0 | 0.0000% | 0 |
| 33: poly_compress_d4 | compression | 0 | 0 | 0.0000% | 0 |
| 34: poly_compress_d10 | compression | 0 | 0 | 0.0000% | 0 |
| 35: poly_decompress_d4 | decompression | 0 | 0 | 0.0000% | 0 |
| 36: poly_decompress_d10 | decompression | 0 | 0 | 0.0000% | 0 |
| 37: poly_tobytes | encoding | 0 | 0 | 0.0000% | 0 |
| 38: poly_frombytes | encoding | 0 | 0 | 0.0000% | 0 |
| 39: poly_frommsg | encoding | 0 | 0 | 0.0000% | 0 |
| 40: poly_tomsg | encoding | 0 | 0 | 0.0000% | 0 |
| 41: zeroize | zeroize | 20 | 13,020 | 0.1382% | 13,020 |
| 42: memcpy | memory_copy | 0 | 0 | 0.0000% | 0 |

## decapsulationKeyCheck / return 0

Exclusive categories partition the API interval; their shares sum to 100% before rounding.

| Category | Exclusive cycles | Exclusive share |
|---|---:|---:|
| Other | 1,920 | 0.0204% |
| api_control | 5,280 | 0.0560% |
| basemul_acc | 0 | 0.0000% |
| compression | 0 | 0.0000% |
| decompression | 0 | 0.0000% |
| encoding | 0 | 0.0000% |
| explicit_reduce_convert | 0 | 0.0000% |
| intt | 0 | 0.0000% |
| keccak_permutation | 9,296,340 | 98.6539% |
| kpke_control | 0 | 0.0000% |
| matrix_control | 0 | 0.0000% |
| memory_copy | 0 | 0.0000% |
| mulcache | 0 | 0.0000% |
| noise_cbd | 0 | 0.0000% |
| noise_control | 0 | 0.0000% |
| ntt | 0 | 0.0000% |
| poly_add_sub | 0 | 0.0000% |
| rejection_sampling | 0 | 0.0000% |
| sha_sponge | 106,630 | 1.1316% |
| zeroize | 13,020 | 0.1382% |

Inclusive values below overlap and must not be added.

| Phase | Category | Calls | Exclusive cycles | Exclusive share | Inclusive cycles |
|---|---|---:|---:|---:|---:|
| 0: unclassified | unclassified | 0 | 1,920 | 0.0204% | 1,920 |
| 1: kem_keypair_derand | api_control | 0 | 0 | 0.0000% | 0 |
| 2: kem_enc_derand | api_control | 0 | 0 | 0.0000% | 0 |
| 3: kem_dec | api_control | 0 | 0 | 0.0000% | 0 |
| 4: kem_check_pk | api_control | 0 | 0 | 0.0000% | 0 |
| 5: kem_check_sk | api_control | 10 | 5,280 | 0.0560% | 9,421,270 |
| 6: indcpa_keypair_derand | kpke_control | 0 | 0 | 0.0000% | 0 |
| 7: indcpa_enc | kpke_control | 0 | 0 | 0.0000% | 0 |
| 8: indcpa_dec | kpke_control | 0 | 0 | 0.0000% | 0 |
| 9: gen_matrix | matrix_control | 0 | 0 | 0.0000% | 0 |
| 10: rej_uniform | rejection_sampling | 0 | 0 | 0.0000% | 0 |
| 11: poly_getnoise_eta1_4x | noise_control | 0 | 0 | 0.0000% | 0 |
| 12: poly_getnoise_eta2 | noise_control | 0 | 0 | 0.0000% | 0 |
| 13: poly_getnoise_eta1122_4x | noise_control | 0 | 0 | 0.0000% | 0 |
| 14: poly_cbd2 | noise_cbd | 0 | 0 | 0.0000% | 0 |
| 15: poly_cbd3 | noise_cbd | 0 | 0 | 0.0000% | 0 |
| 16: keccakf1600_permute | keccak_permutation | 60 | 9,296,340 | 98.6539% | 9,296,340 |
| 17: shake128_absorb_once | sha_sponge | 0 | 0 | 0.0000% | 0 |
| 18: shake128_squeezeblocks | sha_sponge | 0 | 0 | 0.0000% | 0 |
| 19: shake256 | sha_sponge | 0 | 0 | 0.0000% | 0 |
| 20: sha3_256 | sha_sponge | 10 | 106,630 | 1.1316% | 9,413,260 |
| 21: sha3_512 | sha_sponge | 0 | 0 | 0.0000% | 0 |
| 22: shake128x4_absorb_once | sha_sponge | 0 | 0 | 0.0000% | 0 |
| 23: shake128x4_squeezeblocks | sha_sponge | 0 | 0 | 0.0000% | 0 |
| 24: shake256x4 | sha_sponge | 0 | 0 | 0.0000% | 0 |
| 25: poly_ntt | ntt | 0 | 0 | 0.0000% | 0 |
| 26: poly_invntt_tomont | intt | 0 | 0 | 0.0000% | 0 |
| 27: polyvec_basemul_acc_montgomery_cached | basemul_acc | 0 | 0 | 0.0000% | 0 |
| 28: poly_mulcache_compute | mulcache | 0 | 0 | 0.0000% | 0 |
| 29: poly_reduce | explicit_reduce_convert | 0 | 0 | 0.0000% | 0 |
| 30: poly_tomont | explicit_reduce_convert | 0 | 0 | 0.0000% | 0 |
| 31: poly_add | poly_add_sub | 0 | 0 | 0.0000% | 0 |
| 32: poly_sub | poly_add_sub | 0 | 0 | 0.0000% | 0 |
| 33: poly_compress_d4 | compression | 0 | 0 | 0.0000% | 0 |
| 34: poly_compress_d10 | compression | 0 | 0 | 0.0000% | 0 |
| 35: poly_decompress_d4 | decompression | 0 | 0 | 0.0000% | 0 |
| 36: poly_decompress_d10 | decompression | 0 | 0 | 0.0000% | 0 |
| 37: poly_tobytes | encoding | 0 | 0 | 0.0000% | 0 |
| 38: poly_frombytes | encoding | 0 | 0 | 0.0000% | 0 |
| 39: poly_frommsg | encoding | 0 | 0 | 0.0000% | 0 |
| 40: poly_tomsg | encoding | 0 | 0 | 0.0000% | 0 |
| 41: zeroize | zeroize | 20 | 13,020 | 0.1382% | 13,020 |
| 42: memcpy | memory_copy | 0 | 0 | 0.0000% | 0 |

One execution per official record. Key-check valid/invalid returns and dataset revisions remain separate. P95 is nearest rank. M counts are compared, not required identical because instrumentation may alter code generation.

RTL simulation only, not board timing or certification. Observed stack use is not a worst-case bound. No synthetic whole-suite runtime is inferred from separate batches.

`cases.csv` contains matched baseline deltas and opcode counts; `phases.csv` contains each mapped phase per case. `summary.json` retains dataset groups, phase definitions and evidence SHA-256 hashes.
