ML-KEM-1024 PYNQ-Z2 deployment bundle

Keep k4_accel.bit and k4_accel.hwh together with mlkem1024.ipynb, mlkem1024.py,
kat_vectors.json, and release_manifest.json. The notebook loads the bundle from
its current directory and verifies the files against the manifest; it does not
need the machine used to generate the bitstream.

The manifest records provenance from the bundle's original build on
2026-10-04. At that time its physical_board_tested field was false. The same
bitstream and hardware handoff were later exercised on PYNQ-Z2: full official
145/145 results are archived at
results/keccak_cpu/board/20261016_full145/README.md, and matched CPU-only versus
accelerated board results are archived at
results/k4/paired_firmware/board_20261023/summary.md.

To use this bundle, copy these files together to the board and open
mlkem1024.ipynb in Jupyter. See docs/BUILD.md for setup and operation details.
