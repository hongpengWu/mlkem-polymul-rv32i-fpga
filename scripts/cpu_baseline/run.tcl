# Vivado 2024.2 CPU-only software baseline simulation.
# Usage: vivado -mode batch -source scripts/cpu_baseline/run.tcl \
#   -tclargs rv32i|rv32im_iterative|rv32im_fast
set root [file normalize [file join [file dirname [info script]] ../..]]
set config [lindex $argv 0]
if {$config eq ""} {set config rv32i}
source [file join $root scripts/cpu_baseline/project.tcl]
set project_dir [cpu_baseline_create $root $config]
launch_simulation -simset sim_1
close_sim
set logpath [file join $project_dir cpu_baseline.sim sim_1 behav xsim simulate.log]
set f [open $logpath r]; set log [read $f]; close $f
if {[string first "CPU_BASELINE_PASS cases=8 checks=4096" $log] < 0 || [regexp -nocase {fatal:|\$fatal|ERROR:} $log]} {
    error "CPU baseline simulation failed; inspect $logpath"
}
set result_dir [file join $root results cpu_baseline $config]
file mkdir $result_dir
file copy -force $logpath [file join $result_dir simulate.log]
puts "CPU_BASELINE_SIM_PASS config=$config results=$result_dir"
close_project
