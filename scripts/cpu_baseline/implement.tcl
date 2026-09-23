# Vivado 2024.2 CPU-only baseline synthesis and implementation.
# Usage: vivado -mode batch -source scripts/cpu_baseline/implement.tcl \
#   -tclargs rv32i|rv32im_iterative|rv32im_fast
set root [file normalize [file join [file dirname [info script]] ../..]]
set config [lindex $argv 0]
if {$config eq ""} {set config rv32i}
source [file join $root scripts/cpu_baseline/project.tcl]
set project_dir [cpu_baseline_create $root $config]

launch_runs synth_1 -jobs 4
wait_on_run synth_1
if {[get_property STATUS [get_runs synth_1]] ne "synth_design Complete!"} {
    error "Synthesis failed for $config"
}
launch_runs impl_1 -to_step write_bitstream -jobs 4
wait_on_run impl_1
if {[get_property STATUS [get_runs impl_1]] ne "write_bitstream Complete!"} {
    error "Implementation failed for $config"
}

source [file join $root scripts/cpu_baseline/export_reports.tcl]
close_project
puts "CPU_BASELINE_IMPL_PASS config=$config results=$result_dir"
