#!/usr/bin/env python3
"""Run fast, read-only checks for a fresh checkout.

This command intentionally does not start Vivado, Vitis, HLS, XSim, or a KAT
run.  It checks the files and inputs needed by the documented flows, so a
checkout can be reviewed before any long EDA command is started.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
from copy import deepcopy
from pathlib import Path


REQUIRED_FILES = (
    "README.md",
    ".gitignore",
    "mainline/k4/flow.tcl",
    "mainline/k4/bd_axi.tcl",
    "mainline/k4/README.md",
    "mainline/k4/pynq/mlkem1024.py",
    "mainline/k4/pynq/mlkem1024.ipynb",
    "scripts/kat/package_mlkem.py",
    "scripts/kat/validate_acvp_json.py",
    "vectors/official_kat/acvp/SHA256SUMS",
    "third_party/mlkem-native/SOURCE_MANIFEST.json",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def repo_root(value: Path | None) -> Path:
    if value is not None:
        return value.resolve()
    here = Path(__file__).resolve()
    for candidate in (here.parent, *here.parents):
        if (candidate / "mainline/k4/flow.tcl").is_file():
            return candidate
    raise RuntimeError("cannot locate repository root")


def load_module(path: Path, name: str):
    parent = str(path.parent)
    added = parent not in sys.path
    if added:
        sys.path.insert(0, parent)
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if added:
        sys.path.remove(parent)
    return module


def check_required(root: Path) -> list[str]:
    return [name for name in REQUIRED_FILES if not (root / name).is_file()]


def check_python_syntax(root: Path) -> tuple[int, list[str]]:
    checked = 0
    errors: list[str] = []
    candidates = set(root.glob("scripts/**/*.py")) | set(root.glob("mainline/k4/**/*.py"))
    candidates |= set(root.glob("tests/**/*.py"))
    for path in sorted(p for p in candidates if p.is_file()):
        try:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            checked += 1
        except (OSError, SyntaxError, UnicodeError) as exc:
            errors.append(f"{path.relative_to(root).as_posix()}: {exc}")
    return checked, errors


def check_notebooks(root: Path) -> tuple[int, list[str]]:
    checked = 0
    errors: list[str] = []
    for path in sorted(root.glob("**/*.ipynb")):
        if any(part in {"build", "results", ".git"} for part in path.relative_to(root).parts):
            continue
        try:
            notebook = json.loads(path.read_text(encoding="utf-8"))
            for index, cell in enumerate(notebook.get("cells", [])):
                if cell.get("cell_type") == "code":
                    ast.parse("".join(cell.get("source", [])), filename=f"{path} cell {index}")
            checked += 1
        except (OSError, UnicodeError, json.JSONDecodeError, SyntaxError, AttributeError) as exc:
            errors.append(f"{path.relative_to(root).as_posix()}: {exc}")
    return checked, errors


def check_vectors(root: Path) -> tuple[int, int, list[str]]:
    vector_root = root / "vectors/official_kat/acvp"
    validator = load_module(root / "scripts/kat/validate_acvp_json.py", "repository_vector_validator")
    pairs = validator.discover_pairs(vector_root)
    errors = []
    validator.check_sha256_manifest(vector_root, errors)
    groups = tests = 0
    for prompt, expected in pairs:
        group_count, test_count, pair_errors = validator.validate_pair(prompt, expected, vector_root)
        groups += group_count
        tests += test_count
        errors.extend(pair_errors)
    return groups, tests, [str(error) for error in errors]


def check_fixture(root: Path) -> tuple[int, list[str]]:
    package = load_module(root / "scripts/kat/package_mlkem.py", "repository_kat_package")
    fixture_root = root / "tb/software/mlkem1024_suite"
    try:
        cases, sources = package.load_cases(root, 1024)
    except Exception as exc:  # keep a useful one-line failure in CI output
        return 0, [f"ML-KEM-1024 fixture: {type(exc).__name__}: {exc}"]
    errors = []
    if len(cases) != 145:
        errors.append(f"expected 145 ML-KEM-1024 cases, found {len(cases)}")
    identities = {(case["dataset_id"], case["tgId"], case["tcId"]) for case in cases}
    if len(identities) != len(cases):
        errors.append("duplicate ML-KEM-1024 case identity")
    if len(sources) != 6:
        errors.append(f"expected 6 pinned source records, found {len(sources)}")
    cases_json = fixture_root / "cases.json"
    if not cases_json.is_file():
        errors.append(f"missing generated fixture manifest: {cases_json.relative_to(root).as_posix()}")
        return len(cases), errors
    try:
        saved = json.loads(cases_json.read_text(encoding="utf-8"))
        saved_cases = deepcopy(saved.get("cases"))
        if not isinstance(saved_cases, list):
            errors.append("generated fixture manifest has no cases list")
        else:
            # Word offsets are generated bookkeeping; all official identities,
            # fields, and expected bytes must still match the pinned ACVP data.
            for item in saved_cases:
                if isinstance(item, dict):
                    item.pop("input_word_offset", None)
                    item.pop("output_word_offset", None)
            if saved_cases != cases:
                errors.append("saved cases.json differs from freshly generated official cases")
        if saved.get("source", {}).get("files") != sources:
            errors.append("saved cases.json source hashes differ from pinned ACVP files")
        if saved.get("source", {}).get("manifest_sha256") != sha256(root / "vectors/official_kat/acvp/SHA256SUMS"):
            errors.append("saved cases.json vector manifest hash is stale")
        fixture_files = saved.get("fixture", {}).get("files", {})
        for expected, name in ((False, "mlkem1024_input.mem"), (True, "mlkem1024_expected.mem")):
            path = fixture_root / name
            if not path.is_file():
                errors.append(f"missing generated fixture: {path.relative_to(root).as_posix()}")
                continue
            # Rebuild the words from current ACVP cases and validate both the
            # packed metadata/payload and the checked-in fixture digest.
            fresh_cases = deepcopy(cases)
            package.pack_fixture(fresh_cases, 1024, expected)
            package.verify_roundtrip(path, fresh_cases, 1024, expected)
            record = fixture_files.get(name, {})
            if record.get("sha256") != sha256(path):
                errors.append(f"saved fixture hash is stale: {name}")
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        errors.append(f"generated fixture consistency: {type(exc).__name__}: {exc}")
    return len(cases), errors


def check_third_party(root: Path) -> tuple[int, list[str]]:
    """Verify the vendored source tree against its checked-in byte manifest."""
    vendor = root / "third_party/mlkem-native"
    manifest_path = vendor / "SOURCE_MANIFEST.json"
    errors: list[str] = []
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        records = manifest.get("files", [])
        if not isinstance(records, list):
            return 0, ["third-party source manifest has no files list"]
        listed: set[str] = set()
        for record in records:
            relative = record.get("path") if isinstance(record, dict) else None
            expected = record.get("sha256") if isinstance(record, dict) else None
            if not isinstance(relative, str) or not isinstance(expected, str):
                errors.append("third-party source manifest contains an invalid record")
                continue
            listed.add(relative)
            path = (vendor / relative).resolve()
            if vendor.resolve() not in path.parents:
                errors.append(f"third-party manifest path escapes vendor root: {relative}")
            elif not path.is_file():
                errors.append(f"third-party manifest file is missing: {relative}")
            elif sha256(path) != expected:
                errors.append(f"third-party source hash mismatch: {relative}")
        actual = {
            path.relative_to(vendor).as_posix()
            for path in vendor.rglob("*")
            if path.is_file() and path.name != "SOURCE_MANIFEST.json" and path.name != "README.vendor.md"
        }
        for relative in sorted(actual - listed):
            errors.append(f"unlisted third-party source file: {relative}")
        for relative in sorted(listed - actual):
            errors.append(f"manifest lists non-source or missing file: {relative}")
        return len(records), errors
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError) as exc:
        return 0, [f"third-party source manifest: {type(exc).__name__}: {exc}"]


def check_tcl(root: Path) -> str:
    executable = shutil.which("tclsh")
    if executable is None:
        return "SKIP tclsh not installed; Tcl syntax will be checked when Vivado is opened"
    script = (
        "set f [open [lindex $argv 0] r]\n"
        "set s [read $f]\n"
        "close $f\n"
        "if {![info complete $s]} {puts stderr INCOMPLETE; exit 1}\n"
        "puts PASS\n"
    )
    with tempfile.NamedTemporaryFile("w", suffix=".tcl", encoding="utf-8", delete=False) as stream:
        stream.write(script)
        checker = stream.name
    try:
        for relative in ("mainline/k4/flow.tcl", "mainline/k4/bd_axi.tcl"):
            result = subprocess.run([executable, checker, str(root / relative)],
                                    cwd=root, text=True, capture_output=True)
            if result.returncode != 0 or result.stdout.strip() != "PASS":
                detail = result.stderr.strip() or result.stdout.strip() or "incomplete Tcl script"
                return f"FAIL {relative}: {detail}"
    finally:
        Path(checker).unlink(missing_ok=True)
    return "PASS Tcl scripts are syntactically complete (commands not executed)"


def check_paired(root: Path, directory: Path) -> tuple[str, list[str]]:
    required = ("release_manifest.json", "mlkem1024.py", "mlkem1024.ipynb")
    missing = [name for name in required if not (directory / name).is_file()]
    if missing:
        return "FAIL", [f"paired bundle missing {name}" for name in missing]
    try:
        manifest = json.loads((directory / "release_manifest.json").read_text(encoding="utf-8"))
        records = manifest.get("files", manifest.get("artifacts", {}))
        if not isinstance(records, dict):
            return "FAIL", ["paired release manifest has no file records"]
        errors = []
        for name, expected in records.items():
            path = directory / name
            digest = expected.get("sha256") if isinstance(expected, dict) else expected
            if not path.is_file():
                errors.append(f"paired bundle missing manifest file {name}")
            elif digest and sha256(path) != digest:
                errors.append(f"paired bundle hash mismatch {name}")
        return ("PASS" if not errors else "FAIL"), errors
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError) as exc:
        return "FAIL", [f"paired manifest: {type(exc).__name__}: {exc}"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, help="checkout root; defaults to this script's repository")
    parser.add_argument("--paired-dir", type=Path, help="optional existing board bundle to hash-check")
    args = parser.parse_args()
    root = repo_root(args.root)
    failures: list[str] = []

    missing = check_required(root)
    if missing:
        failures.extend(f"missing required file: {name}" for name in missing)
    else:
        print(f"PASS required files ({len(REQUIRED_FILES)})")

    python_count, errors = check_python_syntax(root)
    failures.extend(errors)
    print(f"{'PASS' if not errors else 'FAIL'} Python AST syntax ({python_count} files)")

    notebook_count, errors = check_notebooks(root)
    failures.extend(errors)
    print(f"{'PASS' if not errors else 'FAIL'} notebook syntax ({notebook_count} notebooks)")

    groups, tests, errors = check_vectors(root)
    failures.extend(errors)
    print(f"{'PASS' if not errors else 'FAIL'} official vectors ({groups} groups, {tests} cases)")

    case_count, errors = check_fixture(root)
    failures.extend(errors)
    print(f"{'PASS' if not errors else 'FAIL'} ML-KEM-1024 fixture ({case_count}/145 cases)")

    source_count, errors = check_third_party(root)
    failures.extend(errors)
    print(f"{'PASS' if not errors else 'FAIL'} third-party source manifest ({source_count} files)")

    tcl_status = check_tcl(root)
    print(tcl_status)
    if tcl_status.startswith("FAIL"):
        failures.append(tcl_status)

    if args.paired_dir:
        bundle = args.paired_dir if args.paired_dir.is_absolute() else root / args.paired_dir
        status, errors = check_paired(root, bundle.resolve())
        failures.extend(errors)
        print(f"{status} paired bundle ({bundle})")

    if failures:
        print("\nRepository check failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print("PASS repository checks; no EDA or full KAT was started")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
