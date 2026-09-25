# ML-KEM-512 official KeyGen tcId=1 on the existing CPU/AXI/XPM system.
# This project is a simulation milestone, not a board implementation.
set root [file normalize [file join [file dirname [info script]] ../..]]
if {[version -short] ne "2024.2"} {error "Use Vivado 2024.2"}
set config [lindex $argv 0]
if {$config eq ""} {set config rv32i}
switch -- $config {
    rv32i {set parameters {CPU_ENABLE_MUL=0 CPU_ENABLE_FAST_MUL=0 CPU_ENABLE_DIV=0}; set isa rv32i; set expect_m 0}
    rv32im_iterative {set parameters {CPU_ENABLE_MUL=1 CPU_ENABLE_FAST_MUL=0 CPU_ENABLE_DIV=1}; set isa rv32im; set expect_m 1}
    rv32im_fast {set parameters {CPU_ENABLE_MUL=1 CPU_ENABLE_FAST_MUL=1 CPU_ENABLE_DIV=1}; set isa rv32im; set expect_m 1}
    default {error "Unknown CPU configuration $config"}
}
set project_dir [file join $root vivado mlkem_keygen_$config]
file mkdir $project_dir
set image [file join $project_dir mlkem_keygen.mem]
file copy -force [file join $root firmware images mlkem_keygen $isa.mem] $image
create_project -force mlkem_keygen $project_dir -part xc7z020clg400-1
set_property target_language Verilog [current_project]
set_property simulator_language Mixed [current_project]
set_property XPM_LIBRARIES {XPM_MEMORY} [current_project]
foreach f {rtl/cpu/picorv32.v rtl/benchmark/cpu_benchmark_system.v} {
    add_files -norecurse [file join $root $f]
}
add_files -norecurse $image
set_property file_type {Memory Initialization Files} [get_files $image]
set_property top cpu_benchmark_system [get_filesets sources_1]
set_property generic [concat {FIRMWARE_INIT_FILE=mlkem_keygen.mem RAM_ADDR_BITS=14} $parameters] [get_filesets sources_1]
add_files -fileset sim_1 -norecurse [file join $root tb software tb_mlkem_keygen.sv]
foreach name {mlkem512_keygen_input.mem mlkem512_keygen_expected.mem} {
    set path [file join $root tb software mlkem_keygen $name]
    add_files -fileset sim_1 -norecurse $path
    set_property file_type {Memory Initialization Files} [get_files $path]
}
set_property top tb_mlkem_keygen [get_filesets sim_1]
set_property generic [concat $parameters EXPECT_M=$expect_m] [get_filesets sim_1]
set_property xsim.simulate.runtime all [get_filesets sim_1]
update_compile_order -fileset sources_1
update_compile_order -fileset sim_1
launch_simulation -simset sim_1
close_sim
set logpath [file join $project_dir mlkem_keygen.sim sim_1 behav xsim simulate.log]
set f [open $logpath r]; set log [read $f]; close $f
if {[string first "MLKEM_KEYGEN_PASS" $log] < 0 || [regexp -nocase {fatal:|\$fatal|ERROR:} $log]} {
    error "ML-KEM KeyGen simulation failed; inspect $logpath"
}
set result_dir [file join $root results official_baseline keygen512_tc1 $config]
file mkdir $result_dir
file copy -force $logpath [file join $result_dir simulate.log]
puts "MLKEM_KEYGEN_SIM_PASS config=$config results=$result_dir"
close_project
