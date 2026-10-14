# K4 development flow: tclsh mainline/k4/flow.tcl
# AMD-style stage switches. Override any setting with FLOW_<NAME>.
# All repository-relative paths are resolved from this file, not the caller's cwd.
# Tool-only worker modes below are frozen into each run by the Python drivers.
set HLS 0
set CSIM 1
set CSYNTH 1
set COSIM 1
set VIVADO_SYN 0
set VIVADO_IMPL 0
set EXPORT 0
set SMOKE 0
set BUILD_SMOKE 1
set BUILD_KAT 1
set KAT_SUBSET 0
set FULL_KAT 0
set IMPLEMENTATION 0
set BUILD_BOARD 0
set BOARD_SIM 0
set BOARD_IMPL 0
set BOARD_BITSTREAM 0
set COLLECT 0
set CHECK_ONLY 1

set CANDIDATE structure_check
set PYTHON python
set VIVADO ""
set VITIS_HLS ""
set HLS_RUN build/k4/selected_hls
set SHORT_ROOT build/k4
set RESUME_SYNTH ""
set RESUME_BOARD ""
set max_threads 8

set FLOW_FILE [file normalize [info script]]
set MAIN [file dirname $FLOW_FILE]
set ROOT [file normalize [file join $MAIN ../..]]
set SCRIPT_DIR [file join $MAIN scripts]
set CUR_DIR [pwd]
set WORKER ""
if {![info exists argv]} {set argv {}}
if {[info exists ::env(FLOW_WORKER)]} {set WORKER $::env(FLOW_WORKER)}
if {[llength $argv] && [lindex $argv 0] eq "--worker"} {
    if {[llength $argv] < 2} {error "--worker needs hls|smoke|kat|implementation|internal-timing"}
    set WORKER [lindex $argv 1]
    set argv [lrange $argv 2 end]
}
if {$WORKER ni {{} hls smoke kat implementation internal-timing}} {error "Unknown worker: $WORKER"}

# ---- hls worker: frozen and invoked by the corresponding runner ----
if {$WORKER eq "hls"} {
# Vitis HLS 2024.2 worker; switches are forwarded as HLS_<NAME>.
set CSIM 1
set CSYNTH 1
set COSIM 1
set VIVADO_SYN 0
set VIVADO_IMPL 0
set EXPORT 0
set IO_OPT 1

set max_threads 8
set XPART xc7z020-clg400-1
set CLKP 10.0
set SOLN sol1
set TOP mlkem1024_keccak_accel
set HLS_SOURCE [file join $MAIN hls]
if {![file isdirectory [file join $HLS_SOURCE src]]} {set HLS_SOURCE $MAIN}
if {![file isdirectory [file join $HLS_SOURCE src]]} {error "Missing HLS source or frozen snapshot beside flow.tcl"}
set CUR_DIR [pwd]

foreach setting {CSIM CSYNTH COSIM VIVADO_SYN VIVADO_IMPL EXPORT IO_OPT} {
    if {[info exists ::env(HLS_$setting)]} {set $setting $::env(HLS_$setting)}
    if {[set $setting] ni {0 1}} {error "$setting must be 0 or 1"}
}
if {($VIVADO_SYN || $VIVADO_IMPL) && !$EXPORT} {
    error "Set EXPORT=1 to request Vivado synthesis/implementation."
}
if {!$CSIM && !$CSYNTH && !$COSIM && !$EXPORT} {error "No stage selected."}
set PYTHON python
if {[info exists ::env(HLS_PYTHON)]} {set PYTHON $::env(HLS_PYTHON)}
set BUILD_ROOT [file join $ROOT build k4]
if {[info exists ::env(HLS_BUILD_ROOT)]} {set BUILD_ROOT $::env(HLS_BUILD_ROOT)}
set RUN_ID "[clock format [clock seconds] -format %Y%m%d_%H%M%S]_[pid]"
set REUSE 0
if {!$CSYNTH && ($COSIM || $EXPORT)} {
    if {![info exists ::env(HLS_RUN_ID)]} {
        error "CSYNTH=0 with COSIM/EXPORT needs HLS_RUN_ID of a successful matching run."
    }
    set REUSE 1
}
if {[info exists ::env(HLS_RUN_ID)]} {set RUN_ID $::env(HLS_RUN_ID)}
if {![regexp {^[A-Za-z0-9_-]+$} $RUN_ID]} {error "Unsafe HLS_RUN_ID"}
if {[file pathtype $BUILD_ROOT] ne "absolute"} {set BUILD_ROOT [file join $ROOT $BUILD_ROOT]}
set RUN_DIR [file normalize [file join $BUILD_ROOT hls io$IO_OPT $RUN_ID]]
set PROJ [file join $RUN_DIR p]
set HELPER [file join $HLS_SOURCE scripts collect_reports.py]
set EXPORT_FLOW none
if {$VIVADO_IMPL} {set EXPORT_FLOW impl} elseif {$VIVADO_SYN} {set EXPORT_FLOW syn}

# Freeze inputs and acquire an exclusive lock; never reset an old/active project.
exec $PYTHON $HELPER prepare --source-dir $HLS_SOURCE --flow-script $FLOW_FILE --run-dir $RUN_DIR \
    --reuse $REUSE --pid [pid] --io-opt $IO_OPT --part $XPART --clock $CLKP \
    --stages $CSIM $CSYNTH $COSIM $EXPORT --export-flow $EXPORT_FLOW
puts "INFO: K4 HLS run directory: $RUN_DIR"
set SNAPSHOT [file join $RUN_DIR snapshot]
if {[regexp {\s} $SNAPSHOT]} {error "Use a short HLS_BUILD_ROOT without spaces."}
set FLAGS "-I$SNAPSHOT/src -std=c++14 -DKECCAK_IO_OPT=$IO_OPT"
set opened 0
set failed [catch {
    cd $RUN_DIR
    if {[llength [info commands set_param]]} {set_param general.maxThreads $max_threads}
    open_project $PROJ
    set opened 1
    if {!$REUSE} {
        add_files [file join $SNAPSHOT src mlkem1024_keccak_accel.cpp] -cflags $FLAGS
        add_files [file join $SNAPSHOT src mlkem1024_keccak_accel.h] -cflags $FLAGS
        add_files -tb [file join $SNAPSHOT tb tb_mlkem1024_keccak_accel.cpp] -cflags $FLAGS
        set_top $TOP
        open_solution $SOLN -flow_target vivado
        set_part $XPART
        create_clock -period $CLKP -name default
        set_clock_uncertainty 10%
        config_compile -pipeline_loops 0
    } else {
        open_solution $SOLN
    }
    if {$CSIM} {
        exec $PYTHON $HELPER stage --run-dir $RUN_DIR --stage CSIM --status running
        csim_design
        exec $PYTHON $HELPER stage --run-dir $RUN_DIR --stage CSIM --status pass
    }
    if {$CSYNTH} {
        exec $PYTHON $HELPER stage --run-dir $RUN_DIR --stage CSYNTH --status running
        csynth_design
        exec $PYTHON $HELPER stage --run-dir $RUN_DIR --stage CSYNTH --status pass
    }
    if {$COSIM} {
        exec $PYTHON $HELPER stage --run-dir $RUN_DIR --stage COSIM --status running
        cosim_design -rtl verilog -tool xsim
        exec $PYTHON $HELPER stage --run-dir $RUN_DIR --stage COSIM --status pass
    }
    if {$EXPORT} {
        exec $PYTHON $HELPER stage --run-dir $RUN_DIR --stage EXPORT --status running
        export_design -format ip_catalog -rtl verilog -flow $EXPORT_FLOW
        exec $PYTHON $HELPER stage --run-dir $RUN_DIR --stage EXPORT --status pass
    }
    exec $PYTHON $HELPER collect --run-dir $RUN_DIR --strict
} problem options]
if {$opened} {catch {close_project}}
if {$failed} {
    catch {exec $PYTHON $HELPER fail --run-dir $RUN_DIR --message $problem}
    catch {exec $PYTHON $HELPER collect --run-dir $RUN_DIR}
}
catch {exec $PYTHON $HELPER release --run-dir $RUN_DIR --pid [pid]}
cd $CUR_DIR
if {$failed} {return -options $options $problem}
puts "INFO: Requested K4 HLS stages completed; metrics: $RUN_DIR/reports/metrics.json"
exit
    return
}

