#!/usr/bin/env python3
"""Package the pinned ACVP ML-KEM cases for one parameter set.

This is the parameterized companion to ``package_mlkem512.py``.  It keeps the
fixture format and case ordering identical while selecting ML-KEM-512, -768,
or -1024 from the checked-in ACVP vectors.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import struct

from validate_acvp_json import check_sha256_manifest, validate_pair

MAGIC = 0x3254414B
VERSION = 1
HEADER_WORDS = 8
META_WORDS = 12
CASE_COUNT = 145
ACVP_COMMIT = "975de31eb83d87039ec88934fdc47d8c312b892d"
DATASETS = (
    (1, "fips203/ML-KEM-keyGen", "FIPS203", "keyGen"),
    (2, "fips203/ML-KEM-encapDecap", "FIPS203", "encapDecap"),
    (3, "fips203-tr1/ML-KEM-encapDecap", "FIPS203-tr1", "encapDecap"),
)
OPERATIONS = {
    1: ("keyGen", ("d", "z"), ("ek", "dk")),
    2: ("encapsulation", ("ek", "m"), ("c", "k")),
    3: ("decapsulation", ("dk", "c"), ("k",)),
    4: ("decapsulationSeed", ("d", "z", "c"), ("k",)),
    5: ("encapsulationKeyCheck", ("ek",), ()),
    6: ("decapsulationKeyCheck", ("dk",), ()),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sizes(parameter_set: int) -> dict[str, int]:
    values = {
        512: (800, 1632, 768),
        768: (1184, 2400, 1088),
        1024: (1568, 3168, 1568),
    }
    try:
        pk, sk, ct = values[parameter_set]
    except KeyError as exc:
        raise ValueError("parameter set must be 512, 768, or 1024") from exc
    return {"d": 32, "z": 32, "m": 32, "ek": pk, "dk": sk, "c": ct, "k": 32}


def hex_field(source: dict, field: str, expected_size: int) -> str:
    value = source[field]
    if not isinstance(value, str):
        raise ValueError(f"{field}: expected hex string")
    data = bytes.fromhex(value)
    if len(data) != expected_size or len(value) != 2 * expected_size:
        raise ValueError(f"{field}: expected {expected_size} bytes")
    return data.hex()


def load_cases(root: Path, parameter_set: int) -> tuple[list[dict], list[dict]]:
    vector_root = root / "vectors/official_kat/acvp"
    expected_parameter = f"ML-KEM-{parameter_set}"
    field_sizes = sizes(parameter_set)
    errors: list[str] = []
    check_sha256_manifest(vector_root, errors)
    cases: list[dict] = []
    sources: list[dict] = []
    for dataset_id, dataset, revision, mode in DATASETS:
        prompt_path = vector_root / dataset / "prompt.json"
        expected_path = prompt_path.with_name("expectedResults.json")
        _, _, pair_errors = validate_pair(prompt_path, expected_path, vector_root)
        errors.extend(pair_errors)
        if errors:
            raise ValueError("ACVP validation failed:\n" + "\n".join(map(str, errors)))
        prompt = json.loads(prompt_path.read_text(encoding="utf-8"))
        expected = json.loads(expected_path.read_text(encoding="utf-8"))
        if (prompt["algorithm"], prompt["mode"], prompt["revision"]) != ("ML-KEM", mode, revision):
            raise ValueError(f"unexpected source header: {dataset}")
        egroups = {group["tgId"]: group for group in expected["testGroups"]}
        for group in prompt["testGroups"]:
            if group["parameterSet"] != expected_parameter:
                continue
            function = group.get("function", "keyGen")
            key_format = group.get("keyFormat", "expanded" if function == "decapsulation" else None)
            operation = ("decapsulationSeed" if function == "decapsulation" and key_format == "seed"
                         else function)
            op = next((key for key, spec in OPERATIONS.items() if spec[0] == operation), None)
            if op is None:
                raise ValueError(f"unsupported operation {operation}")
            _, input_fields, output_fields = OPERATIONS[op]
            answers = {test["tcId"]: test for test in egroups[group["tgId"]]["tests"]}
            for test in group["tests"]:
                answer = answers[test["tcId"]]
                inputs = {field: hex_field(test, field, field_sizes[field]) for field in input_fields}
                outputs = {field: hex_field(answer, field, field_sizes[field]) for field in output_fields}
                expected_return = 0
                if op in (5, 6):
                    passed = answer["testPassed"]
                    if not isinstance(passed, bool):
                        raise ValueError("testPassed must be a boolean")
                    outputs["testPassed"] = passed
                    expected_return = 0 if passed else {5: -4, 6: -5}[op]
                cases.append({
                    "case_index": len(cases), "dataset_id": dataset_id,
                    "dataset": dataset, "revision": revision,
                    "vsId": prompt["vsId"], "tgId": group["tgId"], "tcId": test["tcId"],
                    "op": op, "operation": operation, "test_type": group["testType"],
                    "key_format": key_format, "input_fields": list(input_fields),
                    "output_fields": list(output_fields), "input": inputs, "output": outputs,
                    "expected_return": expected_return,
                })
        sources.extend({"path": path.relative_to(root).as_posix(), "sha256": sha256(path)}
                       for path in (prompt_path, expected_path))
    if len(cases) != CASE_COUNT:
        raise ValueError(f"expected {CASE_COUNT} pinned {expected_parameter} cases, got {len(cases)}")
    if len({(case["dataset_id"], case["tgId"], case["tcId"]) for case in cases}) != len(cases):
        raise ValueError("duplicate case identity")
    first = [next(case for case in cases if case["op"] == op) for op in OPERATIONS]
    for op in (5, 6):
        initial = next(case["expected_return"] for case in first if case["op"] == op)
        first.append(next(case for case in cases if case["op"] == op and
                          (case["expected_return"] == 0) != (initial == 0)))
    selected = {case["case_index"] for case in first}
    cases = first + [case for case in cases if case["case_index"] not in selected]
    for index, case in enumerate(cases):
        case["case_index"] = index
    return cases, sources


def lengths(case: dict, direction: str, count: int) -> list[int]:
    values = [len(bytes.fromhex(case[direction][name])) for name in case[f"{direction}_fields"]]
    return values + [0] * (count - len(values))


def metadata(case: dict, expected: bool) -> list[int]:
    return ([case[key] for key in ("case_index", "dataset_id", "vsId", "tgId", "tcId", "op")] +
            lengths(case, "input", 3) + lengths(case, "output", 2) +
            [case["expected_return"] & 0xFFFFFFFF if expected else 0])


def pack_fixture(cases: list[dict], parameter_set: int, expected: bool) -> list[int]:
    words = [MAGIC, VERSION, parameter_set, len(cases), 0, 0, 0, 0]
    direction = "output" if expected else "input"
    for case in cases:
        case[f"{direction}_word_offset"] = len(words)
        words.extend(metadata(case, expected))
        for field in case[f"{direction}_fields"]:
            data = bytes.fromhex(case[direction][field])
            words.extend(struct.unpack(f"<{len(data) // 4}I", data))
    words[4] = len(words)
    return words


def verify_roundtrip(path: Path, cases: list[dict], parameter_set: int, expected: bool) -> None:
    words = [int(line, 16) for line in path.read_text(encoding="ascii").splitlines()]
    if words[:HEADER_WORDS] != [MAGIC, VERSION, parameter_set, len(cases), len(words), 0, 0, 0]:
        raise ValueError(f"{path}: bad header")
    direction = "output" if expected else "input"
    cursor = HEADER_WORDS
    for case in cases:
        meta = words[cursor:cursor + META_WORDS]
        if meta != metadata(case, expected) or case[f"{direction}_word_offset"] != cursor:
            raise ValueError(f"{path}: metadata mismatch case {case['case_index']}")
        cursor += META_WORDS
        for field, size in zip(case[f"{direction}_fields"], meta[9:11] if expected else meta[6:9]):
            data = b"".join(word.to_bytes(4, "little") for word in words[cursor:cursor + size // 4])
            if data.hex() != case[direction][field]:
                raise ValueError(f"{path}: {field} mismatch case {case['case_index']}")
            cursor += size // 4
    if cursor != len(words):
        raise ValueError(f"{path}: trailing or truncated data")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parameter-set", type=int, required=True, choices=(512, 768, 1024))
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--out-dir", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    out_dir = (args.out_dir or root / f"tb/software/mlkem{args.parameter_set}_suite").resolve()
    cases, sources = load_cases(root, args.parameter_set)
    out_dir.mkdir(parents=True, exist_ok=True)
    files = {}
    for expected, name in ((False, f"mlkem{args.parameter_set}_input.mem"),
                           (True, f"mlkem{args.parameter_set}_expected.mem")):
        words = pack_fixture(cases, args.parameter_set, expected)
        path = out_dir / name
        path.write_text("".join(f"{word:08x}\n" for word in words), encoding="ascii", newline="\n")
        verify_roundtrip(path, cases, args.parameter_set, expected)
        files[name] = {"words": len(words), "bytes": path.stat().st_size, "sha256": sha256(path)}
    counts = Counter(case["operation"] for case in cases)
    document = {
        "algorithm": "ML-KEM", "parameterSet": f"ML-KEM-{args.parameter_set}", "case_count": len(cases),
        "source": {"repository": "https://github.com/usnistgov/ACVP-Server", "commit": ACVP_COMMIT,
                   "manifest": "vectors/official_kat/acvp/SHA256SUMS",
                   "manifest_sha256": sha256(root / "vectors/official_kat/acvp/SHA256SUMS"),
                   "manifest_verified": True, "files": sources},
        "generator": {"path": "scripts/kat/package_mlkem.py", "sha256": sha256(Path(__file__))},
        "fixture": {"header_words": HEADER_WORDS, "meta_words": META_WORDS,
                    "endianness": "little-endian 32-bit words; hexadecimal inputs retain ACVP byte order",
                    "header": ["magic=0x3254414b", "version=1", "parameter=parameter_set", "case_count", "total_words", "reserved=0", "reserved=0", "reserved=0"],
                    "metadata": ["case_index", "dataset_id", "vsId", "tgId", "tcId", "op", "in1_bytes", "in2_bytes", "in3_bytes", "out1_bytes", "out2_bytes", "input:0; expected:int32_return"],
                    "payload": "Input fixture: in1||in2||in3. Expected fixture: out1||out2.", "files": files,
                    "roundtrip_verified": True},
        "measurement_notes": {"execution_order": "The first eight cases cover all six operations and both key-check outcomes; remaining cases retain source order.",
                              "seed_decapsulation": "Operation 4 times keypair_derand(d||z) followed by decapsulation.",
                              "scope": "Public ACVP vector regression; not formal CAVP certification."},
        "counts": dict(sorted(counts.items())), "cases": cases,
    }
    (out_dir / "cases.json").write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"MLKEM{args.parameter_set}_PACK_PASS cases={len(cases)} counts={dict(sorted(counts.items()))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
