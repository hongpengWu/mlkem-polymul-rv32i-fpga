# PicoRV32 RV32IM validation

`tb_picorv32_rv32im.sv` executes all eight M-extension instructions through
the **real PicoRV32 decoder, register file and execution path**. The testbench
assembles its own instruction ROM, so no RISC-V toolchain or firmware image is
required. Its 160 KiB program is testbench ROM, not a proposed change to the
board's 4 KiB RAM.

The default is the iterative multiplier: `ENABLE_MUL=1`, `ENABLE_FAST_MUL=0`,
`ENABLE_DIV=1`. `FAST_MUL=1` is available as a future comparison configuration.
Counters are enabled with 32-bit cycle counting; trace, zero register-file
initialization and stack address `0x00000ff0` match the system configuration.
All other CPU parameters retain their existing defaults.

## Coverage

Each instruction (`MUL`, `MULH`, `MULHSU`, `MULHU`, `DIV`, `DIVU`, `REM`,
`REMU`) executes 512 operand pairs, for 4096 arithmetic checks:

- The Cartesian product of 16 corner values, including zero, ±1, ±2,
  signed minimum/maximum, ±3329, powers of two and alternating bit patterns.
- 256 deterministic xorshift32 operand pairs, seed `0x6d6c6b65`.
- Signed/unsigned multiply-high, mixed-sign multiply-high, division by zero,
  signed division overflow, remainder sign and overflow behavior.

A behavioral 64-bit arithmetic reference supplies the expected results.
The CPU loads each operand through `LUI`/`ADDI`, executes the M instruction,
and stores its result to a testbench MMIO address. The testbench checks both
the observed PCPI operands and the architectural result. A mismatch reports
instruction, test index, operands, expected value and actual value. Any trap,
invalid memory access, ordering failure or timeout fails the run.

This is targeted M-extension validation, not a complete RISC-V architectural
compliance suite. It does not establish cryptographic side-channel resistance.

## Timing definitions

The clock is 100 MHz. Native memory has a fixed first-edge handshake:
`mem_ready = mem_valid`, with combinational instruction-ROM read. This
standalone memory model differs from the board's AXI bridge and RAM path;
these timings must not be substituted for application or board measurements.

For every case, the instruction stream contains:

```asm
rdcycle x4
<M instruction> x3, x1, x2
rdcycle x5
sub x6, x5, x4
```

The raw bracket is `x5-x4`. One empty `rdcycle`/`rdcycle` bracket is calibrated
with the same memory handshake. The incremental number subtracts that empty
bracket and describes the measured additional CPU cycles from inserting the
M instruction. Operand setup, result stores and subtraction occur outside
the bracket. This is not a claim that fetch/decode is excluded.

The separately reported PCPI service interval is the rising-edge distance
from the first sampled `pcpi_valid` to the edge sampling
`pcpi_valid && dut.pcpi_int_ready`. This read-only hierarchical observation
excludes CPU fetch/decode and should not be described as total instruction
latency. The reference RTL is unchanged.

`RV32IM_CSV` lines contain the sample count and minimum, mean and maximum of
all three metrics, in cycles. A successful run must contain
`RV32IM_ISA_PASS tests=4096 pcpi=4096`; an exit code alone is insufficient.

## Standalone Vivado 2024.2 reproduction

Run these commands from a disposable simulation working directory, using
absolute source paths as appropriate:

```powershell
& 'E:\Xilinx\Vivado\2024.2\bin\xvlog.bat' --sv <repo>/rtl/cpu/picorv32.v <repo>/tb/cpu/tb_picorv32_rv32im.sv
& 'E:\Xilinx\Vivado\2024.2\bin\xelab.bat' tb_picorv32_rv32im --snapshot rv32im_iterative -debug typical
& 'E:\Xilinx\Vivado\2024.2\bin\xsim.bat' rv32im_iterative --runall --log rv32im_iterative.log
```

For a fast-multiplier comparison, add `-generic_top FAST_MUL=1` to `xelab`
and use a separate snapshot/output directory.
