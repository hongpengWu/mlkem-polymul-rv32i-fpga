# Identical physical envelope for complete CPU-only and CPU+Keccak systems.
# This is an internal system OOC comparison, not a PYNQ board pinout.
create_clock -name system_clk -period 10.000 [get_ports clk]
set_property HD.CLK_SRC BUFGCTRL_X0Y0 [get_ports clk]
set_clock_uncertainty 0.100 [get_clocks system_clk]
set_input_delay -clock system_clk -min 0.000 [get_ports resetn]
set_input_delay -clock system_clk -max 2.000 [get_ports resetn]
set_output_delay -clock system_clk -min 0.000 [all_outputs]
set_output_delay -clock system_clk -max 2.000 [all_outputs]
# resetn is treated as a synchronous internal input. No false paths, board
# LED exemptions, package pins, or asynchronous button assumptions are used.
