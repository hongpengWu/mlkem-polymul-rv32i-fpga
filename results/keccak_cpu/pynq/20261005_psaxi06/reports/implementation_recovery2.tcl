# PS/PL overlay entry point. Vivado 2024.2; PYNQ-Z2 xc7z020clg400-1.
# Example: vivado -mode batch -source scripts/mlkem1024_keccak/vivado_bd.tcl
# Override top switches with BD_<NAME>; RUN_DIR allows resuming frozen inputs.
set PREPARE 1
set SIM 1
set CREATE_BD 1
set SYNTH 1
set IMPL 1
set EXPORT 1
set max_threads 8
set PYTHON D:/Tech/python.exe
set SHORT_ROOT E:/hls/k4pynq
set RUN_DIR ""
set REUSE_SIM ""
set SCRIPT_DIR [file normalize [file dirname [info script]]]
set ROOT [file normalize [file join $SCRIPT_DIR ../..]]
foreach setting {PREPARE SIM CREATE_BD SYNTH IMPL EXPORT} {
    if {[info exists ::env(BD_$setting)]} {set $setting $::env(BD_$setting)}
    if {[set $setting] ni {0 1}} {error "$setting must be 0 or 1"}
}
foreach setting {PYTHON SHORT_ROOT RUN_DIR REUSE_SIM} {
    if {[info exists ::env(BD_$setting)]} {set $setting $::env(BD_$setting)}
}
if {[version -short] ne "2024.2"} {error "Use Vivado 2024.2"}
if {$EXPORT && !$IMPL} {error "EXPORT requires IMPL (including physical signoff)"}
set_param general.maxThreads $max_threads
if {$RUN_DIR eq ""} {
    set RUN_DIR [file join $SHORT_ROOT [clock format [clock seconds] -format %Y%m%d_%H%M%S]]
}
set run [file normalize $RUN_DIR]
set snapshot [file join $run snapshot]
set reports [file join $run reports]
set project_dir [file join $run project]
set helper [file join $SCRIPT_DIR pynq_overlay.py]
file mkdir $reports
cd $ROOT

