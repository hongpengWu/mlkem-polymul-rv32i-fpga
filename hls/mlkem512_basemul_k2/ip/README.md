# Exported HLS IP

`xilinx_com_hls_mlkem512_basemul_acc_k2_1_0.zip` is the Vitis HLS 2024.2 IP export
for the source and Tcl script in the parent directory. It targets
`xc7z020clg400-1`, uses a 10 ns clock, and exposes the generated `ap_ctrl_hs` plus
the array memory ports shown in
[`MLKEM512_ACCELERATOR_INTERFACE.md`](../../../docs/MLKEM512_ACCELERATOR_INTERFACE.md).

The archive is convenient for the Vivado integration step; it can be regenerated
with `run_hls.tcl`. HLS build caches and the temporary short-path project are not
part of the repository.