# ---- smoke worker: frozen and invoked by the corresponding runner ----
if {$WORKER eq "smoke"} {
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
    return
}

# ---- kat worker: frozen and invoked by the corresponding runner ----
if {$WORKER eq "kat"} {
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
    return
}

# ---- implementation worker: frozen and invoked by the corresponding runner ----
if {$WORKER eq "implementation"} {
# Frozen full-system OOC comparison, or standalone PYNQ-Z2 board flow.
# Usage: ... -tclargs run_dir cpu_only|keccak ?resume_synth?
# Board: ... -tclargs run_dir board board_111  (simulation/implementation/bitstream)
if {[version -short] ne "2024.2"} {error "Use Vivado 2024.2"}
if {[llength $argv] ni {2 3}} {error "Expected run_dir variant(cpu_only|keccak|board) ?mode?"}
lassign $argv run variant recovery_mode
if {$variant eq "board"} {
    set board_resume [regexp {^board_resume_([01])$} $recovery_mode -> board_bit]
    if {$board_resume} {
        set board_sim 0
        set board_impl 1
    } elseif {![regexp {^board_([01])([01])([01])$} $recovery_mode -> board_sim board_impl board_bit]} {
        error "Board mode must be board_<simulation><implementation><bitstream>"
    }
    if {$board_bit && !$board_impl} {error "Bitstream requires implementation"}
    if {!$board_sim && !$board_impl} {error "No board stage selected"}
    set run [file normalize $run]
    set snapshot [file join $run snapshot]
    set reports [file join $run reports]
    file mkdir $reports
    set_param general.maxThreads 8
    set part xc7z020clg400-1
    set top mlkem1024_keccak_pynqz2_top
    if {!$board_resume} {
        create_project board [file join $run p] -part $part
        set_property target_language Verilog [current_project]
        set_property simulator_language Mixed [current_project]
        set_property XPM_LIBRARIES {XPM_MEMORY} [current_project]
        foreach pattern {rtl/*.v rtl/*.sv hls/*.v hls/*.dat} {
            foreach f [glob -nocomplain [file join $snapshot $pattern]] {add_files -norecurse $f}
        }
        set firmware [file join $snapshot board.mem]
        if {![file isfile $firmware]} {error "Missing frozen board firmware"}
        add_files -norecurse $firmware
        set_property file_type {Memory Initialization Files} [get_files $firmware]
        set_property top $top [get_filesets sources_1]
        set_property generic {FIRMWARE_INIT_FILE=board.mem} [get_filesets sources_1]
        update_compile_order -fileset sources_1

        # Provide the physical clock to timing-driven synthesis. The full board
        # XDC is applied afterward because its strict reset pin checks need a netlist.
        set synthesis_clock [file join $run synth_clock.xdc]
        set fp [open $synthesis_clock w]
        puts $fp {create_clock -name sys_clk_125mhz -period 8.000 -waveform {0.000 4.000} [get_ports sys_clk]}
        close $fp
        add_files -fileset constrs_1 -norecurse $synthesis_clock
        set_property USED_IN_IMPLEMENTATION false [get_files $synthesis_clock]
    }

    # JSON scalars only; raw reports retain all warnings and diagnostic detail.
    set signoff [dict create scope {PYNQ-Z2 pre-board RTL self-test and physical implementation; no board measurement} \
        status pending passed false simulation_requested [expr {$board_sim ? "true" : "false"}] \
        simulation_passed false simulation_reused [expr {$board_resume ? "true" : "false"}] \
        implementation_requested [expr {$board_impl ? "true" : "false"}] \
        bitstream_requested [expr {$board_bit ? "true" : "false"}] bitstream_written false \
        generated_clock_100mhz false setup_slack_ns null hold_slack_ns null pulse_width_slack_ns null \
        timing_checks_passed false drc_errors null drc_critical_warnings null drc_warnings null \
        drc_rule_counts \{\} async_bram_control_warnings null lut_equation_warnings null \
        drc_rule_limit_warnings null invalid_constraint_messages null critical_tool_warnings null \
        drc_functional_checks_passed false \
        routing_errors null routing_complete false resource_checks_passed false \
        lut null ff null ramb36 null ramb18 null bram36_equivalent null dsp null gate_bitstream false]
    proc board_save_signoff {} {
        set fp [open [file join $::reports board_signoff.json] w]
        puts $fp "\{"
        set entries {}
        dict for {key value} $::signoff {
            if {$key in {scope status}} {set value "\"$value\""}
            lappend entries "  \"$key\": $value"
        }
        puts $fp [join $entries ",\n"]
        puts $fp "\}"
        close $fp
    }
    proc board_read {path} {
        set fp [open $path r]
        set value [read $fp]
        close $fp
        return $value
    }
    proc board_constraint_issues {} {
        # These messages mean a requested exception was rejected, or the XDC
        # contained unsupported Tcl. They are not ordinary advisory warnings.
        set path [file join $::run vivado.log]
        if {![file isfile $path]} {error "Missing Vivado log for constraint validation"}
        return [regexp -all -line {^(WARNING|CRITICAL WARNING): \[(Constraints (18-402|18-513)|Designutils 20-1307)\]} [board_read $path]]
    }
    proc board_critical_issues {} {
        # DRC objects do not include critical synthesis/constraint/placement
        # messages. Count those separately instead of treating zero DRC errors
        # as an all-tool signoff.
        return [regexp -all -line {^CRITICAL WARNING:} [board_read [file join $::run vivado.log]]]
    }
    board_save_signoff
    if {$board_resume} {
        # The Python driver authenticates the prior manifest/result, every
        # frozen input, simulation log and routed DCP. RTL/firmware/TB cannot
        # differ; changes are limited to flow scripts and board constraints.
        if {![file isfile [file join $run board_recovery.json]]} {error "Missing board recovery proof"}
        set log [board_read [file join $run simulate.txt]]
        if {[string first "BOARD_KAT_PASS cases=3 starts=85 resets=1" $log] < 0 ||
            [regexp -nocase {fatal:|ERROR:|BOARD_KAT_FAIL} $log]} {error "Invalid reused board simulation"}
        puts "BOARD_STAGE resume_routed simulation_reused=1"
        open_checkpoint [file join $run source_routed.dcp]
        reset_timing -invalid
        dict set signoff simulation_passed true
    }
    if {$board_sim} {
        puts "BOARD_STAGE simulation threads=[get_param general.maxThreads]"
        add_files -fileset sim_1 -norecurse [file join $snapshot tb tb_mlkem1024_keccak_board.sv]
        foreach name {board_input.mem board_expected.mem} {
            set fixture [file join $snapshot fixtures $name]
            if {![file isfile $fixture]} {error "Missing frozen board fixture $name"}
            add_files -fileset sim_1 -norecurse $fixture
            set_property file_type {Memory Initialization Files} [get_files $fixture]
        }
        set_property top tb_mlkem1024_keccak_board [get_filesets sim_1]
        set_property xsim.simulate.runtime all [get_filesets sim_1]
        set_property xsim.elaborate.debug_level off [get_filesets sim_1]
        update_compile_order -fileset sim_1
        set sim_failed [catch {launch_simulation -simset sim_1} sim_problem]
        catch {close_sim}
        set simlog [file join $run p board.sim sim_1 behav xsim simulate.log]
        set log ""
        if {[file isfile $simlog]} {
            file copy -force $simlog [file join $run simulate.txt]
            set log [board_read $simlog]
        }
        if {$sim_failed || [string first "BOARD_KAT_PASS cases=3 starts=85 resets=1" $log] < 0 ||
            [regexp -nocase {fatal:|ERROR:|BOARD_KAT_FAIL} $log]} {
            dict set signoff status simulation_failed
            board_save_signoff
            error "Board self-test failed: $sim_problem; see simulate.txt"
        }
        dict set signoff simulation_passed true
        dict set signoff status simulation_passed
        dict set signoff passed true
        board_save_signoff
    }
    if {!$board_impl} {
        close_project
        puts "BOARD_FLOW_PASS simulation_only=1"
        exit
    }

    dict set signoff passed false
    dict set signoff status implementation_running
    board_save_signoff
    if {!$board_resume} {
        puts "BOARD_STAGE synthesis threads=[get_param general.maxThreads]"
        synth_design -top $top -part $part -generic {FIRMWARE_INIT_FILE=board.mem}
    }
    # XDC supports constraint commands, not procedural if/error guards.
    # Keep exact endpoint guards here before applying the frozen board XDC.
    if {[llength [get_pins -hier -filter {NAME =~ *reset_sync_reg*/CLR}]] != 4 ||
        [llength [get_pins -hier -filter {REF_PIN_NAME == LOCKED && NAME =~ *clock_manager*/LOCKED}]] != 1} {
        error "Expected four reset synchronizer CLR pins and one MMCM LOCKED pin"
    }
    read_xdc [file join $snapshot system.xdc]
    set invalid_constraints [board_constraint_issues]
    dict set signoff invalid_constraint_messages $invalid_constraints
    set critical_messages [board_critical_issues]
    dict set signoff critical_tool_warnings $critical_messages
    if {$invalid_constraints != 0 || $critical_messages != 0} {
        dict set signoff status constraints_rejected
        board_save_signoff
        error "Board XDC contains rejected or unsupported constraints; see Vivado log"
    }
    set clk100 [get_clocks -quiet -of_objects [get_pins -quiet clock_manager/CLKOUT0]]
    set correct_clock [expr {[llength $clk100] == 1 && abs([get_property PERIOD $clk100] - 10.0) < 0.0001}]
    if {!$correct_clock} {error "Board MMCM output is not constrained to 100 MHz"}
    set_clock_uncertainty 0.100 $clk100
    dict set signoff generated_clock_100mhz true
    if {!$board_resume} {
        report_utilization -file [file join $reports synth_utilization.rpt]
        report_clocks -file [file join $reports synth_clocks.rpt]
        write_xdc -force [file join $reports applied_synth.xdc]
        write_checkpoint -force [file join $run synth.dcp]
        puts "BOARD_STAGE opt"
        opt_design
        puts "BOARD_STAGE place"
        place_design
        puts "BOARD_STAGE phys_opt"
        # Vivado 2024.2 command documentation: explicit optimization options run
        # only the selected passes. Exclude default LUT restructuring/combining,
        # which produced unresolved paired-LUT equation DRCs in the first board run.
        phys_opt_design -fanout_opt -placement_opt -critical_cell_opt -hold_fix
        puts "BOARD_STAGE route"
        route_design
    } else {
        # Recovery changes placement only. The first physical-net retry showed
        # that these PDRCs are implicit FF routethroughs sharing a carry's
        # constant LUT, not logical LUTs that may safely have INIT rewritten.
        puts "BOARD_STAGE repair_implicit_lut_pairs"
        report_drc -file [file join $reports drc_before_recovery.rpt]
        set drc_before [board_read [file join $reports drc_before_recovery.rpt]]
        set pairs [dict create]
        foreach {match letter other site sx sy} [regexp -all -inline \
            {Luts ([ABCD])6LUT and ([ABCD])5LUT in use in site (SLICE_X([0-9]+)Y([0-9]+)) with different equations without A6 pin connected to Global Logic High\.} $drc_before] {
            if {$letter ne $other} {error "Unexpected mixed LUT pair in recovery"}
            dict set pairs "$site/$letter" [list $site $letter $sx $sy]
        }
        if {[dict size $pairs] > 3} {error "Unexpected number of implicit LUT pairs; inspect DRC before recovery"}
        set moves [open [file join $reports recovery_moves.tsv] w]
        puts $moves "cell\tfrom\tto\tclock_region\tinit"
        dict for {key detail} $pairs {
            lassign $detail site letter sx sy
            set b6 [get_bels $site/${letter}6LUT]
            set b5 [get_bels $site/${letter}5LUT]
            if {[llength [get_cells -quiet -of_objects $b6]] ||
                [llength [get_cells -quiet -of_objects $b5]] ||
                [get_property CONFIG.EQN $b6] ne "O6=(A6+~A6)*(0)" ||
                ![regexp {^O5=\(A[1-5]\)$} [get_property CONFIG.EQN $b5]]} {
                error "Recovery only supports diagnosed implicit constant/routethrough pair $key"
            }
            set ff [get_cells -quiet -of_objects [get_bels $site/${letter}FF]]
            if {[llength $ff] != 1 || [get_property REF_NAME $ff] ne "FDRE"} {
                error "Expected one FDRE behind implicit routethrough $key"
            }
            set init [get_property INIT $ff]
            set connected [lsort [get_nets -of_objects $ff]]
            set region [get_clock_regions -of_objects [get_sites $site]]
            if {[llength $region] != 1} {error "Ambiguous clock region for $site"}
            set candidates {}
            foreach free [get_sites -of_objects $region -filter {SITE_TYPE =~ SLICE* && !IS_USED}] {
                if {[get_property NAME $free] eq $site || [llength [get_cells -quiet -of_objects $free]]} {continue}
                if {"PROHIBIT" in [list_property $free] && [get_property PROHIBIT $free]} {continue}
                if {![regexp {^SLICE_X([0-9]+)Y([0-9]+)$} $free -> fx fy]} {continue}
                set target [get_bels -quiet $free/${letter}FF]
                if {[llength $target] != 1 || [get_property IS_USED $target]} {continue}
                lappend candidates [list [expr {abs($fx-$sx)+abs($fy-$sy)}] $free]
            }
            if {![llength $candidates]} {error "No completely unused slice in $region for $ff"}
            set destination [lindex [lindex [lsort -integer -index 0 $candidates] 0] 1]
            puts "BOARD_ECO_MOVE cell=$ff from=$site/${letter}FF to=$destination/${letter}FF"
            place_cell [list $ff $destination/${letter}FF]
            if {[get_property LOC $ff] ne $destination || [get_property INIT $ff] ne $init ||
                [lsort [get_nets -of_objects $ff]] ne $connected} {
                error "FF placement recovery changed logical state/connectivity for $ff"
            }
            puts $moves "$ff\t$site/${letter}FF\t$destination/${letter}FF\t$region\t$init"
            flush $moves
        }
        close $moves
        if {[dict size $pairs]} {
            # Documented -preserve keeps completed routes and repairs only
            # routes affected by the moved FFs. No synthesis or RTL simulation.
            write_checkpoint -force [file join $run recovery_placed.dcp]
            puts "BOARD_STAGE route_preserve"
            route_design -preserve
        } else {
            puts "BOARD_STAGE route_physical_nets"
            route_design -physical_nets
        }
    }

    # Archive diagnostics before writing the large routed checkpoint. No
    # severity downgrades, global reset exceptions or unconstrained IO waivers.
    write_xdc -force [file join $reports applied_routed.xdc]
    report_utilization -file [file join $reports utilization.rpt]
    report_utilization -hierarchical -file [file join $reports utilization_hierarchical.rpt]
    report_timing_summary -delay_type min_max -report_unconstrained -file [file join $reports timing_summary.rpt]
    report_timing -delay_type max -max_paths 10 -file [file join $reports setup_paths.rpt]
    report_timing -delay_type min -max_paths 10 -file [file join $reports hold_paths.rpt]
    check_timing -verbose -file [file join $reports check_timing.rpt]
    report_drc -file [file join $reports drc.rpt]
    report_route_status -file [file join $reports route_status.rpt]
    report_clocks -file [file join $reports clocks.rpt]
    report_io -file [file join $reports io.rpt]
    report_cdc -file [file join $reports cdc.rpt]
    report_exceptions -file [file join $reports exceptions.rpt]

    # The first numeric 12-column row is Design Timing Summary, including
    # pulse width checks. Parse the stable Vivado 2024.2 report format and
    # fail closed if it changes; do not infer pulse width from setup slack.
    set timing_row {}
    foreach line [split [board_read [file join $reports timing_summary.rpt]] "\n"] {
        set fields [regexp -all -inline {\S+} $line]
        if {[llength $fields] != 12} {continue}
        set numeric 1
        foreach field $fields {if {![string is double -strict $field]} {set numeric 0; break}}
        if {$numeric} {set timing_row $fields; break}
    }
    if {[llength $timing_row] != 12} {error "Cannot parse board design timing summary"}
    lassign $timing_row wns tns setup_fail setup_total whs ths hold_fail hold_total wpws tpws pulse_fail pulse_total
    dict set signoff setup_slack_ns $wns
    dict set signoff hold_slack_ns $whs
    dict set signoff pulse_width_slack_ns $wpws
    set timing_ok [expr {$wns >= 0 && $whs >= 0 && $wpws >= 0 &&
        $setup_fail == 0 && $hold_fail == 0 && $pulse_fail == 0 &&
        $setup_total > 0 && $hold_total > 0 && $pulse_total > 0}]
    set checks [board_read [file join $reports check_timing.rpt]]
    foreach name {no_clock constant_clock pulse_width_clock unconstrained_internal_endpoints multiple_clock generated_clocks loops partial_input_delay partial_output_delay latch_loops} {
        if {![regexp [format {checking %s \(([0-9]+)\)} $name] $checks -> count] || $count != 0} {
            set timing_ok 0
        }
    }
    # BTN0 and human LEDs have explicit narrow asynchronous exceptions. Their
    # no-delay notices remain in the report; genuinely missing IO delays fail.
    if {![regexp {There are 0 input ports with no input delay specified\.} $checks] ||
        ![regexp {There are 0 ports with no output delay specified\.} $checks]} {set timing_ok 0}
    dict set signoff timing_checks_passed [expr {$timing_ok ? "true" : "false"}]
    set drc_errors 0
    set drc_critical 0
    set drc_warnings 0
    foreach violation [get_drc_violations -quiet] {
        switch -nocase -- [get_property SEVERITY $violation] {
            Error {incr drc_errors}
            {Critical Warning} {incr drc_critical}
            Warning {incr drc_warnings}
        }
    }
    dict set signoff drc_errors $drc_errors
    dict set signoff drc_critical_warnings $drc_critical
    dict set signoff drc_warnings $drc_warnings
    # Warning severity does not make a functional-risk DRC acceptable. Retain
    # each reported rule/count; CHECK-3 means counts may be truncated. PDRC
    # pair-equation failures are unresolved LUT correctness risks even when
    # write_bitstream would permit them. Do not silently downgrade/waive them.
    set rule_counts [dict create]
    foreach {match rule severity} [regexp -all -inline -line \
        {^([A-Z][A-Z0-9]*-[0-9]+)#[0-9]+ (Error|Critical Warning|Warning)[ \t]*$} \
        [board_read [file join $reports drc.rpt]]] {
        dict incr rule_counts $rule
    }
    set rule_json {}
    set async_bram_warnings 0
    set lut_equation_warnings 0
    set truncated_rules 0
    dict for {rule count} $rule_counts {
        lappend rule_json "\"$rule\": $count"
        if {$rule in {REQP-1839 REQP-1840}} {incr async_bram_warnings $count}
        if {$rule in {PDRC-132 PDRC-134 PDRC-136 PDRC-138 PDRC-140 PDRC-142 PDRC-144 PDRC-146}} {
            incr lut_equation_warnings $count
        }
        if {$rule eq "CHECK-3"} {incr truncated_rules $count}
    }
    dict set signoff drc_rule_counts "\{[join $rule_json {, }]\}"
    dict set signoff async_bram_control_warnings $async_bram_warnings
    dict set signoff lut_equation_warnings $lut_equation_warnings
    dict set signoff drc_rule_limit_warnings $truncated_rules
    set invalid_constraints [board_constraint_issues]
    dict set signoff invalid_constraint_messages $invalid_constraints
    set critical_messages [board_critical_issues]
    dict set signoff critical_tool_warnings $critical_messages
    set functional_drc_ok [expr {$async_bram_warnings == 0 && $lut_equation_warnings == 0 &&
        $truncated_rules == 0 && $invalid_constraints == 0 && $critical_messages == 0}]
    dict set signoff drc_functional_checks_passed [expr {$functional_drc_ok ? "true" : "false"}]
    set routing [board_read [file join $reports route_status.rpt]]
    set routing_ok 1
    foreach {key pattern} {
        route_errors {# of nets with routing errors\.+\s*:\s*([0-9]+)}
        routable {# of routable nets\.+\s*:\s*([0-9]+)}
        routed {# of fully routed nets\.+\s*:\s*([0-9]+)}
    } {
        if {![regexp $pattern $routing -> $key]} {set routing_ok 0; set $key -1}
    }
    set routing_ok [expr {$routing_ok && $route_errors == 0 && $routable > 0 && $routed == $routable}]
    dict set signoff routing_errors $route_errors
    dict set signoff routing_complete [expr {$routing_ok ? "true" : "false"}]
    set lut [llength [get_cells -hier -filter {IS_PRIMITIVE && REF_NAME =~ LUT*}]]
    set ff [llength [get_cells -hier -filter {IS_PRIMITIVE && REF_NAME =~ FD*}]]
    set ramb36 [llength [get_cells -hier -filter {IS_PRIMITIVE && REF_NAME =~ RAMB36*}]]
    set ramb18 [llength [get_cells -hier -filter {IS_PRIMITIVE && REF_NAME =~ RAMB18*}]]
    set dsp [llength [get_cells -hier -filter {IS_PRIMITIVE && REF_NAME =~ DSP48*}]]
    set bram36_equivalent [expr {$ramb36 + 0.5*$ramb18}]
    foreach name {lut ff ramb36 ramb18 bram36_equivalent dsp} {dict set signoff $name [set $name]}
    set resource_ok [expr {$lut > 0 && $lut <= 53200 && $ff > 0 && $ff <= 106400 &&
        $bram36_equivalent >= 32 && $bram36_equivalent <= 140 && $dsp == 4}]
    dict set signoff resource_checks_passed [expr {$resource_ok ? "true" : "false"}]
    set gate [expr {[dict get $signoff simulation_passed] && $timing_ok && $routing_ok &&
        $resource_ok && $drc_errors == 0 && $drc_critical == 0 && $functional_drc_ok}]
    dict set signoff gate_bitstream [expr {$gate ? "true" : "false"}]
    dict set signoff status [expr {$gate ? "routed_checks_passed" : "routed_checks_failed"}]
    board_save_signoff
    puts "BOARD_STAGE routed_checkpoint setup_ns=$wns hold_ns=$whs pulse_ns=$wpws gate=$gate"
    write_checkpoint -force [file join $run routed.dcp]
    if {!$gate} {error "Board signoff gate failed; reports and checkpoint retained"}
    if {$board_bit} {
        puts "BOARD_STAGE bitstream"
        write_bitstream -force [file join $run board.bit]
        if {![file isfile [file join $run board.bit]] || [file size [file join $run board.bit]] == 0} {
            error "Bitstream not produced"
        }
        dict set signoff bitstream_written true
    }
    dict set signoff passed true
    dict set signoff status complete
    board_save_signoff
    close_project
    puts "BOARD_FLOW_PASS setup_ns=$wns hold_ns=$whs pulse_ns=$wpws bitstream=$board_bit"
    exit
}
if {$recovery_mode ni {{} resume_synth}} {error "Invalid recovery mode"}
set run [file normalize $run]
if {$variant ni {cpu_only keccak}} {error "Invalid variant: $variant"}
set snapshot [file join $run snapshot]
set reports [file join $run reports]
file mkdir $reports
set top [expr {$variant eq "cpu_only" ? "cpu_benchmark_system" : "mlkem1024_keccak_system"}]
set part xc7z020clg400-1
set_param general.maxThreads 8
if {$recovery_mode eq "resume_synth"} {
    # Python has verified the original manifest, unchanged design/configuration
    # and copied checkpoint hash. The old run stays immutable.
    puts "SYSTEM_OOC_STAGE variant=$variant stage=resume_synthesis threads=[get_param general.maxThreads]"
    open_checkpoint [file join $run synth.dcp]
    # Top/part/OOC/tool build are verified from dcp.xml before launch; a Vivado
    # current_design object name is not the HDL top module name.
} else {
    create_project -in_memory -part $part
    set_property target_language Verilog [current_project]
    set_property XPM_LIBRARIES {XPM_MEMORY} [current_project]
    set sources [concat [glob -nocomplain [file join $snapshot rtl *.v]] \
                        [glob -nocomplain [file join $snapshot rtl *.sv]]]
    if {[llength $sources] == 0} {error "Missing frozen system RTL"}
    foreach f $sources {
        if {[file extension $f] eq ".sv"} {read_verilog -sv $f} else {read_verilog $f}
    }
    if {$variant eq "keccak"} {
        set hls_files [glob [file join $snapshot hls *.v]]
        foreach f $hls_files {read_verilog $f}
        foreach f [glob [file join $snapshot hls *.dat]] {add_files -norecurse $f}
    }
    set firmware [file join $snapshot firmware.mem]
    set constraints [file join $snapshot system.xdc]
    if {![file exists $firmware] || ![file exists $constraints]} {error "Missing frozen firmware/XDC"}
    add_files -norecurse $firmware
    set_property file_type {Memory Initialization Files} [get_files $firmware]
    read_xdc $constraints
    puts "SYSTEM_OOC_STAGE variant=$variant stage=synthesis threads=[get_param general.maxThreads]"
    synth_design -top $top -part $part -mode out_of_context \
        -generic {FIRMWARE_INIT_FILE=firmware.mem RAM_ADDR_BITS=15 CPU_ENABLE_MUL=1 CPU_ENABLE_FAST_MUL=1 CPU_ENABLE_DIV=1}
}
if {[llength [get_clocks system_clk]] != 1 ||
    abs([get_property PERIOD [get_clocks system_clk]]-10.0)>0.0001 ||
    [get_property HD.CLK_SRC [get_ports clk]] ne "BUFGCTRL_X0Y0"} {
    error "Required OOC clock constraints missing"
}
report_utilization -file [file join $reports synth_utilization.rpt]
report_clocks -file [file join $reports synth_clocks.rpt]
if {$recovery_mode ne "resume_synth"} {write_checkpoint -force [file join $run synth.dcp]}
write_xdc -force [file join $reports applied_synth.xdc]

puts "SYSTEM_OOC_STAGE variant=$variant stage=opt"
opt_design
puts "SYSTEM_OOC_STAGE variant=$variant stage=place"
place_design
puts "SYSTEM_OOC_STAGE variant=$variant stage=phys_opt"
phys_opt_design
puts "SYSTEM_OOC_STAGE variant=$variant stage=route"
route_design
write_xdc -force [file join $reports applied_routed.xdc]

report_utilization -file [file join $reports utilization.rpt]
report_utilization -hierarchical -file [file join $reports utilization_hierarchical.rpt]
report_timing_summary -delay_type min_max -report_unconstrained -file [file join $reports timing_summary.rpt]
report_timing -delay_type max -max_paths 10 -file [file join $reports setup_paths.rpt]
report_timing -delay_type min -max_paths 10 -file [file join $reports hold_paths.rpt]
# Keep internal timing separate from the virtual OOC IO boundary. The raw
# all-path checks below still retain boundary failures; no paths are waived.
set regs [all_registers -clock system_clk]
if {![llength $regs]} {error "No internal clocked registers"}
report_timing -from $regs -to $regs -delay_type max -max_paths 10 -file [file join $reports internal_setup.rpt]
report_timing -from $regs -to $regs -delay_type min -max_paths 10 -file [file join $reports internal_hold.rpt]
set internal_setup [get_timing_paths -from $regs -to $regs -delay_type max -max_paths 1]
set internal_hold [get_timing_paths -from $regs -to $regs -delay_type min -max_paths 1]
if {![llength $internal_setup] || ![llength $internal_hold]} {error "Missing internal timing paths"}
set internal_wns [get_property SLACK [lindex $internal_setup 0]]
set internal_whs [get_property SLACK [lindex $internal_hold 0]]
set internal_met [expr {$internal_wns >= 0 && $internal_whs >= 0 ? "true" : "false"}]
check_timing -verbose -file [file join $reports check_timing.rpt]
report_drc -file [file join $reports drc.rpt]
report_route_status -file [file join $reports route_status.rpt]
report_clocks -file [file join $reports clocks.rpt]

set setup_paths [get_timing_paths -quiet -delay_type max -max_paths 1]
set hold_paths [get_timing_paths -quiet -delay_type min -max_paths 1]
set setup_slack null
set hold_slack null
set timing_met false
if {[llength $setup_paths] && [llength $hold_paths]} {
    set setup_slack [get_property SLACK [lindex $setup_paths 0]]
    set hold_slack [get_property SLACK [lindex $hold_paths 0]]
    if {$setup_slack>=0 && $hold_slack>=0} {set timing_met true}
}
set lut_primitives [llength [get_cells -hier -filter {IS_PRIMITIVE && REF_NAME =~ LUT*}]]
set ff_primitives [llength [get_cells -hier -filter {IS_PRIMITIVE && REF_NAME =~ FD*}]]
set ramb36 [llength [get_cells -hier -filter {IS_PRIMITIVE && REF_NAME =~ RAMB36*}]]
set ramb18 [llength [get_cells -hier -filter {IS_PRIMITIVE && REF_NAME =~ RAMB18*}]]
set dsp [llength [get_cells -hier -filter {IS_PRIMITIVE && REF_NAME =~ DSP48*}]]
set bram36_equiv [expr {$ramb36+0.5*$ramb18}]
set fp [open [file join $reports metrics.json] w]
puts $fp "\{"
puts $fp "  \"scope\": \"Complete system OOC; not board timing or bitstream validation\","
puts $fp "  \"variant\": \"$variant\", \"top\": \"$top\", \"part\": \"$part\","
puts $fp "  \"clock_period_ns\": 10.0, \"clock_uncertainty_ns\": 0.1,"
puts $fp "  \"hd_clk_src\": \"BUFGCTRL_X0Y0\", \"io_min_ns\": 0.0, \"io_max_ns\": 2.0,"
puts $fp "  \"ram_bytes\": 131072, \"cpu_mul\": 1, \"cpu_fast_mul\": 1, \"cpu_div\": 1,"
puts $fp "  \"routed_setup_slack_ns\": $setup_slack, \"routed_hold_slack_ns\": $hold_slack,"
puts $fp "  \"timing_met\": $timing_met,"
puts $fp "  \"register_setup_slack_ns\": $internal_wns, \"register_hold_slack_ns\": $internal_whs,"
puts $fp "  \"internal_timing_met\": $internal_met,"
puts $fp "  \"lut_primitives\": $lut_primitives, \"ff_primitives\": $ff_primitives,"
puts $fp "  \"ramb36_primitives\": $ramb36, \"ramb18_primitives\": $ramb18,"
puts $fp "  \"bram36_equivalent\": $bram36_equiv, \"dsp_primitives\": $dsp,"
puts $fp "  \"resource_count_note\": \"Primitive counts; report_utilization is authoritative for packed LUT and device totals\","
puts $fp "  \"signoff_note\": \"timing_met checks routed worst setup/hold slack only; review DRC, pulse width, unconstrained paths and complete routing separately\""
puts $fp "\}"
close $fp
# Retain timing/resource evidence even if Vivado fails while serializing the
# final checkpoint. A normal exit and both checkpoints are still required by
# the Python runner before it records implementation completion.
puts "SYSTEM_OOC_STAGE variant=$variant stage=routed_checkpoint"
write_checkpoint -force [file join $run routed.dcp]
if {$bram36_equiv<32 || $dsp==0} {error "Expected 128 KiB RAM / fast multiplier missing from physical netlist"}
if {$timing_met ne "true"} {error "Routed setup/hold timing not met; reports retained"}
puts "SYSTEM_OOC_TIMING_MET variant=$variant setup_ns=$setup_slack hold_ns=$hold_slack"
close_project
    return
}

# ---- internal-timing worker: frozen and invoked by the corresponding runner ----
if {$WORKER eq "internal-timing"} {
# Read-only timing audit of already routed complete-system checkpoints.
# Boundary ports lack partition-pin locations: report register-to-register
# timing separately so virtual IO delays cannot be mistaken for board closure.
if {[llength $argv] != 2} {error "Expected group_run_dir analysis_output_dir"}
lassign $argv group output
foreach variant {keccak cpu_only} {
    open_checkpoint [file join $group $variant routed.dcp]
    set dest [file join $output $variant]
    file mkdir $dest
    set regs [all_registers -clock system_clk]
    if {[llength $regs] == 0} {error "No clocked registers"}
    report_timing -from $regs -to $regs -delay_type max -max_paths 10 -file [file join $dest internal_setup.rpt]
    report_timing -from $regs -to $regs -delay_type min -max_paths 10 -file [file join $dest internal_hold.rpt]
    set setup [get_timing_paths -from $regs -to $regs -delay_type max -max_paths 1]
    set hold [get_timing_paths -from $regs -to $regs -delay_type min -max_paths 1]
    if {![llength $setup] || ![llength $hold]} {error "Missing internal paths"}
    set wns [get_property SLACK [lindex $setup 0]]
    set whs [get_property SLACK [lindex $hold 0]]
    set fp [open [file join $dest internal_metrics.json] w]
    puts $fp "\{\"variant\":\"$variant\",\"register_setup_slack_ns\":$wns,\"register_hold_slack_ns\":$whs\}"
    close $fp
    puts "INTERNAL_TIMING variant=$variant setup_ns=$wns hold_ns=$whs"
    close_design
}
    return
}

# ---- Main development dispatcher (ordinary tclsh, no EDA commands here) ----
if {[llength $argv]} {error "Unexpected arguments. Configure stages with FLOW_<NAME> environment variables."}
foreach setting {HLS CSIM CSYNTH COSIM VIVADO_SYN VIVADO_IMPL EXPORT SMOKE BUILD_SMOKE BUILD_KAT KAT_SUBSET FULL_KAT IMPLEMENTATION BUILD_BOARD BOARD_SIM BOARD_IMPL BOARD_BITSTREAM COLLECT CHECK_ONLY} {
    if {[info exists ::env(FLOW_$setting)]} {set $setting $::env(FLOW_$setting)}
    if {[set $setting] ni {0 1}} {error "$setting must be 0 or 1"}
}
foreach setting {CANDIDATE PYTHON VIVADO VITIS_HLS HLS_RUN SHORT_ROOT RESUME_SYNTH RESUME_BOARD} {
    if {[info exists ::env(FLOW_$setting)]} {set $setting $::env(FLOW_$setting)}
}
if {[info exists ::env(FLOW_THREADS)]} {set max_threads $::env(FLOW_THREADS)}
if {![string is integer -strict $max_threads] || $max_threads < 1 || $max_threads > 8} {error "FLOW_THREADS must be 1..8"}
if {![regexp {^[A-Za-z0-9_-]+$} $CANDIDATE]} {error "Unsafe CANDIDATE"}
if {$HLS && ($VIVADO_SYN || $VIVADO_IMPL) && !$EXPORT} {error "Set EXPORT=1 for HLS Vivado synthesis/implementation."}
if {$HLS && !$CSIM && !$CSYNTH && !$COSIM && !$EXPORT} {error "HLS=1 requires at least one HLS stage."}
if {$BOARD_BITSTREAM && !$BOARD_IMPL} {error "BOARD_BITSTREAM requires BOARD_IMPL=1"}
foreach setting {HLS_RUN SHORT_ROOT RESUME_SYNTH RESUME_BOARD} {
    if {[set $setting] ne ""} {
        if {[file pathtype [set $setting]] ne "absolute"} {set $setting [file join $ROOT [set $setting]]}
        set $setting [file normalize [set $setting]]
    }
}
# Python implementation/board helpers use the same selected HLS input even
# when its path was edited only in this file's top configuration.
set ::env(FLOW_HLS_RUN) $HLS_RUN
foreach relative {
    hls/src/mlkem1024_keccak_accel.cpp hls/src/mlkem1024_keccak_accel.h
    hls/tb/tb_mlkem1024_keccak_accel.cpp hls/scripts/collect_reports.py
    rtl/mlkem1024_keccak_system.sv rtl/keccak_mmio_adapter.sv
    firmware/fips202_hw.c firmware/keccak_mmio.c
    tb/tb_mlkem1024_keccak_kat.sv tb/tb_mlkem1024_keccak_cpu_smoke.sv
    scripts/build_smoke.py scripts/build_kat.py scripts/run_smoke.py scripts/run_kat.py
    scripts/implement_system.py scripts/collect_kat.py
} {
    if {![file isfile [file join $MAIN $relative]]} {error "Missing source/helper: $relative"}
}
proc resolve_tool {setting tool_name} {
    if {[set ::$setting] eq ""} {
        set ::$setting [string trim [exec $::PYTHON [file join $::ROOT scripts tool_paths.py] $tool_name]]
    }
    if {![file isfile [set ::$setting]] && ![llength [auto_execok [set ::$setting]]]} {
        error "Cannot find $tool_name; configure FLOW_$setting or PQC_[string toupper $tool_name] / PATH."
    }
}
if {$HLS} {resolve_tool VITIS_HLS vitis_hls}
if {$SMOKE || $KAT_SUBSET || $FULL_KAT || $IMPLEMENTATION || $BOARD_SIM || $BOARD_IMPL} {resolve_tool VIVADO vivado}
set RESULTS_DIR [file join $ROOT results k4 candidates $CANDIDATE kat]
set BUILD_DIR [file join $SHORT_ROOT candidates $CANDIDATE]
set RUN_ROOT [file join $SHORT_ROOT kat $CANDIDATE]
proc run_stage {name command} {
    puts "FLOW_STAGE $name: $command"
    flush stdout
    if {!$::CHECK_ONLY} {exec {*}$command >@ stdout 2>@ stderr}
}
set failed [catch {
    cd $ROOT
    if {$HLS || $SMOKE || $KAT_SUBSET || $FULL_KAT || $IMPLEMENTATION || $BOARD_SIM || $BOARD_IMPL} {
        run_stage TOOL_GUARD [list $PYTHON -c {import sys; sys.path.insert(0, 'mainline/k4/scripts'); from run_kat import tool_guard; tool_guard()}]
    }
    if {$HLS} {
        foreach setting {CSIM CSYNTH COSIM VIVADO_SYN VIVADO_IMPL EXPORT} {set ::env(HLS_$setting) [set $setting]}
        set ::env(HLS_PYTHON) $PYTHON
        set ::env(HLS_BUILD_ROOT) $SHORT_ROOT
        puts "FLOW_HLS_SELECTION $HLS_RUN; explicitly select a newly validated HLS run before CPU integration."
        # Vitis HLS parses CLI options itself and rejects Vivado's --worker
        # argument syntax. Select its worker through the process environment.
        set ::env(FLOW_WORKER) hls
        set hls_failed [catch {run_stage HLS [list $VITIS_HLS -f $FLOW_FILE]} hls_problem hls_options]
        unset ::env(FLOW_WORKER)
        if {$hls_failed} {return -options $hls_options $hls_problem}
    }
    if {$SMOKE} {
        if {$BUILD_SMOKE} {run_stage BUILD_SMOKE [list $PYTHON [file join $SCRIPT_DIR build_smoke.py]]}
        run_stage SMOKE [list $PYTHON [file join $SCRIPT_DIR run_smoke.py] --hls-run $HLS_RUN --vivado $VIVADO --run-root [file join $SHORT_ROOT smoke $CANDIDATE] --evidence-dir [file join $ROOT results k4 candidates $CANDIDATE smoke]]
    }
    if {$BUILD_KAT && ($KAT_SUBSET || $FULL_KAT || $IMPLEMENTATION)} {
        run_stage BUILD_KAT [list $PYTHON [file join $SCRIPT_DIR build_kat.py]]
    }
    if {$KAT_SUBSET || $FULL_KAT} {
        set command [list $PYTHON [file join $SCRIPT_DIR run_kat.py] --hls-run $HLS_RUN --vivado $VIVADO --threads $max_threads --results-dir $RESULTS_DIR --build-dir $BUILD_DIR --run-root $RUN_ROOT]
        if {$FULL_KAT} {lappend command --remaining}
        run_stage KAT $command
    }
    if {$COLLECT && !$FULL_KAT} {
        run_stage COLLECT [list $PYTHON [file join $SCRIPT_DIR collect_kat.py] --results-dir $RESULTS_DIR --partial --write]
    }
    if {$IMPLEMENTATION} {
        set command [list $PYTHON [file join $SCRIPT_DIR implement_system.py] --keccak-source current --variants keccak --vivado $VIVADO --run-root [file join $SHORT_ROOT implementation]]
        if {$RESUME_SYNTH ne ""} {lappend command --resume-synth $RESUME_SYNTH}
        run_stage IMPLEMENTATION $command
    }
    if {$BUILD_BOARD} {run_stage BUILD_BOARD [list $PYTHON [file join $SCRIPT_DIR build_kat.py] --board]}
    if {$BOARD_SIM || $BOARD_IMPL} {
        set command [list $PYTHON [file join $SCRIPT_DIR implement_system.py] --variants board --vivado $VIVADO --run-root [file join $SHORT_ROOT board]]
        if {$BOARD_SIM} {lappend command --board-sim}
        if {$BOARD_IMPL} {lappend command --board-impl}
        if {$BOARD_BITSTREAM} {lappend command --bitstream}
        if {$RESUME_BOARD ne ""} {lappend command --resume-board $RESUME_BOARD}
        run_stage BOARD $command
    }
} problem options]
cd $CUR_DIR
if {$failed} {
    puts stderr "FLOW_FAILED: $problem"
    if {[dict exists $options -errorinfo]} {puts stderr [dict get $options -errorinfo]}
    exit 1
}
if {$CHECK_ONLY} {
    puts "FLOW_CHECK_ONLY: source/helper paths verified; requested commands listed; no EDA process launched."
} else {
    puts "FLOW_FINISHED: requested stages returned; inspect their evidence status."
}
