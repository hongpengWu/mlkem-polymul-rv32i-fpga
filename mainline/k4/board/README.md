# PYNQ-Z2 release bundle

Copy the contents of `release/` to one directory on the board. Open `mlkem1024.ipynb` in Jupyter. The notebook performs a manifest-bound load, runs three representative cases by default, and supports the full 145-case run through `RUN_FULL_145 = True`.

The `.bit` and `.hwh` files are a matched pair. `release_manifest.json` records the bundle hashes and build provenance. The later paired-board evidence is stored in `../evidence/board/`.
