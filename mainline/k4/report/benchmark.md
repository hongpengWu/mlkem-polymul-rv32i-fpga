# K4 benchmark record

The paired board record used one bitstream and two firmware images on PYNQ-Z2. Both modes passed all 145 public ML-KEM-1024 records with exact output and return-value checks.

| Metric | CPU-only | CPU + Keccak |
|---|---:|---:|
| API cycles | 1,699,293,290 | 446,852,439 |
| API time at 100 MHz | 16.992932900 s | 4.468524390 s |
| PS batch wall time | 22.135448812 s | 9.634239928 s |

The reported speedups are 3.802806x for API cycles and 2.297581x for the complete PS batch wall time. API time excludes PS transfer; batch wall time includes upload, polling, readback and exact verification.
