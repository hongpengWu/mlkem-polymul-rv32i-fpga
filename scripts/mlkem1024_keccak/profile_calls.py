#!/usr/bin/env python3
"""Run all 145 official K4 cases and count portable FIPS202 call shapes.

This measures host algorithmic work, never PicoRV32 cycles. Only a generated
copy under build/ is instrumented; vendor and baseline bytes are verified and
left untouched. Requires Python 3 and a host GCC-compatible C compiler.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import ctypes
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/kat"))
from package_mlkem import load_cases  # noqa: E402

MODES = ("SHAKE128", "SHAKE256", "SHA3-256", "SHA3-512")
RATES = (168, 136, 136, 72)
PHASES = ("absorb", "squeeze", "oneshot")

# The counter increments inside actual scalar permutation entry points. x4
# permutation calls are separately counted, and already include four scalar
# entries in the portable backend; they must NOT be added a second time.
RECORDER = r"""
#include <stdint.h>
#include <stdlib.h>
static uint64_t trace_events[4096][8];
static uint64_t trace_count, trace_scalar, trace_x4;
static void trace_call(uint64_t mode, uint64_t phase, uint64_t ways,
                       uint64_t inlen, uint64_t outlen, const void *ctx) {
  uint64_t *event;
  if (trace_count == 4096) abort();
  event = trace_events[trace_count++];
  event[0] = mode; event[1] = phase; event[2] = ways;
  event[3] = inlen; event[4] = outlen; event[5] = (uintptr_t)ctx;
  event[6] = trace_scalar; event[7] = trace_x4;
}
void profile_reset(void) { trace_count = trace_scalar = trace_x4 = 0; }
uint64_t profile_count(void) { return trace_count; }
uint64_t profile_scalar(void) { return trace_scalar; }
uint64_t profile_x4(void) { return trace_x4; }
uint64_t profile_get(uint64_t i, uint64_t j) {
  if (i >= trace_count || j >= 8) abort();
  return trace_events[i][j];
}
"""


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, document):
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8", newline="\n")


def insert_entry(source, function, statement):
    """Pinned public definitions have no contract between signature and body."""
    pattern = rf"(\bvoid\s+{function}\s*\([^;{{}}]*\)\s*\{{)"
    changed, count = re.subn(pattern, lambda match: match[0] + "\n  " + statement,
                             source, flags=re.MULTILINE)
    require(count == 1, f"expected one definition for {function}, got {count}")
    return changed


def build_library(build, compiler):
    vendor = ROOT / "third_party/mlkem-native"
    generated = build / "vendor"
    shutil.copytree(vendor, generated, dirs_exist_ok=True)
    hooks = {
        "fips202.c": {
            "mlk_shake128_absorb_once": "trace_call(0, 0, 1, inlen, 0, state);",
            "mlk_shake128_squeezeblocks": "trace_call(0, 1, 1, 0, nblocks * SHAKE128_RATE, state);",
            "mlk_shake256": "trace_call(1, 2, 1, inlen, outlen, 0);",
            "mlk_sha3_256": "trace_call(2, 2, 1, inlen, 32, 0);",
            "mlk_sha3_512": "trace_call(3, 2, 1, inlen, 64, 0);",
        },
        "fips202x4.c": {
            "mlk_shake128x4_absorb_once": "trace_call(0, 0, 4, inlen, 0, state);",
            "mlk_shake128x4_squeezeblocks": "trace_call(0, 1, 4, 0, nblocks * SHAKE128_RATE, state);",
            "mlk_shake256x4": "trace_call(1, 2, 4, inlen, outlen, 0);",
        },
        "keccakf1600.c": {
            "mlk_keccakf1600_permute": "++trace_scalar;",
            "mlk_keccakf1600x4_permute": "++trace_x4;",
        },
    }
    for filename, functions in hooks.items():
        path = generated / "mlkem/src/fips202" / filename
        source = path.read_text(encoding="utf-8")
        for name, statement in functions.items():
            source = insert_entry(source, name, statement)
        path.write_text(source, encoding="utf-8", newline="\n")
    recorder = build / "profile_runner.c"
    recorder.write_text(RECORDER + '\n#include "vendor/mlkem/mlkem_native.c"\n',
                        encoding="utf-8", newline="\n")
    library = build / ("profile.dll" if os.name == "nt" else "profile.so")
    command = [compiler, "-shared", "-O2", "-std=c11", "-Wall", "-Wextra", "-Werror",
               "-I", str(ROOT / "firmware/mlkem_suite"),
               "-I", str(generated / "mlkem"), "-DMLK_CONFIG_FILE=<mlkem_config.h>",
               "-DMLKEM_LEVEL=1024", "-DMLKEM_NAMESPACE=pico_mlkem1024"]
    if os.name != "nt":
        command.append("-fPIC")
    command.extend([str(recorder), "-o", str(library)])
    process = subprocess.run(command, text=True, capture_output=True, cwd=ROOT)
    require(process.returncode == 0, f"host build failed:\n{process.stdout}{process.stderr}")
    version = subprocess.check_output([compiler, "--version"], text=True).splitlines()[0]
    return library, {
        "compiler": version, "command": command,
        "stdout": process.stdout, "stderr": process.stderr,
        "generated_sha256": {p.relative_to(build).as_posix(): digest(p) for p in
                             [recorder, *[generated / "mlkem/src/fips202" / name for name in hooks]]},
        "library_sha256": digest(library),
    }


def bind_library(path):
    lib = ctypes.CDLL(str(path))
    for name in ("profile_count", "profile_scalar", "profile_x4"):
        getattr(lib, name).argtypes = []
        getattr(lib, name).restype = ctypes.c_uint64
    lib.profile_reset.argtypes = []
    lib.profile_reset.restype = None
    lib.profile_get.argtypes = [ctypes.c_uint64, ctypes.c_uint64]
    lib.profile_get.restype = ctypes.c_uint64
    for name, arity in (("keypair_derand", 3), ("enc_derand", 4), ("dec", 3),
                        ("check_pk", 1), ("check_sk", 1)):
        function = getattr(lib, "pico_mlkem1024_" + name)
        function.argtypes = [ctypes.POINTER(ctypes.c_uint8)] * arity
        function.restype = ctypes.c_int
    return lib


def run_case(lib, case):
    def buffer(data):
        return (ctypes.c_uint8 * len(data)).from_buffer_copy(data)

    api = lambda name: getattr(lib, "pico_mlkem1024_" + name)
    inputs = {key: buffer(bytes.fromhex(value)) for key, value in case["input"].items()}
    pk, sk, ct, ss = ((ctypes.c_uint8 * size)() for size in (1568, 3168, 1568, 32))
    lib.profile_reset()
    op = case["operation"]
    split = None
    if op in ("keyGen", "decapsulationSeed"):
        coins = buffer(bytes(inputs["d"]) + bytes(inputs["z"]))
        result = api("keypair_derand")(pk, sk, coins)
        output = {"ek": bytes(pk), "dk": bytes(sk)}
        if op == "decapsulationSeed":
            require(result == 0, "seed expansion failed")
            split = lib.profile_count()
            result = api("dec")(ss, inputs["c"], sk)
            output = {"k": bytes(ss)}
    elif op == "encapsulation":
        result = api("enc_derand")(ct, ss, inputs["ek"], inputs["m"])
        output = {"c": bytes(ct), "k": bytes(ss)}
    elif op == "decapsulation":
        result = api("dec")(ss, inputs["c"], inputs["dk"])
        output = {"k": bytes(ss)}
    else:
        field, function = (("ek", "check_pk") if op == "encapsulationKeyCheck"
                           else ("dk", "check_sk"))
        result = api(function)(inputs[field])
        output = {}
    require(result == case["expected_return"], f"case {case['case_index']}: return mismatch")
    for name, actual in output.items():
        require(actual.hex() == case["output"][name], f"case {case['case_index']}: {name} mismatch")
    raw = [[lib.profile_get(i, j) for j in range(8)] for i in range(lib.profile_count())]
    raw.append([0] * 6 + [lib.profile_scalar(), lib.profile_x4()])
    events, streams, next_stream = [], {}, 0
    for index, row in enumerate(raw[:-1]):
        mode, phase, ways, inlen, outlen, ctx, scalar, x4 = row
        count = raw[index + 1][6] - scalar
        vector_count = raw[index + 1][7] - x4
        formula = ways * (inlen // RATES[mode] + (outlen + RATES[mode] - 1) // RATES[mode])
        require(count == formula, f"case {case['case_index']}, event {index}: permutation count mismatch")
        require(vector_count == (count // 4 if ways == 4 else 0), "x4 counter mismatch")
        stream, sequence = -1, -1
        if phase == 0:
            stream = next_stream
            next_stream += 1
            streams[ctx] = [stream, 0]
        elif phase == 1:
            require(ctx in streams, "squeeze without matching absorb")
            stream, sequence = streams[ctx]
            streams[ctx][1] += 1
        stage = ("keyGen" if index < split else "decapsulation") if split is not None else op
        events.append(dict(case_index=case["case_index"], operation=op, stage=stage,
                           event_index=index, algorithm=MODES[mode], phase=PHASES[phase],
                           lanes=ways, input_bytes_per_lane=inlen, output_bytes_per_lane=outlen,
                           stream_id=stream, squeeze_index=sequence,
                           scalar_permutations=count, x4_permute_calls=vector_count))
    require(sum(event["scalar_permutations"] for event in events) == lib.profile_scalar(),
            "unattributed permutation")
    result_record = {key: case[key] for key in
                     ("case_index", "dataset", "tgId", "tcId", "operation", "expected_return")}
    result_record.update(actual_return=result, match=True, fips202_api_calls=len(events),
                         scalar_permutations=lib.profile_scalar(),
                         x4_permute_calls=lib.profile_x4(),
                         continuation_api_calls=sum(event["squeeze_index"] > 0 for event in events),
                         output_sha256={key: hashlib.sha256(value).hexdigest() for key, value in output.items()})
    return result_record, events


def summarize(records, events, caps):
    shapes = {}
    for event in events:
        phase = event["phase"]
        if phase == "squeeze":
            phase = "initial_squeeze" if event["squeeze_index"] == 0 else "continuation_squeeze"
        key = (event["algorithm"], phase, event["lanes"],
               event["input_bytes_per_lane"], event["output_bytes_per_lane"])
        if key not in shapes:
            shapes[key] = dict(algorithm=key[0], phase=key[1], lanes=key[2],
                               input_bytes_per_lane=key[3], output_bytes_per_lane=key[4],
                               api_calls=0, lane_calls=0, scalar_permutations=0)
        row = shapes[key]
        row["api_calls"] += 1
        row["lane_calls"] += event["lanes"]
        row["scalar_permutations"] += event["scalar_permutations"]
    by_operation = {}
    for op in sorted({record["operation"] for record in records}):
        group = [record for record in records if record["operation"] == op]
        totals = [record["scalar_permutations"] for record in group]
        by_operation[op] = dict(cases=len(group), matches=sum(record["match"] for record in group),
                                scalar_permutations_total=sum(totals),
                                scalar_permutations_min=min(totals), scalar_permutations_max=max(totals),
                                scalar_permutations_mean=sum(totals) / len(totals),
                                continuation_cases=sum(record["continuation_api_calls"] > 0 for record in group),
                                continuation_api_calls=sum(record["continuation_api_calls"] for record in group),
                                expected_return_counts=dict(Counter(str(record["actual_return"]) for record in group)))
    stream_bytes = Counter()
    for event in events:
        if event["phase"] == "squeeze":
            stream_bytes[(event["case_index"], event["stream_id"])] += event["output_bytes_per_lane"]
    commands = Counter()
    continuation_commands = 0
    for event in events:
        if event["phase"] == "absorb":
            continue  # combined with first squeeze into one HLS HASH per lane
        command = "SQUEEZE" if event["squeeze_index"] > 0 else "HASH"
        commands[command] += event["lanes"]
        if command == "SQUEEZE":
            continuation_commands += event["lanes"]
    return dict(
        scope="Host algorithmic call/permutation counts; not PicoRV32 cycles or accelerator speedup",
        parameter_set="ML-KEM-1024", cases=len(records), matches=sum(record["match"] for record in records),
        fips202_api_calls=len(events), scalar_permutations=sum(e["scalar_permutations"] for e in events),
        x4_permute_calls=sum(e["x4_permute_calls"] for e in events),
        permutation_definition="One 24-round Keccak-f[1600] on one 1600-bit state; x4 counts are already included as four scalar permutations",
        operations=by_operation, call_shapes=sorted(shapes.values(), key=lambda row: tuple(str(row[k]) for k in
                                                    ("algorithm", "phase", "lanes", "input_bytes_per_lane"))),
        hls_mapping=dict(
            **caps, max_observed_input_bytes_per_lane=max(e["input_bytes_per_lane"] for e in events),
            max_observed_output_bytes_per_call_per_lane=max(e["output_bytes_per_lane"] for e in events),
            max_observed_shake128_stream_output_bytes_per_lane=max(stream_bytes.values()),
            observed_shapes_fit=all(e["input_bytes_per_lane"] <= caps["input_capacity_bytes"] and
                                    e["output_bytes_per_lane"] <= caps["output_capacity_bytes"] for e in events),
            logical_scalar_commands=dict(commands), continuation_commands=continuation_commands,
            shake128_stream_length_histogram=dict(sorted(Counter(stream_bytes.values()).items())),
            notes=["Map each x4 call to four independent scalar contexts/commands; x4 lane outputs are separate streams.",
                   "Combine SHAKE128 absorb plus first squeeze as HASH(34,504); save four contexts until sampling completes.",
                   "Additional rejection-sampling blocks require SQUEEZE(0,168) on the same lane context, never a fresh HASH.",
                   "Observed stream maxima are not a proof of a bound for all seeds; rejection sampling must retain continuation support.",
                   "The 3168-byte expanded secret key is not hashed whole: H(ek) takes 1568 bytes; J(z||c) takes 1600 bytes.",
                   "Command counts exclude optional CLEAR operations, CPU packing/transfers, arbitration and rejection sampling."]))


def write_report(out, summary):
    lines = ["# ML-KEM-1024 host FIPS202 call profile", "",
             "Host algorithmic counts only. This is not PicoRV32 cycle profiling, an HLS latency measurement, or a speedup claim.", "",
             f"All {summary['matches']}/{summary['cases']} pinned official ACVP cases matched every output byte and API return.",
             "The exact existing case loader and firmware operation sequence are reused. Seed-format decapsulation includes key generation plus decapsulation.", "",
             "| Operation | Cases | Keccak permutations min/max | Total | Cases needing continuation |", "|---|---:|---:|---:|---:|"]
    for op, row in summary["operations"].items():
        lines.append(f"| {op} | {row['cases']} | {row['scalar_permutations_min']}/{row['scalar_permutations_max']} | {row['scalar_permutations_total']} | {row['continuation_cases']} |")
    lines += ["", "One permutation means all 24 rounds on one 1600-bit state. A portable x4 permutation invokes four scalar permutations; those are already included in the totals.", "",
              "| Algorithm | Phase | Lanes | Input B/lane | Output B/lane | API calls | Scalar permutations |", "|---|---|---:|---:|---:|---:|---:|"]
    for row in summary["call_shapes"]:
        lines.append("| " + " | ".join(str(row[key]) for key in ("algorithm", "phase", "lanes", "input_bytes_per_lane", "output_bytes_per_lane", "api_calls", "scalar_permutations")) + " |")
    mapping = summary["hls_mapping"]
    lines += ["", f"Total: {summary['fips202_api_calls']} FIPS202 API calls, {summary['scalar_permutations']} scalar Keccak permutations.", "",
              f"The HLS input/output capacities are {mapping['input_capacity_bytes']}/{mapping['output_capacity_bytes']} bytes. Observed maxima are {mapping['max_observed_input_bytes_per_lane']} input bytes and {mapping['max_observed_output_bytes_per_call_per_lane']} output bytes per scalar command. All observed shapes fit.", "",
              f"SHAKE128 stream output reached {mapping['max_observed_shake128_stream_output_bytes_per_lane']} bytes per lane. Its observed stream-length histogram (four-lane batches) is {mapping['shake128_stream_length_histogram']}.", "",
              f"Mapping these calls to the scalar HLS interface gives {mapping['logical_scalar_commands']}, excluding CLEAR and transfer overhead.", ""]
    lines += ["- " + note for note in mapping["notes"]]
    lines += ["", "Reproduce: `python scripts/mlkem1024_keccak/profile_calls.py` (host GCC must be available; use `--cc` if needed).", "",
              "`calls.csv` records each invocation and its actual permutation count; `cases.json` records official identities, returns, and output SHA-256 hashes; `summary.json` aggregates shapes; `manifest.json` records compiler arguments and input/build hashes. `run.txt` is the case-level execution log.", "",
              "Instrumentation only inserts observational counters into a generated vendor copy under ignored `build/mlkem1024_keccak_call_profile/`. Vendor manifest hashes are checked before and after the run. Each observed permutation count is independently checked against rate/length arithmetic.", ""]
    (out / "README.md").write_text("\n".join(lines), encoding="utf-8", newline="\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cc", default=shutil.which("gcc") or "gcc")
    args = parser.parse_args()
    vendor = ROOT / "third_party/mlkem-native"
    vendor_manifest = json.loads((vendor / "SOURCE_MANIFEST.json").read_text(encoding="utf-8"))
    inputs = {"third_party/mlkem-native/" + entry["path"]: entry["sha256"]
              for entry in vendor_manifest["files"]}
    for path, expected in inputs.items():
        require(digest(ROOT / path) == expected, f"vendor mismatch before run: {path}")
    cases, sources = load_cases(ROOT, 1024)
    inputs.update({entry["path"]: entry["sha256"] for entry in sources})
    for path in ("third_party/mlkem-native/SOURCE_MANIFEST.json", "vectors/official_kat/acvp/SHA256SUMS",
                 "scripts/kat/package_mlkem.py", "scripts/kat/validate_acvp_json.py",
                 "firmware/mlkem_suite/mlkem_config.h", "firmware/mlkem_suite/kat_suite.c",
                 "scripts/mlkem1024_keccak/profile_calls.py", "hls/mlkem1024_keccak/src/mlkem1024_keccak_accel.h"):
        inputs[path] = digest(ROOT / path)
    header = (ROOT / "hls/mlkem1024_keccak/src/mlkem1024_keccak_accel.h").read_text()
    caps = {direction + "_capacity_bytes": int(re.search(rf"KECCAK_MAX_{direction.upper()}_BYTES\s*=\s*(\d+)", header)[1])
            for direction in ("input", "output")}
    build = ROOT / "build/mlkem1024_keccak_call_profile"
    out = ROOT / "results/keccak_cpu/call_profile"
    build.mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)
    library, build_info = build_library(build, args.cc)
    lib = bind_library(library)
    records, events, log = [], [], []
    for case in cases:
        record, trace = run_case(lib, case)
        records.append(record)
        events.extend(trace)
        log.append(f"PASS case={record['case_index']:03d} dataset={record['dataset']} tgId={record['tgId']} tcId={record['tcId']} operation={record['operation']} return={record['actual_return']} keccak_permutations={record['scalar_permutations']}")
    for path, expected in inputs.items():
        require(digest(ROOT / path) == expected, f"input changed during run: {path}")
    summary = summarize(records, events, caps)
    write_json(out / "cases.json", records)
    write_json(out / "summary.json", summary)
    with (out / "calls.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(events[0]))
        writer.writeheader()
        writer.writerows(events)
    result = f"K4_CALL_PROFILE_PASS cases={len(records)} matches={summary['matches']} scalar_permutations={summary['scalar_permutations']} continuation_commands={summary['hls_mapping']['continuation_commands']} host_algorithmic_only=true"
    (out / "run.txt").write_text("\n".join(log + [result]) + "\n", encoding="utf-8", newline="\n")
    write_report(out, summary)
    write_json(out / "manifest.json", dict(
        generated_utc=datetime.now(timezone.utc).isoformat(), platform=platform.platform(),
        python=sys.version, vendor_commit=vendor_manifest["source_commit"],
        scope=summary["scope"], vendor_unchanged=True, all_input_hashes_verified=True,
        input_sha256=inputs, build=build_info,
        output_sha256={path.name: digest(path) for path in sorted(out.iterdir())
                       if path.is_file() and path.name != "manifest.json"}))
    print(result)
    print(json.dumps(summary["operations"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
