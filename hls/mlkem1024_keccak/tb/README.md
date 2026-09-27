# Keccak/SHA3/SHAKE local unit regression

`tb_mlkem1024_keccak_accel.cpp` drives the packed-word HLS top with independent
Python `hashlib` expected outputs. These are **local differential FIPS 202
vectors**, not NIST ACVP vectors or official ML-KEM-1024 KAT. No test result here
implies CPU integration, complete ML-KEM correctness, or certification.

The fixture JSON is readable evidence; the generated header embeds the same
bytes so C/RTL co-simulation needs no runtime file lookup. `vector_manifest.json`
records the generator hash, fixture hashes, Python version, hashlib provider
types and runtime OpenSSL version.

Regenerate or verify from the repository root:

```powershell
python hls/mlkem1024_keccak/scripts/generate_vectors.py
python hls/mlkem1024_keccak/scripts/generate_vectors.py --check
```

## Coverage

| Class | DUT transactions | Checks |
|---|---:|---|
| One-shot HASH | 74 | SHAKE128, SHAKE256, SHA3-256, SHA3-512; empty/abc; input rate−1/rate/rate+1; multiple blocks; input lengths 33/34/64/1568/1600/2048 B; repeated lengths with different data; SHAKE output rate boundaries, zero and maximum 4096 B |
| SHAKE continuation | 8 | Both SHAKE modes, split `13 + 0 + 491 + 168` B; zero-length SQUEEZE preserves context |
| Interleaved contexts | 6 | Separate SHAKE128/SHAKE256 states, zero-output HASH, unaligned splits and continuation after an exact rate boundary |
| Invalid and clear | 21 | Unsupported mode/command; excessive input/output lengths including UINT32_MAX; SHA3 output length; illegal SQUEEZE/CLEAR parameters; uninitialized/malformed context; mode mismatch; repeatable clear; rejection after clear |
| **Total** | **109** | Final marker emitted only if every check passed |

Every call checks input immutability. Successful output checks every requested
byte against the oracle, zero padding in unused bytes of the final word, and
canaries in every later output word. Invalid calls must preserve the complete
context and output buffers. SHA3 and CLEAR must zero all 26 context words.

Inputs are byte-aligned. This suite does not exercise bit-oriented FIPS 202
messages. Input and output buffers do not alias, as required by the ABI.

For RTL co-simulation, untouched output locations must retain their initialized
canaries. A simulator memory model that omits initialization of a write-only
port cannot verify that ABI promise; use an initialized inout memory model or
an explicit BRAM testbench instead of ignoring tail-check failures.
