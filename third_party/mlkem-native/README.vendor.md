# Vendored mlkem-native portable C source

This directory contains unchanged Git blob bytes from
[pq-code-package/mlkem-native](https://github.com/pq-code-package/mlkem-native/tree/b3ba7b32773e657dd37f6f87bce82528459ad8a4),
commit `b3ba7b32773e657dd37f6f87bce82528459ad8a4`.

Only the portable library, its required headers/table, and upstream license are
included. Native architecture backends, tests, proofs, examples, build scripts,
and assembler compilation units are omitted. Do not enable
`MLK_CONFIG_USE_NATIVE_BACKEND_ARITH` or `MLK_CONFIG_USE_NATIVE_BACKEND_FIPS202`
with this subset. PicoRV32 configuration belongs in the project firmware, not
in these upstream files.

`SOURCE_MANIFEST.json` records each upstream path, byte length, SHA-256, and Git
blob SHA-1. Files were read with `git cat-file blob`; the manifest therefore
checks upstream bytes before any Windows checkout newline conversion.
No algorithm code has been changed.

The simplest portable build compiles `mlkem/mlkem_native.c` as one translation
unit. A separate-translation-unit build uses:

- `mlkem/src/compress.c`
- `mlkem/src/debug.c` (empty with debug checks disabled)
- `mlkem/src/indcpa.c`
- `mlkem/src/kem.c`
- `mlkem/src/poly.c`
- `mlkem/src/poly_k.c`
- `mlkem/src/sampling.c`
- `mlkem/src/verify.c`
- `mlkem/src/fips202/fips202.c`
- `mlkem/src/fips202/fips202x4.c`
- `mlkem/src/fips202/keccakf1600.c`

Compile only one of these approaches to avoid duplicate symbols. The current
KeyGen port uses ML-KEM-512, disables randomized, encapsulation and decapsulation
APIs using the library's configuration macros, and calls `keypair_derand` with
64 bytes `d || z`. The portable default still uses four-way SHAKE matrix
sampling, implemented as scalar Keccak calls on RV32I/RV32IM.

The upstream library offers Apache-2.0 OR ISC OR MIT licensing; see `LICENSE`
and each file's SPDX header. `README.vendor.md` and `SOURCE_MANIFEST.json` are
project packaging metadata, not upstream source files.