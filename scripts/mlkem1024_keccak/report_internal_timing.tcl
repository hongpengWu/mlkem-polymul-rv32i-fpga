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
