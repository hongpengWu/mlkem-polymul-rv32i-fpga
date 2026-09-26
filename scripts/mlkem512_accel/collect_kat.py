"""Collect and validate accelerated ML-KEM-512 batch logs.

The accelerator run uses the same official fixture and row format as the CPU
suite.  This collector only consumes finished batch directories; it never
starts Vivado.  A complete result is reported only when all 145 canonical
cases have one valid row and one ``ACCEL_METRICS`` record.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import statistics
import sys
from datetime import datetime, timezone
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASELINE = ROOT / "results/official_baseline/mlkem512"
RESULTS = ROOT / "results/accelerator_cpu/kat"
SUITE = ROOT / "scripts/mlkem512_suite"

sys.path.insert(0, str(SUITE))
from collect import FIELDS, M_OPS, key_values  # noqa: E402
from collect_resumed import validate_row  # noqa: E402

METRIC_FIELDS = ("index", "starts", "done", "loads", "reads",
                 "core_cycles", "load_cycles", "read_cycles")
NUMERIC_FIELDS = set(FIELDS)
CSV_FIELDS = [
    "case_index", "dataset", "vsId", "tgId", "tcId", "op", "operation",
    "return_code", "software_cycles", "hardware_cycles", "empty_cycles",
    "input_bytes", "output_bytes", "m_total", "mul", "mulh", "mulhsu",
    "mulhu", "div", "divu", "rem", "remu", "min_sp", "starts", "done",
    "loads", "reads", "core_cycles", "load_cycles", "read_cycles",
    "remaining_api_cycles", "load_ratio", "core_ratio", "read_ratio",
    "remaining_api_ratio", "speedup", "speedup_per_sample",
]


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_int(value: str) -> int:
    return int(value, 0)


def read_baseline():
    fixture = json.loads((ROOT / "tb/software/mlkem512_suite/cases.json").read_text(encoding="utf-8"))
    require(fixture.get("parameterSet") == "ML-KEM-512" and
            fixture.get("case_count") == len(fixture.get("cases", [])) == 145,
            "wrong ML-KEM-512 fixture")
    path = BASELINE / "cases.csv"
    with path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    rows = [row for row in rows if row.get("config") == "rv32im_fast"]
    require(len(rows) == 145, f"baseline rv32im_fast rows={len(rows)}, expected 145")
    result = {}
    # The baseline manifest is intentionally immutable evidence.  Its source
    # hashes may predate later tooling changes, so row validation uses the
    # fixed 64 KiB/16 KiB memory contract directly.
    build = {"stack_bottom": 0xbff0, "stack_top": 0xfff0}
    for position, raw in enumerate(rows):
        values = {name: parse_int(raw[name]) for name in FIELDS}
        checked = validate_row(values, fixture["cases"][position],
                               "rv32im_fast", build, position)
        require(checked["original_case_index"] == position,
                f"baseline case order mismatch at {position}")
        result[position] = checked
    return fixture, result


def parse_metrics(log: str, path: Path):
    pattern = re.compile(
        r"^ACCEL_METRICS\s+" +
        r"index=(?P<index>-?\d+)\s+starts=(?P<starts>-?\d+)\s+"
        r"done=(?P<done>-?\d+)\s+loads=(?P<loads>-?\d+)\s+"
        r"reads=(?P<reads>-?\d+)\s+core_cycles=(?P<core_cycles>-?\d+)\s+"
        r"load_cycles=(?P<load_cycles>-?\d+)\s+read_cycles=(?P<read_cycles>-?\d+)\s*$"
    )
    metrics = {}
    for line in log.splitlines():
        match = pattern.match(line.strip())
        if not match:
            continue
        item = {name: int(match.group(name)) for name in METRIC_FIELDS}
        require(item["index"] not in metrics,
                f"duplicate ACCEL_METRICS index={item['index']} in {path}")
        require(all(item[name] >= 0 for name in METRIC_FIELDS[1:]),
                f"negative accelerator metric in {path}")
        metrics[item["index"]] = item
    return metrics


def parse_batch(directory: Path, fixture, baseline):
    meta_path = directory / "batch.json"
    log_path = directory / "accelerate_simulate.log"
    if not log_path.is_file():
        log_path = directory / "simulate.log"
    require(meta_path.is_file(), f"missing {meta_path}")
    require(log_path.is_file(), f"missing accelerate_simulate.log in {directory}")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    indices = [int(i) for i in meta.get("original_indices", [])]
    require(indices and len(indices) == len(set(indices)),
            f"invalid original_indices in {meta_path}")
    require(meta.get("case_count") == len(indices), f"batch count mismatch: {directory}")
    require(all(0 <= i < 145 for i in indices), f"out-of-range case in {directory}")
    log = log_path.read_text(encoding="utf-8")
    require(not re.search(r"(?i)(?:fatal:|\$fatal|ERROR:|MLKEM512_FAIL)", log),
            f"failure marker in {log_path}")
    header = [line[len("MLKEM512_HEADER,"):] for line in log.splitlines()
              if line.startswith("MLKEM512_HEADER,")]
    require(header == [",".join(FIELDS)], f"unexpected header in {log_path}")
    start = [line for line in log.splitlines() if line.startswith("MLKEM512_START ")]
    require(len(start) == 1 and key_values(start[0]).get("cases") == len(indices),
            f"missing or wrong start record in {log_path}")
    pass_lines = [line for line in log.splitlines() if line.startswith("MLKEM512_PASS ")]
    complete_log = (len(pass_lines) == 1 and
                    key_values(pass_lines[0]).get("cases") == len(indices))
    row_lines = [line[len("MLKEM512_ROW,"):] for line in log.splitlines()
                 if line.startswith("MLKEM512_ROW,")]
    require(len(row_lines) <= len(indices), f"duplicate rows in {log_path}")
    metrics = parse_metrics(log, log_path)
    if len(row_lines) != len(indices) or len(metrics) != len(indices) or not complete_log:
        complete_log = False
    if complete_log:
        require(log.index(start[0]) < log.index("MLKEM512_ROW,") and
                max(log.rindex("MLKEM512_ROW,"), log.rindex("ACCEL_METRICS ")) <
                log.index(pass_lines[0]), f"invalid final PASS ordering in {log_path}")
    rows = []
    for local, line in enumerate(row_lines):
        values = line.split(",")
        require(len(values) == len(FIELDS), f"malformed row {directory}/{local}")
        row = {name: parse_int(value) for name, value in zip(FIELDS, values)}
        original = indices[local]
        checked = validate_row(row, fixture["cases"][original],
                               "rv32im_fast", {"stack_bottom": 0xbff0,
                               "stack_top": 0xfff0}, local)
        require(row["index"] == local,
                f"case identity mismatch {directory}/{local}")
        require(original in baseline, f"missing baseline case {original}")
        require(local in metrics, f"missing ACCEL_METRICS index={local} in {log_path}")
        rows.append((original, checked, metrics[local]))
    return rows, dict(directory=directory, log=log_path, complete_log=complete_log,
                      indices=indices, batch=meta)


def make_case(original, checked, metric, baseline):
    calls = metric["starts"]
    require((calls > 0) if checked["op"] <= 4 else (calls == 0),
            f"unexpected accelerator use for case {original}")
    require(metric["done"] == calls and metric["loads"] == 640 * calls and
            metric["reads"] == 128 * calls and metric["core_cycles"] == 136 * calls,
            f"incomplete accelerator calls for case {original}")
    require((metric["load_cycles"] >= metric["loads"] and
             metric["read_cycles"] >= metric["reads"]) if calls else
            (metric["load_cycles"] == metric["read_cycles"] == 0),
            f"invalid accelerator transfer cycles for case {original}")
    sw = int(baseline[original]["raw_cycles"])
    hw = int(checked["raw_cycles"])
    load = metric["load_cycles"]
    core = metric["core_cycles"]
    read = metric["read_cycles"]
    remaining = hw - load - core - read
    require(hw > 0 and remaining >= 0, f"invalid phase totals for case {original}")
    denom = float(hw)
    out = {"case_index": original, "dataset": checked["dataset"],
           "vsId": checked["vsId"], "tgId": checked["tgId"],
           "tcId": checked["tcId"], "op": checked["op"],
           "operation": checked["operation"], "return_code": checked["return_code"],
           "software_cycles": sw, "hardware_cycles": hw,
           "empty_cycles": checked["empty_cycles"],
           "input_bytes": checked["input_bytes"], "output_bytes": checked["output_bytes"]}
    for name in ("m_total", *M_OPS):
        out[name] = checked[name]
    out.update({name: metric[name] for name in METRIC_FIELDS[1:]})
    out.update(remaining_api_cycles=remaining,
               load_ratio=load / denom, core_ratio=core / denom,
               read_ratio=read / denom, remaining_api_ratio=remaining / denom,
               speedup=sw / hw, speedup_per_sample=sw / hw)
    return out


def summarize(rows):
    groups = defaultdict(list)
    for row in rows:
        groups[(row["op"], row["operation"])].append(row)
    operations = {}
    for (op, operation), members in sorted(groups.items()):
        sw = [r["software_cycles"] for r in members]
        hw = [r["hardware_cycles"] for r in members]
        sums = {name: sum(r[name] for r in members)
                for name in ("load_cycles", "core_cycles", "read_cycles", "remaining_api_cycles")}
        total = sum(hw)
        operations[str(op)] = {
            "op": op, "operation": operation, "samples": len(members),
            "software": {"mean": statistics.mean(sw), "min": min(sw), "max": max(sw), "sum": sum(sw)},
            "hardware": {"mean": statistics.mean(hw), "min": min(hw), "max": max(hw), "sum": total},
            "speedup_sum": sum(sw) / total if total else None,
            "speedup_per_sample_mean": statistics.mean(r["speedup_per_sample"] for r in members),
            "phase_cycles": sums,
            "phase_ratio": {name: sums[name] / total if total else None for name in sums},
        }
    all_hw = sum(r["hardware_cycles"] for r in rows)
    all_sw = sum(r["software_cycles"] for r in rows)
    return {"operations": operations, "totals": {
        "samples": len(rows), "software_cycles": all_sw, "hardware_cycles": all_hw,
        "speedup_sum": all_sw / all_hw if all_hw else None,
        "phase_cycles": {name: sum(r[name] for r in rows)
                         for name in ("load_cycles", "core_cycles", "read_cycles", "remaining_api_cycles")},
        "phase_ratio": {name: sum(r[name] for r in rows) / all_hw if all_hw else None
                         for name in ("load_cycles", "core_cycles", "read_cycles", "remaining_api_cycles")},
    }}


def write_outputs(rows, summary, complete, errors):
    RESULTS.mkdir(parents=True, exist_ok=True)
    with (RESULTS / "cases.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    document = {"status": "PASS" if complete else "INCOMPLETE", "parameter_set": "ML-KEM-512",
                "expected_cases": 145, "completed_cases": len(rows), "errors": errors,
                "baseline": "results/official_baseline/mlkem512/cases.csv", **summary}
    (RESULTS / "summary.json").write_text(json.dumps(document, indent=2, sort_keys=True) + "\n",
                                           encoding="utf-8")
    lines = ["# ML-KEM-512 CPU + accelerator comparison", "",
             f"Status: **{document['status']}** ({len(rows)}/145 cases)", "",
             "| operation | samples | software mean/min/max | hardware mean/min/max | speedup (sum) | speedup (per sample) |",
             "|---|---:|---:|---:|---:|---:|"]
    for item in summary["operations"].values():
        s, h = item["software"], item["hardware"]
        lines.append(f"| {item['operation']} | {item['samples']} | {s['mean']:.1f}/{s['min']}/{s['max']} | "
                     f"{h['mean']:.1f}/{h['min']}/{h['max']} | {item['speedup_sum']:.4f}x | "
                     f"{item['speedup_per_sample_mean']:.4f}x |")
    lines += ["", "Phase ratios use accelerated measured API cycles:", "",
              "| scope | load | core | read | remaining API |", "|---|---:|---:|---:|---:|"]
    for scope, item in [("all", summary["totals"]), *[(x["operation"], x) for x in summary["operations"].values()]]:
        ratio = item["phase_ratio"]
        lines.append(f"| {scope} | {ratio['load_cycles']:.4f} | {ratio['core_cycles']:.4f} | "
                     f"{ratio['read_cycles']:.4f} | {ratio['remaining_api_cycles']:.4f} |")
    if errors:
        lines += ["", "## Incomplete batches", ""] + [f"- {e}" for e in errors]
    (RESULTS / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Keep an auditable manifest beside the aggregate results.  The batch
    # logs and fixtures are copied into RESULTS by the run wrapper; hashes are
    # captured here only after collector validation has accepted every case.
    evidence = {}
    for path in sorted(RESULTS.rglob("*")):
        if path.is_file() and path.name != "evidence_manifest.json":
            evidence[path.relative_to(ROOT).as_posix()] = sha(path)
    inputs = [
        "rtl/cpu/picorv32.v",
        "rtl/accelerator/mlkem512_accel_system.sv",
        "rtl/accelerator/mlkem512_tdp_bram.sv",
        "rtl/accelerator/mlkem512_basemul_k2_mmio_adapter.sv",
        "tb/accelerator/tb_mlkem512_kat_accel.sv",
        "firmware/images/mlkem512_accel/kat.mem",
        "tb/software/mlkem512_suite/cases.json",
        "results/official_baseline/mlkem512/cases.csv",
        "scripts/mlkem512_accel/run_kat_batch.tcl",
        "scripts/mlkem512_accel/collect_kat.py",
    ]
    input_hashes = {name: sha(ROOT / name) for name in inputs if (ROOT / name).is_file()}
    manifest = {
        "schema_version": 1,
        "status": document["status"],
        "parameter_set": document["parameter_set"],
        "cases": document["completed_cases"],
        "expected_cases": document["expected_cases"],
        "simulator": "Vivado/XSim 2024.2",
        "cpu_config": "rv32im_fast",
        "clock_mhz": 100,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "input_sha256": input_hashes,
        "evidence_sha256": evidence,
    }
    (RESULTS / "evidence_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", type=Path, default=RESULTS)
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--allow-partial", action="store_true")
    args = parser.parse_args(argv)
    try:
        fixture, baseline = read_baseline()
        batch_dirs = sorted(p for p in args.results_dir.glob("batch_*") if p.is_dir())
        require(batch_dirs, f"no batch directories under {args.results_dir}")
        all_rows, errors, seen = [], [], set()
        for directory in batch_dirs:
            try:
                parsed, meta = parse_batch(directory, fixture, baseline)
                require(meta["complete_log"], "missing final PASS or incomplete batch records")
                batch_rows = []
                for original, checked, metric in parsed:
                    require(original not in seen, f"duplicate official case {original}")
                    batch_rows.append(make_case(original, checked, metric, baseline))
                seen.update(row["case_index"] for row in batch_rows)
                all_rows.extend(batch_rows)
            except Exception as error:  # retain all failures in partial reports
                errors.append(f"{directory.name}: {error}")
        all_rows.sort(key=lambda row: row["case_index"])
        complete = not errors and len(all_rows) == 145 and seen == set(range(145))
        if not complete and not args.allow_partial:
            raise RuntimeError("accelerator KAT incomplete: " + "; ".join(errors or [f"{len(all_rows)}/145 cases"]))
        summary = summarize(all_rows)
        if not args.check_only:
            write_outputs(all_rows, summary, complete, errors)
        print(f"MLKEM512_ACCEL_COLLECT_{'PASS' if complete else 'INCOMPLETE'} cases={len(all_rows)}/145")
        return 0 if complete else 2
    except Exception as error:
        print(f"MLKEM512_ACCEL_COLLECT_FAIL {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
