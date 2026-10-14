"""Repository paths and verified build inputs shared by the K4 entry points."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sys


def repository_root(start=__file__):
    path = Path(start).resolve()
    for parent in (path, *path.parents):
        if (parent / "mainline/k4").is_dir() and (parent / "scripts/kat/package_mlkem.py").is_file():
            return parent
    raise RuntimeError("Cannot locate repository root from " + str(path))


ROOT = repository_root()
K4 = ROOT / "mainline/k4"
BUILD = ROOT / "build/k4"
sys.path.insert(0, str(ROOT / "scripts"))
from tool_paths import riscv_tool, tool_path  # noqa: E402


def repository_path(value):
    path = Path(value)
    return (path if path.is_absolute() else ROOT / path).resolve()


def selected_hls_run(override=None):
    return repository_path(override or os.environ.get("FLOW_HLS_RUN") or
                           os.environ.get("PQC_HLS_RUN") or BUILD / "selected_hls")


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verified_hls(override=None):
    """Validate a completed selected HLS run and bind its exact generated RTL."""
    run = selected_hls_run(override)
    if (run / ".running.lock").exists():
        raise ValueError("Selected HLS run is still locked: " + str(run))
    spec = importlib.util.spec_from_file_location("k4_hls_reports", K4 / "hls/scripts/collect_reports.py")
    reports = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reports)
    manifest = reports.read_json(run / "manifest.json")
    state = reports.read_json(run / "state.json")
    metrics = reports.read_json(run / "reports/metrics.json")
    attempts = state.get("attempts")
    if not isinstance(attempts, list) or not attempts:
        raise ValueError("Selected HLS run has no recorded attempt; run HLS validation first")
    if manifest["input_sha256"] != reports.input_hashes(K4 / "hls"):
        raise ValueError("Selected HLS run differs from current kernel/testbench inputs")
    reports.check_snapshot(run, manifest)
    config = manifest["config"]
    if (config.get("io_opt"), config.get("top"), config.get("part"), config.get("clock_ns")) != (
            1, "mlkem1024_keccak_accel", "xc7z020-clg400-1", 10.0):
        raise ValueError("Selected HLS run has an incompatible configuration")
    if (metrics.get("functional_hls_flow_passed") is not True or
            metrics.get("requested_stages_passed") is not True or metrics.get("errors") or
            metrics.get("input_sha256") != manifest["input_sha256"] or
            metrics.get("configuration") != config or
            metrics.get("stage_evidence") != state["stage_evidence"] or
            metrics.get("current_attempt") != attempts[-1]):
        raise ValueError("Selected HLS metrics do not authenticate a completed functional run")
    report_paths = reports.report_paths(run)
    evidence_hashes = {}
    for stage in ("CSIM", "CSYNTH", "COSIM"):
        entry = state["stage_evidence"].get(stage, {})
        expected_report = report_paths[stage].relative_to(run).as_posix()
        if entry.get("command_returned_success") is not True or expected_report not in entry.get("report_sha256", {}):
            raise ValueError("Selected HLS run lacks successful report evidence: " + stage)
        reports.verify_report(run, stage, entry)
        evidence_hashes.update(entry["report_sha256"])
    csim = report_paths["CSIM"].read_text(encoding="utf-8", errors="replace")
    if ("MLKEM1024_KECCAK_TB_PASS transactions=109 hash_vectors=74" not in csim or
            len(re.findall(r"^PASS \d+ ", csim, re.M)) != 109):
        raise ValueError("Selected HLS C simulation is incomplete")
    reports.validate_synthesis(report_paths["CSYNTH"], config)
    cosim = reports.cosim_metrics(report_paths["COSIM"])
    if cosim["status"].lower() != "pass" or any(v is None for v in cosim["measured_latency_cycles"].values()):
        raise ValueError("Selected HLS co-simulation did not pass with measured latency")
    rtl = run / "p/sol1/syn/verilog"
    selected = {}
    for source in sorted(rtl.iterdir()):
        if source.is_file() and source.suffix in (".v", ".dat"):
            value = digest(source)
            simulated = run / "p/sol1/sim/verilog" / source.name
            if not simulated.is_file() or digest(simulated) != value:
                raise ValueError("Generated HLS input differs from co-simulated RTL: " + source.name)
            selected[source.name] = {"raw_sha256": value}
    if "mlkem1024_keccak_accel.v" not in selected:
        raise ValueError("Selected HLS run has no generated top module")
    return run, dict(schema=1, selected_run=str(run), selected=selected,
        provenance_sha256={name: digest(run / name) for name in
                           ("manifest.json", "state.json", "reports/metrics.json")},
        input_sha256=manifest["input_sha256"], report_sha256=evidence_hashes,
        verification="Current source hashes, completed C/RTL simulation reports, and identical synthesis/co-simulation RTL")


def hls_input_pairs(run, selection):
    pairs = [(run / "p/sol1/syn/verilog" / name, "hls/" + name)
             for name in selection["selected"]]
    evidence = set(selection["provenance_sha256"]) | set(selection["report_sha256"])
    pairs += [(run / name, "hls_provenance/" + name) for name in sorted(evidence)]
    pairs += [(run / "snapshot" / name, "hls_provenance/snapshot/" + name)
              for name in selection["input_sha256"]]
    return pairs


def verify_hls_snapshot(snapshot, selection):
    expected = {"hls/" + name: info["raw_sha256"] for name, info in selection["selected"].items()}
    for field in ("provenance_sha256", "report_sha256"):
        expected.update({"hls_provenance/" + name: value for name, value in selection[field].items()})
    expected.update({"hls_provenance/snapshot/" + name: value
                     for name, value in selection["input_sha256"].items()})
    for name, value in expected.items():
        path = (snapshot / name).resolve()
        if not path.is_relative_to(snapshot.resolve()) or digest(path) != value:
            raise ValueError("Frozen HLS input/report differs from verified selection: " + name)


def verified_firmware(mode):
    path = BUILD / mode / "build.json"
    build = json.loads(path.read_text(encoding="utf-8"))
    for name, expected in build["source_sha256"].items():
        if digest(ROOT / name) != expected:
            raise ValueError("Stale firmware source; rebuild " + mode + ": " + name)
    firmware = ROOT / build["firmware"]
    if digest(firmware) != build["firmware_sha256"]:
        raise ValueError("Firmware image changed: " + str(firmware))
    for name, expected in build.get("generated_sha256", {}).items():
        if digest(BUILD / mode / name) != expected:
            raise ValueError("Firmware build product changed: " + name)
    return path, build, firmware
