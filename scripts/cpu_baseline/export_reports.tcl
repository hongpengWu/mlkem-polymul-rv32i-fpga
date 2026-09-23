# Source with the implemented CPU project open, and root/config set.
set result_dir [file join $root results cpu_baseline $config]
file mkdir $result_dir
open_run impl_1
report_utilization -hierarchical -file [file join $result_dir utilization_hierarchical.rpt]
report_utilization -file [file join $result_dir utilization.rpt]
report_timing_summary -delay_type min_max -report_unconstrained -file [file join $result_dir timing_summary.rpt]
report_drc -file [file join $result_dir drc.rpt]
report_route_status -file [file join $result_dir route_status.rpt]
report_power -file [file join $result_dir power.rpt]
set bit_file [file join [get_property DIRECTORY [get_runs impl_1]] cpu_benchmark_pynqz2_top.bit]
if {![file exists $bit_file]} {error "Missing bitstream: $bit_file"}
set release_dir [file join $root release cpu_baseline_$config]
file mkdir $release_dir
file copy -force $bit_file [file join $release_dir cpu_baseline_$config.bit]
