# Reproducible Vivado 2024.2 project. Caches stay beside the tracked XPR.
proc mlkem512_basemul_k2_create {root {project_dir ""}} {
    if {[version -short] ne "2024.2"} {error "Use Vivado 2024.2"}
    if {$project_dir eq ""} {set project_dir [file join $root vivado mlkem512_basemul_k2]}
    create_project -force basemul $project_dir -part xc7z020clg400-1
    set_property target_language Verilog [current_project]
    foreach f [glob [file join $root rtl/accelerator/mlkem512_basemul_k2/hls/hdl/verilog/*.v]] {add_files -norecurse $f}
    foreach f {mlkem512_tdp_bram.sv mlkem512_basemul_k2_mmio_adapter.sv mlkem512_basemul_k2_pynqz2_top.sv} {
        add_files -norecurse [file join $root rtl accelerator $f]
    }
    foreach f {constraints/pynq_z2_board.xdc constraints/pynqz2_bram_reset.xdc} {
        add_files -fileset constrs_1 -norecurse [file join $root $f]
    }
    set rom [file join $root tb accelerator vectors basemul_bist.mem]
    add_files -norecurse $rom
    set_property file_type {Memory Initialization Files} [get_files $rom]
    set_property top mlkem512_basemul_k2_pynqz2_top [get_filesets sources_1]
    foreach f [glob [file join $root tb accelerator vectors case_*.mem]] {
        add_files -fileset sim_1 -norecurse $f
        set_property file_type {Memory Initialization Files} [get_files $f]
    }
    add_files -fileset sim_1 -norecurse [file join $root tb/accelerator/tb_mlkem512_basemul_k2_mmio.sv]
    add_files -fileset sim_1 -norecurse [file join $root tb/accelerator/tb_mlkem512_basemul_k2_board.sv]
    set_property top tb_mlkem512_basemul_k2_mmio [get_filesets sim_1]
    set_property xsim.simulate.runtime all [get_filesets sim_1]
    update_compile_order -fileset sources_1
    update_compile_order -fileset sim_1
    return $project_dir
}
