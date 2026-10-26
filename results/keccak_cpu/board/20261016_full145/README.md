# ML-KEM-1024 PYNQ-Z2 full board run

Date: 2026-10-16 (Asia/Shanghai; UTC evidence timestamp in JSON)

The released K=4 PS-PL overlay was loaded on PYNQ-Z2 and all 145 unique
official records were run through the board AXI interface.

| Check | Result |
|---|---|
| Status | `FULL_PASS` |
| Coverage | `145/145` unique indices `0..144` |
| Measurement | `PYNQ_BOARD_AXI_LIVE` |
| API cycle sum | `446,852,439` cycles |
| PS batch wall time (excludes overlay load and browser/network transfer) | `9.563158573999772 s` |
| Evidence SHA-256 | `2b90b932ceaccfa7e148d6143deb398c58b961e78811741b4b871c907fb38934` |

The original JSON is preserved as `board_full_20261016.json`. It contains the
per-case output bytes, return values, cycle counters, hardware call counters,
input identities, and paired release artifact hashes.

This is a real board functional and timing run for the accelerated overlay.
It is not a live CPU-only board comparison, a formal CAVP certificate, or a
power measurement. Historical RTL CPU-only values remain labelled as such.

Recheck the archived result locally from the repository root:

```powershell
python results/keccak_cpu/board/20261016_full145/verify.py
```

The independent check returns `INDEPENDENT_FULL145_CHECK_PASS`. It checks
unique indices, official output bytes and return codes, input identities,
hardware counters, timing records, and artifact hashes. The archived
`host_snapshot/` preserves the driver, Notebook and manifest used for this run.
Notebook template hashes record provenance; Jupyter saving a Notebook does not
invalidate the mandatory hashes of the bitstream, HWH, driver or vectors.

The run recorded 3,188 HLS starts, 1,980,263 busy cycles, 257,851 buffer writes,
and 435,632 buffer reads (32-bit words). API time is 4.46852439 seconds at the
100 MHz design clock and is included in PS run-wait time. These intervals
must not be added together. CPU-only board measurements remain a separate
pending experiment; this accelerated result is preserved unchanged.
