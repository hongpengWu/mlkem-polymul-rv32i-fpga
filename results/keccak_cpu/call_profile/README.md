# ML-KEM-1024 host FIPS202 call profile

Host algorithmic counts only. This is not PicoRV32 cycle profiling, an HLS latency measurement, or a speedup claim.

All 145/145 pinned official ACVP cases matched every output byte and API return.
The exact existing case loader and firmware operation sequence are reused. Seed-format decapsulation includes key generation plus decapsulation.

| Operation | Cases | Keccak permutations min/max | Total | Cases needing continuation |
|---|---:|---:|---:|---:|
| decapsulation | 20 | 82/86 | 1656 | 4 |
| decapsulationKeyCheck | 20 | 12/12 | 240 | 0 |
| decapsulationSeed | 10 | 151/151 | 1510 | 0 |
| encapsulation | 50 | 70/78 | 3532 | 7 |
| encapsulationKeyCheck | 20 | 0/0 | 0 | 0 |
| keyGen | 25 | 69/73 | 1745 | 5 |

One permutation means all 24 rounds on one 1600-bit state. A portable x4 permutation invokes four scalar permutations; those are already included in the totals.

| Algorithm | Phase | Lanes | Input B/lane | Output B/lane | API calls | Scalar permutations |
|---|---|---:|---:|---:|---:|---:|
| SHA3-256 | oneshot | 1 | 1568 | 32 | 135 | 1620 |
| SHA3-512 | oneshot | 1 | 33 | 64 | 35 | 35 |
| SHA3-512 | oneshot | 1 | 64 | 64 | 80 | 80 |
| SHAKE128 | absorb | 4 | 34 | 0 | 460 | 0 |
| SHAKE128 | continuation_squeeze | 4 | 0 | 168 | 17 | 68 |
| SHAKE128 | initial_squeeze | 4 | 0 | 504 | 460 | 5520 |
| SHAKE256 | oneshot | 1 | 1600 | 32 | 30 | 360 |
| SHAKE256 | oneshot | 1 | 33 | 128 | 1000 | 1000 |

Total: 2217 FIPS202 API calls, 8683 scalar Keccak permutations.

The HLS input/output capacities are 2048/4096 bytes. Observed maxima are 1600 input bytes and 504 output bytes per scalar command. All observed shapes fit.

SHAKE128 stream output reached 672 bytes per lane. Its observed stream-length histogram (four-lane batches) is {504: 443, 672: 17}.

Mapping these calls to the scalar HLS interface gives {'HASH': 3120, 'SQUEEZE': 68}, excluding CLEAR and transfer overhead.

- Map each x4 call to four independent scalar contexts/commands; x4 lane outputs are separate streams.
- Combine SHAKE128 absorb plus first squeeze as HASH(34,504); save four contexts until sampling completes.
- Additional rejection-sampling blocks require SQUEEZE(0,168) on the same lane context, never a fresh HASH.
- Observed stream maxima are not a proof of a bound for all seeds; rejection sampling must retain continuation support.
- The 3168-byte expanded secret key is not hashed whole: H(ek) takes 1568 bytes; J(z||c) takes 1600 bytes.
- Command counts exclude optional CLEAR operations, CPU packing/transfers, arbitration and rejection sampling.

Reproduce: `python scripts/mlkem1024_keccak/profile_calls.py` (host GCC must be available; use `--cc` if needed).

`calls.csv` records each invocation and its actual permutation count; `cases.json` records official identities, returns, and output SHA-256 hashes; `summary.json` aggregates shapes; `manifest.json` records compiler arguments and input/build hashes. `run.txt` is the case-level execution log.

Instrumentation only inserts observational counters into a generated vendor copy under ignored `build/mlkem1024_keccak_call_profile/`. Vendor manifest hashes are checked before and after the run. Each observed permutation count is independently checked against rate/length arithmetic.
