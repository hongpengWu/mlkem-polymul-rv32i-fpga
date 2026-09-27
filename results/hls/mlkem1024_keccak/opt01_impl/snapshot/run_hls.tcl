# Vitis HLS 2024.2; toggle stages here or with HLS_<NAME> environment variables.
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
set SCRIPT_DIR [file normalize [file dirname [info script]]]
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
set BUILD_ROOT E:/hls
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
set RUN_DIR [file normalize [file join $BUILD_ROOT k4_io$IO_OPT $RUN_ID]]
set PROJ [file join $RUN_DIR p]
set HELPER [file join $SCRIPT_DIR scripts collect_reports.py]
set EXPORT_FLOW none
if {$VIVADO_IMPL} {set EXPORT_FLOW impl} elseif {$VIVADO_SYN} {set EXPORT_FLOW syn}

# Freeze inputs and acquire an exclusive lock; never reset an old/active project.
exec $PYTHON $HELPER prepare --source-dir $SCRIPT_DIR --run-dir $RUN_DIR \
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
