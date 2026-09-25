set root [file normalize [file join [file dirname [info script]] ../..]]
source [file join $root scripts/mlkem512_basemul_k2/project.tcl]
# Simulation must not recreate or discard the implemented release project.
set project_dir [mlkem512_basemul_k2_create $root [file join $root build basemul_rtl]]
launch_simulation -simset sim_1
close_sim
set logpath [file join $project_dir basemul.sim sim_1 behav xsim simulate.log]
set f [open $logpath r]; set log [read $f]; close $f
if {[string first "MLKEM512_BASEMUL_MMIO_RTL_PASS cases=3 checks=768" $log] < 0 || [regexp -nocase {fatal:|ERROR:|FAIL} $log]} {
    error "MMIO regression failed: $logpath"
}
set result_dir [file join $root results accelerator_interface rtl_sim]
file mkdir $result_dir
file copy -force $logpath [file join $result_dir simulate.log]
if {[string first "MMIO_PROTOCOL_PASS" $log] < 0} {error "Protocol checks missing"}
set_property top tb_mlkem512_basemul_k2_board [get_filesets sim_1]
launch_simulation -simset sim_1
close_sim
set f [open $logpath r]; set board_log [read $f]; close $f
if {[string first "MLKEM512_BASEMUL_BOARD_BIST_RTL_PASS runs=2 checked_words=256 mismatch_detected=1 board_top_runs=2" $board_log] < 0 || [regexp -nocase {fatal:|ERROR:|FAIL} $board_log]} {
    error "Board self-test failed: $logpath"
}
file copy -force $logpath [file join $result_dir board_simulate.log]
set_property top tb_mlkem512_basemul_k2_mmio [get_filesets sim_1]
close_project
puts "BASEMUL_MMIO_SIM_PASS results=$result_dir"
