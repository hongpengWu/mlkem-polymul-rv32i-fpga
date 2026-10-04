# PYNQ-Z2 oscillator and user I/O. MMCM creates the 100 MHz system clock;
# Vivado derives that generated clock from this physical 125 MHz input.
set_property -dict {PACKAGE_PIN H16 IOSTANDARD LVCMOS33} [get_ports sys_clk]
create_clock -name sys_clk_125mhz -period 8.000 -waveform {0.000 4.000} [get_ports sys_clk]
set_property -dict {PACKAGE_PIN D19 IOSTANDARD LVCMOS33} [get_ports btn0]
set_property -dict {PACKAGE_PIN R14 IOSTANDARD LVCMOS33} [get_ports {led[0]}]
set_property -dict {PACKAGE_PIN P14 IOSTANDARD LVCMOS33} [get_ports {led[1]}]
set_property -dict {PACKAGE_PIN N16 IOSTANDARD LVCMOS33} [get_ports {led[2]}]
set_property -dict {PACKAGE_PIN M14 IOSTANDARD LVCMOS33} [get_ports {led[3]}]

# The asynchronous request (BTN0 OR !MMCM_LOCKED) ends ONLY on these four CLR
# pins. LOCKED is not a legal timing startpoint, so constrain the exact endpoints.
# Every Q-to-D stage and synchronous reset fanout remains fully timed.
set reset_clear_pins [get_pins -hier -filter {NAME =~ *reset_sync_reg*/CLR}]
set_false_path -to $reset_clear_pins
# Explicitly identify BTN0 as asynchronous external input for check_timing.
set_false_path -from [get_ports btn0] -to $reset_clear_pins
# Human-visible LEDs have no synchronous external receiver.
set_false_path -to [get_ports {led[*]}]

set_property BITSTREAM.GENERAL.COMPRESS TRUE [current_design]
set_property CONFIG_VOLTAGE 3.3 [current_design]
set_property CFGBVS VCCO [current_design]
