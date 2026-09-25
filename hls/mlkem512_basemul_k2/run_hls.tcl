set project_dir [file normalize [file join [pwd] mlkem512_basemul_k2_vivado]]
set root_dir [file normalize [file dirname [info script]]]

open_project -reset $project_dir
set_top mlkem512_basemul_acc_k2
add_files [file join $root_dir src mlkem512_basemul_acc_k2.cpp]
add_files [file join $root_dir src mlkem512_basemul_acc_k2.h]
add_files -tb [file join $root_dir tb tb_mlkem512_basemul_acc_k2.cpp] \
    -cflags "-I[file join $root_dir src]"

open_solution -reset solution1
set_part xc7z020clg400-1
create_clock -period 10 -name default
csim_design
csynth_design
export_design -format ip_catalog
close_project
exit
