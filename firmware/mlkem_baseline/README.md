# PicoRV32 ML-KEM keyGen harness

This directory defines the first PicoRV32 KAT boundary.  It calls the pinned
portable C mlkem-native `keypair_derand()` API using the official ACVP
`d || z` seed.  Native arithmetic and FIPS202 backends are disabled by leaving
their config flags unset.  Compiler value barriers and default buffer
zeroization remain enabled.  Missing implementation symbols fail the link.

Generate the first official ML-KEM-512 keyGen case from the checked-in ACVP
JSON with:

```text
python scripts/kat/package_keygen.py --parameter-set 512 --tc-id 1
```

The generated `tb/software/mlkem_keygen/mlkem512_keygen.h` is included by
`kat_keygen.c`.  `*_input.mem` is a raw data fixture (`d || z` per the
deterministic API); `*_expected.mem` is a testbench-only oracle containing
`ek` and `dk`.  Neither oracle data nor a host JSON parser is linked into the
measured firmware.
The generated JSON manifest records the fixed upstream commit, source URLs,
input JSON hashes, and output file hashes.  Packaging validates the original
ACVP SHA-256 manifest and prompt/expected pairing first, and emits stable
LF-terminated files.

## Debug window protocol

The CPU shell exposes `0x5000_0000..0x5000_003f` as sixteen 32-bit registers.
The harness writes `DEBUG_EVENT` last.  A passive testbench samples the other
fields at that commit and checks the sequence:

| Event | Meaning | `DEBUG_INDEX` / `DEBUG_DATA` |
|---:|---|---|
| `0x100` | case begin | zero / zero |
| `0x101` | `d` input | 32-bit little-endian words |
| `0x102` | `z` input | 32-bit little-endian words |
| `0x103` | encapsulation key `ek` | word index / packed word |
| `0x104` | decapsulation key `dk` | word index / packed word |
| `0x105` | case end | zero / zero |
| `0x108` | enter KeyGen observation window | unused |
| `0x109` | leave KeyGen observation window | unused |
| `0x1ff` | all cases complete or failure | status/error registers |

`DEBUG_VALID` reports the valid byte count (1..4), `DEBUG_CASE` is the ACVP
`tcId`, `DEBUG_CYCLES` is the `rdcycle` difference around key generation, and
`DEBUG_AUX0..3` report parameter set, output sizes, and case count.
`DEBUG_AUX4` is a back-to-back `rdcycle` calibration, and `DEBUG_AUX5` is the
ML-KEM API return code.  Calibration is reported without subtracting it.
`d` and
`z` are streamed only for traceability; the oracle comparison is performed on
`ek` and `dk` by the testbench.

`KAT_STATUS_PASS` is a firmware completion marker after successful API calls;
only the testbench's complete byte-for-byte comparison of `ek` and `dk`
establishes KAT correctness.  The expected keys are never part of the binary.

## Memory map

The original polynomial benchmark instantiates `RAM_ADDR_BITS=12`, i.e.
16 KiB.  The ML-KEM KAT uses that existing parameterized shell with
`RAM_ADDR_BITS=14`, i.e. 64 KiB, identically for all CPU configurations.  It
does not alter the older polynomial benchmark's image or memory map.

The stack top is `0xfff0`, with 16 KiB reserved down to `0xbff0`; code, input
constants, data and BSS must end below that address.  The linker rejects
overlap.  ML-KEM-512 output buffers use 2,432 bytes of BSS and the prepared
coin buffer uses 64 bytes.  Upstream temporary workspaces retain their default
stack allocation and are cleared by upstream code before return.  The
testbench records the observed minimum stack pointer and rejects stack bounds
violations.  Hardware resource comparisons must account for the larger RAM.
