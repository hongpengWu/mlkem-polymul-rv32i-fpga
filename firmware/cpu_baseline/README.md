# CPU software polynomial baseline

This is a separate, freestanding CPU benchmark. It performs multiplication in
`Z_3329[x]/(x^256+1)` using two forward NTTs, BaseMul, inverse NTT with scaling,
and canonical output normalization. It never accesses the PQC accelerator.
The original transfer firmware remains a separate compatibility measurement.

The same C sources and optimization options are compiled for `rv32i/ilp32` and
`rv32im/ilp32`. RV32I uses the compiler runtime for arithmetic instructions it
does not provide. Both iterative and fast RV32IM CPU configurations use the
same RV32IM binary. See the repository's CPU benchmark build/run instructions
for toolchain and configuration details.

## Memory and startup

`link.ld` defines 16 KiB RAM at address zero and places `_start` first.
`startup.S` initializes `gp` and `sp`, clears BSS, and calls `benchmark_main`.
The stack starts at `0x3ff0`; the linker reserves the preceding 2 KiB and rejects
an image whose code, constants, initialized data or BSS overlap that space.
Original A/B, working A/B and the output are static 256-element `int16_t`
arrays (2560 bytes total). The simulator also checks actual stack use.

## Fixtures and correctness

The eight deterministic cases are zero, identity, a negacyclic wrap, all
coefficients equal to 3328, alternating extremes, dense quadratic inputs, and
two pseudorandom inputs seeded by `0xc0dec0de` and `0x6d6c6b65`.
The PRNG is unsigned 32-bit `state = state * 1664525 + 1013904223`, with separate
successive states for A and B. Coefficients are `state % 3329`.

Input generation is outside the timing region. The firmware streams every
input pair and every output coefficient through the debug event protocol.
The TB compares these with an independent Python direct negacyclic convolution
oracle, including every result from both timing modes. Firmware additionally
checks a rotate/XOR checksum against `vectors.h`, generated from that oracle.
An error writes a `0xdead` status and halts. `0x600d600d` and event 15 indicate
all eight cases have completed.

## Timing boundaries

Each case runs twice from fresh working copies:

1. An unsegmented measurement brackets input copy, NTT(A), NTT(B), BaseMul,
   inverse NTT including scale, and canonicalization with two `rdcycle`s.
2. An independent profiled measurement records a timestamp at each phase
   boundary. Its six phase differences sum exactly to its own total modulo
   2^32. The extra timestamps and their compiler bookkeeping are part of this
   profiled total; it is not interchangeable with the unsegmented total.

All reported times are raw CPU cycle differences. The separate empty bracket
records two consecutive `rdcycle` instructions; no automatic subtraction is
applied to phase or total times. Input generation, checksum calculation, result
streaming and debug event writes are outside the measured intervals.
Instruction observation windows open immediately before and close immediately
after each timed run. Their boundary bookkeeping can contain ordinary CPU
instructions, but result/checksum/input-generation arithmetic is excluded.

Register assignments and event codes are specified in
[`docs/CPU_BENCHMARK_PROTOCOL.md`](../../docs/CPU_BENCHMARK_PROTOCOL.md).
No board execution or software/hardware acceleration ratio is implied by the
CPU simulation measurements.
