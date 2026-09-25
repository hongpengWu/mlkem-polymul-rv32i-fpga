# Comparator rejection check

This check uses the same RV32IM fast firmware, CPU RTL and testbench as the
145-case ML-KEM-512 regression. It copies fixtures into an isolated ignored build
directory, flips bit 0 of expected fixture word 20 (KeyGen case 0, public-key byte
0), and runs until the first output comparison. The CPU receives the original
input only; its algorithm and output are unchanged.

Reproduce from the repository root with Vivado 2024.2:

```powershell
& 'E:/Xilinx/Vivado/2024.2/bin/vivado.bat' -mode batch -source scripts/mlkem512_suite/verify_rejection.tcl
```

The script succeeds only when the testbench reports exactly the injected byte
mismatch, emits one fatal diagnostic and no suite PASS marker, and the original
fixtures, firmware, RTL and testbench remain byte-for-byte unchanged.
See `mutation.txt` for the expected rejection and `simulate.log` for the actual
diagnostic. A successful negative check confirms this comparator detects the
injected error; it is not a passing official test case.
