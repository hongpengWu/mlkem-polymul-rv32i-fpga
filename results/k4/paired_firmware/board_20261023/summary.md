# Independent paired board evidence verification

INDEPENDENT_PAIRED_CHECK_PASS

- CPU-only and accelerated: 145/145 official cases each; 290 exact output/return checks.
- Subset: 3 cases per mode. Repetitions: cases 0/1/115, 10 runs per mode (60 checks).
- Recovery: reset, invalid mailbox magic and injected short timeout, each in both modes.
- Firmware: 8 complete 128 KiB loads; expected/readback hashes independently recomputed.
- Source ZIP and all JSON bytes are preserved; upload_snapshot retains the bound release.

| Operation | Cases | CPU cycles | Accelerated cycles | API speedup | PS case-wall speedup |
|---|---:|---:|---:|---:|---:|
| keyGen | 25 | 329299932 | 78355067 | 4.202663x | 2.061730x |
| encapsulation | 50 | 700468526 | 192648502 | 3.635993x | 2.349137x |
| decapsulation | 20 | 331730752 | 92092680 | 3.602140x | 2.626936x |
| decapsulationSeed | 10 | 295059840 | 77103770 | 3.826789x | 3.181554x |
| encapsulationKeyCheck | 20 | 5148150 | 5148150 | 1.000000x | 0.958034x |
| decapsulationKeyCheck | 20 | 37586090 | 1504270 | 24.986266x | 1.703102x |
| **All 145** | **145** | **1699293290** | **446852439** | **3.802806x** | **2.298548x** |

At 100 MHz: API 16.992932900 s versus 4.468524390 s; summed PS case wall 22.128231089 s versus 9.627048410 s.
Batch wall 22.135448812 s versus 9.634239928 s (2.297581x).

## Measurement scope

- One board session, fixed cpu_only block then accelerated block; repeats are three fixed vectors, not random workloads.
- Both modes use the same bitstream; this measures software versus hardware Keccak service, not removed-core area or power.
- API time excludes PS transfer; case wall time includes reset, transfer, polling and exact verification. Firmware load/readback and JSON saving are excluded.
- Recovery JSON preserves successful official cases before/after reset, bad-magic rejection and expected timeout; intermediate reset-register reads were asserted by the hash-bound driver but not persisted individually.
- Hardware counters and timestamps are board-driver observations, not independent physical instrumentation or cryptographically attested measurements.
- Public official vectors passing is not CAVP or FIPS certification.
