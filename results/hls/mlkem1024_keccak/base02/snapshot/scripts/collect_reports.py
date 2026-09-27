#!/usr/bin/env python3
"""Freeze HLS inputs and collect evidence without calling estimates measurements.

Used by run_hls.tcl. Standalone: python collect_reports.py collect --run-dir RUN.
Generated state, source snapshots and reports remain in the external build dir.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
import xml.etree.ElementTree as ET

TOP = "mlkem1024_keccak_accel"
STAGES = ("CSIM", "CSYNTH", "COSIM", "EXPORT")


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, data):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def report_paths(run):
    sol = run / "p" / "sol1"
    return {
        "CSIM": sol / "csim" / "report" / f"{TOP}_csim.log",
        "CSYNTH": sol / "syn" / "report" / f"{TOP}_csynth.xml",
        "COSIM": sol / "sim" / "report" / f"{TOP}_cosim.rpt",
    }


def parse_number(value):
    if value is None:
        return None
    text = value.strip().replace(",", "")
    if re.fullmatch(r"[-+]?\d+", text):
        return int(text)
    if re.fullmatch(r"[-+]?(?:\d+\.\d*|\d*\.\d+)", text):
        return float(text)
    return None


def synthesis_metrics(path):
    if not path.is_file():
        raise ValueError(f"Missing synthesis XML: {path}")
    root = ET.parse(path).getroot()
    def value(xpath):
        return root.findtext(xpath)
    perf = "PerformanceEstimates/"
    latency = perf + "SummaryOfOverallLatency/"
    timing = perf + "SummaryOfTimingAnalysis/"
    resources = root.find("AreaEstimates/Resources")
    available = root.find("AreaEstimates/AvailableResources")
    return {
        "tool_version": value("ReportVersion/Version"),
        "part": value("UserAssignments/Part"),
        "top": value("UserAssignments/TopModelName"),
        "configured_clock_ns": parse_number(value("UserAssignments/TargetClockPeriod")),
        "clock_uncertainty_ns": parse_number(value("UserAssignments/ClockUncertainty")),
        "estimated_clock_ns": parse_number(value(timing + "EstimatedClockPeriod")),
        "estimated_latency_cycles": {
            "min": parse_number(value(latency + "Best-caseLatency")),
            "avg": parse_number(value(latency + "Average-caseLatency")),
            "max": parse_number(value(latency + "Worst-caseLatency")),
        },
        "estimated_interval_cycles": {
            "min": parse_number(value(latency + "Interval-min")),
            "max": parse_number(value(latency + "Interval-max")),
        },
        "resources": {n.tag: parse_number(n.text) for n in resources} if resources is not None else {},
        "available_resources": {n.tag: parse_number(n.text) for n in available} if available is not None else {},
    }


def cosim_metrics(path):
    if not path.is_file():
        raise ValueError(f"Missing co-simulation report: {path}")
    text = path.read_text(encoding="utf-8", errors="replace")
    rows = []
    for line in text.splitlines():
        cells = [v.strip() for v in line.strip().strip("|").split("|")]
        if len(cells) >= 8 and cells[0].lower() == "verilog":
            rows.append((cells, line))
    if len(rows) != 1:
        raise ValueError("Expected exactly one Verilog co-simulation summary row")
    cells, raw = rows[0]
    cycles = [parse_number(x) for x in cells[2:]]
    total = cycles[6] if len(cycles) >= 7 else None
    # Never substitute synthesis worst-case latency for co-simulation totals.
    explicit = re.search(r"Total\s*Execution\s*\(\s*cycles\s*\)\s*[:=]\s*([\d,]+)", text, re.I)
    if explicit:
        total = parse_number(explicit.group(1))
    return {
        "rtl": cells[0], "status": cells[1],
        "measured_latency_cycles": dict(zip(("min", "avg", "max"), cycles[:3])),
        "measured_interval_cycles": dict(zip(("min", "avg", "max"), cycles[3:6])),
        "total_execution_cycles": total,
        "report_row": raw.strip(),
    }


def validate_synthesis(path, config):
    metrics = synthesis_metrics(path)
    expected = {"tool_version": "2024.2", "part": config["part"], "top": TOP,
                "configured_clock_ns": config["clock_ns"]}
    for name, value in expected.items():
        if metrics[name] != value:
            raise ValueError(f"Synthesis {name}: {metrics[name]!r}, expected {value!r}")
    return metrics


def input_hashes(source):
    paths = sorted(p for folder in ("src", "tb") for p in (source / folder).rglob("*") if p.is_file())
    if not paths:
        raise ValueError("No kernel/testbench inputs")
    return {p.relative_to(source).as_posix(): sha(p) for p in paths}


def check_snapshot(run, manifest):
    for name, digest in manifest["input_sha256"].items():
        path = run / "snapshot" / name
        if not path.is_file() or sha(path) != digest:
            raise ValueError(f"Frozen input mismatch: {name}")


def verify_report(run, stage, entry):
    if entry.get("status") != "pass":
        raise ValueError(f"{stage} has no successful command evidence")
    for name, digest in entry.get("report_sha256", {}).items():
        path = run / name
        if not path.is_file() or sha(path) != digest:
            raise ValueError(f"{stage} report changed: {name}")


def prepare(args):
    source, run = args.source_dir.resolve(), args.run_dir.resolve()
    if len(str(run).encode("utf-8")) > 100:
        raise ValueError("Build path too long; use a shorter HLS_BUILD_ROOT / HLS_RUN_ID")
    hashes = input_hashes(source)
    config = {"io_opt": args.io_opt, "part": args.part, "clock_ns": args.clock,
              "clock_uncertainty": "10%", "pipeline_loops": 0,
              "partition_state": True, "language": "c++14", "top": TOP}
    if args.reuse:
        manifest = read_json(run / "manifest.json")
        if manifest["config"] != config or manifest["input_sha256"] != hashes:
            raise ValueError("Stale run: source/testbench/config differs. Run CSYNTH=1 with a new HLS_RUN_ID.")
        check_snapshot(run, manifest)
        state = read_json(run / "state.json")
        verify_report(run, "CSYNTH", state["stage_evidence"].get("CSYNTH", {}))
        validate_synthesis(report_paths(run)["CSYNTH"], config)
    else:
        if run.exists():
            raise ValueError("Run directory already exists; choose a new HLS_RUN_ID (never reset old runs).")
        run.mkdir(parents=True)
        manifest = {"schema": 1, "created_utc": now(), "source_dir": str(source),
                    "config": config, "input_sha256": hashes,
                    "informational_script_sha256": {name: sha(source / name) for name in
                        ("run_hls.tcl", "scripts/collect_reports.py")}}
        for name in list(hashes) + ["run_hls.tcl", "scripts/collect_reports.py"]:
            dest = run / "snapshot" / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source / name, dest)
        check_snapshot(run, manifest)
        write_json(run / "manifest.json", manifest)
        state = {"stage_evidence": {}, "attempts": []}
    # Never remove an existing lock automatically: it may own a live HLS process.
    lock = run / ".running.lock"
    with lock.open("x", encoding="utf-8") as stream:
        json.dump({"pid": args.pid, "started_utc": now()}, stream)
    try:
        attempt = {"started_utc": now(), "pid": args.pid, "reuse": bool(args.reuse),
                   "requested": dict(zip(STAGES, (bool(v) for v in args.stages))),
                   "stages": {key: "pending" if v else "skipped" for key, v in zip(STAGES, args.stages)},
                   "export_flow": args.export_flow}
        state["attempts"].append(attempt)
        write_json(run / "state.json", state)
    except Exception:
        lock.unlink()
        raise


def stage(args):
    run = args.run_dir.resolve()
    manifest, state = read_json(run / "manifest.json"), read_json(run / "state.json")
    attempt = state["attempts"][-1]
    if not attempt["requested"].get(args.stage):
        raise ValueError(f"Stage {args.stage} was not selected")
    if args.status == "running":
        state["stage_evidence"].pop(args.stage, None)
        attempt["stages"][args.stage] = "running"
    else:
        check_snapshot(run, manifest)
        paths = report_paths(run)
        if args.stage == "CSYNTH":
            validate_synthesis(paths[args.stage], manifest["config"])
        elif args.stage == "COSIM":
            result = cosim_metrics(paths[args.stage])
            if result["status"].lower() != "pass":
                raise ValueError(f"Co-simulation not Pass: {result['status']}")
            if any(v is None for v in result["measured_latency_cycles"].values()):
                raise ValueError("Co-simulation has missing measured latency")
        if args.stage in paths and not paths[args.stage].is_file():
            raise ValueError(f"Missing {args.stage} report: {paths[args.stage]}")
        evidence = {"status": "pass", "completed_utc": now(), "command_returned_success": True,
                    "report_sha256": {}}
        if args.stage in paths:
            p = paths[args.stage]
            evidence["report_sha256"][p.relative_to(run).as_posix()] = sha(p)
        if args.stage == "EXPORT":
            evidence["flow"] = attempt["export_flow"]
            artifacts = list((run / "p" / "sol1" / "impl" / "ip").glob("*.zip"))
            if not artifacts:
                raise ValueError("export_design returned but no packaged IP zip exists")
            evidence["report_sha256"].update({p.relative_to(run).as_posix(): sha(p) for p in artifacts})
        state["stage_evidence"][args.stage] = evidence
        attempt["stages"][args.stage] = "pass"
    write_json(run / "state.json", state)


def collect(args):
    run = args.run_dir.resolve()
    manifest, state = read_json(run / "manifest.json"), read_json(run / "state.json")
    attempt, errors = state["attempts"][-1], []
    out = {"schema": 1, "collected_utc": now(), "run_dir": str(run),
           "input_sha256": manifest["input_sha256"], "configuration": manifest["config"],
           "current_attempt": attempt, "stage_evidence": state["stage_evidence"],
           "synthesis_estimates": None, "cosimulation_measurements": None}
    try:
        check_snapshot(run, manifest)
        for key, entry in state["stage_evidence"].items():
            verify_report(run, key, entry)
        if "CSYNTH" in state["stage_evidence"]:
            out["synthesis_estimates"] = validate_synthesis(report_paths(run)["CSYNTH"], manifest["config"])
        if "COSIM" in state["stage_evidence"]:
            out["cosimulation_measurements"] = cosim_metrics(report_paths(run)["COSIM"])
    except (ValueError, OSError, ET.ParseError) as error:
        errors.append(str(error))
    for key, requested in attempt["requested"].items():
        if requested and attempt["stages"][key] != "pass":
            errors.append(f"Requested stage {key}: {attempt['stages'][key]}")
    out["requested_stages_passed"] = not errors and any(attempt["requested"].values())
    out["functional_hls_flow_passed"] = not errors and all(
        state["stage_evidence"].get(k, {}).get("status") == "pass" for k in ("CSIM", "CSYNTH", "COSIM"))
    out["errors"] = errors
    synth, cosim = out["synthesis_estimates"], out["cosimulation_measurements"]
    if cosim:
        total, period = cosim["total_execution_cycles"], manifest["config"]["clock_ns"]
        cosim["total_time_at_configured_clock_ns"] = total * period if total is not None else None
        estimated = synth["estimated_clock_ns"] if synth else None
        cosim["projected_total_time_at_hls_estimate_ns"] = total * estimated if total is not None and estimated is not None else None
    reports = run / "reports"
    reports.mkdir(exist_ok=True)
    write_json(reports / "metrics.json", out)
    def fmt(value):
        return "N/A" if value is None else str(value)
    rows = ["# K4 Keccak HLS run", "", f"Run: `{run}`", "",
            "| Stage | This attempt | Verified evidence |", "|---|---|---|"]
    for key in STAGES:
        rows.append(f"| {key} | {attempt['stages'][key]} | {state['stage_evidence'].get(key, {}).get('status', 'none')} |")
    rows += ["", "| Metric | Value |", "|---|---|",
             f"| Configured clock period (ns) | {manifest['config']['clock_ns']} |"]
    if synth:
        rows.append(f"| HLS estimated clock period (ns) | {fmt(synth['estimated_clock_ns'])} |")
        for label, values in (("HLS estimated latency", synth["estimated_latency_cycles"]),
                              ("HLS estimated interval", synth["estimated_interval_cycles"])):
            rows.append(f"| {label} (cycles) | " + ", ".join(f"{k}={fmt(v)}" for k, v in values.items()) + " |")
        for key, value in synth["resources"].items():
            rows.append(f"| {key} (HLS estimate) | {fmt(value)} |")
    if cosim:
        rows.append("| RTL measured latency (cycles) | " + ", ".join(f"{k}={fmt(v)}" for k, v in cosim["measured_latency_cycles"].items()) + " |")
        rows.append(f"| RTL total execution (cycles, entire TB) | {fmt(cosim['total_execution_cycles'])} |")
        rows.append(f"| TB time at configured clock (ns) | {fmt(cosim['total_time_at_configured_clock_ns'])} |")
        rows.append(f"| Projected TB time using HLS clock estimate (ns) | {fmt(cosim['projected_total_time_at_hls_estimate_ns'])} |")
    rows += ["", "HLS worst-case latency is an estimate over supported sizes; it is not measured TotalExecution.",
             "Co-simulation totals describe the whole testbench workload, not one ML-KEM operation.",
             "Clock estimates are not post-route timing; skipped/missing stages are not passes.", ""]
    if errors:
        rows += ["Errors:"] + [f"- {e}" for e in errors] + [""]
    (reports / "metrics.md").write_text("\n".join(rows), encoding="utf-8")
    print(json.dumps({"requested_stages_passed": out["requested_stages_passed"],
                      "functional_hls_flow_passed": out["functional_hls_flow_passed"],
                      "metrics": str(reports / "metrics.json"), "errors": errors}))
    if args.strict and errors:
        raise ValueError("Requested HLS stages did not all validate")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare")
    prep.add_argument("--source-dir", type=Path, required=True)
    prep.add_argument("--run-dir", type=Path, required=True)
    prep.add_argument("--reuse", type=int, choices=(0, 1), required=True)
    prep.add_argument("--pid", type=int, required=True)
    prep.add_argument("--io-opt", type=int, choices=(0, 1), required=True)
    prep.add_argument("--part", required=True)
    prep.add_argument("--clock", type=float, required=True)
    prep.add_argument("--stages", type=int, choices=(0, 1), nargs=4, required=True)
    prep.add_argument("--export-flow", choices=("none", "syn", "impl"), required=True)
    st = sub.add_parser("stage")
    st.add_argument("--run-dir", type=Path, required=True)
    st.add_argument("--stage", choices=STAGES, required=True)
    st.add_argument("--status", choices=("running", "pass"), required=True)
    co = sub.add_parser("collect")
    co.add_argument("--run-dir", type=Path, required=True)
    co.add_argument("--strict", action="store_true")
    release = sub.add_parser("release")
    release.add_argument("--run-dir", type=Path, required=True)
    release.add_argument("--pid", type=int, required=True)
    fail = sub.add_parser("fail")
    fail.add_argument("--run-dir", type=Path, required=True)
    fail.add_argument("--message", required=True)
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            prepare(args)
        elif args.command == "stage":
            stage(args)
        elif args.command == "collect":
            collect(args)
        elif args.command == "release":
            lock = args.run_dir / ".running.lock"
            if read_json(lock)["pid"] != args.pid:
                raise ValueError("Refusing to release another process's lock")
            lock.unlink()
        elif args.command == "fail":
            state = read_json(args.run_dir / "state.json")
            attempt = state["attempts"][-1]
            attempt["error"] = args.message
            attempt["failed_utc"] = now()
            for key, status in attempt["stages"].items():
                if status == "running":
                    attempt["stages"][key] = "failed"
            write_json(args.run_dir / "state.json", state)
    except (OSError, ValueError, KeyError, ET.ParseError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
