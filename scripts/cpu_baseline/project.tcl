# Shared project definition for simulation and implementation.
proc cpu_baseline_parameters {config} {
    switch -- $config {
        rv32i { return {CPU_ENABLE_MUL=0 CPU_ENABLE_FAST_MUL=0 CPU_ENABLE_DIV=0} }
        rv32im_iterative { return {CPU_ENABLE_MUL=1 CPU_ENABLE_FAST_MUL=0 CPU_ENABLE_DIV=1} }
        rv32im_fast { return {CPU_ENABLE_MUL=1 CPU_ENABLE_FAST_MUL=1 CPU_ENABLE_DIV=1} }
        default { error "Unknown CPU config $config" }
    }
}

proc cpu_baseline_add_simulation {root config} {
    add_files -fileset sim_1 -norecurse [file join $root tb/software/tb_cpu_baseline.sv]
    set vectors [file join $root tb/software/cpu_polymul_vectors.mem]
    add_files -fileset sim_1 -norecurse $vectors
    set_property file_type {Memory Initialization Files} [get_files $vectors]
    set_property top tb_cpu_baseline [get_filesets sim_1]
    set expect_m [expr {$config ne "rv32i"}]
    set_property generic [concat [cpu_baseline_parameters $config] EXPECT_M=$expect_m] [get_filesets sim_1]
    set_property xsim.simulate.runtime all [get_filesets sim_1]
    update_compile_order -fileset sim_1
}

proc cpu_baseline_create {root config} {
    if {[version -short] ne "2024.2"} {error "Use Vivado 2024.2"}
    set parameters [cpu_baseline_parameters $config]
    set project_dir [file join $root vivado cpu_baseline_$config]
    set isa [expr {$config eq "rv32i" ? "rv32i" : "rv32im"}]
    set generated_mem [file join $project_dir cpu_baseline.mem]
    file mkdir $project_dir
    file copy -force [file join $root firmware images cpu_baseline $isa.mem] $generated_mem
    create_project -force cpu_baseline $project_dir -part xc7z020clg400-1
    set_property target_language Verilog [current_project]
    set_property simulator_language Mixed [current_project]
    set_property XPM_LIBRARIES {XPM_MEMORY} [current_project]
    foreach f {
        rtl/cpu/picorv32.v
        rtl/benchmark/cpu_benchmark_system.v
        rtl/benchmark/cpu_benchmark_pynqz2_top.v
    } {add_files -norecurse [file join $root $f]}
    foreach f {constraints/pynq_z2_board.xdc constraints/pynqz2_bram_reset.xdc} {
        add_files -fileset constrs_1 -norecurse [file join $root $f]
    }
    add_files -norecurse $generated_mem
    set_property file_type {Memory Initialization Files} [get_files $generated_mem]
    set_property top cpu_benchmark_pynqz2_top [get_filesets sources_1]
    set_property generic [concat {FIRMWARE_INIT_FILE=cpu_baseline.mem ENABLE_VIO=0} $parameters] [get_filesets sources_1]
    update_compile_order -fileset sources_1
    cpu_baseline_add_simulation $root $config
    return $project_dir
}
