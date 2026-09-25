# Complete ML-KEM-512 official suite on the unchanged CPU/AXI/XPM shell.
set root [file normalize [file join [file dirname [info script]] ../..]]
if {[version -short] ne "2024.2"} {error "Use Vivado 2024.2"}
set config [lindex $argv 0]
switch -- $config {
    rv32i {set parameters {CPU_ENABLE_MUL=0 CPU_ENABLE_FAST_MUL=0 CPU_ENABLE_DIV=0}; set isa rv32i; set expect_m 0}
    rv32im_iterative {set parameters {CPU_ENABLE_MUL=1 CPU_ENABLE_FAST_MUL=0 CPU_ENABLE_DIV=1}; set isa rv32im; set expect_m 1}
    rv32im_fast {set parameters {CPU_ENABLE_MUL=1 CPU_ENABLE_FAST_MUL=1 CPU_ENABLE_DIV=1}; set isa rv32im; set expect_m 1}
    default {error "Expected rv32i, rv32im_iterative or rv32im_fast"}
}
set project_dir [file join $root vivado mlkem512_$config]
file mkdir $project_dir
set image [file join $project_dir mlkem512.mem]
file copy -force [file join $root firmware images mlkem512_suite $isa.mem] $image
create_project -force mlkem512 $project_dir -part xc7z020clg400-1
set_property target_language Verilog [current_project]
set_property simulator_language Mixed [current_project]
set_property XPM_LIBRARIES {XPM_MEMORY} [current_project]
foreach f {rtl/cpu/picorv32.v rtl/benchmark/cpu_benchmark_system.v} {add_files -norecurse [file join $root $f]}
add_files -norecurse $image
set_property file_type {Memory Initialization Files} [get_files $image]
set_property top cpu_benchmark_system [get_filesets sources_1]
set_property generic [concat {FIRMWARE_INIT_FILE=mlkem512.mem RAM_ADDR_BITS=14} $parameters] [get_filesets sources_1]
add_files -fileset sim_1 -norecurse [file join $root tb software tb_mlkem512_suite.sv]
foreach name {mlkem512_input.mem mlkem512_expected.mem} {
    set path [file join $root tb software mlkem512_suite $name]
    add_files -fileset sim_1 -norecurse $path
    set_property file_type {Memory Initialization Files} [get_files $path]
}
set_property top tb_mlkem512_suite [get_filesets sim_1]
set_property generic [concat $parameters EXPECT_M=$expect_m] [get_filesets sim_1]
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
if {[string first "MLKEM512_PASS cases=145" $log] < 0 || [regexp -nocase {fatal:|\$fatal|ERROR:} $log]} {
    error "ML-KEM-512 suite failed: $logpath"
}
set result_dir [file join $root results official_baseline mlkem512 $config]
file mkdir $result_dir
file copy -force $logpath [file join $result_dir simulate.log]
puts "MLKEM512_SIM_PASS config=$config results=$result_dir"
close_project
