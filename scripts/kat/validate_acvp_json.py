#!/usr/bin/env python3
"""Validate the checked-in ACVP ML-KEM prompt/response pairs.

This is deliberately a structural check.  It verifies that the official JSON
files are parseable, that prompt and expected-result test cases are paired, and
that the fields used by the FIPS 203 ACVP registration have the expected
shape.  It does not claim that an implementation has passed the vectors.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


HEX_RE = re.compile(r"^[0-9A-Fa-f]+$")
SHA256_LINE_RE = re.compile(r"^([0-9A-Fa-f]{64})  (.+)$")
REQUIRED_HEADER = ("vsId", "algorithm", "mode", "revision", "isSample", "testGroups")


class ValidationError:
    def __init__(self, path: Path, message: str) -> None:
        self.path = path
        self.message = message

    def __str__(self) -> str:
        return f"{self.path}: {self.message}"


def load_object(path: Path, errors: List[ValidationError]) -> Optional[Dict[str, Any]]:
    try:
        with path.open("r", encoding="utf-8") as stream:
            value = json.load(stream)
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(ValidationError(path, f"cannot parse JSON ({exc})"))
        return None
    if not isinstance(value, dict):
        errors.append(ValidationError(path, "top level must be a JSON object"))
        return None
    return value


def check_header(
    path: Path,
    value: Dict[str, Any],
    errors: List[ValidationError],
) -> None:
    missing = [key for key in REQUIRED_HEADER if key not in value]
    if missing:
        errors.append(ValidationError(path, f"missing top-level fields: {', '.join(missing)}"))
    if value.get("algorithm") != "ML-KEM":
        errors.append(ValidationError(path, "algorithm must be ML-KEM"))
    if value.get("mode") not in ("keyGen", "encapDecap"):
        errors.append(ValidationError(path, "mode must be keyGen or encapDecap"))
    if not isinstance(value.get("vsId"), int) or isinstance(value.get("vsId"), bool):
        errors.append(ValidationError(path, "vsId must be an integer"))
    if not isinstance(value.get("isSample"), bool):
        errors.append(ValidationError(path, "isSample must be a boolean"))
    if not isinstance(value.get("testGroups"), list):
        errors.append(ValidationError(path, "testGroups must be an array"))


def check_hex_fields(
    path: Path,
    test_path: str,
    test: Dict[str, Any],
    errors: List[ValidationError],
) -> None:
    for field, value in test.items():
        if field == "tcId":
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                errors.append(ValidationError(path, f"{test_path}.tcId must be a positive integer"))
            continue
        if field == "testPassed":
            if not isinstance(value, bool):
                errors.append(ValidationError(path, f"{test_path}.testPassed must be a boolean"))
            continue
        if not isinstance(value, str) or len(value) == 0 or len(value) % 2 or HEX_RE.fullmatch(value) is None:
            errors.append(
                ValidationError(
                    path,
                    f"{test_path}.{field} must be a non-empty even-length hexadecimal string",
                )
            )


def check_test_array(
    path: Path,
    group_path: str,
    tests: Any,
    errors: List[ValidationError],
) -> List[int]:
    if not isinstance(tests, list) or not tests:
        errors.append(ValidationError(path, f"{group_path}.tests must be a non-empty array"))
        return []
    ids: List[int] = []
    for index, test in enumerate(tests):
        test_path = f"{group_path}.tests[{index}]"
        if not isinstance(test, dict):
            errors.append(ValidationError(path, f"{test_path} must be an object"))
            continue
        if "tcId" not in test:
            errors.append(ValidationError(path, f"{test_path} is missing tcId"))
        elif isinstance(test.get("tcId"), int) and not isinstance(test.get("tcId"), bool):
            ids.append(test["tcId"])
        check_hex_fields(path, test_path, test, errors)
    if len(ids) != len(set(ids)):
        errors.append(ValidationError(path, f"{group_path} contains duplicate tcId values"))
    return ids


def check_required_fields(
    path: Path,
    test_path: str,
    test: Dict[str, Any],
    required: Iterable[str],
    errors: List[ValidationError],
) -> None:
    missing = [field for field in required if field not in test]
    if missing:
        errors.append(ValidationError(path, f"{test_path} missing fields: {', '.join(missing)}"))


def expected_shapes(
    mode: str,
    prompt_group: Dict[str, Any],
    prompt_test: Dict[str, Any],
) -> Tuple[Sequence[str], Sequence[str]]:
    """Return required prompt and expected-result fields for one test case."""
    if mode == "keyGen":
        return ("tcId", "z", "d"), ("tcId", "ek", "dk")
    function = prompt_group.get("function")
    if function == "encapsulation":
        return ("tcId", "ek", "m"), ("tcId", "c", "k")
    if function == "decapsulation":
        # FIPS203 has both VAL forms: a complete dk, or z/d/c for the
        # decapsulation-key reconstruction path.
        if "dk" in prompt_test:
            prompt_fields = ("tcId", "dk", "c")
        else:
            prompt_fields = ("tcId", "z", "d", "c")
        return prompt_fields, ("tcId", "k")
    if function == "decapsulationKeyCheck":
        return ("tcId", "dk"), ("tcId", "testPassed")
    if function == "encapsulationKeyCheck":
        return ("tcId", "ek"), ("tcId", "testPassed")
    return (), ()


def validate_pair(prompt_path: Path, expected_path: Path, root: Path) -> Tuple[int, int, List[ValidationError]]:
    errors: List[ValidationError] = []
    prompt = load_object(prompt_path, errors)
    expected = load_object(expected_path, errors)
    if prompt is None or expected is None:
        return 0, 0, errors
    check_header(prompt_path, prompt, errors)
    check_header(expected_path, expected, errors)
    for key in ("algorithm", "mode", "revision", "vsId", "isSample"):
        if prompt.get(key) != expected.get(key):
            errors.append(ValidationError(expected_path, f"{key} differs from prompt.json"))

    prompt_groups = prompt.get("testGroups")
    expected_groups = expected.get("testGroups")
    if not isinstance(prompt_groups, list) or not isinstance(expected_groups, list):
        return 0, 0, errors
    if len(prompt_groups) != len(expected_groups):
        errors.append(
            ValidationError(
                prompt_path,
                f"prompt/expected group count differs ({len(prompt_groups)} vs {len(expected_groups)})",
            )
        )

    group_count = min(len(prompt_groups), len(expected_groups))
    test_count = 0
    prompt_group_ids: List[int] = []
    expected_group_ids: List[int] = []
    for index in range(group_count):
        p_group = prompt_groups[index]
        e_group = expected_groups[index]
        group_path = f"testGroups[{index}]"
        if not isinstance(p_group, dict) or not isinstance(e_group, dict):
            errors.append(ValidationError(prompt_path, f"{group_path} must be an object in both files"))
            continue
        p_id = p_group.get("tgId")
        e_id = e_group.get("tgId")
        if not isinstance(p_id, int) or isinstance(p_id, bool):
            errors.append(ValidationError(prompt_path, f"{group_path}.tgId must be an integer"))
        else:
            prompt_group_ids.append(p_id)
        if not isinstance(e_id, int) or isinstance(e_id, bool):
            errors.append(ValidationError(expected_path, f"{group_path}.tgId must be an integer"))
        else:
            expected_group_ids.append(e_id)
        if p_id != e_id:
            errors.append(ValidationError(expected_path, f"{group_path}.tgId differs from prompt.json"))
        if prompt.get("mode") == "encapDecap":
            for field in ("testType", "parameterSet", "function"):
                if field not in p_group:
                    errors.append(ValidationError(prompt_path, f"{group_path} missing {field}"))
        p_ids = check_test_array(prompt_path, f"{group_path}", p_group.get("tests"), errors)
        e_ids = check_test_array(expected_path, f"{group_path}", e_group.get("tests"), errors)
        if p_ids != e_ids:
            errors.append(ValidationError(expected_path, f"{group_path} prompt/expected tcId sequence differs"))
        test_count += len(p_ids)

        p_tests = p_group.get("tests")
        e_tests = e_group.get("tests")
        if isinstance(p_tests, list) and isinstance(e_tests, list):
            for test_index, (p_test, e_test) in enumerate(zip(p_tests, e_tests)):
                if not isinstance(p_test, dict) or not isinstance(e_test, dict):
                    continue
                required_prompt, required_expected = expected_shapes(prompt.get("mode", ""), p_group, p_test)
                if required_prompt:
                    check_required_fields(prompt_path, f"{group_path}.tests[{test_index}]", p_test, required_prompt, errors)
                    check_required_fields(expected_path, f"{group_path}.tests[{test_index}]", e_test, required_expected, errors)

    if len(prompt_group_ids) != len(set(prompt_group_ids)):
        errors.append(ValidationError(prompt_path, "duplicate tgId values"))
    if len(expected_group_ids) != len(set(expected_group_ids)):
        errors.append(ValidationError(expected_path, "duplicate tgId values"))
    return len(prompt_groups), test_count, errors


def discover_pairs(root: Path) -> List[Tuple[Path, Path]]:
    pairs: List[Tuple[Path, Path]] = []
    for prompt in sorted(root.rglob("prompt.json")):
        expected = prompt.parent / "expectedResults.json"
        if expected.is_file():
            pairs.append((prompt, expected))
    return pairs


def check_sha256_manifest(root: Path, errors: List[ValidationError]) -> None:
    """Verify every checked-in vector against the adjacent SHA256SUMS file."""
    manifest = root / "SHA256SUMS"
    if not manifest.is_file():
        errors.append(ValidationError(manifest, "missing SHA256SUMS manifest"))
        return
    listed: set[str] = set()
    try:
        lines = manifest.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        errors.append(ValidationError(manifest, f"cannot read SHA256SUMS ({exc})"))
        return
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        match = SHA256_LINE_RE.fullmatch(line)
        if match is None:
            errors.append(ValidationError(manifest, f"line {line_number} is not '<sha256>  <path>'"))
            continue
        digest, relative_name = match.groups()
        if relative_name in listed:
            errors.append(ValidationError(manifest, f"duplicate path: {relative_name}"))
            continue
        listed.add(relative_name)
        path = (root / relative_name).resolve()
        if root.resolve() not in path.parents:
            errors.append(ValidationError(manifest, f"path escapes vector root: {relative_name}"))
            continue
        if not path.is_file():
            errors.append(ValidationError(manifest, f"listed file does not exist: {relative_name}"))
            continue
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual.lower() != digest.lower():
            errors.append(ValidationError(path, f"SHA-256 mismatch (manifest {digest}, actual {actual})"))
    expected = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*.json")
        if path.is_file()
    }
    missing = sorted(expected - listed)
    extra = sorted(listed - expected)
    for relative_name in missing:
        errors.append(ValidationError(manifest, f"JSON file is not listed: {relative_name}"))
    for relative_name in extra:
        errors.append(ValidationError(manifest, f"manifest path is not a JSON vector: {relative_name}"))


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    default_root = Path(__file__).resolve().parents[2] / "vectors" / "official_kat" / "acvp"
    parser.add_argument("--root", type=Path, default=default_root, help="ACVP vector root (default: %(default)s)")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    if not root.is_dir():
        print(f"error: vector root does not exist: {root}", file=sys.stderr)
        return 2
    pairs = discover_pairs(root)
    if not pairs:
        print(f"error: no prompt.json/expectedResults.json pairs found under {root}", file=sys.stderr)
        return 2

    total_groups = 0
    total_tests = 0
    errors: List[ValidationError] = []
    check_sha256_manifest(root, errors)
    for prompt_path, expected_path in pairs:
        groups, tests, pair_errors = validate_pair(prompt_path, expected_path, root)
        total_groups += groups
        total_tests += tests
        errors.extend(pair_errors)
        label = prompt_path.relative_to(root).parent.as_posix()
        status = "PASS" if not pair_errors else "FAIL"
        print(f"{status} {label}: {groups} groups, {tests} prompt/expected test cases")

    if errors:
        print(f"\n{len(errors)} validation error(s):", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print(f"Validated {len(pairs)} ACVP pair(s), {total_groups} groups, {total_tests} test cases.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
