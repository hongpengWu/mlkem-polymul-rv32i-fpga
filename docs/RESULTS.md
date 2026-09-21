# Results and measurement scope

The results below use PYNQ-Z2 at 100 MHz, the BRAM wrapper, mode-3 firmware and read-only VIO. Routed resources and timing come from archived implementation reports; cycle counts were also reproduced in the 2026-09-21 RTL regression.

| Measurement | Historical result | Scope |
|---|---:|---|
| Core | 4789 cycles / 47.89 us | Wrapper internal busy counter |
| Input write | 5873 cycles | CPU transfer loop, includes CPU overhead |
| Start | 19 cycles | CPU launch write |
| Poll | 4827 cycles | Overlaps hardware computation |
| Output read | 3233 cycles | CPU readback loop |
| Call | 13952 cycles / 139.52 us | Existing local inputs to local output; excludes generation/check |
| Routed LUT / FF | 3908 / 5053 | Full system including VIO |
| DSP | 1 | Full system including VIO |
| RAMB36 / RAMB18 | 4 / 5 | Full system including VIO; 6.5 BRAM36 equivalents |
| WNS / WHS | +1.820 / +0.028 ns | Original board constraints at 100 MHz |

`Call = Input write + Start + Poll + Output read = 13952 cycles`. Core execution overlaps the CPU's polling interval and is not an additional term. Transfer intervals include CPU instructions and local RAM accesses as well as AXI transactions.

The reported 6.5 BRAM36 equivalents correspond to four RAMB36 and five RAMB18 primitives. Positive setup and hold slack indicates timing closure for the reported constraints, not a measured maximum operating frequency or power result.

The [board snapshot](../evidence/historical/board_vio/hardware/snapshot_20260912_203558_7590119437774.txt) records `done=1`, `trap=0`, `status=0x600d600d` and the tabulated cycle counts. Probe values in that file are hexadecimal. The [migration RTL log](../evidence/migration/vio_simulate.log) records three reset trials using the same deterministic input pair and an independent 256-coefficient reference. Only one numerical physical-board snapshot is included.

Resource and timing sources: [routed utilization](../evidence/historical/board_vio/utilization_routed.rpt), [timing summary](../evidence/historical/board_vio/timing_routed.rpt) and [DRC report](../evidence/historical/board_vio/drc_routed.rpt).

## Wrapper resource comparison

These archived out-of-context (OOC) results cover the system top without the board-level clock and VIO configuration above.

| Resource | Register wrapper | BRAM wrapper |
|---|---:|---:|
| LUT | 14673 | 2936 |
| FF | 14118 | 2759 |
| RAMB36 | 4 | 4 |
| RAMB18 | 2 | 5 |
| DSP | 1 | 1 |

Sources: [register-wrapper report](../evidence/historical/bram_wrapper/baseline/utilization_routed.rpt) and [BRAM-wrapper report](../evidence/historical/bram_wrapper/bram/utilization_routed.rpt). The BRAM implementation reduces LUT and register use while adding three RAMB18 primitives. These resource reports do not establish a latency improvement. Matched timing logs for both wrapper configurations are not included in this repository.

## Software reference

The [RV32I software audit](../evidence/historical/profile/software_compute_audit_1789549904/simulate.log) reports 2050106 cycles between function-boundary observations and 2050123 cycles in the surrounding `rdcycle` window. The 17-cycle difference reflects the measurement boundaries. Both values refer to the PolyMul computation in a specific `-O2` firmware image, measured in RTL simulation rather than on the host computer or physical board. This reference is not a survey of optimized software implementations.

## Evidence records

`evidence/historical/` contains archived reports, while `evidence/migration/` contains the 2026-09-21 regression logs. Local paths and hostnames have been redacted without changing measured values. Import, redaction and current-file hashes are recorded separately in `SOURCE_MANIFEST.csv`, `evidence/REDACTION_MANIFEST.csv` and `FINAL_MANIFEST.csv`.

The migration test scope and untested stages are documented in [MIGRATION_VALIDATION.md](MIGRATION_VALIDATION.md).
