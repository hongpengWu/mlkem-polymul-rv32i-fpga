# Source with the implemented project open; root is set by implement.tcl.
set result_dir [file join $root results accelerator_interface vivado_impl]
file mkdir $result_dir
open_run impl_1
report_utilization -hierarchical -file [file join $result_dir utilization_hierarchical.rpt]
report_utilization -file [file join $result_dir utilization.rpt]
report_timing_summary -delay_type min_max -report_unconstrained -file [file join $result_dir timing_summary.rpt]
report_drc -file [file join $result_dir drc.rpt]
report_route_status -file [file join $result_dir route_status.rpt]
report_power -file [file join $result_dir power.rpt]
set setup_path [get_timing_paths -delay_type max -max_paths 1]
set hold_path [get_timing_paths -delay_type min -max_paths 1]
if {[llength $setup_path] == 0 || [llength $hold_path] == 0} {error "Missing timed paths"}
set wns [get_property SLACK $setup_path]
set whs [get_property SLACK $hold_path]
if {$wns < 0 || $whs < 0} {error "Routed timing not met: WNS=$wns WHS=$whs"}
set brams [get_cells -hierarchical -filter {REF_NAME =~ RAMB*}]
set dsps [get_cells -hierarchical -filter {REF_NAME =~ DSP48*}]
if {[llength $brams] < 7 || [llength $dsps] < 12} {error "Core/memory was optimized away"}
set fp [open [file join $result_dir metrics.json] w]
puts $fp "{\"setup_wns_ns\":$wns,\"hold_whs_ns\":$whs,\"bram_primitives\":[llength $brams],\"dsp_primitives\":[llength $dsps],\"clock_mhz\":100,\"scope\":\"PYNQ-Z2 standalone BIST+MMIO+BRAM+HLS; not CPU\"}"
close $fp
set bit_file [file join [get_property DIRECTORY [get_runs impl_1]] mlkem512_basemul_k2_pynqz2_top.bit]
if {![file exists $bit_file]} {error "Missing bitstream: $bit_file"}
set release_dir [file join $root release mlkem512_basemul_k2]
file mkdir $release_dir
file copy -force $bit_file [file join $release_dir mlkem512_basemul_k2_validation.bit]
