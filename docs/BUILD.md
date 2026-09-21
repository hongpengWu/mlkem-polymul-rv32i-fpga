# Build and verification

## Toolchain

Tested local tools are AMD Vivado/Vitis 2025.2 and the bundled RISC-V GCC. No tool installation paths are hard-coded in active scripts. Add Vivado/Vitis executables to PATH or use their full path. Tool libraries such as `ap_int.h`, `hls_stream.h`, UNISIM and VIO are supplied by AMD, not this repository.

## Fixed RTL and firmware regression

From the repository root:

```text
vivado -mode batch -source scripts/run.tcl -tclargs vio
vivado -mode batch -source scripts/run.tcl -tclargs board
vivado -mode batch -source scripts/run.tcl -tclargs protocol
```

`vio` is the recommended full correctness/cycle regression. `board` is a smaller no-VIO LED and restart check, not a substitute for the independent oracle. `protocol` includes reset clearing, byte strobes, backpressure and ring-boundary arithmetic checks. They use only local source files; Vivado's installed primitive/IP libraries are external prerequisites.

## Rebuild firmware

```powershell
./scripts/build_memory_transfer_compare.ps1 -ToolDir 'YOUR_RISCV_BIN_DIRECTORY'
```

This builds four transfer-loop configurations into `firmware/build/`, using RV32I/ILP32/-O2, checks static RAM layout and rejects M-extension instructions. The linker reserves at least 496 bytes below the stack address; this is a static gap, not proof of maximum runtime stack usage. `firmware/prebuilt/` is never overwritten.

To test newly built mode-3 firmware:

```text
vivado -mode batch -source scripts/run.tcl -tclargs vio firmware/build
```

The cycle assertions belong to the archived toolchain/configuration. A compiler change may require a separately documented functional regression; never silently change expected cycles to force PASS.

## HLS source

Run from `hls/` so config paths resolve locally:

```text
vitis-run --mode hls --csim --config hls_config.cfg --work_dir ../build/hls_csim
v++ --mode hls --config hls_config.cfg --work_dir ../build/hls_synthesis
```

The missing support include has been restored unchanged from the historical HLS source. Do not compile it as a separate top-level translation unit: the main C++ file includes it. C simulation uses AMD arbitrary-width types and an independent O(N^2) oracle. Synthesis and subsequent RTL co-simulation are separate validation stages. Existing generated RTL is not replaced automatically.

### Windows drive-local `/dev/null` failure

On the validation machine, a pre-existing ordinary file at the D-drive root's `dev/null` caused GNU Make to report `/dev/null:1: missing separator` before compilation. No source correction was needed. Running the HLS build in a fresh C-drive temporary directory passed all three C tests. Do not delete or overwrite that unrelated file as part of project setup.

For the same symptom, use a clean temporary location on a drive without that conflicting file (the source/configuration remain in this repository):

```powershell
$config = (Resolve-Path './hls/hls_config.cfg').Path
$taskCsim = Join-Path $env:TEMP ('mlkem-csim-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $taskCsim | Out-Null
Push-Location $taskCsim
try { vitis-run --mode hls --csim --config $config --work_dir component }
finally { Pop-Location }
```

This workaround changes only the build-output location. The created temporary component is retained for inspection; this recipe does not clean up unrelated files. Ensure the command exits successfully and the log contains `CSim done with 0 errors`.

## Implementation and board

```text
vivado -mode batch -source scripts/run.tcl -tclargs implement
```

This explicitly runs VIO simulation, synthesis, place/route and bitstream generation. It does not connect to or program a board. Outputs are in the new build directory. Use its matching BIT and LTX together. Read probes with `scripts/read_board_vio.tcl` after manual programming. BTN0 resets; successful self-test is LED[3:0]=0101. Historical snapshots and logs are not newly measured results.

## Optional experiment sources

`firmware/profile_firmware.c` is the six-stage benchmark; `prepare_compare_firmware.c` compares input preparation; `software_profile.c`, `software_polymul.c`, `software_start.S` implement the software baseline. These and their old-wrapper tests are retained for study, but the current release entrypoint does not claim to reproduce every historical experiment. The software compute audit uses fixed instruction addresses and must not be reused after recompiling without updating and validating the monitor.
