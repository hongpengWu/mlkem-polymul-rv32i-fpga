# Vivado 2024.2 synthesis, implementation and bitstream generation.
set root [file normalize [file join [file dirname [info script]] ../..]]
source [file join $root scripts mlkem512_basemul_k2 project.tcl]
set project_dir [mlkem512_basemul_k2_create $root]
launch_runs synth_1 -jobs 4
wait_on_run synth_1
if {[get_property STATUS [get_runs synth_1]] ne "synth_design Complete!"} {error "Synthesis failed"}
launch_runs impl_1 -to_step write_bitstream -jobs 4
wait_on_run impl_1
if {[get_property STATUS [get_runs impl_1]] ne "write_bitstream Complete!"} {error "Implementation failed"}
source [file join $root scripts mlkem512_basemul_k2 export_reports.tcl]
close_project
puts "BASEMUL_VIVADO_IMPL_PASS results=$result_dir"
