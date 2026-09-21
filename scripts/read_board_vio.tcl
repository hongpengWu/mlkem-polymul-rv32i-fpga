# Run in the GUI Tcl Console after programming the matching BIT and LTX.
# This script only reads probes. It never programs, resets, or drives the board.
set root [file normalize [file join [file dirname [info script]] ..]]
set vios [get_hw_vios -quiet]
if {[llength $vios] != 1} {error "Expected exactly one VIO. Connect the board and load this project's BIT and LTX first."}
set vio [lindex $vios 0]
set probes [get_hw_probes -of_objects $vio]
if {[llength $probes] != 14} {error "Expected 12 word probes plus done and trap; check the matching LTX file."}
refresh_hw_vio $vio
set dir [file join $root build hardware]
file mkdir $dir
set path [file join $dir snapshot_[clock format [clock seconds] -format %Y%m%d_%H%M%S]_[clock clicks].txt]
set f [open $path {WRONLY CREAT EXCL}]
puts $f "timestamp=[clock format [clock seconds] -format {%Y-%m-%d %H:%M:%S %Z}]"
puts $f "device=[current_hw_device]"
puts $f "vio=$vio"
puts $f "program_file=[get_property PROGRAM.FILE [current_hw_device]]"
puts $f "probes_file=[get_property PROBES.FILE [current_hw_device]]"
foreach p $probes {
  set line "[get_property NAME $p]\t[get_property INPUT_VALUE $p]"
  puts $f $line
  puts $line
}
close $f
puts "BOARD_VIO_SNAPSHOT=$path"
puts "Raw probe values saved. Check status/detail/trap and the documented radix before interpreting counts."
