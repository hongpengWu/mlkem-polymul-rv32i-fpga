# Expected-failure check of the official KeyGen byte comparator.
# Only a private copy of the expected fixture is changed; firmware and RTL
# are identical to the successful fast-RV32IM test.
# vivado -mode batch -source scripts/mlkem_baseline/verify_rejection.tcl
set root [file normalize [file join [file dirname [info script]] ../..]]
if {[version -short] ne "2024.2"} {error "Use Vivado 2024.2"}

proc read_all {path} {
    set f [open $path rb]
    set data [read $f]
    close $f
    return $data
}

set expected_source [file join $root tb software mlkem_keygen mlkem512_keygen_expected.mem]
set input_source [file join $root tb software mlkem_keygen mlkem512_keygen_input.mem]
set firmware_source [file join $root firmware images mlkem_keygen rv32im.mem]
set expected_original [read_all $expected_source]
set input_original [read_all $input_source]
set firmware_original [read_all $firmware_source]
set words [regexp -all -inline {\S+} $expected_original]
if {[llength $words] != 617 || [lindex $words 0] ne "3141544b" ||
    [lindex $words 4] ne "00000001" || [lindex $words 8] ne "00000001"} {
    error "Expected the unchanged ML-KEM-512 KeyGen tcId=1 fixture"
}
# Eight header words, one tcId word, then the first little-endian ek word.
scan [lindex $words 9] %x original_word
set bad_word [expr {$original_word ^ 1}]
set original_byte [format %02x [expr {$original_word & 255}]]
set bad_byte [format %02x [expr {$bad_word & 255}]]
lset words 9 [format %08x $bad_word]

# A unique build directory rules out accidentally reading an earlier log.
set project_dir [file join $root build keygen_rejection_[clock seconds]_[pid]]
file mkdir $project_dir
set image [file join $project_dir mlkem_keygen.mem]
file copy $firmware_source $image
set input_copy [file join $project_dir mlkem512_keygen_input.mem]
file copy $input_source $input_copy
set expected_copy [file join $project_dir mlkem512_keygen_expected.mem]
set f [open $expected_copy w]
puts $f [join $words "\n"]
close $f
puts "MLKEM_REJECTION_INJECTION word=9 byte=0 original=$original_byte mutated=$bad_byte project=$project_dir"

create_project mlkem_keygen_rejection $project_dir -part xc7z020clg400-1
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
set_property generic [concat {FIRMWARE_INIT_FILE=mlkem_keygen.mem RAM_ADDR_BITS=14} $parameters] [get_filesets sources_1]
add_files -fileset sim_1 -norecurse [file join $root tb software tb_mlkem_keygen.sv]
foreach path [list $input_copy $expected_copy] {
    add_files -fileset sim_1 -norecurse $path
    set_property file_type {Memory Initialization Files} [get_files $path]
}
set_property top tb_mlkem_keygen [get_filesets sim_1]
set_property generic [concat $parameters EXPECT_M=1] [get_filesets sim_1]
set_property xsim.simulate.runtime all [get_filesets sim_1]
update_compile_order -fileset sources_1
update_compile_order -fileset sim_1
set launch_code [catch {launch_simulation -simset sim_1} launch_message]
catch {close_sim}
set logpath [file join $project_dir mlkem_keygen_rejection.sim sim_1 behav xsim simulate.log]
if {![file exists $logpath]} {error "No simulation log; launch code=$launch_code message=$launch_message"}
set log [read_all $logpath]
set marker "MLKEM_KEYGEN_FAIL byte mismatch tcId=1 event=00000103 byte=0 got=$original_byte expected=$bad_byte"
if {[string first $marker $log] < 0 || [string first "MLKEM_KEYGEN_PASS" $log] >= 0 ||
    [regexp -all -nocase {Fatal:} $log] != 1} {
    error "Negative check did not reject exactly the injected byte; inspect $logpath"
}
foreach {path original} [list $expected_source $expected_original $input_source $input_original $firmware_source $firmware_original] {
    if {[read_all $path] ne $original} {error "Official input changed during rejection check: $path"}
}

set result_dir [file join $root results official_baseline keygen512_tc1 negative_check]
file mkdir $result_dir
file copy -force $logpath [file join $result_dir simulate.log]
set f [open [file join $result_dir mutation.txt] w]
puts $f "operation=ML-KEM-512 KeyGen tcId=1"
puts $f "configuration=CPU_ENABLE_MUL=1 CPU_ENABLE_FAST_MUL=1 CPU_ENABLE_DIV=1 EXPECT_M=1"
puts $f "fixture_word=9"
puts $f "ek_byte=0"
puts $f "original_word=[format %08x $original_word]"
puts $f "mutated_word=[format %08x $bad_word]"
puts $f "expected_rejection=$marker"
puts $f "official_input_expected_and_firmware_unchanged=PASS"
puts $f "result=MLKEM_REJECTION_CHECK_PASS"
close $f
close_project
puts "MLKEM_REJECTION_CHECK_PASS results=$result_dir"
