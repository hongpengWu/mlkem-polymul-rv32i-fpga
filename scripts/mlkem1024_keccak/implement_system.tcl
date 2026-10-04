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
