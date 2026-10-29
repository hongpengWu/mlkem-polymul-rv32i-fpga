# K4 build outputs

`flow.tcl` and `bd_axi.tcl` in the parent directory are the two supported Tcl entry points. They use repository-relative paths and write generated HLS/Vivado projects under `build/k4` at the repository root. This directory is reserved for generated output and short build notes; generated projects are not source files and are not committed.
