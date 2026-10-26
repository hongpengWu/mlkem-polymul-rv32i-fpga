"""Freeze/verify/collect the same-overlay firmware-switch RTL subset.

EDA execution stays in bd_axi.tcl (BD_PAIR_SIM=1). This is simulation
evidence only; no board connection, programming, or measurement occurs.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil

from paths import ROOT, K4, repository_path


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dump(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def freeze(run, source, firmware):
    if (run / "snapshot").exists():
        raise ValueError("Use a fresh run directory; snapshot already exists")
    source_manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    release_path = source / "release_manifest.json"
    if not release_path.is_file():
        release_path = source / "bundle/release_manifest.json"
    release = json.loads(release_path.read_text(encoding="utf-8"))
    if sha(source / "manifest.json") != release["input_manifest_sha256"]:
        raise ValueError("Published release does not bind this source manifest")
    pairs = []
    for name, record in source_manifest["inputs"].items():
        if name.startswith(("rtl/", "hls/")) or name in ("ps.mem", "board_input.mem", "board_expected.mem"):
            path = source / "snapshot" / name
            if sha(path) != record["sha256"]:
                raise ValueError("Published RTL/HLS/fixture hash mismatch: " + name)
            pairs.append((path, name))
    for group in ("accelerated", "cpu_only"):
        build_path = firmware / group / "build.json"
        build = json.loads(build_path.read_text(encoding="utf-8"))
        image = firmware / group / "ps.mem"
        if sha(image) != build["firmware_sha256"]:
            raise ValueError("Firmware hash mismatch: " + group)
        words = image.read_text(encoding="ascii").split()
        if len(words) != 32768 or any(not re.fullmatch("[0-9a-fA-F]{8}", w) for w in words):
            raise ValueError("Firmware must contain all 32768 words: " + group)
        pairs += [(image, group + ".mem"), (build_path, group + "_build.json")]
    if sha(firmware / "accelerated/ps.mem") != source_manifest["inputs"]["ps.mem"]["sha256"]:
        raise ValueError("Accelerated image differs from published overlay firmware")
    pairs += [(K4 / "tb/tb_mlkem1024_keccak_axi.sv", "tb/tb_mlkem1024_keccak_axi.sv"),
              (K4 / "bd_axi.tcl", "bd_axi.tcl"), (Path(__file__), "paired_rtl.py"),
              (source / "manifest.json", "published_manifest.json"),
              (release_path, "published_release_manifest.json")]
    records = {}
    for path, name in pairs:
        target = run / "snapshot" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        records[name] = {"sha256": sha(target), "source": str(path)}
    dump(run / "manifest.json", {
        "schema": 1, "scope": "RTL subset; not a physical-board test",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "same_published_overlay_rtl_hls": True,
        "bitstream_sha256": release["files"]["k4_accel.bit"],
        "official_indices": [0, 1, 115],
        "sequence": [["accelerated", [0, 1, 115]], ["cpu_only", [0, 1, 115]], ["accelerated", [0]]],
        "inputs": records,
    })
    print("PAIRED_RTL_FREEZE_PASS " + str(run))


def verify(run):
    manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
    for name, record in manifest["inputs"].items():
        if sha(run / "snapshot" / name) != record["sha256"]:
            raise ValueError("Frozen paired input changed: " + name)
    return manifest


def collect(run, evidence):
    manifest = verify(run)
    text = (run / "simulate.log").read_text(encoding="utf-8")
    if re.search(r"fatal:|ERROR:|AXI_KAT_FAIL", text, re.I):
        raise ValueError("Paired RTL simulation contains failure")
    rows = []
    for line in text.splitlines():
        if line.startswith("AXI_PAIR_ROW "):
            rows.append({key: int(value) for key, value in re.findall(r"(\w+)=(\d+)", line)})
    expected = [(0, 0, 0), (0, 0, 1), (0, 0, 115), (1, 1, 0), (1, 1, 1), (1, 1, 115), (2, 0, 0)]
    if [(r["group"], r["cpu_only"], r["official"]) for r in rows] != expected:
        raise ValueError("Incomplete/duplicate/unexpected paired row coverage")
    for row in rows:
        index = [0, 1, 115].index(row["official"])
        expected_counts = (0, 0, 0) if row["cpu_only"] else (
            [26, 27, 32][index], [1969, 2037, 2697][index], [3648, 3732, 4168][index])
        if (row["starts"], row["writes"], row["reads"]) != expected_counts or row["starts"] != row["done"]:
            raise ValueError("Paired hardware counter mismatch")
        if row["cpu_only"] and row["busy"] != 0:
            raise ValueError("CPU-only used accelerator cycles")
        if not row["cpu_only"] and not 0 < row["busy"] < row["cycles"]:
            raise ValueError("Missing hardware activity")
        if not 0 < row["empty"] < row["cycles"]:
            raise ValueError("Invalid measured API cycles")
    images = re.findall(r"AXI_PAIR_IMAGE_PASS cpu_only=(\d+) words=32768 readback_words=32768", text)
    if images != ["0", "1", "0"]:
        raise ValueError("All three full-image writes/readbacks must pass")
    if "AXI_PAIR_PASS cases=7 starts=111 output_bytes=17472 firmware_switches=3 image_words=32768 readback_words=32768" not in text:
        raise ValueError("Missing final paired PASS")
    if "AXI_PROTOCOL_PASS " not in text:
        raise ValueError("Missing existing protocol validation")
    if rows[0]["cycles"] != rows[6]["cycles"]:
        raise ValueError("Accelerated recovery cycle count changed")
    result = {"passed": True, "scope": "RTL subset; not physical-board evidence",
              "same_published_overlay_rtl_hls": True, "rows": rows,
              "firmware_switches": 3, "full_image_verified_words_per_switch": 32768,
              "manifest_sha256": sha(run / "manifest.json"), "log_sha256": sha(run / "simulate.log"),
              "bitstream_sha256": manifest["bitstream_sha256"]}
    dump(run / "result.json", result)
    if evidence:
        if evidence.exists():
            raise ValueError("Evidence directory already exists; refusing overwrite")
        evidence.mkdir(parents=True)
        for name in ("manifest.json", "result.json", "simulate.log"):
            shutil.copyfile(run / name, evidence / name)
        shutil.copytree(run / "snapshot", evidence / "snapshot")
    print("PAIRED_RTL_PASS cases=7 image_switches=3 scope=RTL_only")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("freeze", "verify", "collect"))
    parser.add_argument("run", type=repository_path)
    parser.add_argument("--source", type=repository_path)
    parser.add_argument("--firmware", type=repository_path)
    parser.add_argument("--evidence", type=repository_path)
    args = parser.parse_args()
    if args.stage == "freeze":
        if args.source is None or args.firmware is None:
            parser.error("freeze requires --source and --firmware")
        freeze(args.run, args.source, args.firmware)
    elif args.stage == "verify":
        verify(args.run)
    else:
        collect(args.run, args.evidence)


if __name__ == "__main__":
    main()
