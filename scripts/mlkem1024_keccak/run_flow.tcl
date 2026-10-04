# One development entry point: tclsh scripts/mlkem1024_keccak/run_flow.tcl
# Edit switches here, or override with FLOW_<NAME> environment variables.
# Development uses 3 official cases; enable FULL_KAT only for final acceptance.
set HLS 0
set CSIM 1
set CSYNTH 1
set COSIM 1
set VIVADO_SYN 0
set VIVADO_IMPL 0
set EXPORT 0
set SMOKE 0
set BUILD_SMOKE 1
set KAT_SUBSET 1
set FULL_KAT 0
set IMPLEMENTATION 0
set COLLECT 1
set CHECK_ONLY 0

set CANDIDATE timing_decode_v3
set PYTHON python
set VIVADO E:/Xilinx/Vivado/2024.2/bin/vivado.bat
set VITIS_HLS E:/Xilinx/Vitis_HLS/2024.2/bin/vitis_hls.bat
set HLS_RUN E:/hls/k4_io1/opt02
set SHORT_ROOT E:/hls
set RESUME_SYNTH ""
set max_threads 8

set SCRIPT_DIR [file normalize [file dirname [info script]]]
set ROOT [file normalize [file join $SCRIPT_DIR ../..]]
set CUR_DIR [pwd]
foreach setting {HLS CSIM CSYNTH COSIM VIVADO_SYN VIVADO_IMPL EXPORT SMOKE BUILD_SMOKE KAT_SUBSET FULL_KAT IMPLEMENTATION COLLECT CHECK_ONLY} {
    if {[info exists ::env(FLOW_$setting)]} {set $setting $::env(FLOW_$setting)}
    if {[set $setting] ni {0 1}} {error "$setting must be 0 or 1"}
}
if {$HLS && ($VIVADO_SYN || $VIVADO_IMPL) && !$EXPORT} {
    error "Set EXPORT=1 for HLS Vivado synthesis/implementation."
}
if {$HLS && !$CSIM && !$CSYNTH && !$COSIM && !$EXPORT} {
    error "HLS=1 requires at least one HLS stage."
}
foreach setting {CANDIDATE PYTHON VIVADO VITIS_HLS HLS_RUN SHORT_ROOT RESUME_SYNTH} {
    if {[info exists ::env(FLOW_$setting)]} {set $setting $::env(FLOW_$setting)}
}
if {![regexp {^[A-Za-z0-9_-]+$} $CANDIDATE]} {error "Unsafe CANDIDATE"}
if {![string is integer -strict $max_threads] || $max_threads < 1 || $max_threads > 8} {
    error "max_threads must be 1..8"
}
set RESULTS_DIR [file join $ROOT results keccak_cpu candidates $CANDIDATE kat]
set BUILD_DIR [file join $ROOT build keccak_cpu candidates $CANDIDATE]
set RUN_ROOT [file join $SHORT_ROOT k4kat_$CANDIDATE]

proc run_stage {name command} {
    puts "FLOW_STAGE $name: $command"
    flush stdout
    if {!$::CHECK_ONLY} {exec {*}$command >@ stdout 2>@ stderr}
}

set failed [catch {
    cd $ROOT
    if {$HLS || $SMOKE || $KAT_SUBSET || $FULL_KAT || $IMPLEMENTATION} {
        run_stage TOOL_GUARD [list $PYTHON -c \
            {import sys; sys.path.insert(0, 'scripts/mlkem1024_keccak'); from run_kat import tool_guard; tool_guard()}]
    }
    if {$HLS} {
        foreach setting {CSIM CSYNTH COSIM VIVADO_SYN VIVADO_IMPL EXPORT} {
            set ::env(HLS_$setting) [set $setting]
        }
        set ::env(HLS_PYTHON) $PYTHON
        set ::env(HLS_BUILD_ROOT) $SHORT_ROOT
        puts "FLOW_HLS_OPTIONS CSIM=$CSIM CSYNTH=$CSYNTH COSIM=$COSIM VIVADO_SYN=$VIVADO_SYN VIVADO_IMPL=$VIVADO_IMPL EXPORT=$EXPORT"
        # New HLS runs require verification/selection before CPU integration;
        # HLS_RUN keeps selecting the explicitly configured verified RTL.
        puts "FLOW_HLS_SELECTION remains $HLS_RUN; new HLS output is not automatically selected."
        run_stage HLS [list $VITIS_HLS -f [file join $ROOT hls mlkem1024_keccak run_hls.tcl]]
    }
    if {$SMOKE} {
        # Preparation is enabled by default when SMOKE=1. Disable only when
        # intentionally reusing a matching build; run_smoke still checks hashes.
        if {$BUILD_SMOKE} {
            run_stage BUILD_SMOKE [list $PYTHON [file join $SCRIPT_DIR build_smoke.py]]
        }
        run_stage SMOKE [list $PYTHON [file join $SCRIPT_DIR run_smoke.py] \
            --hls-run $HLS_RUN --vivado $VIVADO --run-root [file join $SHORT_ROOT k4cpu_$CANDIDATE]]
    }
    if {$KAT_SUBSET || $FULL_KAT} {
        set command [list $PYTHON [file join $SCRIPT_DIR run_kat.py] \
            --hls-run $HLS_RUN --vivado $VIVADO --threads $max_threads \
            --results-dir $RESULTS_DIR --build-dir $BUILD_DIR --run-root $RUN_ROOT]
        if {$FULL_KAT} {lappend command --remaining}
        run_stage KAT $command
    }
    if {$COLLECT && !$FULL_KAT} {
        # Full KAT already performs strict collection inside its scheduler.
        # Subsets retain PARTIAL status and never claim 145/145 coverage.
        run_stage COLLECT [list $PYTHON [file join $SCRIPT_DIR collect_kat.py] \
            --results-dir $RESULTS_DIR --partial --write]
    }
    if {$IMPLEMENTATION} {
        # Freeze current candidate RTL; never rerun the frozen CPU-only baseline.
        # The implementation runner archives reports as part of this stage.
        set command [list $PYTHON [file join $SCRIPT_DIR implement_system.py] \
            --keccak-source current --variants keccak --vivado $VIVADO \
            --run-root [file join $SHORT_ROOT k4sys]]
        if {$RESUME_SYNTH ne ""} {lappend command --resume-synth $RESUME_SYNTH}
        run_stage IMPLEMENTATION $command
    }
} problem options]
cd $CUR_DIR
if {$failed} {
    puts stderr "FLOW_FAILED: $problem"
    exit 1
}
if {$CHECK_ONLY} {
    puts "FLOW_CHECK_ONLY: commands checked; no process launched or evidence modified."
} else {
    puts "FLOW_FINISHED: requested stages returned; inspect KAT/implementation result status."
}
