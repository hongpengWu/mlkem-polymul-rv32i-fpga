"""Validate finished parameterized CPU RTL KAT runs; never start a simulator.

The default CLI is read-only. Use --write to save cases.csv and summaries after
145 distinct pinned official cases have passed in a full run or disjoint batches.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from copy import deepcopy
import csv
import hashlib
import json
import math
from pathlib import Path
import re
import statistics
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/kat"))
from package_mlkem import ACVP_COMMIT, load_cases, pack_fixture  # noqa: E402

FIELDS = ("index,dataset,vsId,tgId,tcId,op,return_code,raw_cycles,empty_cycles,"
          "input_bytes,output_bytes,m_total,mul,mulh,mulhsu,mulhu,div,divu,rem,remu,min_sp").split(",")
M_OPS = "mul mulh mulhsu mulhu div divu rem remu".split()
CONFIGS = {"rv32i": (0, 0, 0, 0), "rv32im_iterative": (1, 0, 1, 1),
           "rv32im_fast": (1, 1, 1, 1)}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def key_values(line):
    return {key: int(value, 0) for key, value in
            re.findall(r"(\w+)=(-?0x[0-9a-fA-F]+|-?[0-9]+)", line)}


def one_line(log, prefix):
    lines = [line[len(prefix):] for line in log.splitlines() if line.startswith(prefix)]
    require(len(lines) == 1, f"Expected exactly one {prefix} record, got {len(lines)}")
    return lines[0]


def payload_bytes(case, direction):
    return sum(len(bytes.fromhex(case[direction][name])) for name in case[direction + "_fields"])


def expected_rejection(case):
    if case["op"] not in (3, 4):
        return None
    parts = [bytes.fromhex(case["input"][name]) for name in case["input_fields"]]
    z, ciphertext = (parts[0][-32:], parts[1]) if case["op"] == 3 else (parts[1], parts[2])
    return hashlib.shake_256(z + ciphertext).digest(32).hex() == case["output"]["k"]


def verify_inputs(path, cases, config, ram_bytes, stack_bytes):
    record_path = path.parent / "run_inputs.json"
    run = json.loads(record_path.read_text(encoding="utf-8"))
    level = run["parameter_set"]
    require(level in (768, 1024) and run["config"] == config and
            run["simulator"] == "Vivado/XSim 2024.2" and
            run["ram_bytes"] == ram_bytes == 131072 and
            run["stack_bytes"] == stack_bytes == 32768, f"Wrong run provenance: {record_path}")
    hashes = run["input_sha256"]
    snapshot_path = path.parent / "snapshot_manifest.json"
    if snapshot_path.is_file():
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        require(snapshot["run_input_sha256"] == hashes, f"Snapshot provenance mismatch: {snapshot_path}")
        for name, wanted in {**hashes, **snapshot.get("additional_postrun_sha256", {})}.items():
            archived = (path.parent / "run_snapshot" / name).resolve()
            require(archived.is_relative_to(path.parent.resolve() / "run_snapshot") and
                    archived.is_file() and sha(archived) == wanted, f"Snapshot hash mismatch: {name}")
    isa = "rv32i" if config == "rv32i" else "rv32im"
    required = {"rtl/cpu/picorv32.v", "rtl/benchmark/cpu_benchmark_system.v",
                "tb/software/tb_mlkem_suite.sv", f"firmware/images/mlkem{level}_suite/{isa}.mem"}
    require(required <= hashes.keys(), f"Missing frozen RTL/firmware inputs: {record_path}")
    require(any(name.endswith(".tcl") for name in hashes), f"Missing simulation script: {record_path}")
    verified = {}
    for name, wanted in hashes.items():
        source = (ROOT / name).resolve()
        require(source.is_relative_to(ROOT), f"Input escapes repository: {name}")
        if not source.is_file() or sha(source) != wanted:
            require(snapshot_path.is_file(), f"Missing snapshot provenance for changed input: {name}")
            source = (path.parent / "run_snapshot" / name).resolve()
            require(source.is_relative_to(path.parent.resolve() / "run_snapshot") and
                    source.is_file() and sha(source) == wanted,
                    f"Changed or missing simulation input (including archived snapshot): {name}")
        verified[name] = source
    official, _ = load_cases(ROOT, level)
    by_identity = {tuple(c[name] for name in ("dataset_id", "vsId", "tgId", "tcId")): c for c in official}
    seen = set()
    for index, case in enumerate(cases):
        identity = tuple(case[name] for name in ("dataset_id", "vsId", "tgId", "tcId"))
        require(identity in by_identity and identity not in seen and case["case_index"] == index,
                f"Unknown/duplicate/nonlocal official case: {index}")
        seen.add(identity)
        canonical = by_identity[identity]
        require(all(case.get(name) == value for name, value in canonical.items() if name != "case_index"),
                f"Fixture differs from pinned ACVP bytes/metadata: case {index}")
    for expected, suffix in ((False, "input"), (True, "expected")):
        names = [name for name in hashes if Path(name).name == f"mlkem{level}_{suffix}.mem"]
        require(len(names) == 1, f"Missing/ambiguous frozen {suffix} fixture: {record_path}")
        actual = [int(line, 16) for line in verified[names[0]].read_text(encoding="ascii").splitlines()]
        require(actual == pack_fixture(deepcopy(cases), level, expected),
                f"Frozen {suffix} fixture does not match official cases: {record_path}")
    return run


def validate_log(path, cases, config, ram_bytes, stack_bytes) -> list[dict]:
    """Validate a finished log and adjacent run_inputs.json; cases use local IDs.

    Returned dictionaries contain numeric FIELDS plus config, operation,
    dataset_name, revision, expected_implicit_rejection, algorithm_ms_at_100mhz
    and observed_algorithm_stack_bytes. ``index`` remains the local row index.
    The hashed TB checks both rdcycle samples against the observed CPU cycles.
    """
    path = Path(path)
    require(config in CONFIGS and cases, "Invalid config or empty case list")
    success_path = path.parent / 'success.json'
    if success_path.is_file():
        success = json.loads(success_path.read_text(encoding='utf-8'))
        require(success['status'] == 'passed' and success['case_count'] == len(cases) and
                success['log_sha256'] == sha(path) and
                success['run_inputs_sha256'] == sha(path.parent / 'run_inputs.json'),
                f'Saved success evidence changed: {success_path}')
    verify_inputs(path, cases, config, ram_bytes, stack_bytes)
    log = path.read_text(encoding="utf-8")
    require(not re.search(r"(?i)fatal:|\$fatal|ERROR:|MLKEM_FAIL", log), f"Failure marker: {path}")
    require(one_line(log, "MLKEM_HEADER,").split(",") == FIELDS, f"Unexpected columns: {path}")
    start = key_values(one_line(log, "MLKEM_START "))
    end = key_values(one_line(log, "MLKEM_PASS "))
    require(tuple(start[name] for name in ("mul", "fast_mul", "div", "expect_m")) == CONFIGS[config] and
            tuple(end[name] for name in ("cpu_mul", "cpu_fast_mul", "cpu_div", "expect_m")) == CONFIGS[config],
            f"CPU configuration mismatch: {path}")
    require(start["cases"] == end["cases"] == len(cases) and
            start["ram_bytes"] == ram_bytes and start["stack_bytes"] == stack_bytes and
            start["clock_mhz"] == 100, f"Memory/clock/case count mismatch: {path}")
    lines = [line[len("MLKEM_ROW,"):] for line in log.splitlines() if line.startswith("MLKEM_ROW,")]
    require(len(lines) == len(cases), f"Incomplete or duplicate rows: {path}")
    require(log.index("MLKEM_HEADER,") < log.index("MLKEM_START ") <
            log.index("MLKEM_ROW,") <= log.rindex("MLKEM_ROW,") < log.index("MLKEM_PASS "),
            f"Invalid final PASS ordering: {path}")
    stack_top = ram_bytes - 16
    stack_bottom = stack_top - stack_bytes
    require(stack_bottom <= end["min_sp"] <= stack_top and end["min_sp"] % 16 == 0 and
            end["stack_used"] == stack_top - end["min_sp"], f"Invalid whole-run stack: {path}")
    rows = []
    for index, (line, case) in enumerate(zip(lines, cases)):
        values = line.split(",")
        require(len(values) == len(FIELDS), f"Malformed row: {path}/{index}")
        row = dict(zip(FIELDS, (int(value, 0) for value in values)))
        wanted = [case[name] for name in ("case_index", "dataset_id", "vsId", "tgId", "tcId", "op")]
        require([row[name] for name in FIELDS[:6]] == wanted and row["index"] == index,
                f"Case identity/order mismatch: {path}/{index}")
        require(row["return_code"] == case["expected_return"] and
                row["input_bytes"] == payload_bytes(case, "input") and
                row["output_bytes"] == payload_bytes(case, "output"), f"Return/bytes mismatch: {path}/{index}")
        require(row["raw_cycles"] > row["empty_cycles"] > 0, f"Invalid rdcycle interval: {path}/{index}")
        require(all(row[op] >= 0 for op in M_OPS) and row["m_total"] == sum(row[op] for op in M_OPS),
                f"Invalid M instruction counters: {path}/{index}")
        require(row["m_total"] == 0 if config == "rv32i" else
                (row["mul"] > 0 if case["op"] <= 4 else True), f"Wrong M execution: {path}/{index}")
        require(end["min_sp"] <= row["min_sp"] <= stack_top and row["min_sp"] % 16 == 0,
                f"Stack outside reservation: {path}/{index}")
        rows.append(dict(row, config=config, operation=case["operation"], dataset_name=case["dataset"],
                         revision=case["revision"], expected_implicit_rejection=expected_rejection(case),
                         algorithm_ms_at_100mhz=row["raw_cycles"] / 100000,
                         observed_algorithm_stack_bytes=stack_top - row["min_sp"]))
    require(all(end[name] == sum(row[name] for row in rows) for name in ("input_bytes", "output_bytes")),
            f"Incomplete suite byte totals: {path}")
    require(end["cycles"] > sum(row["raw_cycles"] for row in rows) and
            end["all_m"] >= sum(row["m_total"] for row in rows) and
            (end["all_m"] == 0 if config == "rv32i" else end["all_m"] > 0), f"Invalid whole-run totals: {path}")
    return rows


def collect(level, config):
    cases, _ = load_cases(ROOT, level)
    result_dir = ROOT / f"results/official_baseline/mlkem{level}"
    complete = result_dir / config / "simulate.log"
    batches = sorted((result_dir / "batches" / config).glob("batch_*/batch.json"))
    require(not (complete.is_file() and batches), "Ambiguous full-run and batch results; archive one explicitly")
    require(complete.is_file() or batches, "No complete run or batches found")
    runs = [(complete, list(range(145)))] if complete.is_file() else []
    for meta_path in batches:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        indices = meta["original_indices"]
        require(meta["parameter_set"] == level and meta["config"] == config and
                meta["case_count"] == len(indices) > 0 and len(indices) == len(set(indices)) and
                all(type(i) is int and 0 <= i < 145 for i in indices), f"Wrong batch metadata: {meta_path}")
        runs.append((meta_path.parent / "simulate.log", indices))
    rows, details, evidence = [], [], {}
    for path, indices in runs:
        local = deepcopy([cases[index] for index in indices])
        for index, case in enumerate(local):
            case["case_index"] = index
        checked = validate_log(path, local, config, 131072, 32768)
        rows.extend(dict(row, case_index=original) for row, original in zip(checked, indices))
        end = key_values(one_line(path.read_text(encoding="utf-8"), "MLKEM_PASS "))
        details.append(dict(path=path.relative_to(ROOT).as_posix(), original_indices=indices, **end))
        for source in (path, path.parent / "run_inputs.json", path.parent / "batch.json",
                       path.parent / "snapshot_manifest.json", path.parent / "success.json"):
            if source.is_file():
                evidence[source.relative_to(ROOT).as_posix()] = sha(source)
    require(len(rows) == 145 and sorted(row["case_index"] for row in rows) == list(range(145)),
            "Expected 145 uniquely covered official cases")
    rows.sort(key=lambda row: row["case_index"])
    groups = defaultdict(list)
    for row in rows:
        groups[row["operation"], row["return_code"]].append(row)
    aggregate = []
    for (operation, ret), members in groups.items():
        cycles = sorted(row["raw_cycles"] for row in members)
        aggregate.append(dict(operation=operation, return_code=ret, samples=len(cycles),
                              cycle_min=cycles[0], cycle_mean=statistics.mean(cycles),
                              cycle_median=statistics.median(cycles), cycle_p95=cycles[math.ceil(.95 * len(cycles)) - 1],
                              cycle_max=cycles[-1], total_cycles=sum(cycles)))
    summary = dict(parameter_set=level, config=config, case_count=145, acvp_commit=ACVP_COMMIT,
                   ram_bytes=131072, stack_bytes=32768, clock_mhz=100,
                   total_sim_cycles=sum(run["cycles"] for run in details),
                   timed_cycles=sum(row["raw_cycles"] for row in rows),
                   input_bytes=sum(row["input_bytes"] for row in rows),
                   output_bytes=sum(row["output_bytes"] for row in rows),
                   timed_m=sum(row["m_total"] for row in rows), all_m=sum(run["all_m"] for run in details),
                   observed_stack_bytes=max(run["stack_used"] for run in details),
                   expected_implicit_rejection_cases=sum(row["expected_implicit_rejection"] is True for row in rows),
                   timing="Raw rdcycle delta around dispatch/API; seed decapsulation includes key expansion; mailbox, oracle comparison, startup and entropy acquisition excluded. Internal zeroization included; empty bracket not subtracted.",
                   limitations="CPU-only RTL simulation; no K=3/K=4 accelerator support, board measurement, formal certification or worst-case stack bound. Each pinned record executes once; P95 uses nearest rank. RAM/stack envelope differs from the 64 KiB/16 KiB ML-KEM-512 baseline.",
                   aggregate=aggregate, runs=details, evidence_sha256=evidence)
    return result_dir, summary, rows


def markdown(summary):
    lines = [f"# ML-KEM-{summary['parameter_set']} {summary['config']} 官方公开向量回归", "",
             "145/145 条官方记录逐字节验证通过，包含两类 KeyCheck 的有效／无效返回。",
             "CPU-only Vivado/XSim 2024.2 RTL 仿真；128 KiB RAM、32 KiB 栈。100 MHz 时间仅为周期换算。", "",
             f"算法总周期：{summary['timed_cycles']:,}；输入／输出核对：{summary['input_bytes']:,} / {summary['output_bytes']:,} B；全程观测栈：{summary['observed_stack_bytes']:,} B。", "",
             "| 操作 | 返回值 | N | 最小周期 | 平均周期 | 中位周期 | P95 周期 | 最大周期 |", "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for item in summary["aggregate"]:
        lines.append(f"| {item['operation']} | {item['return_code']} | {item['samples']} | {item['cycle_min']:,} | {item['cycle_mean']:,.2f} | {item['cycle_median']:,.1f} | {item['cycle_p95']:,} | {item['cycle_max']:,} |")
    lines += ["", "计时包括 API 内部计算与清零，seed 解封装包括密钥展开；不含 mailbox、oracle 核对、启动和熵源采集。空计时区间保留、不扣除。", "",
              "每条官方记录执行一次，P95 为 nearest-rank；不是正式认证或实板结果，也不代表 K=3/K=4 加速硬件已通过。栈为观测值，非最坏情况上界。", "",
              "与 ML-KEM-512 的 64 KiB RAM／16 KiB 栈口径不同。逐例数据见 cases.csv，日志及冻结输入证据见 summary.json 和各 run_inputs.json。", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parameter-set", required=True, type=int, choices=(768, 1024))
    parser.add_argument("--config", choices=CONFIGS, default="rv32im_fast")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check-only", action="store_true", help="validate only (default)")
    mode.add_argument("--write", action="store_true", help="save validated tables")
    args = parser.parse_args()
    directory, summary, rows = collect(args.parameter_set, args.config)
    if args.write:
        directory = directory / args.config
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        (directory / "summary.md").write_text(markdown(summary), encoding="utf-8")
        with (directory / "cases.csv").open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=["case_index"] + [name for name in rows[0] if name != "case_index"])
            writer.writeheader()
            writer.writerows(rows)
    print(f"MLKEM{args.parameter_set}_COLLECT_PASS config={args.config} cases=145 cycles={summary['timed_cycles']}")


if __name__ == "__main__":
    main()
