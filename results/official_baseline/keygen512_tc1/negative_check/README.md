# Expected rejection of an incorrect key byte

This is a **negative test**. The `Fatal: MLKEM_KEYGEN_FAIL byte mismatch`
in `simulate.log` is the expected result, not a failure of the correct firmware.
The ordinary successful KeyGen results are in the three sibling CPU directories.

`scripts/mlkem_baseline/verify_rejection.tcl` creates a separate Vivado project
under `build/` and runs the existing RV32IM firmware with the fast multiplier,
64 KiB RAM and the original testbench. It changes only a private copy of the
expected-results fixture: bit 0 of the first encapsulation-key byte, from
`0x28` to `0x29` (word 9 changes from `086a2628` to `086a2629`).

The check succeeds only when the monitor rejects exactly `tcId=1`, EK event
`0x103`, byte 0, actual `0x28`, expected `0x29`, with one fatal diagnostic and
no `MLKEM_KEYGEN_PASS`. It also checks that the official expected fixture,
input fixture and RV32IM firmware remain byte-for-byte unchanged.

Reproduce from the repository root:

```text
vivado -mode batch -source scripts/mlkem_baseline/verify_rejection.tcl
```

Success of the negative test is reported as `MLKEM_REJECTION_CHECK_PASS`.
`mutation.txt` records the injected change and the exact required rejection;
`simulate.log` preserves the actual simulation evidence. This verifies that
the byte comparator is active; it does not expand the official case coverage.
