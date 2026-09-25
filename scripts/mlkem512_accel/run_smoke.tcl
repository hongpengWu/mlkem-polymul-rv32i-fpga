set root [file normalize [file join [file dirname [info script]] ../..]]
if {[version -short] ne "2024.2"} {error "Use Vivado 2024.2"}
set dir [file join $root build cpu_accel_smoke]
create_project -force cpu_accel_smoke $dir -part xc7z020clg400-1
set_property target_language Verilog [current_project]
set_property XPM_LIBRARIES {XPM_MEMORY} [current_project]
foreach f {rtl/cpu/picorv32.v rtl/accelerator/mlkem512_accel_system.sv rtl/accelerator/mlkem512_tdp_bram.sv rtl/accelerator/mlkem512_basemul_k2_mmio_adapter.sv} {
    add_files -norecurse [file join $root $f]
}
foreach f [glob [file join $root rtl/accelerator/mlkem512_basemul_k2/hls/hdl/verilog/*.v]] {add_files -norecurse $f}
set image [file join $root firmware/images/mlkem512_accel/smoke.mem]
add_files -norecurse $image
set_property file_type {Memory Initialization Files} [get_files $image]
set_property top mlkem512_accel_system [get_filesets sources_1]
add_files -fileset sim_1 -norecurse [file join $root tb/accelerator/tb_mlkem512_cpu_smoke.sv]
foreach f [glob [file join $root tb/accelerator/vectors/case_*_expected.mem]] {
    add_files -fileset sim_1 -norecurse $f
    set_property file_type {Memory Initialization Files} [get_files $f]
}
set_property top tb_mlkem512_cpu_smoke [get_filesets sim_1]
set_property xsim.simulate.runtime all [get_filesets sim_1]
set_property xsim.elaborate.debug_level off [get_filesets sim_1]
update_compile_order -fileset sources_1
update_compile_order -fileset sim_1
launch_simulation -simset sim_1
close_sim
set logpath [file join $dir cpu_accel_smoke.sim sim_1 behav xsim simulate.log]
set f [open $logpath r]; set log [read $f]; close $f
if {[string first "CPU_ACCEL_SMOKE_PASS cases=3 coefficients=768" $log]<0 || [regexp -nocase {fatal:|ERROR:|CPU_ACCEL_SMOKE_FAIL} $log]} {error "CPU accelerator smoke failed: $logpath"}
set evidence [file join $root results accelerator_cpu]
file mkdir $evidence
file copy -force $logpath [file join $evidence smoke_simulate.log]
close_project
puts "CPU_ACCEL_INTEGRATION_PASS"
