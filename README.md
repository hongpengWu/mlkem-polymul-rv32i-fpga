# ML-KEM PolyMul RV32I FPGA Accelerator

This repository implements polynomial multiplication in `Z_3329[x]/(x^256+1)` using a shared HLS arithmetic engine controlled by PicoRV32 over AXI4-Lite. It targets PYNQ-Z2 (`xc7z020clg400-1`) at a 100 MHz PL clock, without using the Zynq PS.

The implemented operation is `FNTT(A) -> FNTT(B) -> BaseMul -> INTT -> FinalScale`. The repository does not implement complete ML-KEM key generation, encapsulation or decapsulation, and has not been evaluated for side-channel resistance.

The default configuration uses the BRAM wrapper in `rtl/axi/`, mode-3 firmware with both transfer loops unrolled four times, and optional read-only VIO. The register-based comparison implementation is isolated under `experiments/` and excluded from the default build.

![Architecture](docs/architecture.svg)

## Start here

- [中文目录与文件说明](docs/START_HERE_CN.md)
- [Build and verification](docs/BUILD.md)
- [Results and measurement boundaries](docs/RESULTS.md)
- [License status and third-party notices](THIRD_PARTY_NOTICES.md)
- [Migration verification](docs/MIGRATION_VALIDATION.md)
- `SOURCE_MANIFEST.csv`: original imported hashes and relative source categories.
- `FINAL_MANIFEST.csv`: current file inventory and SHA256 hashes, excluding itself and generated builds.

## Quick simulation

Simulation requires Vivado 2025.2 with Zynq-7000 device support, but does not require a physical board.

From this directory in a Vivado-enabled shell:

```text
vivado -mode batch -source scripts/run.tcl -tclargs vio
vivado -mode batch -source scripts/run.tcl -tclargs protocol
```

`vio` repeats the same deterministic input pair across three resets, checking all 256 output coefficients against an independent convolution reference. It also checks cycle counts and VIO connections. `protocol` tests AXI transactions and arithmetic edge cases.

Each run creates `build/<mode>_<timestamp>_<pid>/mlkem.xpr`; generated projects are not tracked in Git. The script requires project sources to reside within the repository root. See [BUILD.md](docs/BUILD.md) for command locations, expected outputs and tool dependencies.

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
evidence/     Historical reports and migration logs, with local paths redacted
docs/         Usage, measurement scopes, file map and migration checks
build/        Regenerated local projects and logs (ignored)
```

Legacy `v39e` names inside HLS/generated RTL are intentionally preserved to avoid changing module references or invalidating hierarchy-based observers. HLS C simulation does not establish equivalence between regenerated RTL and the archived RTL snapshot. Run synthesis, co-simulation and implementation before updating that snapshot.

## License status

The source is publicly hosted, but no project-wide license has been selected. Existing third-party notices remain applicable; public access does not grant a blanket license to reuse or redistribute all files. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for component-level provenance and outstanding license questions.
