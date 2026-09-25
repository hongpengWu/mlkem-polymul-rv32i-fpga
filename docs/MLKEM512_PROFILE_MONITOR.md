# ML-KEM-512 profiling monitor

`tb/software/tb_mlkem512_profile.sv` is a separate copy of the strict suite
testbench. Its default CPU configuration is RV32IM with fast multiply, and its
default fixture count is 145. The original `tb_mlkem512_suite.sv` is unchanged.
All input, output, API return, stack, instruction, mailbox, and two-`rdcycle`
checks remain active.

The timed algorithm may write one aligned 32-bit marker to `debug_regs[14]`
at `0x50000038`. `0x30000000 | phase` enters a scope and
`0x40000000 | phase` exits it. Phase IDs are 1 through 63 with the default
`PROFILE_PHASES=64`; phase zero is reserved for unclassified/outer-driver
cycles. All other bits must match exactly. A smaller `PROFILE_PHASES` parameter
(2 through 64) restricts valid IDs and the number of output rows.

Markers must occur between the original start and stop `rdcycle` instructions
while the suite state is `MEASURE`. No other debug-register write is permitted
inside this interval. Outside measurement, register 14 retains its existing
valid-byte count: zero for case boundary records, four for data streams.
Firmware scopes should use one volatile MMIO
write for entry and one for exit, including cleanup on early returns; they must
not introduce additional cycle-counter reads.

The monitor maintains a stack of at most 32 active scopes. An exit must match
the most recent entry. Unknown bits, malformed markers, invalid IDs, unmatched
exits, overflow, out-of-window markers, and active scopes at the stop boundary
are fatal errors. Repeated and recursively nested calls to the same phase are
supported.

On each CPU clock the monitor processes the original start/stop boundary,
then markers, then charges one exclusive cycle if measurement remains active.
The start edge is included and the stop edge is excluded. An entry edge belongs
to the entered phase; an exit edge belongs to its parent. Inclusive cycles are
the exit clock number minus the entry clock number, summed across calls.
Exclusive cycles accrue only to the innermost scope. Marker instruction and
MMIO overhead therefore remain part of the measured result.

Each completed case emits all phase rows, including zero-valued phases:

```text
PROFILE_HEADER,index,phase,exclusive_cycles,inclusive_cycles,calls
PROFILE_ROW,<case>,<phase>,<exclusive>,<inclusive>,<calls>
PROFILE_CASE_HEADER,index,cycles,accounted,enters,exits,max_depth
PROFILE_CASE,<case>,<raw_cycles>,<exclusive_sum>,<enters>,<exits>,<max_depth>
```

Headers occur once before execution. Phase zero has equal exclusive and
inclusive totals and zero calls. Inclusive totals across phases overlap and
must not be added to obtain case time. The monitor checks at case end that the
exclusive sum equals the unchanged raw `rdcycle` delta, that entry/exit counts
and per-phase completion counts match, and that no scope remains active.
Existing `MLKEM512_ROW` and `MLKEM512_PASS` records retain their original schema.
