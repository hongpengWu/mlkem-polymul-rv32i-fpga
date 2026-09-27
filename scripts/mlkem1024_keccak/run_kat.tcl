# Run only frozen inputs in a unique short directory. No synthesis needed for RTL KAT.
if {[version -short] ne "2024.2"} {error "Use Vivado 2024.2"}
if {[llength $argv] != 3} {error "Expected run_dir case_count threads"}
lassign $argv run case_count threads
set run [file normalize $run]
set snapshot [file join $run snapshot]
if {![string is integer -strict $case_count] || $case_count<1 || $case_count>145} {error "Invalid case count"}
if {![string is integer -strict $threads] || $threads<1 || $threads>8} {error "Invalid thread count"}
set_param general.maxThreads $threads
puts "KECCAK_THREADS general.maxThreads=[get_param general.maxThreads]"
create_project keccakkat [file join $run p] -part xc7z020clg400-1
set_property target_language Verilog [current_project]
set_property XPM_LIBRARIES {XPM_MEMORY} [current_project]
foreach f [glob [file join $snapshot rtl *]] {add_files -norecurse $f}
foreach f [glob [file join $snapshot hls *.v]] {add_files -norecurse $f}
foreach f [glob [file join $snapshot hls *.dat]] {add_files -norecurse $f}
set fw [file join $snapshot fixtures mlkem1024.mem]
add_files -norecurse $fw
set_property file_type {Memory Initialization Files} [get_files $fw]
set_property top mlkem1024_keccak_system [get_filesets sources_1]
set_property generic {FIRMWARE_INIT_FILE=mlkem1024.mem RAM_ADDR_BITS=15 CPU_ENABLE_MUL=1 CPU_ENABLE_FAST_MUL=1 CPU_ENABLE_DIV=1} [get_filesets sources_1]
add_files -fileset sim_1 -norecurse [file join $snapshot tb tb_mlkem1024_keccak_kat.sv]
foreach name {mlkem1024_input.mem mlkem1024_expected.mem} {
    set f [file join $snapshot fixtures $name]
    add_files -fileset sim_1 -norecurse $f
    set_property file_type {Memory Initialization Files} [get_files $f]
}
set_property top tb_mlkem1024_keccak_kat [get_filesets sim_1]
set_property generic [list EXPECTED_CASES=$case_count] [get_filesets sim_1]
set_property xsim.simulate.runtime all [get_filesets sim_1]
set_property xsim.elaborate.debug_level off [get_filesets sim_1]
set_property xsim.elaborate.mt_level auto [get_filesets sim_1]
# Avoid waveform recording overhead in long official regressions.
set sim_tcl [file join $run sim.tcl]
set fp [open $sim_tcl w]
puts $fp "run all\nquit"
close $fp
set_property xsim.simulate.custom_tcl $sim_tcl [get_filesets sim_1]
update_compile_order -fileset sources_1
update_compile_order -fileset sim_1
launch_simulation -simset sim_1
close_sim
set logfile [file join $run p keccakkat.sim sim_1 behav xsim simulate.log]
file copy $logfile [file join $run simulate.log]
set fp [open $logfile r]; set log [read $fp]; close $fp
if {![regexp "MLKEM_PASS cases=$case_count " $log] || ![regexp "KECCAK_PASS cases=$case_count " $log] ||
    [regexp -nocase {fatal:|ERROR:|MLKEM_FAIL|KECCAK_FAIL} $log]} {error "Full KEM hardware KAT failed: $logfile"}
close_project
puts "KECCAK_KAT_RUN_PASS"
