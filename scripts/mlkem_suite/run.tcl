# Parameterized CPU-only ML-KEM official suite.  The K=2 path remains on its
# original scripts; this path is independent and uses the 128 KiB/32 KiB
# envelope for K=3/K=4.
set root [file normalize [file join [file dirname [info script]] ../..]]
if {[version -short] ne "2024.2"} {error "Use Vivado 2024.2"}
if {[llength $argv] != 2} {error "Expected parameter_set config"}
set level [lindex $argv 0]
set config [lindex $argv 1]
if {$level ni {768 1024}} {error "Expected parameter set 768 or 1024"}
switch -- $config {
    rv32i {set parameters {CPU_ENABLE_MUL=0 CPU_ENABLE_FAST_MUL=0 CPU_ENABLE_DIV=0}; set isa rv32i; set expect_m 0}
    rv32im_iterative {set parameters {CPU_ENABLE_MUL=1 CPU_ENABLE_FAST_MUL=0 CPU_ENABLE_DIV=1}; set isa rv32im; set expect_m 1}
    rv32im_fast {set parameters {CPU_ENABLE_MUL=1 CPU_ENABLE_FAST_MUL=1 CPU_ENABLE_DIV=1}; set isa rv32im; set expect_m 1}
    default {error "Expected rv32i, rv32im_iterative or rv32im_fast"}
}
set ram_bits [expr {$level == 512 ? 14 : 15}]
set stack_bytes [expr {$level == 512 ? 16384 : 32768}]
set tag mlkem${level}
set project_dir [file join $root vivado ${tag}_$config]
file mkdir $project_dir
set image [file join $project_dir ${tag}.mem]
file copy -force [file join $root firmware images ${tag}_suite $isa.mem] $image
create_project -force $tag $project_dir -part xc7z020clg400-1
set_property target_language Verilog [current_project]
set_property simulator_language Mixed [current_project]
set_property XPM_LIBRARIES {XPM_MEMORY} [current_project]
foreach f {rtl/cpu/picorv32.v rtl/benchmark/cpu_benchmark_system.v} {add_files -norecurse [file join $root $f]}
add_files -norecurse $image
set_property file_type {Memory Initialization Files} [get_files $image]
set_property top cpu_benchmark_system [get_filesets sources_1]
set_property generic [concat [list FIRMWARE_INIT_FILE=${tag}.mem RAM_ADDR_BITS=$ram_bits] $parameters] [get_filesets sources_1]
add_files -fileset sim_1 -norecurse [file join $root tb software tb_mlkem_suite.sv]
foreach name [list ${tag}_input.mem ${tag}_expected.mem] {
    set path [file join $root tb software ${tag}_suite $name]
    add_files -fileset sim_1 -norecurse $path
    set_property file_type {Memory Initialization Files} [get_files $path]
}
set_property top tb_mlkem_suite [get_filesets sim_1]
set sim_generics [concat [list PARAMETER_SET=$level RAM_ADDR_BITS=$ram_bits STACK_BYTES=$stack_bytes FIRMWARE_INIT_FILE=${tag}.mem INPUT_FIXTURE_FILE=${tag}_input.mem EXPECTED_FIXTURE_FILE=${tag}_expected.mem] $parameters [list EXPECT_M=$expect_m]]
set_property generic $sim_generics [get_filesets sim_1]
set_property xsim.elaborate.debug_level off [get_filesets sim_1]
set_property xsim.simulate.custom_tcl [file join $root scripts mlkem_suite sim.tcl] [get_filesets sim_1]
set_property xsim.simulate.runtime all [get_filesets sim_1]
update_compile_order -fileset sources_1
update_compile_order -fileset sim_1
launch_simulation -simset sim_1
close_sim
set logpath [file join $project_dir ${tag}.sim sim_1 behav xsim simulate.log]
set f [open $logpath r]; set log [read $f]; close $f
if {[string first "MLKEM_PASS cases=145" $log] < 0 || [regexp -nocase {fatal:|\$fatal|ERROR:} $log]} {
    error "ML-KEM-$level suite failed: $logpath"
}
set result_dir [file join $root results official_baseline $tag $config]
file mkdir $result_dir
file copy -force $logpath [file join $result_dir simulate.log]
puts "MLKEM${level}_SIM_PASS config=$config results=$result_dir"
close_project
