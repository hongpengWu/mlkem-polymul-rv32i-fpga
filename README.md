# ML-KEM PolyMul RV32I FPGA Accelerator

**Research source release. No project-wide license has been granted yet.** Public visibility is not an open-source license; see [third-party notices](THIRD_PARTY_NOTICES.md) before reuse or redistribution.

Exact multiplication in `Z_3329[x]/(x^256+1)`, implemented using a shared HLS arithmetic engine and called by PicoRV32 over AXI4-Lite. The target is PYNQ-Z2 (`xc7z020clg400-1`), with a 100 MHz PL clock. This is a polynomial multiplier, **not a complete ML-KEM implementation** and not a side-channel-hardened cryptographic product.

The sole recommended configuration uses the BRAM wrapper in `rtl/axi/`, the mode-3 transfer firmware, and optional read-only VIO. The old register-based wrapper is isolated under `experiments/` and never included by the main script.

![Architecture](docs/architecture.svg)

## Start here

- [中文目录与文件说明](docs/START_HERE_CN.md)
- [Build and verification](docs/BUILD.md)
- [Results and measurement boundaries](docs/RESULTS.md)
- [Third-party notices and release blockers](THIRD_PARTY_NOTICES.md)
- [Migration verification](docs/MIGRATION_VALIDATION.md)
- `SOURCE_MANIFEST.csv`: original imported hashes and relative source categories.
- `FINAL_MANIFEST.csv`: final candidate file inventory and SHA256 hashes (excludes generated builds).

## Quick simulation

Requires Vivado 2025.2 with Zynq-7000 device support. No physical board, ARM software or Jupyter is needed.

From this directory in a Vivado-enabled shell:

```text
vivado -mode batch -source scripts/run.tcl -tclargs vio
vivado -mode batch -source scripts/run.tcl -tclargs protocol
```

`vio` checks three reset trials, all 256 coefficients against an independent oracle, profile values and VIO connections. `protocol` checks AXI transactions and arithmetic edge cases. Every run creates a new `build/<mode>_<timestamp>_<pid>/mlkem.xpr`; the script rejects project source dependencies outside this directory. Generated build files may contain local paths and must not be published.

## Layout

```text
hls/          Complete HLS source, independent C testbench and config
rtl/          Active CPU, generated core, BRAM wrapper and board/system RTL
firmware/     Firmware source, linker script and reference data
  prebuilt/   Archived text memory images for fixed-cycle reproduction
sim/          Core, board, protocol, software and observer test sources
constraints/  Device pin and clock/reset constraints
scripts/      Portable project creation, simulation and firmware entrypoints
experiments/  Isolated old-wrapper comparison sources
evidence/     Historical reports, with local paths/hostnames redacted
docs/         Usage, measurement scopes, file map and migration checks
build/        Regenerated local projects and logs (ignored)
```

Legacy `v39e` names inside HLS/generated RTL are intentionally preserved to avoid changing module references or invalidating hierarchy-based observers. HLS C simulation does not establish equivalence between regenerated RTL and the archived RTL snapshot. Run synthesis, co-simulation and implementation before updating that snapshot.

No old Vivado project tree, cache, third-party tool installation, presentation, academic PDF or historical bitstream is included. The owner authorized public hosting on 2026-09-21. Project licensing and third-party redistribution terms are separate matters; existing notices are preserved.
