# K4 Keccak HLS run

Run: `E:\hls\k4_io1\opt02`

| Stage | This attempt | Verified evidence |
|---|---|---|
| CSIM | pass | pass |
| CSYNTH | pass | pass |
| COSIM | pass | pass |
| EXPORT | skipped | none |

| Metric | Value |
|---|---|
| Configured clock period (ns) | 10.0 |
| HLS estimated clock period (ns) | 8.895 |
| HLS estimated latency (cycles) | min=1, avg=1256, max=36247 |
| HLS estimated interval (cycles) | min=2, max=36248 |
| BRAM_18K (HLS estimate) | 2 |
| FF (HLS estimate) | 15385 |
| LUT (HLS estimate) | 15244 |
| DSP (HLS estimate) | 0 |
| URAM (HLS estimate) | 0 |
| RTL measured latency (cycles) | min=30, avg=696, max=7462 |
| RTL total execution (cycles, entire TB) | 75280 |
| TB time at configured clock (ns) | 752800.0 |
| Projected TB time using HLS clock estimate (ns) | 669615.6 |

HLS worst-case latency is an estimate over supported sizes; it is not measured TotalExecution.
Co-simulation totals describe the whole testbench workload, not one ML-KEM operation.
Clock estimates are not post-route timing; skipped/missing stages are not passes.
