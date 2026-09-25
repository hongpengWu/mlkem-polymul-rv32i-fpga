# Reproduce one expected-failure check without changing official fixtures.
# vivado -mode batch -source scripts/mlkem512_suite/verify_rejection.tcl
set root [file normalize [file join [file dirname [info script]] ../..]]
if {[version -short] ne "2024.2"} {error "Use Vivado 2024.2"}

proc read_all {path} {
    set f [open $path rb]
    set data [read $f]
    close $f
    return $data
}

set expected_source [file join $root tb software mlkem512_suite mlkem512_expected.mem]
set input_source [file join $root tb software mlkem512_suite mlkem512_input.mem]
set firmware_source [file join $root firmware images mlkem512_suite rv32im.mem]
set originals [dict create]
foreach path [list $expected_source $input_source $firmware_source \
    [file join $root rtl cpu picorv32.v] \
    [file join $root rtl benchmark cpu_benchmark_system.v] \
    [file join $root tb software tb_mlkem512_suite.sv]] {
    dict set originals $path [read_all $path]
}
set words [regexp -all -inline {\S+} [dict get $originals $expected_source]]
scan [lindex $words 4] %x declared_words
if {[llength $words] != $declared_words || [lindex $words 0] ne "3254414b" ||
    [lindex $words 3] ne "00000091" || [lindex $words 8] ne "00000000" ||
    [lindex $words 12] ne "00000001" || [lindex $words 13] ne "00000001"} {
    error "Expected the unchanged 145-case suite beginning with KeyGen tcId=1"
}
# Eight header words plus twelve metadata words precede the first ek word.
scan [lindex $words 20] %x original_word
set bad_word [expr {$original_word ^ 1}]
set original_byte [format %02x [expr {$original_word & 255}]]
set bad_byte [format %02x [expr {$bad_word & 255}]]
lset words 20 [format %08x $bad_word]

# A fresh build directory prevents acceptance of a stale rejection log.
set project_dir [file join $root build mlkem512_rejection_[clock seconds]_[pid]]
file mkdir $project_dir
set image [file join $project_dir mlkem512.mem]
set input_copy [file join $project_dir mlkem512_input.mem]
set expected_copy [file join $project_dir mlkem512_expected.mem]
file copy $firmware_source $image
file copy $input_source $input_copy
set f [open $expected_copy w]
puts $f [join $words "\n"]
close $f
puts "MLKEM512_REJECTION_INJECTION word=20 byte=0 original=$original_byte mutated=$bad_byte project=$project_dir"

create_project mlkem512_rejection $project_dir -part xc7z020clg400-1
set_property target_language Verilog [current_project]
set_property simulator_language Mixed [current_project]
set_property XPM_LIBRARIES {XPM_MEMORY} [current_project]
foreach path {rtl/cpu/picorv32.v rtl/benchmark/cpu_benchmark_system.v} {
    add_files -norecurse [file join $root $path]
}
add_files -norecurse $image
set_property file_type {Memory Initialization Files} [get_files $image]
set parameters {CPU_ENABLE_MUL=1 CPU_ENABLE_FAST_MUL=1 CPU_ENABLE_DIV=1}
set_property top cpu_benchmark_system [get_filesets sources_1]
set_property generic [concat {FIRMWARE_INIT_FILE=mlkem512.mem RAM_ADDR_BITS=14} $parameters] [get_filesets sources_1]
add_files -fileset sim_1 -norecurse [file join $root tb software tb_mlkem512_suite.sv]
foreach path [list $input_copy $expected_copy] {
    add_files -fileset sim_1 -norecurse $path
    set_property file_type {Memory Initialization Files} [get_files $path]
}
set_property top tb_mlkem512_suite [get_filesets sim_1]
set_property generic [concat $parameters EXPECT_M=1] [get_filesets sim_1]
set_property xsim.elaborate.debug_level off [get_filesets sim_1]
set_property xsim.simulate.custom_tcl [file join $root scripts mlkem512_suite sim.tcl] [get_filesets sim_1]
set_property xsim.simulate.runtime all [get_filesets sim_1]
update_compile_order -fileset sources_1
update_compile_order -fileset sim_1
set launch_code [catch {launch_simulation -simset sim_1} launch_message]
catch {close_sim}
set logpath [file join $project_dir mlkem512_rejection.sim sim_1 behav xsim simulate.log]
if {![file exists $logpath]} {error "No simulation log; launch code=$launch_code message=$launch_message"}
set log [read_all $logpath]
set marker "MLKEM512_FAIL byte mismatch case=0 output=1 byte=0 got=$original_byte expected=$bad_byte"
if {[string first $marker $log] < 0 || [string first "MLKEM512_PASS" $log] >= 0 ||
    [regexp -all -nocase {Fatal:} $log] != 1} {
    error "Negative check did not reject exactly the injected byte; inspect $logpath"
}
dict for {path original} $originals {
    if {[read_all $path] ne $original} {error "Original input/source changed during rejection check: $path"}
}
set result_dir [file join $root results official_baseline mlkem512 negative_check]
file mkdir $result_dir
file copy -force $logpath [file join $result_dir simulate.log]
set f [open [file join $result_dir mutation.txt] w]
puts $f "operation=ML-KEM-512 KeyGen case_index=0 tcId=1"
puts $f "configuration=CPU_ENABLE_MUL=1 CPU_ENABLE_FAST_MUL=1 CPU_ENABLE_DIV=1 EXPECT_M=1"
puts $f "fixture_word=20"
puts $f "ek_byte=0"
puts $f "original_word=[format %08x $original_word]"
puts $f "mutated_word=[format %08x $bad_word]"
puts $f "expected_rejection=$marker"
puts $f "official_fixtures_firmware_RTL_TB_unchanged=PASS"
puts $f "result=MLKEM512_REJECTION_CHECK_PASS"
close $f
close_project
puts "MLKEM512_REJECTION_CHECK_PASS results=$result_dir"
