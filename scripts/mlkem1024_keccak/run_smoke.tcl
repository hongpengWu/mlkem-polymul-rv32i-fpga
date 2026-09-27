# Frozen CPU + Keccak integration smoke; no synthesis or baseline mutation.
if {[version -short] ne "2024.2"} {error "Use Vivado 2024.2"}
if {[llength $argv] != 1} {error "Expected unique frozen run directory"}
set run [file normalize [lindex $argv 0]]
set snapshot [file join $run snapshot]
create_project keccakcpu [file join $run p] -part xc7z020clg400-1
set_property target_language Verilog [current_project]
set_property XPM_LIBRARIES {XPM_MEMORY} [current_project]
foreach f [glob [file join $snapshot rtl *]] {add_files -norecurse $f}
foreach f [glob [file join $snapshot hls *.v]] {add_files -norecurse $f}
foreach f [glob [file join $snapshot hls *.dat]] {
    add_files -norecurse $f
}
set fw [file join $snapshot fixtures smoke.mem]
add_files -norecurse $fw
set_property file_type {Memory Initialization Files} [get_files $fw]
set_property top mlkem1024_keccak_system [get_filesets sources_1]
add_files -fileset sim_1 -norecurse [file join $snapshot tb tb_mlkem1024_keccak_cpu_smoke.sv]
foreach name {expected.mem meta.mem} {
    set f [file join $snapshot fixtures $name]
    add_files -fileset sim_1 -norecurse $f
    set_property file_type {Memory Initialization Files} [get_files $f]
}
set_property top tb_mlkem1024_keccak_cpu_smoke [get_filesets sim_1]
set_property xsim.simulate.runtime all [get_filesets sim_1]
set_property xsim.elaborate.debug_level off [get_filesets sim_1]
update_compile_order -fileset sources_1
update_compile_order -fileset sim_1
launch_simulation -simset sim_1
close_sim
set logfile [file join $run p keccakcpu.sim sim_1 behav xsim simulate.log]
set fp [open $logfile r]
set log [read $fp]
close $fp
file copy $logfile [file join $run simulate.txt]
if {[string first "KECCAK_CPU_SMOKE_PASS" $log] < 0 || [regexp -nocase {fatal:|ERROR:|KECCAK_CPU_SMOKE_FAIL} $log]} {
    error "CPU Keccak smoke failed; see $logfile"
}
close_project
puts "KECCAK_CPU_RUN_PASS"
