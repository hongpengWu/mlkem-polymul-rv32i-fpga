# CPU baseline test protocol

This file specifies the new CPU-only benchmark interface. It does not change
the original accelerator system or its phase-2 measurements.

The CPU uses picorv32_axi and a 16 KiB XPM single-port BRAM (32-bit words,
one-cycle synchronous read), at 100 MHz. Three configurations differ only in
MUL/FAST_MUL/DIV: RV32I 0/0/0, iterative 1/0/1, fast 1/1/1. Debug registers
occupy 0x50000000..0x5000003f and retain the original local AXI handshake.
Stack top is 0x3ff0; linker reserves 2 KiB for the stack.

Firmware writes arguments first, then a full-word event to debug register 15.
The TB observes the accepted write at system_i.local_write_commit, using
commit_addr/data/strb. Debug registers reflect earlier completed argument writes.

| Register | Meaning |
|---|---|
| 0 | status: RUN=0x52554e21, PASS=0x600d600d, failure prefix 0xdead |
| 1 | error detail |
| 2 | input case index 0..7 |
| 3 | prepare: copy original A/B into working arrays |
| 4 | forward NTT of A |
| 5 | forward NTT of B |
| 6 | BaseMul |
| 7 | inverse NTT including its scale |
| 8 | canonical output normalization |
| 9 | total cycles (unsegmented or profiled, by event) |
| 10 | empty rdcycle bracket |
| 11 | output checksum |
| 12 | coefficient index |
| 13 | coefficient payload |
| 14 | reserved |
| 15 | event strobe |

| Event | Meaning |
|---|---|
| 1 | begin input case |
| 2 | input coefficient pair: reg12=index, reg13=A low 16 bits / B high 16 |
| 3 | unsegmented result: reg12=index, reg13=canonical 16-bit result |
| 4 | unsegmented metrics ready (9,10,11) |
| 5 | profiled result, same payload as event 3 |
| 6 | profiled metrics ready (3..11) |
| 7 | case complete |
| 8 / 9 | open / close unsegmented dynamic M-instruction observation window |
| 10 / 11 | open / close profiled observation window |
| 15 | all eight cases complete |

Input generation, checksums, result streaming and these event writes occur
outside rdcycle timing. Full measurement includes input copies, two forward
NTTs, BaseMul, inverse/scale, canonical output. Phase profiling is a separate
run; its sum must equal its own total, not the unsegmented total.

The independent TB oracle file is 8 * 768 32-bit words: for each case A[256],
B[256], expected[256]. The CPU generates inputs itself; TB checks all input
and output streams against this independent file. Expected results are direct
negacyclic convolution modulo 3329, not an NTT reference.
