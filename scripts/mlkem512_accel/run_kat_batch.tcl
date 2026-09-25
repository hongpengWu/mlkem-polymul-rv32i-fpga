set root [file normalize [file join [file dirname [info script]] ../..]]
if {[version -short] ne "2024.2"} {error "Use Vivado 2024.2"}
if {[llength $argv] != 3} {error "Expected batch_dir project_dir case_count"}
lassign $argv result_dir project_dir case_count
set result_dir [file normalize $result_dir]; set project_dir [file normalize $project_dir]
file mkdir $project_dir
create_project -force mlkem512_accel $project_dir -part xc7z020clg400-1
set_param general.maxThreads 1
set_property target_language Verilog [current_project]
set_property simulator_language Mixed [current_project]
set_property XPM_LIBRARIES {XPM_MEMORY} [current_project]
foreach f {rtl/cpu/picorv32.v rtl/accelerator/mlkem512_accel_system.sv rtl/accelerator/mlkem512_tdp_bram.sv rtl/accelerator/mlkem512_basemul_k2_mmio_adapter.sv} {add_files -norecurse [file join $root $f]}
foreach f [glob [file join $root rtl/accelerator/mlkem512_basemul_k2/hls/hdl/verilog/*.v]] {add_files -norecurse $f}
set image [file join $root firmware/images/mlkem512_accel/kat.mem]; add_files -norecurse $image; set_property file_type {Memory Initialization Files} [get_files $image]
set_property top mlkem512_accel_system [get_filesets sources_1]
add_files -fileset sim_1 -norecurse [file join $root tb/accelerator/tb_mlkem512_kat_accel.sv]
foreach f {mlkem512_input.mem mlkem512_expected.mem} {set p [file join $result_dir $f]; add_files -fileset sim_1 -norecurse $p; set_property file_type {Memory Initialization Files} [get_files $p]}
set_property top tb_mlkem512_kat_accel [get_filesets sim_1]
puts "SIM_TOP=[get_property top [get_filesets sim_1]]"
set_property generic [list EXPECT_M=1 EXPECTED_CASES=$case_count] [get_filesets sim_1]
set_property xsim.simulate.runtime all [get_filesets sim_1]
set_property xsim.elaborate.debug_level off [get_filesets sim_1]
set_property xsim.simulate.custom_tcl [file join $root scripts/mlkem512_suite/sim.tcl] [get_filesets sim_1]
update_compile_order -fileset sources_1; update_compile_order -fileset sim_1
set_property top tb_mlkem512_kat_accel [get_filesets sim_1]
launch_simulation -simset sim_1; close_sim
set logpath [file join $project_dir mlkem512_accel.sim sim_1 behav xsim simulate.log]
set f [open $logpath r]; set log [read $f]; close $f
if {![regexp "MLKEM512_PASS cases=$case_count " $log] || [regexp -nocase {fatal:|\$fatal|ERROR:|MLKEM512_FAIL} $log]} {error "Accelerated KAT failed: $logpath"}
file copy -force $logpath [file join $result_dir accelerate_simulate.log]
puts "MLKEM512_ACCEL_BATCH_PASS cases=$case_count results=$result_dir"; close_project
