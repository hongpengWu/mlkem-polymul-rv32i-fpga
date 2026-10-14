#!/usr/bin/env python3
"""Validate ML-KEM-512 profiling evidence and summarize exclusive/inclusive cycles.

The default requires all 145 pinned records. --partial is explicitly a bootstrap
report, never a replacement for the completed uninstrumented baseline.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import re
import statistics
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[2]
BASELINE = ROOT / "results/official_baseline/mlkem512"
RESULTS = BASELINE / "profile"
FIXTURES = ROOT / "tb/software/mlkem512_suite"
CONFIG = "rv32im_fast"
CASE_COUNT = 145
PHASE_COUNT = 64
FIELDS = ("index,dataset,vsId,tgId,tcId,op,return_code,raw_cycles,empty_cycles,"
          "input_bytes,output_bytes,m_total,mul,mulh,mulhsu,mulhu,div,divu,rem,remu,min_sp").split(",")
M_OPS = "mul mulh mulhsu mulhu div divu rem remu".split()
PROFILE_FIELDS = "index,phase,exclusive_cycles,inclusive_cycles,calls".split(",")
PROFILE_CASE_FIELDS = "index,cycles,accounted,enters,exits,max_depth".split(",")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_hash(path, wanted):
    require(isinstance(wanted, str) and re.fullmatch(r"[0-9a-f]{64}", wanted) and
            Path(path).is_file() and sha(path) == wanted, f"Changed or missing input: {path}")


def root_path(name):
    path = (ROOT / name).resolve()
    require(not Path(name).is_absolute() and path.is_relative_to(ROOT.resolve()),
            f"Expected repository-relative evidence path: {name}")
    return path


def relative(path):
    return Path(path).resolve().relative_to(ROOT.resolve()).as_posix()


def one_line(log, prefix):
    lines = [line[len(prefix):] for line in log.splitlines() if line.startswith(prefix)]
    require(len(lines) == 1, f"Expected one {prefix} record, got {len(lines)}")
    return lines[0]


def key_values(line):
    pairs = re.findall(r"(\w+)=(-?0x[0-9a-fA-F]+|-?[0-9]+)", line)
    require(len({key for key, _ in pairs}) == len(pairs), f"Duplicate fields: {line}")
    return {key: int(value, 0) for key, value in pairs}


def parse_row(line, fields, label):
    values = line.split(",")
    require(len(values) == len(fields), f"Malformed {label} row")
    try:
        return dict(zip(fields, (int(value, 0) for value in values)))
    except ValueError as error:
        raise ValueError(f"Noninteger {label} row") from error


def payload_bytes(case, direction):
    return sum(len(bytes.fromhex(case[direction][name])) for name in case[direction + "_fields"])


def expected_rejection(case):
    if case["op"] not in (3, 4):
        return None
    parts = [bytes.fromhex(case["input"][name]) for name in case["input_fields"]]
    z, ciphertext = (parts[0][-32:], parts[1]) if case["op"] == 3 else (parts[1], parts[2])
    expected_key = bytes.fromhex(case["output"][case["output_fields"][0]])
    return hashlib.shake_256(z + ciphertext).digest(32) == expected_key


def validate_fixture():
    fixture = read_json(FIXTURES / "cases.json")
    cases = fixture["cases"]
    require(fixture["parameterSet"] == "ML-KEM-512" and
            fixture["case_count"] == len(cases) == CASE_COUNT, "Wrong official fixture scope")
    require([case["case_index"] for case in cases] == list(range(CASE_COUNT)),
            "Noncanonical official indices")
    require(len({(c["dataset_id"], c["tgId"], c["tcId"]) for c in cases}) == CASE_COUNT,
            "Duplicate official identities")
    verify_hash(root_path(fixture["source"]["manifest"]), fixture["source"]["manifest_sha256"])
    for entry in fixture["source"]["files"]:
        verify_hash(root_path(entry["path"]), entry["sha256"])
    verify_hash(root_path(fixture["generator"]["path"]), fixture["generator"]["sha256"])
    for name, entry in fixture["fixture"]["files"].items():
        verify_hash(FIXTURES / name, entry["sha256"])
    for expected in (False, True):
        verify_batch_fixture(FIXTURES, cases, expected)
    return fixture


def phase_definitions(manifest):
    definitions = manifest["phase_map"]
    require(isinstance(definitions, list) and definitions, "Missing phase map")
    result = {}
    for entry in definitions:
        require(type(entry["id"]) is int and 0 <= entry["id"] < PHASE_COUNT and
                entry["id"] not in result, "Invalid or duplicate phase ID")
        require(all(isinstance(entry[name], str) and entry[name] for name in ("name", "category")),
                "Invalid phase name/category")
        require(all(isinstance(entry[name], str) for name in ("source", "function")),
                "Invalid phase source/function")
        result[entry["id"]] = entry
    require(0 in result and result[0]["name"] == "unclassified",
            "Phase map must include unclassified phase 0")
    return result


def reconstruct_patched_sources(patch, originals):
    """Apply exact unified-diff hunks in memory; no fuzz, tools or build cache needed."""
    lines = patch.splitlines(keepends=True)
    reconstructed, cursor = {}, 0
    while cursor < len(lines):
        require(lines[cursor].startswith("--- "), "Malformed instrumentation patch file header")
        name = lines[cursor][4:].rstrip("\r\n")
        cursor += 1
        require(cursor < len(lines) and lines[cursor] == "+++ " + name + "\n" and
                name in originals and name not in reconstructed,
                f"Unexpected or duplicate patch target: {name}")
        cursor += 1
        original = originals[name].read_text(encoding="utf-8").splitlines(keepends=True)
        output, consumed, hunks = [], 0, 0
        while cursor < len(lines) and not lines[cursor].startswith("--- "):
            match = re.fullmatch(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@[^\n]*\n",
                                 lines[cursor])
            require(match is not None, f"Malformed instrumentation patch hunk: {name}")
            old_start, old_count, new_start, new_count = match.groups()
            old_count = int(old_count) if old_count is not None else 1
            new_count = int(new_count) if new_count is not None else 1
            old_pos = int(old_start) - (1 if old_count else 0)
            new_pos = int(new_start) - (1 if new_count else 0)
            require(consumed <= old_pos <= len(original), f"Overlapping/out-of-range patch hunk: {name}")
            output.extend(original[consumed:old_pos])
            require(len(output) == new_pos, f"Wrong patch output position: {name}")
            consumed, old_seen, new_seen = old_pos, 0, 0
            cursor += 1
            while (cursor < len(lines) and lines[cursor][0:1] in (" ", "+", "-") and
                   not lines[cursor].startswith("--- ")):
                line = lines[cursor]
                if line[0] in " -":
                    require(consumed < len(original) and original[consumed] == line[1:],
                            f"Patch does not match original source: {name}")
                    consumed += 1
                    old_seen += 1
                if line[0] in " +":
                    output.append(line[1:])
                    new_seen += 1
                cursor += 1
            require(old_seen == old_count and new_seen == new_count,
                    f"Wrong instrumentation patch hunk size: {name}")
            hunks += 1
        require(hunks > 0, f"Empty instrumentation patch target: {name}")
        output.extend(original[consumed:])
        reconstructed[name] = "".join(output).encode("utf-8")
    return reconstructed


def validate_generated_sources(manifest, result_dir):
    """Verify archived source reconstruction, plus cache bytes whenever present."""
    patch_path = Path(result_dir) / "instrumentation.patch"
    verify_hash(patch_path, manifest["instrumentation_patch_sha256"])
    require(read_json(Path(result_dir) / "phase_map.json") == manifest["phase_map"],
            "Archived phase map differs from the build manifest")
    prefix = "build/mlkem512_profile/generated/"
    originals, entries = {}, {}
    for entry in manifest["generated_sources"]:
        name = entry["path"]
        require(name.startswith(prefix), f"Unexpected generated source path: {name}")
        target = name[len(prefix):]
        require(target not in entries, f"Duplicate generated source: {name}")
        if target.startswith("mlkem/"):
            source = "third_party/mlkem-native/" + target
        else:
            source = {"runtime.c": "firmware/mlkem_baseline/runtime.c",
                      "profile_main.c": "firmware/mlkem512_suite/kat_suite.c"}.get(target)
        require(source in manifest["source_sha256"], f"Missing original source provenance: {name}")
        originals[target], entries[target] = root_path(source), entry
    reconstructed = reconstruct_patched_sources(patch_path.read_text(encoding="utf-8"), originals)
    for target, entry in entries.items():
        data = reconstructed[target] if target in reconstructed else originals[target].read_bytes()
        require(hashlib.sha256(data).hexdigest() == entry["sha256"],
                f"Archived source reconstruction differs from build: {entry['path']}")
        cached = root_path(entry["path"])
        if cached.exists():
            verify_hash(cached, entry["sha256"])


def validate_manifest(manifest, result_dir=RESULTS):
    require(manifest["isa"] == "rv32im" and manifest["config"] == CONFIG,
            "Profiling requires the fixed rv32im_fast configuration")
    require(manifest["ram_bytes"] == 65536 and manifest["stack_reserved"] == 16384 and
            manifest["stack_top"] == 65520 and manifest["stack_bottom"] == 49136 and
            0 < manifest["binary_bytes"] <= manifest["static_end"] <= manifest["stack_bottom"],
            "Invalid 64 KiB memory/static/stack layout")
    require("-march=rv32im" in manifest["flags"] and "-mabi=ilp32" in manifest["flags"] and
            bool(manifest["compiler"]), "Wrong profile compiler ISA/ABI provenance")
    verify_hash(root_path(manifest["firmware"]), manifest["firmware_sha256"])
    for name, wanted in manifest["source_sha256"].items():
        verify_hash(root_path(name), wanted)
    require(bool(manifest["source_sha256"]) and bool(manifest["generated_sources"]),
            "Missing original/generated source provenance")
    validate_generated_sources(manifest, result_dir)
    frozen = manifest["baseline_paths_sha256"]
    required = {relative(BASELINE / "cases.csv"), relative(BASELINE / "summary.json"),
                relative(BASELINE / "build_manifest.json"), relative(FIXTURES / "cases.json")}
    require(required <= frozen.keys(), "Missing frozen baseline comparison provenance")
    for name, wanted in frozen.items():
        verify_hash(root_path(name), wanted)
    phase_definitions(manifest)


def verify_batch_fixture(directory, cases, expected):
    """Rebuild every header, metadata and payload word using the canonical cases."""
    direction = "output" if expected else "input"
    words = [0x3254414B, 1, 512, len(cases), 0, 0, 0, 0]
    for index, case in enumerate(cases):
        inputs = [len(bytes.fromhex(case["input"][name])) for name in case["input_fields"]]
        outputs = [len(bytes.fromhex(case["output"][name])) for name in case["output_fields"]]
        meta = [index] + [case[name] for name in ("dataset_id", "vsId", "tgId", "tcId", "op")]
        meta += inputs + [0] * (3 - len(inputs)) + outputs + [0] * (2 - len(outputs))
        meta += [case["expected_return"] & 0xffffffff if expected else 0]
        require(len(meta) == 12, "Invalid official fixture metadata")
        words.extend(meta)
        for name in case[direction + "_fields"]:
            payload = bytes.fromhex(case[direction][name])
            require(len(payload) % 4 == 0, "Unaligned official payload")
            words.extend(int.from_bytes(payload[pos:pos + 4], "little")
                         for pos in range(0, len(payload), 4))
    words[4] = len(words)
    path = Path(directory) / ("mlkem512_expected.mem" if expected else "mlkem512_input.mem")
    actual = [int(line, 16) for line in path.read_text(encoding="ascii").splitlines()]
    require(actual == words, f"Fixture differs from official cases: {path}")
    return len(words)


def validate_project_generics(path, count):
    tree = ET.parse(path)
    cpu = dict(CPU_ENABLE_MUL="1", CPU_ENABLE_FAST_MUL="1", CPU_ENABLE_DIV="1")
    for fileset, expected in (
        ("sources_1", dict(FIRMWARE_INIT_FILE="mlkem512.mem", RAM_ADDR_BITS="14", **cpu)),
        ("sim_1", dict(EXPECTED_CASES=str(count), EXPECT_M="1", PROFILE_PHASES=str(PHASE_COUNT), **cpu)),
    ):
        entries = tree.findall(f".//FileSet[@Name='{fileset}']//Generic")
        actual = {entry.get("Name"): entry.get("Val") for entry in entries}
        require(len(actual) == len(entries) and
                all(actual.get(key) == value for key, value in expected.items()),
                f"Wrong CPU/memory/case generics: {path}/{fileset}")


def parse_batch_log(path, manifest, cases):
    """Validate the testbench records; also usable before a runner writes success.json."""
    log = Path(path).read_text(encoding="utf-8")
    executable_lines = "\n".join(line for line in log.splitlines() if not line.startswith("#"))
    require(not re.search(r"(?i)fatal:|\$fatal|ERROR:|MLKEM512_FAIL|PROFILE_FAIL", executable_lines),
            f"Simulation failure in {path}")
    require(one_line(log, "MLKEM512_HEADER,").split(",") == FIELDS, "Wrong API row columns")
    require(one_line(log, "PROFILE_HEADER,").split(",") == PROFILE_FIELDS, "Wrong phase columns")
    require(one_line(log, "PROFILE_CASE_HEADER,").split(",") == PROFILE_CASE_FIELDS,
            "Wrong profile case columns")
    start = key_values(one_line(log, "MLKEM512_START "))
    end = key_values(one_line(log, "MLKEM512_PASS "))
    require(tuple(start[name] for name in ("mul", "fast_mul", "div", "expect_m")) == (1, 1, 1, 1) and
            tuple(end[name] for name in ("cpu_mul", "cpu_fast_mul", "cpu_div", "expect_m")) == (1, 1, 1, 1),
            "Start/completion CPU configuration differs from rv32im_fast")
    require(start["cases"] == end["cases"] == len(cases) and
            start["ram_bytes"] == manifest["ram_bytes"] == 65536 and
            start["stack_bytes"] == manifest["stack_reserved"] == 16384 and
            start["clock_mhz"] == 100, "Wrong count, memory or clock")
    lines = log.splitlines()
    records = {prefix: [(pos, line[len(prefix):]) for pos, line in enumerate(lines)
                        if line.startswith(prefix)] for prefix in
               ("MLKEM512_ROW,", "PROFILE_ROW,", "PROFILE_CASE,")}
    require(len(records["MLKEM512_ROW,"]) == len(cases) and
            len(records["PROFILE_ROW,"]) == len(cases) * PHASE_COUNT and
            len(records["PROFILE_CASE,"]) == len(cases), "Incomplete or duplicate profile/API records")
    start_pos = next(pos for pos, line in enumerate(lines) if line.startswith("MLKEM512_START "))
    end_pos = next(pos for pos, line in enumerate(lines) if line.startswith("MLKEM512_PASS "))
    require(all(start_pos < pos < end_pos for group in records.values() for pos, _ in group),
            "Profile/API records appear outside the completed run")
    definitions = phase_definitions(manifest)
    rows, phase_rows = [], []
    for index, ((_, line), case) in enumerate(zip(records["MLKEM512_ROW,"], cases)):
        label = f"{Path(path).parent.name}/{case['case_index']}"
        row = parse_row(line, FIELDS, label)
        wanted = [index] + [case[name] for name in ("dataset_id", "vsId", "tgId", "tcId", "op")]
        require([row[name] for name in FIELDS[:6]] == wanted, f"Wrong case identity/order: {label}")
        require(row["return_code"] == case["expected_return"], f"API return mismatch: {label}")
        require(row["input_bytes"] == payload_bytes(case, "input") and
                row["output_bytes"] == payload_bytes(case, "output"), f"Incomplete byte comparison: {label}")
        require(row["raw_cycles"] > row["empty_cycles"] > 0, f"Invalid cycles: {label}")
        require(all(row[op] >= 0 for op in M_OPS) and row["m_total"] == sum(row[op] for op in M_OPS),
                f"M opcode sum mismatch: {label}")
        # Early key-check rejection can execute no M instructions.
        require(row["mul"] > 0 if case["op"] in (1, 2, 3, 4) else True,
                f"No multiply executed by full KEM API: {label}")
        require(manifest["stack_bottom"] <= end["min_sp"] <= row["min_sp"] <= manifest["stack_top"] and
                row["min_sp"] % 16 == 0, f"Stack outside reservation: {label}")
        profile = parse_row(records["PROFILE_CASE,"][index][1], PROFILE_CASE_FIELDS, label)
        require(profile["index"] == index and
                profile["cycles"] == profile["accounted"] == row["raw_cycles"],
                f"Profile interval does not match raw API cycles: {label}")
        group = [parse_row(item, PROFILE_FIELDS, label) for _, item in
                 records["PROFILE_ROW,"][index * PHASE_COUNT:(index + 1) * PHASE_COUNT]]
        require([phase["phase"] for phase in group] == list(range(PHASE_COUNT)) and
                all(phase["index"] == index for phase in group), f"Missing/duplicate phase IDs: {label}")
        for phase in group:
            phase_id = phase["phase"]
            excl, incl, calls = [phase[key] for key in PROFILE_FIELDS[2:]]
            require(0 <= excl <= incl and calls >= 0, f"Invalid phase counters: {label}/{phase_id}")
            if phase_id == 0:
                require(incl == excl and calls == 0, f"Wrong unclassified accounting: {label}")
            else:
                require(calls > 0 or excl == incl == 0, f"Uncalled phase has cycles: {label}/{phase_id}")
                require(phase_id in definitions or excl == incl == calls == 0,
                        f"Executed unmapped phase: {label}/{phase_id}")
            if phase_id in definitions:
                definition = definitions[phase_id]
                phase_rows.append(dict(config=CONFIG, index=case["case_index"], source_local_index=index,
                                       dataset=case["dataset_id"], vsId=case["vsId"], tgId=case["tgId"],
                                       tcId=case["tcId"], op=case["op"], operation=case["operation"],
                                       return_code=case["expected_return"], phase=phase_id,
                                       name=definition["name"], category=definition["category"],
                                       source=definition["source"], function=definition["function"],
                                       exclusive_cycles=excl, inclusive_cycles=incl, calls=calls,
                                       exclusive_share_percent=100 * excl / row["raw_cycles"]))
        require(sum(p["exclusive_cycles"] for p in group) == row["raw_cycles"],
                f"Exclusive phases do not cover complete API interval: {label}")
        calls = sum(p["calls"] for p in group)
        require(profile["enters"] == profile["exits"] == calls and
                (1 <= profile["max_depth"] <= calls if calls else profile["max_depth"] == 0),
                f"Unbalanced markers or invalid nesting depth: {label}")
        rows.append(dict(config=CONFIG, **dict(row, index=case["case_index"]),
                         source_local_index=index, original_case_index=case["case_index"],
                         operation=case["operation"], dataset_name=case["dataset"], revision=case["revision"],
                         expected_implicit_rejection=expected_rejection(case),
                         observed_algorithm_stack_bytes=manifest["stack_top"] - row["min_sp"],
                         profile_accounted_cycles=profile["accounted"], profile_enters=profile["enters"],
                         profile_exits=profile["exits"], profile_max_depth=profile["max_depth"]))
    require(end["input_bytes"] == sum(row["input_bytes"] for row in rows) and
            end["output_bytes"] == sum(row["output_bytes"] for row in rows), "Incomplete batch byte totals")
    require(end["cycles"] > sum(row["raw_cycles"] for row in rows) and
            end["all_m"] >= sum(row["m_total"] for row in rows), "Invalid whole-batch cycles/M count")
    require(end["min_sp"] % 16 == 0 and end["stack_used"] == manifest["stack_top"] - end["min_sp"],
            "Whole-batch stack accounting mismatch")
    return rows, phase_rows, dict(config=CONFIG, cases=len(rows), input_bytes=end["input_bytes"],
                                 output_bytes=end["output_bytes"], total_sim_cycles=end["cycles"],
                                 timed_cycles=sum(row["raw_cycles"] for row in rows), all_m=end["all_m"],
                                 timed_m=sum(row["m_total"] for row in rows),
                                 observed_stack_bytes=end["stack_used"], log_sha256=sha(path))


def validate_batch(directory, manifest, cases):
    """Return (API rows, mapped phase rows, metrics), checking the archived evidence."""
    directory = Path(directory)
    validate_manifest(manifest, directory.parents[1])
    require(len(cases) == CASE_COUNT and [c["case_index"] for c in cases] == list(range(CASE_COUNT)),
            "validate_batch requires all canonical cases, not a selected subset")
    require(cases == read_json(FIXTURES / "cases.json")["cases"],
            "Supplied cases differ from the pinned canonical fixture")
    require(manifest == read_json(directory.parents[1] / "build_manifest.json"),
            "Supplied build manifest differs from the archived profile build")
    batch_path = directory / "batch.json"
    batch = read_json(batch_path)
    indices = batch["original_indices"]
    require(isinstance(indices, list) and indices and all(type(i) is int for i in indices) and
            indices == sorted(set(indices)) and all(0 <= i < len(cases) for i in indices),
            f"Invalid batch original indices: {directory}")
    require(directory.name == f"batch_{indices[0]:03d}_{indices[-1]:03d}" and
            batch["case_count"] == len(indices) and batch["config"] == CONFIG and
            batch["schema_version"] == 1, f"Wrong batch name/count/configuration: {directory}")
    selected = [cases[index] for index in indices]
    require(batch["input_words"] == verify_batch_fixture(directory, selected, False) and
            batch["expected_words"] == verify_batch_fixture(directory, selected, True) and
            batch["input_bytes"] == sum(payload_bytes(c, "input") for c in selected) and
            batch["output_bytes"] == sum(payload_bytes(c, "output") for c in selected),
            f"Batch sizes differ from official payloads: {directory}")
    run_path, log_path = directory / "run_inputs.json", directory / "simulate.log"
    success = read_json(directory / "success.json")
    require(success["status"] == "passed" and success["case_count"] == len(selected),
            f"No successful batch completion: {directory}")
    for path, key in ((batch_path, "batch_sha256"), (run_path, "run_inputs_sha256"), (log_path, "log_sha256"),
                      (directory / "project.xpr", "project_sha256"),
                      (directory / "staged_hashes.json", "staged_hashes_sha256")):
        verify_hash(path, success[key])
    run = read_json(run_path)
    require(run["config"] == CONFIG and run["ram_bytes"] == 65536 and
            run["simulator"] == "Vivado/XSim 2024.2", f"Wrong run provenance: {directory}")
    hashes = run["input_sha256"]
    required = {"rtl/cpu/picorv32.v", "rtl/benchmark/cpu_benchmark_system.v",
                "tb/software/tb_mlkem512_profile.sv", "scripts/mlkem512_suite/sim.tcl",
                relative(FIXTURES / "cases.json"),
                relative(directory.parents[1] / "build_manifest.json"), manifest["firmware"]}
    required.update(relative(directory / name) for name in
                    ("batch.json", "mlkem512_input.mem", "mlkem512_expected.mem"))
    require(required <= hashes.keys(), f"Missing frozen simulation inputs: {directory}")
    require(any(name.endswith(".py") and "scripts/mlkem512_profile/" in name for name in hashes) and
            any(name.endswith(".tcl") and "scripts/mlkem512_profile/" in name for name in hashes),
            f"Missing profile runner provenance: {directory}")
    for name, wanted in hashes.items():
        verify_hash(root_path(name), wanted)
    require(hashes[manifest["firmware"]] == manifest["firmware_sha256"], "Different simulated firmware")
    staged = read_json(directory / "staged_hashes.json")
    expected_staged = {"mlkem512.mem": manifest["firmware_sha256"],
                       **{name: sha(directory / name) for name in
                          ("mlkem512_input.mem", "mlkem512_expected.mem", "simulate.log")}}
    require(staged == expected_staged, f"Staged firmware/fixture/log hashes differ: {directory}")
    validate_project_generics(directory / "project.xpr", len(selected))
    rows, phases, metrics = parse_batch_log(log_path, manifest, selected)
    for row in rows + phases:
        row["source_chunk"] = directory.name
    evidence = {relative(directory / name): sha(directory / name) for name in
                ("batch.json", "run_inputs.json", "success.json", "simulate.log", "project.xpr",
                 "staged_hashes.json", "mlkem512_input.mem", "mlkem512_expected.mem")}
    metrics.update(batch=directory.name, original_indices=indices, evidence_sha256=evidence)
    return rows, phases, metrics


def baseline_rows(cases):
    """Read the retained uninstrumented results keyed by exact original identity."""
    with (BASELINE / "cases.csv").open(encoding="utf-8", newline="") as stream:
        records = [row for row in csv.DictReader(stream) if row["config"] == CONFIG]
    require(len(records) == CASE_COUNT, "Incomplete rv32im_fast baseline comparison")
    result = {}
    for record in records:
        row = {name: int(record[name], 0) for name in FIELDS}
        index = row["index"]
        require(0 <= index < CASE_COUNT and index not in result, "Duplicate/invalid baseline identity")
        case = cases[index]
        wanted = [case[name] for name in ("case_index", "dataset_id", "vsId", "tgId", "tcId", "op")]
        require([row[name] for name in FIELDS[:6]] == wanted and
                row["return_code"] == case["expected_return"] and
                row["input_bytes"] == payload_bytes(case, "input") and
                row["output_bytes"] == payload_bytes(case, "output"), "Baseline official identity mismatch")
        require(row["raw_cycles"] > row["empty_cycles"] > 0 and
                all(row[name] >= 0 for name in M_OPS) and
                row["m_total"] == sum(row[name] for name in M_OPS), "Invalid baseline counters")
        result[index] = row
    return result


def statistics_for(values):
    ordered = sorted(values)
    return dict(min=min(values), mean=statistics.mean(values), median=statistics.median(values),
                p95=ordered[math.ceil(.95 * len(values)) - 1], max=max(values))


def summarize_group(rows, phases, definitions):
    cycles = sum(row["raw_cycles"] for row in rows)
    baseline = sum(row["baseline_raw_cycles"] for row in rows)
    categories, by_phase = {}, []
    for phase_id, definition in sorted(definitions.items()):
        members = [row for row in phases if row["phase"] == phase_id]
        exclusive = sum(row["exclusive_cycles"] for row in members)
        category = "Other" if phase_id == 0 else definition["category"]
        categories[category] = categories.get(category, 0) + exclusive
        by_phase.append(dict(**definition, exclusive_cycles=exclusive,
                             inclusive_cycles=sum(row["inclusive_cycles"] for row in members),
                             calls=sum(row["calls"] for row in members),
                             exclusive_share_percent=100 * exclusive / cycles))
    require(sum(categories.values()) == cycles, "Category accounting does not cover the API interval")
    category_rows = [dict(category=name, exclusive_cycles=value, exclusive_share_percent=100 * value / cycles)
                     for name, value in sorted(categories.items())]
    return dict(cases=len(rows), input_bytes=sum(row["input_bytes"] for row in rows),
                output_bytes=sum(row["output_bytes"] for row in rows), profiled_raw_cycles=cycles,
                baseline_raw_cycles=baseline, delta_cycles=cycles - baseline,
                overhead_percent=100 * (cycles - baseline) / baseline,
                cycle_statistics=statistics_for([row["raw_cycles"] for row in rows]),
                delta_statistics=statistics_for([row["delta_cycles"] for row in rows]),
                same_m_cases=sum(row["same_m"] for row in rows),
                observed_algorithm_stack_max=max(row["observed_algorithm_stack_bytes"] for row in rows),
                phases=by_phase, categories=category_rows,
                exclusive_share_sum_percent=sum(row["exclusive_share_percent"] for row in category_rows))


def collect(result_dir=RESULTS, partial=False):
    result_dir = Path(result_dir).resolve()
    fixture = validate_fixture()
    cases = fixture["cases"]
    manifest = read_json(result_dir / "build_manifest.json")
    validate_manifest(manifest, result_dir)
    baseline = baseline_rows(cases)
    rows, phases, batches = [], [], []
    directories = sorted((result_dir / "batches").glob("batch_*"))
    require(directories, "No profiling batches exist")
    incomplete = []
    for directory in directories:
        if not (directory / "success.json").is_file():
            incomplete.append(directory.name)
            continue
        parsed, phase_rows, metrics = validate_batch(directory, manifest, cases)
        rows.extend(parsed)
        phases.extend(phase_rows)
        batches.append(metrics)
    indices = [row["index"] for row in rows]
    require(rows and len(indices) == len(set(indices)), "No successful cases or duplicate profiled cases")
    missing = sorted(set(range(CASE_COUNT)) - set(indices))
    require(partial or (not missing and not incomplete),
            f"Incomplete profiling: {len(rows)}/{CASE_COUNT}; use --partial only for a labeled bootstrap report")
    rows.sort(key=lambda row: row["index"])
    phases.sort(key=lambda row: (row["index"], row["phase"]))
    for row in rows:
        base = baseline[row["index"]]
        delta = row["raw_cycles"] - base["raw_cycles"]
        row.update(baseline_raw_cycles=base["raw_cycles"], delta_cycles=delta,
                   overhead_percent=100 * delta / base["raw_cycles"],
                   baseline_m_total=base["m_total"], same_m=all(row[name] == base[name] for name in M_OPS))
        row.update({"baseline_" + name: base[name] for name in M_OPS})
    definitions = phase_definitions(manifest)
    by_api, by_dataset = [], []
    for dataset in (None, *sorted({row["dataset"] for row in rows})):
        for op, ret in sorted({(row["op"], row["return_code"]) for row in rows
                               if dataset is None or row["dataset"] == dataset}):
            members = [row for row in rows if row["op"] == op and row["return_code"] == ret and
                       (dataset is None or row["dataset"] == dataset)]
            selected = {row["index"] for row in members}
            entry = dict(op=op, operation=members[0]["operation"], return_code=ret,
                         **summarize_group(members, [p for p in phases if p["index"] in selected], definitions))
            if dataset is None:
                by_api.append(entry)
            else:
                entry.update(dataset_id=dataset, dataset=members[0]["dataset_name"], revision=members[0]["revision"])
                by_dataset.append(entry)
    evidence = {relative(path): sha(path) for path in
                (Path(__file__), result_dir / "build_manifest.json", result_dir / "instrumentation.patch",
                 result_dir / "phase_map.json", FIXTURES / "cases.json",
                 BASELINE / "cases.csv", BASELINE / "summary.json")}
    for batch in batches:
        evidence.update(batch["evidence_sha256"])
    complete = not missing and not incomplete
    summary = dict(schema_version=1, config=CONFIG, status="complete" if complete else "partial_bootstrap",
                   scope=f"{len(rows)}/145 pinned official ML-KEM-512 records; " +
                         ("complete profiling suite" if complete else "PARTIAL BOOTSTRAP ONLY"),
                   case_count=len(rows), expected_case_count=CASE_COUNT, missing_indices=missing,
                   incomplete_batches=incomplete, firmware_sha256=manifest["firmware_sha256"],
                   compiler=manifest["compiler"], flags=manifest["flags"],
                   ram_bytes=manifest["ram_bytes"], binary_bytes=manifest["binary_bytes"],
                   static_end=manifest["static_end"], stack_reserved=manifest["stack_reserved"],
                   acvp_commit=fixture["source"]["commit"],
                   timing="Raw rdcycle API interval, empty bracket retained without subtraction; seed decapsulation includes key expansion. Exclusive phases, including Other/unclassified, partition this exact interval.",
                   inclusive_timing="Inclusive cycles include nested phases and overlap; never sum them or interpret their sum as a runtime share.",
                   overhead="Per-case delta versus the identical original rv32im_fast official record. It includes marker execution and compiler/code-layout perturbation; it is not a pure marker cost. Profiled cycles are diagnostic, not a new performance baseline.",
                   statistics="One execution per official record. Key-check valid/invalid returns and dataset revisions remain separate. P95 is nearest rank. M counts are compared, not required identical because instrumentation may alter code generation.",
                   limitations="RTL simulation only, not board timing or certification. Observed stack use is not a worst-case bound. No synthetic whole-suite runtime is inferred from separate batches.",
                   totals=summarize_group(rows, phases, definitions), by_api=by_api, by_dataset=by_dataset,
                   phase_map=manifest["phase_map"], batches=batches, evidence_sha256=evidence)
    return summary, rows, phases


def markdown(summary):
    lines = ["# ML-KEM-512 phase profile", "", summary["scope"] + ".", "",
             "Configuration: rv32im_fast, 64 KiB RAM; profiling firmware is separate from the retained baseline.",
             "", summary["timing"], "", summary["inclusive_timing"], "", summary["overhead"], "",
             "## Instrumentation and compiler overhead", "",
             "| API / return | N | Baseline cycles | Profiled cycles | Delta cycles | Delta % | Same M counts |",
             "|---|---:|---:|---:|---:|---:|---:|"]
    for item in summary["by_api"]:
        lines.append(f"| {item['operation']} / {item['return_code']} | {item['cases']} | "
                     f"{item['baseline_raw_cycles']:,} | {item['profiled_raw_cycles']:,} | "
                     f"{item['delta_cycles']:+,} | {item['overhead_percent']:+.3f}% | "
                     f"{item['same_m_cases']}/{item['cases']} |")
    for item in summary["by_api"]:
        lines += ["", f"## {item['operation']} / return {item['return_code']}", "",
                  "Exclusive categories partition the API interval; their shares sum to 100% before rounding.", "",
                  "| Category | Exclusive cycles | Exclusive share |", "|---|---:|---:|"]
        for category in item["categories"]:
            lines.append(f"| {category['category']} | {category['exclusive_cycles']:,} | "
                         f"{category['exclusive_share_percent']:.4f}% |")
        lines += ["", "Inclusive values below overlap and must not be added.", "",
                  "| Phase | Category | Calls | Exclusive cycles | Exclusive share | Inclusive cycles |",
                  "|---|---|---:|---:|---:|---:|"]
        for phase in item["phases"]:
            lines.append(f"| {phase['id']}: {phase['name']} | {phase['category']} | {phase['calls']:,} | "
                         f"{phase['exclusive_cycles']:,} | {phase['exclusive_share_percent']:.4f}% | "
                         f"{phase['inclusive_cycles']:,} |")
    lines += ["", summary["statistics"], "", summary["limitations"], "",
              "`cases.csv` contains matched baseline deltas and opcode counts; `phases.csv` contains each mapped "
              "phase per case. `summary.json` retains dataset groups, phase definitions and evidence SHA-256 hashes.", ""]
    if summary["status"] != "complete":
        lines += ["**PARTIAL BOOTSTRAP: full-suite profiling has not completed.**", "",
                  "Missing original indices: " + ", ".join(map(str, summary["missing_indices"])), ""]
    return "\n".join(lines)


def write_csv(path, rows):
    with Path(path).open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result-dir", type=Path, default=RESULTS)
    parser.add_argument("--partial", action="store_true", help="allow a clearly labeled bootstrap subset")
    parser.add_argument("--check", action="store_true", help="validate without rewriting reports")
    args = parser.parse_args()
    summary, rows, phases = collect(args.result_dir, args.partial)
    if not args.check:
        (args.result_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        (args.result_dir / "summary.md").write_text(markdown(summary), encoding="utf-8")
        write_csv(args.result_dir / "cases.csv", rows)
        write_csv(args.result_dir / "phases.csv", phases)
    print(f"MLKEM512_PROFILE_COLLECT_PASS status={summary['status']} cases={len(rows)}/145 "
          f"batches={len(summary['batches'])}")


if __name__ == "__main__":
    main()
