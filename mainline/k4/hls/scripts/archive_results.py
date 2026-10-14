#!/usr/bin/env python3
"""Archive small verified reports, never generated HLS projects/IP/RTL."""
import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path

from collect_reports import check_snapshot, read_json, verify_report


def digest(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def transactions(run):
    log = (run / "p/sol1/csim/report/mlkem1024_keccak_accel_csim.log").read_text()
    if "MLKEM1024_KECCAK_TB_PASS transactions=109 hash_vectors=74" not in log:
        raise ValueError("Missing complete testbench marker")
    calls = re.findall(r"^PASS (\d+) (\S+) mode=(\d+) command=(\d+) in=(\d+) out=(\d+) rc=(-?\d+)$", log, re.M)
    rpt = (run / "p/sol1/sim/report/verilog/result.transaction.rpt").read_text()
    cycles = re.findall(r"transaction\s+(\d+):\s+(\d+)\s+(\d+|x)", rpt)
    if len(calls) != 109 or len(cycles) != 109:
        raise ValueError("Expected 109 calls and RTL latency rows")
    result = []
    for i, (call, cycle) in enumerate(zip(calls, cycles)):
        if int(call[0]) != i+1 or int(cycle[0]) != i:
            raise ValueError("Transaction order mismatch")
        result.append(dict(index=i, name=call[1], mode=int(call[2]), command=int(call[3]),
                           input_bytes=int(call[4]), output_bytes=int(call[5]), rc=int(call[6]),
                           latency_cycles=int(cycle[1]),
                           interval_cycles=None if cycle[2] == "x" else int(cycle[2])))
    return result


def archive_run(run, dest):
    if (run / ".running.lock").exists():
        raise ValueError(f"Run still active: {run}")
    manifest, state = read_json(run / "manifest.json"), read_json(run / "state.json")
    check_snapshot(run, manifest)
    metrics = read_json(run / "reports/metrics.json")
    if not metrics["functional_hls_flow_passed"] or not metrics["requested_stages_passed"]:
        raise ValueError(f"Incomplete HLS run: {run}")
    for stage, evidence in state["stage_evidence"].items():
        verify_report(run, stage, evidence)
    paths = ["manifest.json", "state.json", "reports/metrics.json", "reports/metrics.md",
             "p/sol1/csim/report/mlkem1024_keccak_accel_csim.log",
             "p/sol1/syn/report/mlkem1024_keccak_accel_csynth.xml",
             "p/sol1/syn/report/mlkem1024_keccak_accel_csynth.rpt",
             "p/sol1/sim/report/mlkem1024_keccak_accel_cosim.rpt",
             "p/sol1/sim/report/verilog/result.transaction.rpt",
             "snapshot/src/mlkem1024_keccak_accel.cpp", "snapshot/src/mlkem1024_keccak_accel.h",
             "snapshot/run_hls.tcl", "snapshot/scripts/collect_reports.py"]
    # Keep physical reports and applied constraints; no netlists, checkpoints or IP archives.
    impl = run / "p/sol1/impl/verilog"
    paths += [p.relative_to(run).as_posix() for p in sorted((impl / "report").glob("*.rpt"))]
    paths += [p.relative_to(run).as_posix() for p in sorted(impl.glob("*.xdc"))]
    paths += [p.relative_to(run).as_posix() for p in sorted((impl / "project.runs/impl_1").glob("*drc_routed.rpt"))]
    dest.mkdir(parents=True, exist_ok=False)
    mapping = {}
    for name in paths:
        source = run / name
        target = dest / name
        if target.suffix == ".log":
            target = target.with_suffix(".txt")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        mapping[target.relative_to(dest).as_posix()] = dict(source=name, sha256=digest(source.read_bytes()))
    write_json(dest / "archive_manifest.json", mapping)
    return metrics, transactions(run)


def rtl_equivalence(implemented, selected):
    def hashes(run):
        root = run / "p/sol1/syn/verilog"
        result = {}
        for p in sorted(root.iterdir()):
            if not p.is_file():
                continue
            data = p.read_bytes()
            # Only HLS's informational resource/latency attribute may differ.
            norm = re.sub(rb'^\(\* CORE_GENERATION_INFO="[^"\r\n]*" \*\)\r?\n', b'', data, flags=re.M)
            result[p.name] = dict(raw_sha256=digest(data), normalized_sha256=digest(norm))
        return result
    a, b = hashes(implemented), hashes(selected)
    if not a or a.keys() != b.keys() or any(a[k]["normalized_sha256"] != b[k]["normalized_sha256"] for k in a):
        raise ValueError("Selected RTL differs from implemented RTL beyond informational HLS metadata")
    return dict(implemented_run=str(implemented), selected_run=str(selected),
                normalization="Remove only complete CORE_GENERATION_INFO attribute lines; all other bytes unchanged",
                equivalent=True, implemented=a, selected=b)


def physical_metrics(run):
    state = read_json(run / "state.json")
    evidence = state["stage_evidence"].get("EXPORT", {})
    verify_report(run, "EXPORT", evidence)
    if evidence.get("flow") != "impl":
        raise ValueError("No successful implementation export")
    reports = run / "p/sol1/impl/verilog/report"
    timing = (reports / "mlkem1024_keccak_accel_timing_routed.rpt").read_text()
    area = (reports / "mlkem1024_keccak_accel_utilization_routed.rpt").read_text()
    if "Design State : Routed" not in area or "All user specified timing constraints are met." not in timing:
        raise ValueError("Routed timing has not passed")
    match = re.search(r"^\s+([-\d.]+)\s+([-\d.]+)\s+\d+\s+\d+\s+([-\d.]+)\s+([-\d.]+)\s+\d+\s+\d+\s+[-\d.]+", timing, re.M)
    if not match:
        raise ValueError("Missing timing summary row")
    wns, tns, whs, ths = map(float, match.groups())
    if min(wns, whs) < 0 or tns != 0 or ths != 0:
        raise ValueError("Timing violations")
    resources = {}
    for label in ("Slice LUTs", "Slice Registers", "Block RAM Tile", "DSPs"):
        match = re.search(r"\| " + re.escape(label) + r"\s*\|\s*(\d+)\s*\|", area)
        if not match:
            raise ValueError(f"Missing resource: {label}")
        resources[label] = int(match.group(1))
    return dict(scope="Standalone out-of-context HLS IP; external CPU/data/context memories absent",
                configuration="Vivado 2024.2 xc7z020clg400-1, 10 ns clock-only XDC",
                wns_ns=wns, tns_ns=tns, whs_ns=whs, ths_ns=ths, resources=resources,
                limitations=["No external input/output delays in generated XDC",
                             "HD.CLK_SRC unset: final top-level clock skew not modeled",
                             "ZPS7-1 warning: standalone IP has no PS7",
                             "No full-system timing, bitstream, or board claim"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("baseline", "selected", "implemented", "destination"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    if args.destination.exists():
        raise ValueError("Archive already exists; do not overwrite historical evidence")
    equiv = rtl_equivalence(args.implemented, args.selected)
    physical = physical_metrics(args.implemented)
    records = {}
    for label, run in (("base02", args.baseline), ("opt02", args.selected), ("opt01_impl", args.implemented)):
        metrics, calls = archive_run(run, args.destination / label)
        records[label] = dict(metrics=metrics, transactions=calls)
    base, opt = records["base02"], records["opt02"]
    a, b = base["metrics"], opt["metrics"]
    if a["configuration"]["io_opt"] != 0 or b["configuration"]["io_opt"] != 1:
        raise ValueError("Unexpected IO configurations")
    for key in a["configuration"]:
        if key != "io_opt" and a["configuration"][key] != b["configuration"][key]:
            raise ValueError(f"Incomparable configuration: {key}")
    # Compare every TB fixture hash; implementation annotation changes are recorded separately.
    for key, value in a["input_sha256"].items():
        if key.startswith("tb/") and b["input_sha256"].get(key) != value:
            raise ValueError(f"Different testbench inputs: {key}")
    compared = []
    for left, right in zip(base["transactions"], opt["transactions"]):
        if any(left[k] != right[k] for k in left if not k.endswith("cycles")):
            raise ValueError("Different transaction sequence")
        compared.append(dict(transaction=left["index"], name=left["name"], mode=left["mode"],
                             command=left["command"], input_bytes=left["input_bytes"], output_bytes=left["output_bytes"],
                             base_cycles=left["latency_cycles"], opt_cycles=right["latency_cycles"]))
    write_json(args.destination / "transactions.json", compared)
    write_json(args.destination / "rtl_equivalence.json", equiv)
    write_json(args.destination / "physical_metrics.json", physical)
    print(f"Archived {len(compared)} matched RTL transactions to {args.destination}")


if __name__ == "__main__":
    main()
