# Isolated resume batch; same firmware and CPU/AXI/XPM design as the full suite.
set root [file normalize [file join [file dirname [info script]] ../..]]
if {[version -short] ne "2024.2"} {error "Use Vivado 2024.2"}
if {[llength $argv] != 4} {error "Expected config batch_dir project_dir case_count"}
lassign $argv config result_dir project_dir case_count
set result_dir [file normalize $result_dir]
set project_dir [file normalize $project_dir]
if {![string is integer -strict $case_count] || $case_count<1 || $case_count>145} {error "Invalid case count"}
switch -- $config {
    rv32i {set parameters {CPU_ENABLE_MUL=0 CPU_ENABLE_FAST_MUL=0 CPU_ENABLE_DIV=0}; set isa rv32i; set expect_m 0}
    rv32im_iterative {set parameters {CPU_ENABLE_MUL=1 CPU_ENABLE_FAST_MUL=0 CPU_ENABLE_DIV=1}; set isa rv32im; set expect_m 1}
    rv32im_fast {set parameters {CPU_ENABLE_MUL=1 CPU_ENABLE_FAST_MUL=1 CPU_ENABLE_DIV=1}; set isa rv32im; set expect_m 1}
    default {error "Invalid CPU configuration"}
}
file mkdir $project_dir
set image [file join $project_dir mlkem512.mem]
file copy -force [file join $root firmware images mlkem512_suite $isa.mem] $image
create_project -force mlkem512 $project_dir -part xc7z020clg400-1
set_param general.maxThreads 1
set_property target_language Verilog [current_project]
set_property simulator_language Mixed [current_project]
set_property XPM_LIBRARIES {XPM_MEMORY} [current_project]
foreach name {rtl/cpu/picorv32.v rtl/benchmark/cpu_benchmark_system.v} {add_files -norecurse [file join $root $name]}
add_files -norecurse $image
set_property file_type {Memory Initialization Files} [get_files $image]
set_property top cpu_benchmark_system [get_filesets sources_1]
set_property generic [concat {FIRMWARE_INIT_FILE=mlkem512.mem RAM_ADDR_BITS=14} $parameters] [get_filesets sources_1]
add_files -fileset sim_1 -norecurse [file join $root tb software tb_mlkem512_suite.sv]
foreach name {mlkem512_input.mem mlkem512_expected.mem} {
    set path [file join $result_dir $name]
    add_files -fileset sim_1 -norecurse $path
    set_property file_type {Memory Initialization Files} [get_files $path]
}
set_property top tb_mlkem512_suite [get_filesets sim_1]
set_property generic [concat $parameters EXPECT_M=$expect_m EXPECTED_CASES=$case_count] [get_filesets sim_1]
set_property xsim.elaborate.debug_level off [get_filesets sim_1]
set_property xsim.simulate.custom_tcl [file join $root scripts mlkem512_suite sim.tcl] [get_filesets sim_1]
set_property xsim.simulate.runtime all [get_filesets sim_1]
update_compile_order -fileset sources_1
update_compile_order -fileset sim_1
launch_simulation -simset sim_1
close_sim
set logpath [file join $project_dir mlkem512.sim sim_1 behav xsim simulate.log]
set f [open $logpath r]
set log [read $f]
close $f
if {![regexp "MLKEM512_PASS cases=$case_count " $log] || [regexp -nocase {fatal:|\$fatal|ERROR:|MLKEM512_FAIL} $log]} {
    error "ML-KEM-512 batch failed: $logpath"
}
file copy -force $logpath [file join $result_dir simulate.log]
puts "MLKEM512_BATCH_PASS config=$config cases=$case_count results=$result_dir"
close_project
