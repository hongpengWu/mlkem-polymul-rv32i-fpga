# Full-system resource/timing comparison using frozen inputs only.
# Usage: vivado -mode batch -source implement_system.tcl -tclargs run_dir cpu_only|keccak ?resume_synth?
if {[version -short] ne "2024.2"} {error "Use Vivado 2024.2"}
if {[llength $argv] ni {2 3}} {error "Expected run_dir variant(cpu_only|keccak) ?resume_synth?"}
lassign $argv run variant recovery_mode
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
