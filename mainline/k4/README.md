# ML-KEM-1024 K4 AMD review package

This directory is the AMD-facing entry point for the ML-KEM-1024 hardware acceleration system. It contains the HLS kernel, RTL integration, RISC-V firmware, testbenches, PYNQ notebook, build Tcl files, board release files, and reproducible evidence.

## Directory map

```text
mainline/k4/
├── flow.tcl              # HLS, firmware, RTL KAT and implementation switches
├── bd_axi.tcl            # AXI/PS-PL build and overlay switches
├── hls/                  # Keccak/SHAKE HLS source and local FIPS 202 testbench
├── rtl/                  # AXI, MMIO, system and PYNQ-Z2 top level
├── firmware/             # ML-KEM-1024 RISC-V firmware and drivers
├── tb/                   # RTL and board-level testbenches
├── pynq/                 # Python driver and Jupyter demonstration
├── constraints/          # PYNQ-Z2 pin and timing constraints
├── board/release/        # k4_accel.bit, k4_accel.hwh and board notebook bundle
├── data/                 # pinned vectors and HLS fixture manifests
├── evidence/             # board and HLS result summaries
├── report/               # architecture figure and benchmark notes
├── skill/                # board validation and overlay contract skills
└── build/                # generated output location and build notes
```

The K4 entry point depends only on the shared CPU, firmware, pinned ML-KEM implementation, official vectors and fixture files in the repository parent. These are required build inputs, not unrelated experiments.

## Reproduction

Run from the repository root with Vivado/Vitis HLS 2024.2, Python 3.10 or newer, Tcl, and the RISC-V GCC toolchain available on `PATH` or configured through the project environment variables.

```powershell
tclsh mainline/k4/flow.tcl
```

The top of `flow.tcl` controls `HLS`, `CSIM`, `CSYNTH`, `COSIM`, `VIVADO_SYN`, `VIVADO_IMPL`, `EXPORT`, `SMOKE`, `KAT_SUBSET`, `FULL_KAT`, and `CHECK_ONLY`. The default mode performs path and configuration checks and launches no EDA process. Set `FLOW_CHECK_ONLY=0` and enable only the stages required for the current reproduction.

```powershell
$env:FLOW_HLS=1
$env:FLOW_CHECK_ONLY=0
tclsh mainline/k4/flow.tcl
```

The AXI/PS-PL entry point is:

```powershell
vivado -mode batch -source mainline/k4/bd_axi.tcl
```

It uses the same top-level switch style. Generated projects and reports remain under the configured `build/k4` directory; source directories are not modified by a run.

## Direct PYNQ reproduction

Copy all files from `mainline/k4/board/release/` to one directory on the PYNQ-Z2, open `mlkem1024.ipynb` in Jupyter, and run the notebook. The default demonstration executes official vector indices `0`, `1`, and `115`. Set `RUN_FULL_145 = True` in the first code cell to execute all 145 cases.

Expected full-run marker:

```text
FULL_PASS 145 / 145
```

The notebook verifies the `.bit`, `.hwh`, Python driver, notebook, vector file and release manifest before loading the overlay. The board bundle is self-contained and does not require the host repository.

## Verified results

The same PYNQ-Z2 bitstream, 100 MHz clock, RV32IM-fast firmware configuration, 128 KiB RAM and 32 KiB stack were used for both modes.

| Metric | CPU-only | CPU + Keccak | Result |
|---|---:|---:|---:|
| Official records | 145/145 | 145/145 | exact output and return checks |
| API cycles | 1,699,293,290 | 446,852,439 | 3.802806x |
| API time at 100 MHz | 16.992932900 s | 4.468524390 s | 3.802806x |
| PS batch wall time | 22.135448812 s | 9.634239928 s | 2.297581x |

The HLS local differential suite passed 109 FIPS 202 transactions. The official KAT and board evidence are archived under `evidence/`; public vector validation is an engineering verification result and is not CAVP or FIPS certification.

## Evidence map

- `evidence/board/summary.md`: independent paired-board summary and timing definition.
- `evidence/board/verification.json`: independent verification record.
- `evidence/hls/summary.md`: HLS functional and synthesis evidence.
- `report/architecture.svg`: system architecture figure.

## Tools and scope

- Target: AMD/Xilinx PYNQ-Z2, `xc7z020-clg400-1`.
- HLS top: `mlkem1024_keccak_accel`.
- Interfaces: AXI-Lite control, packed BRAM data, PS-PL overlay through the PYNQ driver.
- Clock target: 100 MHz.
- Security target: ML-KEM-1024, NIST security category 5 parameter set.

All paths in the entry scripts are resolved from the repository, so the project does not depend on the original development machine or an absolute Windows path.
