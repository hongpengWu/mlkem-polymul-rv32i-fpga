# Build and verification

## Toolchain

The migration regression used Windows, AMD Vivado/Vitis 2025.2 and the bundled RISC-V GCC 13.4.0. Install Zynq-7000 device support and use a shell configured for the AMD tools. The firmware build script requires PowerShell and the directory containing `riscv64-unknown-elf-gcc.exe` and its companion tools.

Tool installation paths are not hard-coded in the build scripts. Headers such as `ap_int.h` and `hls_stream.h`, FPGA primitives and VIO are supplied by AMD, not this repository.

## Fixed RTL and firmware regression

From the repository root:

```text
vivado -mode batch -source scripts/run.tcl -tclargs vio
vivado -mode batch -source scripts/run.tcl -tclargs board
vivado -mode batch -source scripts/run.tcl -tclargs protocol
```

| Mode | Test coverage | Expected log marker |
|---|---|---|
| `vio` | Three resets with the same input pair; independent 256-coefficient reference; cycle counts and VIO connections | `BOARD VIO SIM PASS` |
| `board` | No-VIO LED status and button restart | `PYNQZ2 BOARD SIM PASS` |
| `protocol` | Reset clearing, byte strobes, backpressure, busy access and ring-boundary arithmetic | `BRAM PROTOCOL PASS` |

The script also emits `CANDIDATE_REGRESSION_PASS` on success, retaining the original marker for compatibility. Logs and the generated `.xpr` reside in `build/<mode>_<timestamp>_<pid>/`. Project sources must remain within the repository; installed AMD simulation libraries are external dependencies.

## Rebuild firmware

```powershell
./scripts/build_memory_transfer_compare.ps1 -ToolDir 'YOUR_RISCV_BIN_DIRECTORY'
```

This builds four transfer-loop configurations into `firmware/build/`, using RV32I/ILP32/-O2, checks static RAM layout and rejects M-extension instructions. The linker reserves at least 496 bytes below the stack address; this is a static gap, not proof of maximum runtime stack usage. `firmware/prebuilt/` is never overwritten.

To test newly built mode-3 firmware:

```text
vivado -mode batch -source scripts/run.tcl -tclargs vio firmware/build
```

Fixed cycle assertions apply to the archived toolchain and hardware configuration. Compiler changes can alter cycle counts; any revised expectations require an independently verified and documented baseline.

## HLS source

Run from `hls/` so config paths resolve locally:

```text
vitis-run --mode hls --csim --config hls_config.cfg --work_dir ../build/hls_csim
v++ --mode hls --config hls_config.cfg --work_dir ../build/hls_synthesis
```

The main C++ file includes `mlkem_poly_mul256_v39e_unified_stream_support.cpp`; this support file must not be compiled as a separate translation unit. C simulation checks three input cases against an independent O(N^2) convolution reference. The synthesis command is provided for subsequent development; HLS synthesis and RTL co-simulation were not rerun during the migration regression. Neither command automatically replaces `rtl/accelerator/`.

### Windows drive-local `/dev/null` failure

On the validation machine, a pre-existing ordinary file at the D-drive root's `dev/null` caused GNU Make to report `/dev/null:1: missing separator` before compilation. No source correction was needed. Running the HLS build in a fresh C-drive temporary directory passed all three C tests. Do not delete or overwrite that unrelated file as part of project setup.

For the same symptom, run the following from the **repository root**, using a temporary directory on a drive without the conflicting file:

```powershell
$config = (Resolve-Path './hls/hls_config.cfg').Path
$taskCsim = Join-Path $env:TEMP ('mlkem-csim-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $taskCsim | Out-Null
Push-Location $taskCsim
try {
    vitis-run --mode hls --csim --config $config --work_dir component
    if ($LASTEXITCODE -ne 0) { throw 'HLS C simulation failed; inspect component/logs/.' }
}
finally { Pop-Location }
```

This workaround changes only the build-output location. The created temporary component is retained for inspection; this recipe does not clean up unrelated files. Ensure the command exits successfully and the log contains `CSim done with 0 errors`.

## Implementation and board

```text
vivado -mode batch -source scripts/run.tcl -tclargs implement
```

Run this command from the repository root. It requests VIO simulation, synthesis, place and route, and bitstream generation; it does not program a board. This script's implementation path was not exercised during the migration regression, and the archived routed reports predate that regression.

Before programming, inspect the generated timing and DRC reports. Completion of bitstream generation alone does not establish timing closure. Use the BIT and LTX files from the same build. After programming through Hardware Manager, source `scripts/read_board_vio.tcl` in the Vivado Tcl Console to save a read-only snapshot under `build/hardware/`.

BTN0 resets the system. A successful firmware self-test produces `LED[3:0]=0101`: PASS and done asserted, error and trap deasserted.

## Optional experiment sources

`firmware/profile_firmware.c` implements six-stage profiling; `prepare_compare_firmware.c` compares input preparation methods. The `software_profile.c`, `software_polymul.c` and `software_start.S` files implement the RV32I software baseline.

These experiments are not selected by `scripts/run.tcl` and require separate source sets and matching firmware images. The software compute monitor uses fixed instruction addresses tied to `firmware/prebuilt/software_o2.mem`; rebuilding that image requires revalidating the monitor boundaries.
