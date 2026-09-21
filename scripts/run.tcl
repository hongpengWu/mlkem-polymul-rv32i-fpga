# vivado -mode batch -source scripts/run.tcl -tclargs vio|board|protocol|implement ?firmware_dir?
set root [file normalize [file join [file dirname [info script]] ..]]
set mode [lindex $argv 0]
if {$mode eq ""} {set mode vio}
if {$mode ni {vio board protocol implement}} {error "Expected vio, board, protocol or implement"}
set firmware [file join $root firmware prebuilt]
if {[llength $argv] > 1} {set firmware [file normalize [lindex $argv 1]]}
set run [file join $root build ${mode}_[clock seconds]_[pid]]
file mkdir $run
create_project mlkem $run -part xc7z020clg400-1
foreach dir {rtl/accelerator rtl/axi} {
    add_files -norecurse [glob [file join $root $dir *.v]]
}
add_files -norecurse [glob [file join $root rtl accelerator *.dat]]
if {$mode eq "protocol"} {
    add_files -fileset sim_1 -norecurse [file join $root sim profile tb_bram_wrapper_protocol.sv]
    set simtop tb_bram_wrapper_protocol
    set expected "BRAM PROTOCOL PASS"
} else {
    foreach f {rtl/cpu/picorv32.v rtl/system/mlkem_polymul_rv32i_profile_top.v rtl/board/mlkem_polymul_pynqz2_top.v} {
        add_files -norecurse [file join $root $f]
    }
    add_files -norecurse [file join $firmware transfer_both_unroll4.mem]
    foreach f {pynq_z2_board.xdc pynqz2_bram_reset.xdc} {
        add_files -fileset constrs_1 -norecurse [file join $root constraints $f]
    }
    set_property top mlkem_polymul_pynqz2_top [get_filesets sources_1]
    if {$mode eq "board"} {
        set simtop tb_pynqz2_bram_board
        set expected "PYNQZ2 BOARD SIM PASS"
    } else {
        create_ip -name vio -vendor xilinx.com -library ip -version 3.0 -module_name mlkem_profile_vio
        set config [list CONFIG.C_NUM_PROBE_IN 13 CONFIG.C_NUM_PROBE_OUT 0 CONFIG.C_EN_PROBE_IN_ACTIVITY 0]
        for {set i 0} {$i < 12} {incr i} {lappend config CONFIG.C_PROBE_IN${i}_WIDTH 32}
        lappend config CONFIG.C_PROBE_IN12_WIDTH 2
        set_property -dict $config [get_ips mlkem_profile_vio]
        generate_target all [get_ips mlkem_profile_vio]
        set_property generic {ENABLE_VIO=1} [get_filesets sources_1]
        add_files -fileset sim_1 -norecurse [file join $root sim observer mlkem_core_cycle_observer.sv]
        set simtop tb_pynqz2_profile_vio
        set expected "BOARD VIO SIM PASS"
    }
    add_files -fileset sim_1 -norecurse [file join $root sim profile ${simtop}.sv]
}
set_property top $simtop [get_filesets sim_1]
set_property xsim.simulate.runtime all [get_filesets sim_1]
update_compile_order -fileset sources_1
# Reject any external source/IP dependency before simulation.
foreach f [get_files -all] {
    set full [file normalize $f]
    set relative [string range $full 0 [expr {[string length $root]-1}]]
    if {![string equal -nocase $relative $root] || [string index $full [string length $root]] ne "/"} {
        error "Source outside candidate root: $full"
    }
}
launch_simulation
close_sim
set logpath [file join $run mlkem.sim sim_1 behav xsim simulate.log]
file copy $logpath [file join $run simulate.log]
set f [open $logpath r]; set log [read $f]; close $f
if {[string first $expected $log] < 0 || [regexp -nocase {fatal:|\$fatal|ERROR:} $log]} {
    error "Regression failed; inspect $logpath"
}
if {$mode eq "implement"} {
    set_property strategy Flow_PerfOptimized_high [get_runs synth_1]
    set_property strategy Performance_Explore [get_runs impl_1]
    launch_runs synth_1 -jobs 4
    wait_on_run synth_1
    if {[get_property PROGRESS [get_runs synth_1]] ne "100%"} {error "Synthesis failed"}
    launch_runs impl_1 -to_step write_bitstream -jobs 4
    wait_on_run impl_1
    if {[get_property PROGRESS [get_runs impl_1]] ne "100%"} {error "Implementation failed"}
    open_run impl_1
    report_utilization -file [file join $run utilization_routed.rpt]
    report_timing_summary -report_unconstrained -file [file join $run timing_routed.rpt]
    report_drc -file [file join $run drc_routed.rpt]
    write_debug_probes [file join $run mlkem_profile_vio.ltx]
}
puts "CANDIDATE_REGRESSION_PASS mode=$mode project=[file join $run mlkem.xpr]"
close_project
