# Register-wrapper comparison sources

`register_wrapper/` contains the register-based AXI wrapper and tests that access its internal arrays. It defines the same module name as the default BRAM wrapper; the two implementations must be compiled in separate source sets. `scripts/run.tcl` includes only the BRAM implementation in `rtl/axi/`.

| Testbench | Experiment |
|---|---|
| `tb_mlkem_polymul_rv32i_profile.sv` | Six-stage firmware profiling |
| `tb_mlkem_prepare_compare.sv` | Buffered input preparation versus direct generation into the accelerator input region |
| `tb_mlkem_memory_transfer_compare.sv` | CPU transfer-loop unrolling |

These tests require matching firmware and wrapper internals. They are retained for comparison but were not rerun in the migration regression. The corresponding BRAM transfer test is `sim/profile/tb_mlkem_bram_transfer.sv`; both transfer test files define `tb_mlkem_memory_transfer_compare` and must also be kept in separate source sets.

The repository includes selected implementation reports rather than the complete historical experiment archive. Available results and their measurement scopes are listed in [RESULTS.md](../docs/RESULTS.md).
