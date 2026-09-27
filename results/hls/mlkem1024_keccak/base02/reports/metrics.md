# K4 Keccak HLS run

Run: `E:\hls\k4_io0\base02`

| Stage | This attempt | Verified evidence |
|---|---|---|
| CSIM | pass | pass |
| CSYNTH | pass | pass |
| COSIM | pass | pass |
| EXPORT | skipped | none |

| Metric | Value |
|---|---|
| Configured clock period (ns) | 10.0 |
| HLS estimated clock period (ns) | 8.622 |
| HLS estimated latency (cycles) | min=1, avg=N/A, max=247935 |
| HLS estimated interval (cycles) | min=2, max=247936 |
| BRAM_18K (HLS estimate) | 2 |
| FF (HLS estimate) | 17008 |
| LUT (HLS estimate) | 14612 |
| DSP (HLS estimate) | 0 |
| URAM (HLS estimate) | 0 |
| RTL measured latency (cycles) | min=30, avg=12066, max=89306 |
| RTL total execution (cycles, entire TB) | 1314553 |
| TB time at configured clock (ns) | 13145530.0 |
| Projected TB time using HLS clock estimate (ns) | 11334075.966 |

HLS worst-case latency is an estimate over supported sizes; it is not measured TotalExecution.
Co-simulation totals describe the whole testbench workload, not one ML-KEM operation.
Clock estimates are not post-route timing; skipped/missing stages are not passes.
