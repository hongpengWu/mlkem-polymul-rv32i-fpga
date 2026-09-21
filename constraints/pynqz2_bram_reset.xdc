# BTN0 is asynchronous, and drives only the reset synchronizer's async clear.
# Synchronizer Q-to-D stages and reset release into system logic remain timed.
set_false_path -from [get_ports btn0] -to [get_pins -hier -filter {NAME =~ *reset_sync_reg*/CLR}]
# Human-visible LEDs have no synchronous external receiver.
set_false_path -to [get_ports {led[*]}]
