# V39-E independent out-of-context timing target.
# This clock is virtual from the viewpoint of the final board design; the
# complete PicoRV32 system will receive its own board-level clock constraint.
create_clock -name ap_clk -period 10.000 [get_ports ap_clk]

