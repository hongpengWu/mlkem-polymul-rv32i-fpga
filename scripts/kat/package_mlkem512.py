#!/usr/bin/env python3
"""Package the pinned official ML-KEM-512 cases for the PicoRV32 RTL suite.

Inputs and expected outputs remain separate.  The testbench supplies only the
input fixture to the CPU mailbox; expected bytes/return values are its oracle.
The seed-format decapsulation operation includes key expansion and decapsulation.
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
PARAMETER_SET = 512
CASE_COUNT = 145
HEADER_WORDS = 8
META_WORDS = 12
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
SIZES = {"d": 32, "z": 32, "m": 32, "ek": 800, "dk": 1632, "c": 768, "k": 32}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def hex_field(source: dict, field: str) -> str:
    value = source[field]
    if not isinstance(value, str):
        raise ValueError(f"{field}: expected hex string")
    data = bytes.fromhex(value)
    if len(data) != SIZES[field] or len(value) != 2 * SIZES[field]:
        raise ValueError(f"{field}: expected {SIZES[field]} bytes")
    return data.hex()


def load_cases(root: Path) -> tuple[list[dict], list[dict]]:
    vector_root = root / "vectors/official_kat/acvp"
    errors = []
    check_sha256_manifest(vector_root, errors)
    cases, sources = [], []
    for dataset_id, dataset, revision, mode in DATASETS:
        prompt_path = vector_root / dataset / "prompt.json"
        expected_path = prompt_path.with_name("expectedResults.json")
        _, _, pair_errors = validate_pair(prompt_path, expected_path, vector_root)
        errors.extend(pair_errors)
        if errors:
            raise ValueError("ACVP validation failed:\n" + "\n".join(map(str, errors)))
        prompt = json.loads(prompt_path.read_text(encoding="utf-8"))
        expected = json.loads(expected_path.read_text(encoding="utf-8"))
        for document in (prompt, expected):
            if (document["algorithm"], document["mode"], document["revision"]) != (
                "ML-KEM", mode, revision
            ):
                raise ValueError(f"unexpected source header: {dataset}")
        egroups = {group["tgId"]: group for group in expected["testGroups"]}
        for group in prompt["testGroups"]:
            if group["parameterSet"] != "ML-KEM-512":
                continue
            function = group.get("function", "keyGen")
            key_format = group.get("keyFormat", "expanded" if function == "decapsulation" else None)
            operation = "decapsulationSeed" if function == "decapsulation" and key_format == "seed" else function
            op = next((key for key, spec in OPERATIONS.items() if spec[0] == operation), None)
            if op is None:
                raise ValueError(f"unsupported operation {operation}")
            _, input_fields, output_fields = OPERATIONS[op]
            answers = {test["tcId"]: test for test in egroups[group["tgId"]]["tests"]}
            for test in group["tests"]:
                answer = answers[test["tcId"]]
                inputs = {field: hex_field(test, field) for field in input_fields}
                outputs = {field: hex_field(answer, field) for field in output_fields}
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
                    "key_format": key_format,
                    "input_fields": list(input_fields), "output_fields": list(output_fields),
                    "input": inputs, "output": outputs, "expected_return": expected_return,
                })
        sources.extend({"path": path.relative_to(root).as_posix(), "sha256": sha256(path)}
                       for path in (prompt_path, expected_path))
    if len(cases) != CASE_COUNT:
        raise ValueError(f"expected {CASE_COUNT} pinned ML-KEM-512 cases, got {len(cases)}")
    if len({(case["dataset_id"], case["tgId"], case["tcId"]) for case in cases}) != len(cases):
        raise ValueError("duplicate case identity")
    # Cover every operation and both key-check outcomes before the longer
    # sweep, without running a duplicate smoke suite or changing case data.
    first = [next(case for case in cases if case["op"] == op) for op in OPERATIONS]
    for op in (5, 6):
        initial_return = next(case["expected_return"] for case in first if case["op"] == op)
        first.append(next(case for case in cases if case["op"] == op and
                          (case["expected_return"] == 0) != (initial_return == 0)))
    selected = {case["case_index"] for case in first}
    cases = first + [case for case in cases if case["case_index"] not in selected]
    for index, case in enumerate(cases):
        case["case_index"] = index
    return cases, sources


def lengths(case: dict, direction: str, count: int) -> list[int]:
    values = [len(bytes.fromhex(case[direction][name])) for name in case[f"{direction}_fields"]]
    return values + [0] * (count - len(values))


def metadata(case: dict, expected: bool) -> list[int]:
    return [case[key] for key in ("case_index", "dataset_id", "vsId", "tgId", "tcId", "op")] + \
        lengths(case, "input", 3) + lengths(case, "output", 2) + \
        [case["expected_return"] & 0xFFFFFFFF if expected else 0]


def pack_fixture(cases: list[dict], expected: bool) -> list[int]:
    words = [MAGIC, VERSION, PARAMETER_SET, len(cases), 0, 0, 0, 0]
    direction = "output" if expected else "input"
    for case in cases:
        case[f"{direction}_word_offset"] = len(words)
        words.extend(metadata(case, expected))
        for field in case[f"{direction}_fields"]:
            data = bytes.fromhex(case[direction][field])
            if len(data) % 4:
                raise ValueError("fixture payload must be word aligned")
            words.extend(struct.unpack(f"<{len(data) // 4}I", data))
    words[4] = len(words)
    return words


def verify_roundtrip(path: Path, cases: list[dict], expected: bool) -> None:
    """Decode the serialized fixture and compare every field with parsed JSON."""
    words = [int(line, 16) for line in path.read_text(encoding="ascii").splitlines()]
    if words[:HEADER_WORDS] != [MAGIC, VERSION, PARAMETER_SET, len(cases), len(words), 0, 0, 0]:
        raise ValueError(f"{path}: bad header")
    direction = "output" if expected else "input"
    cursor = HEADER_WORDS
    for case in cases:
        meta = words[cursor:cursor + META_WORDS]
        if meta != metadata(case, expected) or case[f"{direction}_word_offset"] != cursor:
            raise ValueError(f"{path}: metadata mismatch case {case['case_index']}")
        cursor += META_WORDS
        sizes = meta[9:11] if expected else meta[6:9]
        for field, size in zip(case[f"{direction}_fields"], sizes):
            data = b"".join(word.to_bytes(4, "little") for word in words[cursor:cursor + size // 4])
            if data.hex() != case[direction][field]:
                raise ValueError(f"{path}: {field} mismatch case {case['case_index']}")
            cursor += size // 4
    if cursor != len(words):
        raise ValueError(f"{path}: trailing or truncated data")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--out-dir", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    out_dir = (args.out_dir or root / "tb/software/mlkem512_suite").resolve()
    cases, sources = load_cases(root)
    out_dir.mkdir(parents=True, exist_ok=True)
    files = {}
    for expected, name in ((False, "mlkem512_input.mem"), (True, "mlkem512_expected.mem")):
        words = pack_fixture(cases, expected)
        path = out_dir / name
        path.write_text("".join(f"{word:08x}\n" for word in words), encoding="ascii", newline="\n")
        verify_roundtrip(path, cases, expected)
        files[name] = {"words": len(words), "bytes": path.stat().st_size, "sha256": sha256(path)}
    counts = Counter(case["operation"] for case in cases)
    document = {
        "algorithm": "ML-KEM", "parameterSet": "ML-KEM-512", "case_count": len(cases),
        "source": {"repository": "https://github.com/usnistgov/ACVP-Server", "commit": ACVP_COMMIT,
                   "manifest": "vectors/official_kat/acvp/SHA256SUMS",
                   "manifest_sha256": sha256(root / "vectors/official_kat/acvp/SHA256SUMS"),
                   "manifest_verified": True, "files": sources},
        "generator": {"path": "scripts/kat/package_mlkem512.py", "sha256": sha256(Path(__file__))},
        "fixture": {"header_words": HEADER_WORDS, "meta_words": META_WORDS,
                    "endianness": "little-endian 32-bit words; hexadecimal inputs retain ACVP byte order",
                    "header": ["magic=0x3254414b", "version=1", "parameter=512", "case_count", "total_words", "reserved=0", "reserved=0", "reserved=0"],
                    "metadata": ["case_index", "dataset_id", "vsId", "tgId", "tcId", "op", "in1_bytes", "in2_bytes", "in3_bytes", "out1_bytes", "out2_bytes", "input:0; expected:int32_return"],
                    "payload": "Input fixture: in1||in2||in3. Expected fixture: out1||out2. No padding is needed for these pinned cases.",
                    "files": files, "roundtrip_verified": True},
        "measurement_notes": {
            "execution_order": "The first eight cases cover all six operations and both outcomes for each key check. Remaining cases retain source order; dataset/tgId/tcId are unchanged.",
            "seed_decapsulation": "Operation 4 times keypair_derand(d||z) followed by decapsulation; report separately from expanded-key decapsulation.",
            "key_checks": "testPassed maps to API return 0 (valid), -4 (invalid ek), or -5 (invalid dk). All pinned check inputs have the nominal byte length.",
            "implicit_rejection": "Decapsulation returns 0 for invalid ciphertexts; compare the returned 32-byte shared secret with the official k, including rejection keys.",
            "scope": "Public ACVP vector regression; not formal CAVP certification or proof of completeness."
        },
        "counts": dict(sorted(counts.items())), "cases": cases,
    }
    (out_dir / "cases.json").write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"MLKEM512_PACK_PASS cases={len(cases)} counts={dict(sorted(counts.items()))}")
    for name, info in files.items():
        print(f"{name}: words={info['words']} sha256={info['sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
