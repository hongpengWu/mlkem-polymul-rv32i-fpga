# CPU software baseline simulation

`tb_cpu_baseline.sv` runs the compiled `cpu_baseline.mem` on the real
`cpu_benchmark_system`: PicoRV32 AXI, the local AXI response pipeline, and a
16 KiB XPM synchronous BRAM. The clock is 100 MHz. The board counterpart uses
the same CPU/RAM subsystem; its clock manager and optional VIO are omitted
from this functional simulation.

The testbench reads `cpu_polymul_vectors.mem` from the simulator working
directory. Its eight cases contain A, B, and the independently calculated
direct negacyclic convolution modulo 3329 (256 words each). Every input pair
and every result coefficient is checked. Both the unsegmented and profiled
executions must pass, giving 4096 checked output coefficients. Ordered
event/index checks reject duplicates, missing coefficients, missing phases,
and premature completion. The protocol is specified in
[`CPU_BENCHMARK_PROTOCOL.md`](../../docs/CPU_BENCHMARK_PROTOCOL.md).

`CPU_ENABLE_MUL`, `CPU_ENABLE_FAST_MUL`, and `CPU_ENABLE_DIV` select the CPU
hardware. `EXPECT_M` describes the binary: 0 requires no completed M instruction
inside either algorithm window; 1 requires completed M instructions, including
MUL, in every window. Setting `EXPECT_M=0` on an M-enabled CPU tests the same
RV32I image as a control. Per-opcode counts observe the real CPU PCPI completion
handshake and exclude input generation, checksums, and output streaming.

The monitor rejects CPU address requests outside RAM and the 64-byte debug
register area, traps, firmware checksum failures, and out-of-reservation stack
pointers. Stack checking starts when firmware reports RUN, after startup has
constructed `sp` and entered the main function. This excludes reset zeros and
the intermediate value of the two-instruction `la sp` sequence. It then tracks
the actual CPU register throughout execution; allowed `sp` is
`0x37f0..0x3ff0`. No CPU register, RAM contents, or arithmetic result is forced.

The log contains `CPU_BENCH_HEADER` and 16 `CPU_BENCH_ROW` CSV records: one
unsegmented and one profiled row per case. Phase values of -1 mean not sampled
in the unsegmented run. `total` and phase cycles are raw firmware `rdcycle`
differences; `empty` is a separately measured back-to-back bracket and is not
automatically subtracted. The six profiled phases must sum to their own total.
`min_sp` is the lowest observed stack pointer within that row's algorithm
window; the final PASS record also reports the minimum over the whole monitored
execution. These are CPU-system measurements, not the native-memory ISA
microbenchmark or accelerator latency measurements.

Success requires `CPU_BASELINE_PASS cases=8 checks=4096`. A timeout after
100 million cycles, failed assertion, or missing PASS marker is a failure.
