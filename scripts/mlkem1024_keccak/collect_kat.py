#!/usr/bin/env python3
"""Strictly collect finished PicoRV32 + Keccak K4 KAT attempts; never run RTL.

Default: validate 145 unique successful official cases, read-only. --partial
permits a pilot subset; --write saves aggregate JSON/Markdown/CSV separately
from frozen CPU baselines and attempt evidence. Failed attempts stay excluded.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from copy import deepcopy
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import statistics
import sys

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "results/keccak_cpu/kat"
PROFILE = ROOT / "results/keccak_cpu/call_profile"
BASELINE = ROOT / "results/official_baseline/mlkem1024/rv32im_fast/cases.csv"
sys.path.insert(0, str(ROOT / "scripts/kat"))
from package_mlkem import load_cases, pack_fixture  # noqa: E402

FIELDS = ("index,dataset,vsId,tgId,tcId,op,return_code,raw_cycles,empty_cycles,"
          "input_bytes,output_bytes,m_total,mul,mulh,mulhsu,mulhu,div,divu,rem,remu,min_sp").split(",")
HARDWARE_FIELDS = "index starts done hash squeeze busy buffer_writes buffer_reads".split()
M_OPS = "mul mulh mulhsu mulhu div divu rem remu".split()
STACK_TOP, STACK_BOTTOM = 131072 - 16, 131072 - 16 - 32768


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def key_values(line):
    pairs = re.findall(r"(\w+)=(-?0x[0-9a-fA-F]+|-?[0-9]+)", line)
    require(len({key for key, _ in pairs}) == len(pairs), "duplicate key in log record")
    return {key: int(value, 0) for key, value in pairs}


def single(lines, prefix):
    matches = [(index, line[len(prefix):]) for index, line in enumerate(lines) if line.startswith(prefix)]
    require(len(matches) == 1, f"expected exactly one {prefix} record, got {len(matches)}")
    return matches[0]


def payload_bytes(case, direction):
    return sum(len(bytes.fromhex(case[direction][name])) for name in case[direction + "_fields"])


def implicit_rejection(case):
    if case["op"] not in (3, 4):
        return None
    data = case["input"]
    z = bytes.fromhex(data["dk"][-64:] if case["op"] == 3 else data["z"])
    return hashlib.shake_256(z + bytes.fromhex(data["c"])).hexdigest(32) == case["output"]["k"]


def selected_cases(cases, original_indices):
    require(isinstance(original_indices, list) and original_indices and
            all(type(index) is int and 0 <= index < 145 for index in original_indices) and
            len(set(original_indices)) == len(original_indices), "invalid/duplicate original indices")
    canonical, _ = load_cases(ROOT, 1024)
    if isinstance(cases, dict):
        cases = cases["cases"]
    require(len(cases) in (145, len(original_indices)), "wrong supplied case count")
    selected = [cases[index] for index in original_indices] if len(cases) == 145 else cases
    for original, supplied in zip(original_indices, selected):
        official = canonical[original]
        require(all(supplied.get(key) == value for key, value in official.items() if key != "case_index"),
                f"case {original} differs from pinned official ACVP data")
    return [canonical[index] for index in original_indices]


def expected_hardware():
    """Map observed portable calls to deferred-absorb scalar HLS commands.

    The current driver transfers 52 context words before and after every
    command, plus rounded input/output words. CLEAR is not used by provider.
    """
    manifest = read_json(PROFILE / "manifest.json")
    for name in ("cases.json", "calls.csv"):
        require(manifest["output_sha256"][name] == sha(PROFILE / name), f"changed call profile: {name}")
    cases = read_json(PROFILE / "cases.json")
    official, _ = load_cases(ROOT, 1024)
    require(len(cases) == 145, "incomplete call profile")
    for index, (case, reference) in enumerate(zip(cases, official)):
        require(case["case_index"] == index and case["match"] is True and
                all(case[key] == reference[key] for key in ("dataset", "tgId", "tcId", "operation", "expected_return")) and
                case["actual_return"] == reference["expected_return"], f"bad call-profile identity {index}")
    with (PROFILE / "calls.csv").open(encoding="utf-8", newline="") as stream:
        events = list(csv.DictReader(stream))
    expected = {index: Counter() for index in range(145)}
    streams, seen_events = {}, Counter()
    for event in events:
        index, ways = int(event["case_index"]), int(event["lanes"])
        require(index in expected and ways in (1, 4), "invalid call-profile case or lanes")
        require(int(event["event_index"]) == seen_events[index], "call-profile event ordering mismatch")
        seen_events[index] += 1
        count = expected[index]
        count["scalar_permutations"] += int(event["scalar_permutations"])
        inlen, outlen = int(event["input_bytes_per_lane"]), int(event["output_bytes_per_lane"])
        stream = (index, int(event["stream_id"]))
        if event["phase"] == "absorb":
            streams[stream] = (inlen, ways)
            continue
        command = "hash"
        if event["phase"] == "squeeze":
            require(stream in streams and streams[stream][1] == ways, "squeeze has no absorb context")
            if int(event["squeeze_index"]) == 0:
                inlen = streams[stream][0]
            else:
                command = "squeeze"
        else:
            require(event["phase"] == "oneshot", "unknown call-profile phase")
        count[command] += ways
        count["starts"] += ways
        count["buffer_writes"] += ways * (52 + (inlen + 3) // 4)
        count["buffer_reads"] += ways * (52 + (outlen + 3) // 4)
    for index, case in enumerate(cases):
        require(seen_events[index] == case["fips202_api_calls"] and
                expected[index]["scalar_permutations"] == case["scalar_permutations"],
                f"call-profile totals mismatch {index}")
    return expected


def validate_cpu_row(row, case, index):
    require([row[name] for name in FIELDS[:6]] ==
            [index, *[case[name] for name in ("dataset_id", "vsId", "tgId", "tcId", "op")]],
            f"case identity/order mismatch: local {index}, official {case['case_index']}")
    require(row["return_code"] == case["expected_return"] and
            row["input_bytes"] == payload_bytes(case, "input") and
            row["output_bytes"] == payload_bytes(case, "output"), f"return/byte count mismatch: {index}")
    require(row["raw_cycles"] > row["empty_cycles"] > 0, f"invalid rdcycle interval: {index}")
    require(all(row[name] >= 0 for name in M_OPS) and row["m_total"] == sum(row[name] for name in M_OPS),
            f"invalid M instruction counts: {index}")
    require(case["op"] > 4 or row["mul"] > 0, f"missing expected RV32IM arithmetic: {index}")
    require(STACK_BOTTOM <= row["min_sp"] <= STACK_TOP and row["min_sp"] % 16 == 0,
            f"stack out of bounds: {index}")


def validate_log(text, cases, original_indices):
    """Return (CPU rows, hardware rows) only for a complete strict K4 log.

    cases accepts the canonical 145-case list/document or the selected list;
    official data are checked independently. Row indices are local to the log;
    returned case_index fields retain the canonical identities.
    """
    selected = selected_cases(cases, original_indices)
    expected = expected_hardware()
    require(not re.search(r"fatal:|\$fatal|ERROR:|MLKEM_FAIL|KECCAK\w*_FAIL", text, re.I), "log contains failure marker")
    lines = [line.strip() for line in text.splitlines()]
    header_pos, header = single(lines, "MLKEM_HEADER,")
    require(header.split(",") == FIELDS, "wrong MLKEM_HEADER columns")
    start_pos, start_text = single(lines, "MLKEM_START ")
    end_pos, end_text = single(lines, "MLKEM_PASS ")
    hw_end_pos, hw_end_text = single(lines, "KECCAK_PASS ")
    start, end, hw_end = map(key_values, (start_text, end_text, hw_end_text))
    require(tuple(start.get(k) for k in ("mul", "fast_mul", "div", "expect_m")) == (1, 1, 1, 1) and
            tuple(end.get(k) for k in ("cpu_mul", "cpu_fast_mul", "cpu_div", "expect_m")) == (1, 1, 1, 1),
            "wrong CPU configuration")
    require(start.get("cases") == end.get("cases") == hw_end.get("cases") == len(selected) and
            (start.get("ram_bytes"), start.get("stack_bytes"), start.get("clock_mhz")) == (131072, 32768, 100),
            "wrong case count/memory/clock")
    cpu_lines = [(i, line[len("MLKEM_ROW,"):]) for i, line in enumerate(lines) if line.startswith("MLKEM_ROW,")]
    hw_lines = [(i, line[len("KECCAK_ROW,"):]) for i, line in enumerate(lines) if line.startswith("KECCAK_ROW,")]
    require(len(cpu_lines) == len(hw_lines) == len(selected), "incomplete/duplicate CPU or hardware rows")
    require(header_pos < start_pos < min(cpu_lines[0][0], hw_lines[0][0]) and
            max(cpu_lines[-1][0], hw_lines[-1][0]) < min(end_pos, hw_end_pos), "invalid PASS/row ordering")
    rows, hardware = [], []
    for index, (case, cpu_line, hw_line) in enumerate(zip(selected, cpu_lines, hw_lines)):
        values, hw_values = cpu_line[1].split(","), hw_line[1].split(",")
        require(len(values) == len(FIELDS) and len(hw_values) == len(HARDWARE_FIELDS), f"wrong row columns: {index}")
        row = dict(zip(FIELDS, (int(value, 0) for value in values)))
        hw = dict(zip(HARDWARE_FIELDS, (int(value, 0) for value in hw_values)))
        validate_cpu_row(row, case, index)
        require(hw["index"] == index and all(hw[name] >= 0 for name in HARDWARE_FIELDS), f"invalid hardware row: {index}")
        wanted = expected[original_indices[index]]
        require(hw["starts"] == hw["done"] == hw["hash"] + hw["squeeze"] == wanted["starts"] and
                all(hw[name] == wanted[name] for name in ("hash", "squeeze", "buffer_writes", "buffer_reads")),
                f"hardware command/transfer count mismatch: official {original_indices[index]}")
        require((0 < hw["busy"] < row["raw_cycles"]) if hw["starts"] else
                all(hw[name] == 0 for name in HARDWARE_FIELDS[1:]), f"invalid busy/zero-call metrics: {index}")
        rows.append(dict(row, case_index=original_indices[index], operation=case["operation"],
                         expected_implicit_rejection=implicit_rejection(case)))
        hardware.append(dict(hw, case_index=original_indices[index]))
    require(all(end.get(name) == sum(row[name] for row in rows) for name in ("input_bytes", "output_bytes")),
            "wrong whole-run byte totals")
    require(end.get("cycles", 0) > sum(row["raw_cycles"] for row in rows) and
            end.get("all_m", -1) >= sum(row["m_total"] for row in rows), "wrong whole-run cycles/M totals")
    require(STACK_BOTTOM <= end.get("min_sp", -1) <= min(row["min_sp"] for row in rows) and
            end["min_sp"] % 16 == 0 and end.get("stack_used") == STACK_TOP - end["min_sp"], "wrong whole-run stack")
    require(all(hw_end.get(name) == sum(row[name] for row in hardware) for name in ("starts", "done", "hash", "squeeze")),
            "wrong KECCAK_PASS totals")
    for name in ("busy", "buffer_writes", "buffer_reads"):
        if name in hw_end:
            require(hw_end[name] == sum(row[name] for row in hardware), f"wrong optional hardware total: {name}")
    return rows, hardware


def under(directory, name):
    path = (directory / name).resolve()
    require(path.is_relative_to(directory.resolve()) and path != directory.resolve(), f"path escapes evidence: {name}")
    return path


def validate_attempt(directory, cases):
    manifest_path, result_path = directory / "manifest.json", directory / "result.json"
    manifest, result = read_json(manifest_path), read_json(result_path)
    require(result.get("passed") is True and result.get("exit_code") == 0 and
            result.get("input_manifest_sha256") == sha(manifest_path), "changed/unsuccessful success manifest")
    elapsed = result.get("elapsed_seconds")
    require(type(elapsed) in (int, float) and math.isfinite(elapsed) and elapsed >= 0, "invalid elapsed_seconds")
    require((manifest.get("parameter_set"), manifest.get("config"), manifest.get("ram_bytes"), manifest.get("stack_bytes")) ==
            (1024, "rv32im_fast", 131072, 32768), "wrong attempt configuration")
    indices = manifest["original_indices"]
    local = deepcopy(selected_cases(cases, indices))
    require(manifest.get("case_count") == len(local), "attempt case_count mismatch")
    require(isinstance(manifest.get("command"), list) and manifest["command"] and
            all(isinstance(part, str) for part in manifest["command"]), "missing simulator command")
    snapshot = Path(manifest["run_dir"]) / "snapshot"
    inputs = manifest["inputs"]
    required = {"rtl/picorv32.v", "rtl/keccak_mmio_adapter.sv", "rtl/mlkem1024_keccak_system.sv",
                "tb/tb_mlkem1024_keccak_kat.sv", "fixtures/mlkem1024.mem",
                "fixtures/mlkem1024_input.mem", "fixtures/mlkem1024_expected.mem",
                "hls/mlkem1024_keccak_accel.v", "build.json", "hls_selection.json", "run_kat.tcl"}
    require(isinstance(inputs, dict) and required <= inputs.keys(), "missing frozen simulation inputs")
    for name, info in inputs.items():
        generated_fixture = name in {"fixtures/mlkem1024_input.mem", "fixtures/mlkem1024_expected.mem"}
        require(isinstance(info.get("source"), str) and
                (Path(info["source"]).is_absolute() or
                 (generated_fixture and info["source"] == "Generated from pinned public ACVP cases")),
                f"missing source provenance: {name}")
        require(sha(under(snapshot, name)) == info["sha256"], f"changed frozen snapshot: {name}")
    build = read_json(snapshot / "build.json")
    require((build.get("parameter_set"), build.get("isa"), build.get("ram_bytes"), build.get("stack_reserved")) ==
            (1024, "rv32im", 131072, 32768) and build.get("excluded_software_fips202") is True and
            build.get("software_keccak_symbols") == [], "wrong hardware-only firmware build")
    require(sha(snapshot / "fixtures/mlkem1024.mem") == build["firmware_sha256"], "frozen firmware/build hash mismatch")
    require(build.get("source_sha256") and build.get("compiled_sources") and
            all("/src/fips202/" not in name for name in build["compiled_sources"]), "software FIPS202 compilation recorded")
    for name, expected in build["source_sha256"].items():
        relative = "source/" + name
        require(relative in inputs and inputs[relative]["sha256"] == expected and
                sha(under(snapshot, relative)) == expected, f"frozen build source mismatch: {name}")
    selection = read_json(snapshot / "hls_selection.json")["selected"]
    require(selection and "mlkem1024_keccak_accel.v" in selection, "missing selected HLS RTL")
    for name, info in selection.items():
        require("hls/" + name in inputs and sha(under(snapshot, "hls/" + name)) == info["raw_sha256"],
                f"HLS RTL differs from verified selection: {name}")
    output_hashes = result.get("output_sha256", {})
    require("simulate.log" in output_hashes, "success has no log hash")
    for name, expected in output_hashes.items():
        require(sha(under(directory, name)) == expected, f"changed result output: {name}")
    for index, case in enumerate(local):
        case["case_index"] = index
    for expected, suffix in ((False, "input"), (True, "expected")):
        path = snapshot / f"fixtures/mlkem1024_{suffix}.mem"
        words = [int(line, 16) for line in path.read_text(encoding="ascii").splitlines()]
        require(words == pack_fixture(deepcopy(local), 1024, expected), f"fixture is not exact official data: {suffix}")
    text = (directory / "simulate.log").read_text(encoding="utf-8", errors="replace")
    rows, hardware = validate_log(text, cases, indices)
    _, final_text = single([line.strip() for line in text.splitlines()], "MLKEM_PASS ")
    final = key_values(final_text)
    return rows, hardware, dict(path=str(directory), original_indices=indices,
                               elapsed_seconds=elapsed, manifest_sha256=sha(manifest_path),
                               result_sha256=sha(result_path), log_sha256=sha(directory / "simulate.log"),
                               observed_stack_bytes=final["stack_used"])


def read_baseline(cases):
    with BASELINE.open(encoding="utf-8", newline="") as stream:
        raw = list(csv.DictReader(stream))
    require(len(raw) == 145, "CPU baseline must contain all 145 cases")
    result = {}
    for item in raw:
        index = int(item["case_index"])
        require(0 <= index < 145 and index not in result and item["config"] == "rv32im_fast", "duplicate/wrong CPU baseline row")
        row = {name: int(item[name], 0) for name in FIELDS}
        validate_cpu_row(row, cases[index], row["index"])
        result[index] = row
    return result


def collect(results_dir=RESULTS, partial=False):
    cases, _ = load_cases(ROOT, 1024)
    baseline = read_baseline(cases)
    rows, attempts, ignored, seen = [], [], [], set()
    for result_path in sorted((results_dir / "batches").glob("*/*/result.json")):
        if read_json(result_path).get("passed") is not True:
            ignored.append(str(result_path.parent))
            continue
        cpu_rows, hardware, evidence = validate_attempt(result_path.parent, cases)
        for row, hw in zip(cpu_rows, hardware):
            index = row["case_index"]
            require(index not in seen, f"duplicate successful official case {index}; select disjoint attempts explicitly")
            seen.add(index)
            cycles, software = row["raw_cycles"], baseline[index]["raw_cycles"]
            rows.append(dict(row, **{name: hw[name] for name in HARDWARE_FIELDS[1:]},
                             software_cycles=software, accelerated_cycles=cycles,
                             speedup=software / cycles, busy_ratio=hw["busy"] / cycles,
                             other_api_cycles=cycles - hw["busy"], attempt=str(result_path.parent)))
        attempts.append(evidence)
    require(rows, "no validated successful attempts")
    require(partial or seen == set(range(145)), f"need 145 unique official cases, found {len(seen)}; use --partial for pilot")
    rows.sort(key=lambda row: row["case_index"])
    groups = defaultdict(list)
    for row in rows:
        groups[(row["operation"], row["return_code"])].append(row)
    aggregate = []
    for (operation, ret), group in sorted(groups.items()):
        sw, hw = [row["software_cycles"] for row in group], [row["accelerated_cycles"] for row in group]
        aggregate.append(dict(operation=operation, return_code=ret, cases=len(group),
                              software_cycles=sum(sw), accelerated_cycles=sum(hw),
                              accelerated_min=min(hw), accelerated_mean=statistics.mean(hw), accelerated_max=max(hw),
                              speedup_ratio_of_sums=sum(sw) / sum(hw),
                              busy_cycles=sum(row["busy"] for row in group)))
    summary = dict(status="PASS" if len(seen) == 145 else "PARTIAL", parameter_set=1024,
                   config="rv32im_fast", case_count=len(rows), expected_case_count=145,
                   original_indices=sorted(seen), missing_indices=sorted(set(range(145)) - seen),
                   generated_utc=datetime.now(timezone.utc).isoformat(), attempts=attempts,
                   ignored_unsuccessful_attempts=ignored, aggregate=aggregate,
                   software_cycles=sum(row["software_cycles"] for row in rows),
                   accelerated_cycles=sum(row["accelerated_cycles"] for row in rows),
                   starts=sum(row["starts"] for row in rows), squeeze=sum(row["squeeze"] for row in rows),
                   hardware_busy_cycles=sum(row["busy"] for row in rows),
                   buffer_write_words=sum(row["buffer_writes"] for row in rows),
                   buffer_read_words=sum(row["buffer_reads"] for row in rows),
                   batch_count=len(attempts),
                   total_run_elapsed_seconds=sum(attempt["elapsed_seconds"] for attempt in attempts),
                   observed_stack_bytes=max(attempt["observed_stack_bytes"] for attempt in attempts),
                   baseline=str(BASELINE.relative_to(ROOT)), baseline_sha256=sha(BASELINE),
                   profile_manifest_sha256=sha(PROFILE / "manifest.json"), collector_sha256=sha(Path(__file__)),
                   scope="PicoRV32 fast CPU plus real generated Keccak RTL, official K4 cases; not board measurement or certification",
                   timing="Raw rdcycle API intervals including CPU/MMIO work and zeroization; empty bracket retained; seed decapsulation includes key expansion. Busy cycles measure HLS activity; remaining API cycles also include transfers and CPU work, not pure transfer overhead.",
                   elapsed_scope="Sum of individual simulator run durations, including compilation/elaboration; not uninterrupted wall elapsed time.",
                   evidence_retention="Strict recollection requires every manifest run_dir/snapshot directory, retained outside Git. Log and manifest hashes alone cannot reconstruct frozen firmware, testbench or generated HLS inputs.")
    summary["speedup_ratio_of_sums"] = summary["software_cycles"] / summary["accelerated_cycles"]
    return rows, summary


def markdown(summary):
    lines = ["# ML-KEM-1024 CPU + Keccak official KAT", "",
             f"Status: **{summary['status']}**, {summary['case_count']}/145 unique official cases.", "",
             summary["scope"] + ".", "", summary["timing"], "",
             "| Operation | Return | Cases | CPU cycles | Accelerated cycles | Ratio of sums |",
             "|---|---:|---:|---:|---:|---:|"]
    for row in summary["aggregate"]:
        lines.append(f"| {row['operation']} | {row['return_code']} | {row['cases']} | {row['software_cycles']} | {row['accelerated_cycles']} | {row['speedup_ratio_of_sums']:.3f}x |")
    lines += ["", f"API cycle sums: CPU {summary['software_cycles']:,}; accelerated {summary['accelerated_cycles']:,}; ratio **{summary['speedup_ratio_of_sums']:.6f}x**. This ratio applies to this official case mix.",
              "", f"Hardware commands: {summary['starts']:,} starts, including {summary['squeeze']} continuation squeezes. HLS busy: {summary['hardware_busy_cycles']:,} cycles. Buffer transfers: {summary['buffer_write_words']:,} writes / {summary['buffer_read_words']:,} reads, in 32-bit words including context.",
              "", f"Completed batches: {summary['batch_count']}. Run-duration sum: {summary['total_run_elapsed_seconds']:,.3f} s. {summary['elapsed_scope']}",
              "", f"Maximum observed stack: {summary['observed_stack_bytes']:,} bytes, from verified final PASS records; not a worst-case bound.",
              "", "Only successful, hash-verified, disjoint attempts are included. Every result checks official identities, byte counts, returns, CPU configuration, measured boundaries and exact expected hardware command/transfer counts.",
              "", summary["evidence_retention"]]
    if summary["status"] == "PARTIAL":
        lines += ["", "This pilot does not establish full 145-case RTL coverage. Selected original indices: " + str(summary["original_indices"]) + "."]
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", type=Path, default=RESULTS)
    parser.add_argument("--partial", action="store_true", help="accept a validated pilot subset")
    parser.add_argument("--write", action="store_true", help="write aggregate tables (default read-only)")
    args = parser.parse_args(argv)
    try:
        rows, summary = collect(args.results_dir.resolve(), args.partial)
        if args.write:
            args.results_dir.mkdir(parents=True, exist_ok=True)
            (args.results_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
            (args.results_dir / "summary.md").write_text(markdown(summary), encoding="utf-8")
            with (args.results_dir / "cases.csv").open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
        print(f"KECCAK_KAT_COLLECT_{summary['status']} cases={len(rows)}/145 starts={summary['starts']}")
        return 0
    except (ValueError, KeyError, OSError) as error:
        print(f"KECCAK_KAT_COLLECT_FAIL {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
