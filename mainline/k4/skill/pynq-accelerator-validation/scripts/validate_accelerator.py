"""Golden comparison and reproducible measurement, Python 3.6+, no PYNQ import on PC."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import platform
import re
import statistics
import sys
import time
import xml.etree.ElementTree as ET


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def first_difference(actual, expected, atol=0.0, rtol=0.0, path="output"):
    """Exact nested JSON comparison by default; tolerances only apply to numeric leaves."""
    if not all(math.isfinite(x) and x >= 0 for x in (atol, rtol)):
        raise ValueError("Tolerances must be finite and nonnegative")
    if type(actual) is bool or type(expected) is bool:
        return None if type(actual) is type(expected) and actual == expected else path + ": boolean differs"
    if isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
        if not math.isfinite(actual) or not math.isfinite(expected):
            return path + ": nonfinite value"
        if atol == 0 and rtol == 0:
            return None if actual == expected else path + ": numeric value differs"
        return None if abs(actual - expected) <= atol + rtol * abs(expected) else path + ": outside tolerance"
    if type(actual) is not type(expected):
        return path + ": type/shape differs"
    if isinstance(expected, list):
        if len(actual) != len(expected):
            return path + ": length differs"
        for i, (a, b) in enumerate(zip(actual, expected)):
            error = first_difference(a, b, atol, rtol, path + "[{}]".format(i))
            if error:
                return error
        return None
    if isinstance(expected, dict):
        if set(actual) != set(expected):
            return path + ": keys differ"
        for key in sorted(expected):
            error = first_difference(actual[key], expected[key], atol, rtol, path + "." + key)
            if error:
                return error
        return None
    if expected is None or isinstance(expected, str):
        return None if actual == expected else path + ": value differs"
    raise ValueError("Output must be JSON-compatible")


def percentile(values, fraction):
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def summarize(values):
    if not values:
        return None
    return dict(count=len(values), min=min(values), median=statistics.median(values),
                p95=percentile(values, .95), max=max(values), mean=statistics.mean(values))


def numeric(text):
    if text is None:
        return None
    text = text.strip().replace(",", "")
    if re.fullmatch(r"[-+]?\d+", text):
        return int(text)
    try:
        value = float(text)
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def resource_metrics(spec, directory):
    path = (directory / spec["path"]).resolve()
    common = dict(path=str(path), sha256=digest(path), kind=spec["kind"], stage=spec["stage"],
                  scope=spec["scope"])
    if not common["scope"]:
        raise ValueError("Resource scope must name the top/IP/system")
    if spec["kind"] == "hls-csynth-xml":
        if spec["stage"] != "hls-estimate":
            raise ValueError("HLS reports must be labelled hls-estimate")
        root = ET.parse(str(path)).getroot()
        # Strip XML namespaces for tool-version portability.
        for node in root.iter():
            node.tag = node.tag.rsplit("}", 1)[-1]
        nodes = root.find("AreaEstimates/Resources")
        if nodes is None:
            raise ValueError("No AreaEstimates/Resources in HLS XML")
        resources = {n.tag: numeric(n.text) for n in nodes}
        if not resources or any(v is None or v < 0 for v in resources.values()):
            raise ValueError("Unparseable HLS resource count")
        return dict(common, resources=resources, part=root.findtext("UserAssignments/Part"),
                    top=root.findtext("UserAssignments/TopModelName"),
                    estimated_clock_ns=numeric(root.findtext(
                        "PerformanceEstimates/SummaryOfTimingAnalysis/EstimatedClockPeriod")),
                    timing_status="estimate-only; not routed timing closure")
    if spec["kind"] != "vivado-utilization" or spec["stage"] not in ("synthesis", "implementation"):
        raise ValueError("Unsupported report kind or stage")
    aliases = {"Slice LUTs": "LUT", "CLB LUTs": "LUT", "Slice Registers": "FF",
               "CLB Registers": "FF", "Block RAM Tile": "BRAM_TILE", "DSPs": "DSP", "DSP48E1": "DSP", "DSP48E2": "DSP"}
    resources = {}
    text = path.read_text(encoding="utf-8", errors="replace")
    state = re.search(r"Design State\s*:\s*(.+)", text)
    if state is None:
        raise ValueError("Vivado report lacks Design State; stage cannot be checked")
    state = state.group(1).strip()
    if spec["stage"] == "implementation" and state.lower() not in ("routed", "placed", "optimized"):
        raise ValueError("Report does not describe an implementation state: " + state)
    if spec["stage"] == "synthesis" and state.lower() != "synthesized":
        raise ValueError("Report is not a synthesized utilization report: " + state)
    common["reported_design_state"] = state
    for line in text.splitlines():
        cells = [v.strip() for v in line.strip().strip("|").split("|")]
        label = cells[0].rstrip("*").strip()
        if len(cells) >= 2 and label in aliases:
            value = numeric(cells[1])
            if value is None or value < 0:
                raise ValueError("Unparseable Vivado used count: " + label)
            key = aliases[label]
            if key in resources and resources[key] != value:
                raise ValueError("Ambiguous resource rows: " + label)
            resources[key] = value
    if not resources:
        raise ValueError("No supported utilization rows; inspect report format")
    return dict(common, resources=resources, timing_status="not collected; utilization does not prove timing closure")


def load_adapter(path):
    spec = importlib.util.spec_from_file_location("skill_user_adapter", str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_plan(plan):
    if type(plan.get("schema")) is not int or plan["schema"] != 1 or plan.get("measurement_kind") not in ("offline-demo", "board-live"):
        raise ValueError("Require schema 1 and explicit measurement_kind")
    for key, minimum in (("repeats", 1), ("warmup", 0)):
        if type(plan[key]) is not int or plan[key] < minimum:
            raise ValueError("Invalid " + key)
    if not isinstance(plan.get("timeout_seconds"), (int, float)) or isinstance(plan["timeout_seconds"], bool) or not math.isfinite(plan["timeout_seconds"]) or plan["timeout_seconds"] <= 0:
        raise ValueError("Require a positive finite timeout_seconds")
    if not plan.get("cases"):
        raise ValueError("Require at least one case")
    ids = set()
    for case in plan["cases"]:
        if not isinstance(case["id"], str) or not case["id"] or case["id"] in ids:
            raise ValueError("Case IDs must be unique strings")
        ids.add(case["id"])
        canonical(case["input"])
        canonical(case["expected"])
    tolerance = plan.get("tolerance", {})
    first_difference(0, 0, tolerance.get("atol", 0), tolerance.get("rtol", 0))


def run_plan(plan_path, adapter_path):
    plan_path, adapter_path = Path(plan_path).resolve(), Path(adapter_path).resolve()
    plan = json.loads(plan_path.read_text(encoding="utf-8-sig"))
    validate_plan(plan)
    canonical(plan)
    # Hash config/cases before loading user code; its source and artifacts are recorded.
    report = dict(schema=1, started_at_utc=datetime.now(timezone.utc).isoformat(),
                  measurement_kind=plan["measurement_kind"], passed=False,
                  plan_sha256=digest(plan_path), adapter_sha256=digest(adapter_path), runner_sha256=digest(__file__),
                  python=platform.python_version(), platform=platform.platform(),
                  metadata=plan.get("metadata", {}), setup_excluded=True,
                  wall_scope="adapter.run only; includes its transfer/poll/readback and any internal checks; excludes runner comparison/report IO",
                  percentile_method="linear interpolation at (n-1)*p", records=[], resources=[])
    session, setup = None, False
    tolerance = plan.get("tolerance", {})
    try:
        # Parse resource evidence before opening hardware.
        report["resources"] = [resource_metrics(s, plan_path.parent) for s in plan.get("resources", [])]
        artifacts = plan.get("artifacts", [])
        report["artifacts_sha256"] = {name: digest((plan_path.parent / name).resolve()) for name in artifacts}
        module = load_adapter(adapter_path)
        if module.MEASUREMENT_KIND != plan["measurement_kind"]:
            raise ValueError("Adapter and plan measurement_kind differ")
        session = module.create(plan, plan_path.parent)
        setup = True
        evidence = session.describe()
        if not isinstance(evidence, dict) or evidence.get("measurement_kind") != plan["measurement_kind"]:
            raise ValueError("Session must describe its measurement_kind and provenance")
        canonical(evidence)
        report["session"] = evidence
        for phase, repeats in (("warmup", plan["warmup"]), ("measured", plan["repeats"])):
            for iteration in range(repeats):
                for case in plan["cases"]:
                    record = dict(case_id=case["id"], phase=phase, iteration=iteration,
                                  passed=False, input_sha256=hashlib.sha256(canonical(case["input"])).hexdigest(),
                                  expected_sha256=hashlib.sha256(canonical(case["expected"])).hexdigest())
                    report["records"].append(record)
                    start = time.perf_counter()
                    try:
                        # Adapters must bound hardware polling; no generic safe thread cancellation exists.
                        result = session.run(json.loads(canonical(case["input"]).decode("utf-8")), plan["timeout_seconds"])
                        elapsed = time.perf_counter() - start
                        record["wall_seconds"] = elapsed
                        if elapsed > plan["timeout_seconds"]:
                            raise TimeoutError("Adapter exceeded declared timeout")
                        output = result["output"]
                        record["output_sha256"] = hashlib.sha256(canonical(output)).hexdigest()
                        record["difference"] = first_difference(output, case["expected"], tolerance.get("atol", 0), tolerance.get("rtol", 0))
                        if record["difference"]:
                            record.update(actual=output, expected=case["expected"])
                            raise ValueError(record["difference"])
                        if "device_cycles" in result or "frequency_hz" in result:
                            cycles, frequency = result["device_cycles"], result["frequency_hz"]
                            if type(cycles) is not int or cycles < 0 or isinstance(frequency, bool) or not isinstance(frequency, (int, float)) or not math.isfinite(frequency) or frequency <= 0 or not isinstance(result.get("cycle_scope"), str) or not result["cycle_scope"]:
                                raise ValueError("Invalid hardware cycle/frequency/scope evidence")
                            record.update(device_cycles=cycles, frequency_hz=frequency,
                                          device_seconds=cycles / frequency, cycle_scope=result["cycle_scope"])
                        detail = result.get("detail", {})
                        canonical(detail)
                        record["detail"] = detail
                        # Ensure adapter evidence can be persisted even on successful comparison.
                        canonical(record)
                        record["passed"] = True
                    except Exception as exc:
                        record.update(wall_seconds=time.perf_counter() - start,
                                      error_type=type(exc).__name__, error=str(exc))
                        if hasattr(exc, "record"):
                            try:
                                canonical(exc.record)
                                record["adapter_failure"] = exc.record
                            except Exception as diagnostic_error:
                                record["diagnostic_error"] = str(diagnostic_error)
                        raise
        report["passed"] = True
    except Exception as exc:
        report.update(error_type=type(exc).__name__, error=str(exc))
    finally:
        if setup:
            try:
                session.close()
            except Exception as exc:
                report.update(passed=False, close_error=str(exc))
    measured = [r for r in report["records"] if r["phase"] == "measured" and r["passed"]]
    report["performance_eligible"] = report["passed"] and bool(measured)
    report["successful_measured_samples"] = len(measured)
    report["wall_seconds"] = summarize([r["wall_seconds"] for r in measured])
    # Per-case summaries prevent a tiny operation from concealing a slow one.
    report["per_case_wall_seconds"] = {c["id"]: summarize([r["wall_seconds"] for r in measured if r["case_id"] == c["id"]]) for c in plan["cases"]}
    report["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
    return report


def markdown(report):
    lines = ["# Accelerator validation report", "", "- Result: " + ("PASS" if report["passed"] else "FAIL"),
             "- Measurement kind: " + report.get("measurement_kind", "invalid-plan"),
             "- Performance eligible: " + str(report.get("performance_eligible", False)),
             "- Plan SHA-256: " + report.get("plan_sha256", "unavailable"),
             "- Adapter SHA-256: " + report.get("adapter_sha256", "unavailable"),
             "- Scope: " + report.get("wall_scope", "not measured"), ""]
    if report.get("error"):
        lines += ["Error: " + report["error"], ""]
    if report.get("close_error"):
        lines += ["Cleanup error: " + report["close_error"], ""]
    lines += ["| Case | Samples | Median (s) | P95 (s) | Max (s) |", "|---|---:|---:|---:|---:|"]
    for name, value in report.get("per_case_wall_seconds", {}).items():
        safe_name = name.replace("|", "\\|").replace("\n", " ")
        if value:
            lines.append("| {} | {} | {:.9g} | {:.9g} | {:.9g} |".format(safe_name, value["count"], value["median"], value["p95"], value["max"]))
        else:
            lines.append("| {} | 0 | unavailable | unavailable | unavailable |".format(safe_name))
    lines += ["", "Percentiles use linear interpolation; small samples do not establish tail latency.",
              "Hardware cycles and host wall time have different scopes; no cross-scope speedup is calculated.", ""]
    for item in report.get("resources", []):
        lines += ["Resource evidence: {} / {} / {}".format(item["kind"], item["stage"], item["scope"]),
                  "", "```json", json.dumps(item, ensure_ascii=False, indent=2), "```", ""]
    if not report.get("resources"):
        lines += ["Resource evidence: not collected. No area or timing claim.", ""]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("--adapter", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        report = run_plan(args.plan, args.adapter)
    except Exception as exc:
        report = dict(schema=1, passed=False, performance_eligible=False,
                      error_type=type(exc).__name__, error=str(exc))
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    (args.output / "report.md").write_text(markdown(report), encoding="utf-8")
    print("{}: {}".format("PASS" if report["passed"] else "FAIL", args.output / "report.md"))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