proc read_text {path} {set f [open $path r]; set t [read $f]; close $f; return $t}
proc require_one {objects description} {
    if {[llength $objects] != 1} {error "Expected one $description, got $objects"}
    return [lindex $objects 0]
}
proc add_core {} {
    foreach pattern {rtl/*.v rtl/*.sv hls/*.v hls/*.dat} {
        foreach f [glob -nocomplain [file join $::snapshot $pattern]] {add_files -norecurse $f}
    }
    set fw [file join $::snapshot ps.mem]
    add_files -norecurse $fw
    set_property file_type {Memory Initialization Files} [get_files $fw]
    set_property target_language Verilog [current_project]
    set_property simulator_language Mixed [current_project]
    set_property XPM_LIBRARIES {XPM_MEMORY} [current_project]
}
proc save_metrics {} {
    set fields {}
    dict for {k v} $::metrics {lappend fields "\"$k\": $v"}
    set f [open [file join $::run metrics.json] w]
    puts $f "\{[join $fields ",\n"]\}"
    close $f
}
set metrics [dict create passed false rtl_subset_passed false bd_validated false physical_board_tested false]
puts "PYNQ_RUN_DIR $run"
set failed [catch {
    if {$PREPARE} {
        exec $PYTHON -E [file join $SCRIPT_DIR build_kat.py] --ps >@ stdout 2>@ stderr
        set command [list $PYTHON -E $helper prepare $run]
        if {$REUSE_SIM ne ""} {lappend command --reuse-sim $REUSE_SIM}
        exec {*}$command >@ stdout 2>@ stderr
    } else {exec $PYTHON -E $helper verify $run >@ stdout 2>@ stderr}
    # Keep all Vivado-generated side files inside this candidate directory.
    cd $run
    if {$SIM} {
        puts "PYNQ_STAGE AXI_RTL_SIM"
        create_project axi_sim [file join $run sim] -part xc7z020clg400-1
        add_core
        set_property top mlkem1024_keccak_axi [get_filesets sources_1]
        set_property generic {FIRMWARE_INIT_FILE=ps.mem} [get_filesets sources_1]
        add_files -fileset sim_1 -norecurse [file join $snapshot tb tb_mlkem1024_keccak_axi.sv]
        foreach name {board_input.mem board_expected.mem} {
            set f [file join $snapshot $name]
            add_files -fileset sim_1 -norecurse $f
            set_property file_type {Memory Initialization Files} [get_files $f]
        }
        set_property top tb_mlkem1024_keccak_axi [get_filesets sim_1]
        set_property generic {FIRMWARE_INIT_FILE=ps.mem} [get_filesets sim_1]
        set_property xsim.simulate.runtime all [get_filesets sim_1]
        set_property xsim.elaborate.debug_level off [get_filesets sim_1]
        set f [open [file join $run sim.tcl] w]; puts $f "run all"; close $f
        set_property xsim.simulate.custom_tcl [file join $run sim.tcl] [get_filesets sim_1]
        update_compile_order -fileset sources_1
        update_compile_order -fileset sim_1
        launch_simulation
        close_sim
        file copy -force [file join $run sim axi_sim.sim sim_1 behav xsim simulate.log] [file join $run simulate.log]
        close_project
    }
    if {![file exists [file join $run simulate.log]]} {error "Missing AXI RTL verification"}
    set simlog [read_text [file join $run simulate.log]]
    if {![regexp {AXI_KAT_PASS cases=3} $simlog] || [regexp -nocase {fatal:|ERROR:|AXI_KAT_FAIL} $simlog]} {
        error "AXI subset/transport verification failed"
    }
    dict set metrics rtl_subset_passed true
    save_metrics

    if {$CREATE_BD} {
        puts "PYNQ_STAGE CREATE_BD"
        create_project k4_pynq $project_dir -part xc7z020clg400-1
        set board [require_one [get_board_parts -quiet tul.com.tw:pynq-z2:part0:*] {PYNQ-Z2 board preset}]
        set_property board_part $board [current_project]
        add_core
        # Vivado module references require a Verilog top; this wrapper uses
        # Verilog-2001 syntax. Its SystemVerilog child modules remain unchanged.
        set_property file_type Verilog [get_files [file join $snapshot rtl mlkem1024_keccak_axi.sv]]
        update_compile_order -fileset sources_1
        create_bd_design system
        set ps [create_bd_cell -type ip -vlnv xilinx.com:ip:processing_system7:5.5 ps7]
        apply_bd_automation -rule xilinx.com:bd_rule:processing_system7 -config {make_external "FIXED_IO, DDR" apply_board_preset "1" Master "Disable" Slave "Disable"} $ps
        set_property -dict [list CONFIG.PCW_USE_M_AXI_GP0 {1} CONFIG.PCW_EN_CLK0_PORT {1} \
            CONFIG.PCW_FPGA0_PERIPHERAL_FREQMHZ {100.000000} CONFIG.PCW_EN_RST0_PORT {1}] $ps
        # The board preset pins the read-only GP0 metadata to 10 MHz. Release
        # that USER override so Vivado propagates the connected 100 MHz clock.
        set_property CONFIG.PCW_M_AXI_GP0_FREQMHZ.VALUE_SRC DEFAULT $ps
        set bus [create_bd_cell -type ip -vlnv xilinx.com:ip:axi_interconnect:2.1 axi_bus]
        set_property -dict [list CONFIG.NUM_SI {1} CONFIG.NUM_MI {1}] $bus
        set core [create_bd_cell -type module -reference mlkem1024_keccak_axi k4_core]
        set_property CONFIG.FIRMWARE_INIT_FILE {ps.mem} $core
        set rst [create_bd_cell -type ip -vlnv xilinx.com:ip:proc_sys_reset:5.0 reset_100m]
        # EXT polarity follows the PS FCLK_RESET0_N pin. AUX is explicitly
        # active-low, so its unused input must be tied HIGH (not to zero).
        set_property CONFIG.C_AUX_RESET_HIGH {0} $rst
        set one [create_bd_cell -type ip -vlnv xilinx.com:ip:xlconstant:1.1 locked_one]
        set_property CONFIG.CONST_VAL {1} $one
        set zero [create_bd_cell -type ip -vlnv xilinx.com:ip:xlconstant:1.1 reset_zero]
        set_property CONFIG.CONST_VAL {0} $zero
        connect_bd_intf_net [get_bd_intf_pins ps7/M_AXI_GP0] [get_bd_intf_pins axi_bus/S00_AXI]
        connect_bd_intf_net [get_bd_intf_pins axi_bus/M00_AXI] [get_bd_intf_pins k4_core/S_AXI]
        foreach name {ps7/M_AXI_GP0_ACLK axi_bus/ACLK axi_bus/S00_ACLK axi_bus/M00_ACLK k4_core/s_axi_aclk reset_100m/slowest_sync_clk} {
            connect_bd_net [get_bd_pins ps7/FCLK_CLK0] [require_one [get_bd_pins -quiet $name] $name]
        }
        connect_bd_net [get_bd_pins ps7/FCLK_RESET0_N] [get_bd_pins reset_100m/ext_reset_in]
        connect_bd_net [get_bd_pins locked_one/dout] [get_bd_pins reset_100m/dcm_locked] [get_bd_pins reset_100m/aux_reset_in]
        connect_bd_net [get_bd_pins reset_zero/dout] [get_bd_pins reset_100m/mb_debug_sys_rst]
        connect_bd_net [get_bd_pins reset_100m/interconnect_aresetn] [get_bd_pins axi_bus/ARESETN]
        foreach name {axi_bus/S00_ARESETN axi_bus/M00_ARESETN k4_core/s_axi_aresetn} {
            connect_bd_net [get_bd_pins reset_100m/peripheral_aresetn] [require_one [get_bd_pins -quiet $name] $name]
        }
        set leds [create_bd_port -dir O -from 3 -to 0 led]
        connect_bd_net $leds [get_bd_pins k4_core/led]
        set segment [require_one [get_bd_addr_segs -quiet k4_core/S_AXI/*] {core address segment}]
        assign_bd_address -offset 0x40000000 -range 0x00040000 -target_address_space [get_bd_addr_spaces ps7/Data] $segment
        validate_bd_design
        if {[get_property CONFIG.C_EXT_RESET_HIGH $rst] != 0 || [get_property CONFIG.C_AUX_RESET_HIGH $rst] != 0} {
            error "Unexpected reset polarity"
        }
        if {[get_bd_nets -of_objects [get_bd_pins reset_100m/aux_reset_in]] ne [get_bd_nets -of_objects [get_bd_pins locked_one/dout]]} {
            error "AUX reset must be inactive high"
        }
        save_bd_design
        write_bd_tcl -force [file join $reports system_bd.tcl]
        set bd [require_one [get_files -quiet */system.bd] system.bd]
        generate_target all $bd
        add_files -norecurse [make_wrapper -files $bd -top]
        set_property top system_wrapper [get_filesets sources_1]
        # Explicit board LED pins; DDR/FIXED_IO are configured by the PS preset.
        set xdc [file join $snapshot overlay_io.xdc]
        add_files -fileset constrs_1 -norecurse $xdc
        update_compile_order -fileset sources_1
        exec $PYTHON -E $helper check-bd $run >@ stdout 2>@ stderr
    } elseif {$SYNTH || $IMPL} {
        open_project [file join $project_dir k4_pynq.xpr]
    }
    if {$CREATE_BD || $SYNTH || $IMPL} {dict set metrics bd_validated true}
    if {$SYNTH} {
        puts "PYNQ_STAGE SYNTH"
        launch_runs synth_1 -jobs $max_threads
        wait_on_run synth_1
        if {[get_property PROGRESS [get_runs synth_1]] ne "100%"} {error "Synthesis failed"}
    }
    if {$IMPL} {
        puts "PYNQ_STAGE IMPLEMENT"
        set_property strategy Performance_ExplorePostRoutePhysOpt [get_runs impl_1]
        set impl_dir [get_property DIRECTORY [get_runs impl_1]]
        set route_end [file join $impl_dir .route_design.end.rst]
        set route_dcp [file join $impl_dir system_wrapper_routed.dcp]
        # Vivado reports the NEXT enabled step as "Not started" after a
        # bounded launch. Use the completed route marker/checkpoint instead.
        # Resuming the same verified candidate must not rerun completed routing.
        if {![file exists $route_end] || ![file exists $route_dcp]} {
            launch_runs impl_1 -to_step route_design -jobs $max_threads
            wait_on_run impl_1
        }
        if {![file exists $route_end] || ![file exists $route_dcp] ||
            [file exists [file join $impl_dir .route_design.error.rst]]} {
            error "Routing failed: [get_property STATUS [get_runs impl_1]]"
        }
        open_run impl_1
        phys_opt_design -directive Explore
        report_timing_summary -delay_type min_max -report_unconstrained -file [file join $reports timing_summary.rpt]
        check_timing -verbose -file [file join $reports check_timing.rpt]
        report_utilization -file [file join $reports utilization.rpt]
        report_route_status -file [file join $reports route_status.rpt]
        report_drc -file [file join $reports drc.rpt]
        report_cdc -file [file join $reports cdc.rpt]
        report_clocks -file [file join $reports clocks.rpt]
        report_timing -delay_type max -max_paths 10 -file [file join $reports setup_paths.rpt]
        report_timing -delay_type min -max_paths 10 -file [file join $reports hold_paths.rpt]
        set row {}
        foreach line [split [read_text [file join $reports timing_summary.rpt]] "\n"] {
            set values [regexp -all -inline {\S+} $line]
            if {[llength $values] != 12} {continue}
            set numeric 1
            foreach x $values {if {![string is double -strict $x]} {set numeric 0}}
            if {$numeric} {set row $values; break}
        }
        if {[llength $row] != 12} {error "Cannot parse timing summary"}
        lassign $row wns tns sf st whs ths hf ht wpws tpws pf pt
        set timing_ok [expr {$wns>=0 && $whs>=0 && $wpws>=0 && $sf==0 && $hf==0 && $pf==0 && $st>0 && $ht>0 && $pt>0}]
        foreach {key value} [list setup_ns $wns hold_ns $whs pulse_ns $wpws] {dict set metrics $key $value}
        set checks [read_text [file join $reports check_timing.rpt]]
        foreach name {no_clock constant_clock pulse_width_clock unconstrained_internal_endpoints multiple_clock generated_clocks loops partial_input_delay partial_output_delay latch_loops} {
            if {![regexp [format {checking %s \(([0-9]+)\)} $name] $checks -> count] || $count!=0} {set timing_ok 0}
        }
        set bad_drc 0
        foreach v [get_drc_violations -quiet] {
            if {[get_property SEVERITY $v] in {Error {Critical Warning}}} {incr bad_drc}
        }
        set drc [read_text [file join $reports drc.rpt]]
        if {[regexp {REQP-1839|REQP-1840|PDRC-1(32|34|36|38|40|42|44|46)|CHECK-3} $drc]} {incr bad_drc}
        set route [read_text [file join $reports route_status.rpt]]
        set route_ok 1
        foreach {key pattern} {
            errors {# of nets with routing errors\.+\s*:\s*([0-9]+)}
            routable {# of routable nets\.+\s*:\s*([0-9]+)}
            routed {# of fully routed nets\.+\s*:\s*([0-9]+)}
        } {if {![regexp $pattern $route -> $key]} {set route_ok 0; set $key -1}}
        set route_ok [expr {$route_ok && $errors==0 && $routable>0 && $routed==$routable}]
        dict set metrics drc_blockers $bad_drc
        dict set metrics routing_errors $errors
        dict set metrics fully_routed_nets $routed
        set gate [expr {$timing_ok && $route_ok && $bad_drc==0}]
        dict set metrics implementation_passed [expr {$gate ? "true" : "false"}]
        save_metrics
        write_checkpoint -force [file join $run routed.dcp]
        if {!$gate} {error "Physical signoff failed; reports preserved; no deployable overlay published"}
        if {$EXPORT} {
            puts "PYNQ_STAGE EXPORT"
            set impl_bit [file join [get_property DIRECTORY [get_runs impl_1]] system_wrapper.bit]
            write_bitstream -force $impl_bit
            file copy -force $impl_bit [file join $run k4_accel.bit]
            write_hw_platform -fixed -include_bit -force -file [file join $run k4_accel.xsa]
            dict set metrics passed true
        }
    }
    save_metrics
    exec $PYTHON -E $helper collect $run >@ stdout 2>@ stderr
} reason options]
if {$failed} {
    save_metrics
    catch {exec $PYTHON -E $helper collect $run >@ stdout 2>@ stderr}
    puts stderr "PYNQ_FLOW_FAILED: $reason"
    if {[dict exists $options -errorinfo]} {puts stderr [dict get $options -errorinfo]}
    exit 1
}
puts "PYNQ_FLOW_FINISHED run=$run"
exit
