"""Portable PYNQ host for the ML-KEM-1024 PicoRV32 + Keccak AXI overlay.

Developer PC: python mlkem1024.py --prepare --root <repo> --output <bundle-dir>
Host checks:  python mlkem1024.py --self-test
Board:       Python 3.6+; use mlkem1024.ipynb beside the release files.
Preparation requires Python 3.10+ and the repository on the developer PC.
"""

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import re
import statistics
import struct
import sys
import time
import xml.etree.ElementTree as ET


BASE = 0x40000000
SPAN = 0x40000
REG = 0x20000
RAM_BYTES = 131072
INPUT = 0x10000
OUTPUT = 0x12000
WINDOW_BYTES = 8192
HARDWARE_ID = 0x4B344158
ABI = 1
FREQUENCY = 100000000
RUNNING = 0x4B415452
COMPLETE = 0x4B415450
FAILED = 0x4B415446
OUTPUT_MAGIC = 0x4B34524F
CASE_COUNT = 145
MODES = ("cpu_only", "accelerated")
OPERATIONS = {1: "keyGen", 2: "encapsulation", 3: "decapsulation",
              4: "decapsulationSeed", 5: "encapsulationKeyCheck",
              6: "decapsulationKeyCheck"}
SHAPES = {1: ([32, 32, 0], [1568, 3168]),
          2: ([1568, 32, 0], [1568, 32]),
          3: ([3168, 1568, 0], [32, 0]),
          4: ([32, 32, 1568], [32, 0]),
          5: ([1568, 0, 0], [0, 0]),
          6: ([3168, 0, 0], [0, 0])}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def signed32(word):
    return word - 0x100000000 if word & 0x80000000 else word


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def repository_root(start=None):
    """Discover the checkout for preparation; deployed bundles need no checkout."""
    path = Path(start if start is not None else __file__).resolve()
    for parent in (path, *path.parents):
        if (parent / "mainline/k4").is_dir() and (parent / "scripts/kat/package_mlkem.py").is_file():
            return parent
    raise ValueError("Cannot locate repository root; pass --root <repository>")


def prepare(root, output):
    """Freeze public vectors and historical references on the developer PC."""
    require(sys.version_info >= (3, 10), "Run --prepare on the developer PC with Python 3.10+")
    root, output = repository_root(root), Path(output).resolve()
    sys.path[:0] = [str(root / "scripts/kat"), str(root / "mainline/k4/scripts")]
    from package_mlkem import ACVP_COMMIT, load_cases, pack_fixture
    from collect_kat import expected_hardware, read_baseline

    cases, sources = load_cases(root, 1024)
    baseline = read_baseline(cases)
    calls = expected_hardware()
    packaged = []
    for index, case in enumerate(cases):
        local = deepcopy(case)
        local["case_index"] = 0
        words = pack_fixture([local], 1024, False)
        payload = b"".join(bytes.fromhex(case["output"][field])
                           for field in case["output_fields"])
        reference = baseline[index]
        packaged.append(dict(
            case_index=index, op=case["op"], operation=case["operation"],
            identity={key: case[key] for key in
                      ("dataset_id", "dataset", "revision", "vsId", "tgId", "tcId",
                       "test_type", "key_format")},
            input_words=words,
            expected_return=case["expected_return"],
            output_fields=case["output_fields"],
            output_lengths=SHAPES[case["op"]][1],
            expected_hex=payload.hex(),
            expected_sha256=hashlib.sha256(payload).hexdigest(),
            expected_hardware={name: calls[index][name] for name in
                               ("starts", "buffer_writes", "buffer_reads")},
            historical_rtl_cpu_only=dict(
                kind="HISTORICAL_RTL_CPU_ONLY", config="rv32im_fast",
                raw_cycles=reference["raw_cycles"],
                empty_cycles=reference["empty_cycles"], frequency_hz=FREQUENCY)))
    provenance_paths = ["vectors/official_kat/acvp/SHA256SUMS",
                        "scripts/kat/package_mlkem.py",
                        "scripts/kat/validate_acvp_json.py",
                        "mainline/k4/scripts/collect_kat.py",
                        "mainline/k4/scripts/paths.py",
                        "scripts/tool_paths.py",
                        "results/official_baseline/mlkem1024/rv32im_fast/cases.csv",
                        "results/keccak_cpu/call_profile/manifest.json",
                        "results/keccak_cpu/call_profile/cases.json",
                        "results/keccak_cpu/call_profile/calls.csv"]
    document = dict(schema=1, algorithm="ML-KEM-1024", case_count=CASE_COUNT,
        provenance=dict(acvp_repository="https://github.com/usnistgov/ACVP-Server",
            acvp_commit=ACVP_COMMIT, source_manifest_verified=True,
            sources=sources, supporting_sha256={name: sha256(root / name)
                                               for name in provenance_paths},
            driver_sha256=sha256(__file__)),
        fixture="Single case, local index 0; 8 header words + 12 metadata words + little-endian payload",
        reference_note="Historical RTL CPU-only baseline; not a live CPU-only board measurement",
        cases=packaged)
    validate_vectors(document)
    target = output / "kat_vectors.json"
    write_json(target, document)
    return target


def validate_vectors(document):
    require(document.get("schema") == 1 and document.get("algorithm") == "ML-KEM-1024"
            and document.get("case_count") == CASE_COUNT, "Unsupported vector package")
    cases = document.get("cases", [])
    require(len(cases) == CASE_COUNT, "Vector package must contain exactly 145 cases")
    identities = set()
    for index, case in enumerate(cases):
        require(case.get("case_index") == index, "Missing, duplicate, or reordered vector index")
        op = case.get("op")
        require(op in SHAPES and case.get("operation") == OPERATIONS[op], "Invalid vector operation")
        words = case["input_words"]
        require(isinstance(words, list) and 20 <= len(words) <= WINDOW_BYTES // 4 and
                all(type(word) is int and 0 <= word <= 0xFFFFFFFF for word in words),
                "Invalid input words")
        require(words[:8] == [0x3254414B, 1, 1024, 1, len(words), 0, 0, 0],
                "Invalid single-case fixture header")
        identity = case["identity"]
        require(words[8:14] == [0, *[identity[key] for key in
                ("dataset_id", "vsId", "tgId", "tcId")], op], "Fixture identity mismatch")
        require(words[14:17] == SHAPES[op][0] and words[17:19] == SHAPES[op][1]
                and words[19] == 0 and 4 * (len(words) - 20) == sum(words[14:17]),
                "Fixture shape mismatch")
        key = tuple(identity[name] for name in ("dataset_id", "tgId", "tcId"))
        require(key not in identities, "Duplicate official case identity")
        identities.add(key)
        payload = bytes.fromhex(case["expected_hex"])
        require(case["output_lengths"] == SHAPES[op][1]
                and len(payload) == sum(case["output_lengths"])
                and hashlib.sha256(payload).hexdigest() == case["expected_sha256"],
                "Expected payload mismatch")
        valid_returns = (0, -4) if op == 5 else (0, -5) if op == 6 else (0,)
        require(case["expected_return"] in valid_returns, "Invalid expected return code")
        require(all(type(case["expected_hardware"].get(name)) is int
                    and case["expected_hardware"][name] >= 0
                    for name in ("starts", "buffer_writes", "buffer_reads")),
                "Missing hardware call expectations")
        reference = case["historical_rtl_cpu_only"]
        require(reference["kind"] == "HISTORICAL_RTL_CPU_ONLY"
                and reference["config"] == "rv32im_fast"
                and reference["raw_cycles"] > reference["empty_cycles"] > 0
                and reference["frequency_hz"] == FREQUENCY, "Invalid historical cycle reference")
    return document


def verify_bundle(manifest_path):
    """Verify the paired overlay and vectors before importing PYNQ or downloading."""
    manifest_path = Path(manifest_path).resolve()
    directory = manifest_path.parent
    manifest = read_json(manifest_path)
    require(manifest.get("schema") == 1, "Unsupported release manifest schema")
    overlay = manifest["overlay"]
    required = dict(base_address=BASE, address_range=SPAN, id=HARDWARE_ID,
                    abi=ABI, frequency_hz=FREQUENCY, ram_bytes=RAM_BYTES)
    require(all(overlay.get(key) == value for key, value in required.items()),
            "Release address, identity, or clock contract mismatch")
    bit_name = overlay["bitstream"]
    require(Path(bit_name).suffix == ".bit", "Release must name a .bit file")
    hwh_name = str(Path(bit_name).with_suffix(".hwh"))
    files = manifest["files"]
    require(all(name in files for name in (bit_name, hwh_name, "kat_vectors.json")),
            "Manifest must hash the matching .bit/.hwh pair and vectors")
    verified = {}
    for name, item in files.items():
        # Releases deliberately use a flat, portable directory.
        require(Path(name).name == name and name not in (".", "..")
                and "/" not in name and "\\" not in name, "Unsafe release filename")
        path = directory / name
        digest = item.get("sha256") if isinstance(item, dict) else item
        require(path.is_file() and sha256(path) == digest, "Release SHA-256 mismatch: " + name)
        verified[name] = digest
    paired = manifest.get("paired_firmware")
    if paired is not None:
        require(isinstance(paired, dict) and set(paired) == set(MODES),
                "Paired release requires exactly cpu_only and accelerated firmware")
        require("mlkem1024.py" in verified, "Paired release must hash its host driver")
        require(sha256(__file__) == verified["mlkem1024.py"],
                "Imported host driver does not match the paired release")
        for mode in MODES:
            item = paired[mode]
            require(isinstance(item, dict) and item.get("file") in verified and
                    item.get("sha256") == verified[item["file"]],
                    "Paired firmware must match a release file hash: " + mode)
            read_firmware(directory / item["file"])
        require(paired["cpu_only"]["sha256"] != paired["accelerated"]["sha256"],
                "Paired firmware images must differ")
    ranges = []
    for node in ET.parse(directory / hwh_name).iter():
        attrs = {key.upper(): value for key, value in node.attrib.items()}
        if "BASEVALUE" in attrs and "HIGHVALUE" in attrs:
            ranges.append((int(attrs["BASEVALUE"], 0), int(attrs["HIGHVALUE"], 0)))
    require((BASE, BASE + SPAN - 1) in ranges, "HWH does not map the expected AXI address range")
    vectors = validate_vectors(read_json(directory / "kat_vectors.json"))
    return manifest, vectors, dict(
        manifest_sha256=sha256(manifest_path), files_sha256=verified,
        bitstream=bit_name, hwh=hwh_name, manifest_path=str(manifest_path),
        release_metadata={key: value for key, value in manifest.items()
                          if key not in ("files", "overlay")})


def read_firmware(path):
    """A full 128-KiB readmemh image, one 32-bit hexadecimal word per line."""
    words = Path(path).read_text(encoding="ascii").splitlines()
    require(len(words) == RAM_BYTES // 4 and
            all(re.fullmatch(r"[0-9a-fA-F]{8}", word.strip()) for word in words),
            "Firmware must contain exactly 32768 hexadecimal 32-bit words")
    return [int(word, 16) for word in words]


class CaseFailure(RuntimeError):
    def __init__(self, message, record):
        super().__init__(message)
        self.record = record


class MLKEM1024:
    """One reset/run/verify transaction at a time; no concurrent callers."""

    def __init__(self, mmio, vectors, artifacts=None, overlay=None,
                 paired_firmware=None, bundle_directory=None):
        self.mmio = mmio
        self.vectors = validate_vectors(vectors)
        self.artifacts = artifacts or {}
        self.overlay = overlay
        self.paired_firmware = paired_firmware
        self.bundle_directory = Path(bundle_directory) if bundle_directory is not None else None
        self.firmware_mode = None if paired_firmware else "accelerated"
        self.firmware_load = None
        self.loaded_at_utc = utc_now()
        self._verify_identity()
        self.reset()  # Explicit even immediately after Overlay.download().

    @classmethod
    def load(cls, manifest_path="release_manifest.json"):
        manifest_path = Path(manifest_path).resolve()
        manifest, vectors, artifacts = verify_bundle(manifest_path)
        from pynq import MMIO, Overlay

        overlay = Overlay(str(manifest_path.parent / manifest["overlay"]["bitstream"]),
                          download=False)
        # HWH MEMRANGE plus the hardware identity is sufficient even when PYNQ
        # does not create an ip_dict entry for a Vivado module-reference IP.
        overlay.download()
        return cls(MMIO(BASE, SPAN), vectors, artifacts=artifacts, overlay=overlay,
                   paired_firmware=manifest.get("paired_firmware"),
                   bundle_directory=manifest_path.parent)

    def select_firmware(self, mode):
        """Stop CPU, clear all RAM, load the full image, hash all RAM before RUN."""
        require(self.paired_firmware is not None and mode in MODES,
                "Firmware switching requires a verified paired release")
        started = time.perf_counter()
        record = dict(kind="FIRMWARE_LOAD", mode=mode, started_at_utc=utc_now(),
                      passed=False, ram_bytes=RAM_BYTES,
                      excluded_from_case_and_speedup_timing=True)
        self.firmware_mode, self.firmware_load = None, None
        try:
            self._verify_identity()
            self.reset()
            item = self.paired_firmware[mode]
            path = self.bundle_directory / item["file"]
            require(sha256(path) == item["sha256"], "Firmware file changed since release verification")
            words = read_firmware(path)
            expected = hashlib.sha256(struct.pack("<%dI" % len(words), *words)).hexdigest()
            record.update(file=item["file"], file_sha256=item["sha256"],
                          expected_ram_sha256=expected)
            self._write_words(0, [0] * (RAM_BYTES // 4))
            self._write_words(0, words)
            actual = hashlib.sha256(self._read_bytes(0, RAM_BYTES)).hexdigest()
            record["readback_ram_sha256"] = actual
            require(actual == expected, "Full 128-KiB firmware RAM readback SHA-256 mismatch")
            require(self._read(REG + 8) == 0, "CPU left reset during firmware upload")
            require(all(self._read(REG + 0x80 + 4 * i) == 0 for i in range(4)),
                    "Hardware counters did not clear on reset")
            record["passed"] = True
            self.firmware_mode = mode
        except Exception as exc:
            record.update(error_type=type(exc).__name__, error=str(exc))
            try:
                self.reset()
            except Exception as reset_error:
                record["reset_error"] = str(reset_error)
            record["load_seconds"] = time.perf_counter() - started
            raise CaseFailure(str(exc), record) from exc
        record["load_seconds"] = time.perf_counter() - started
        self.firmware_load = deepcopy(record)
        return record

    def _read(self, offset):
        return int(self.mmio.read(offset)) & 0xFFFFFFFF

    def _verify_identity(self):
        actual = tuple(self._read(REG + offset) for offset in (0, 4, 0x14, 0x18))
        require(actual == (HARDWARE_ID, ABI, FREQUENCY, RAM_BYTES),
                "Wrong overlay ID, ABI, clock, or RAM size: " + str(actual))

    def reset(self):
        self.mmio.write(REG + 8, 0)
        require(self._read(REG + 8) & 1 == 0, "CPU reset did not assert")

    def _write_words(self, offset, words):
        require(offset % 4 == 0 and offset >= 0 and offset + 4 * len(words) <= RAM_BYTES,
                "RAM write outside aligned RAM region")
        require(self._read(REG + 8) & 1 == 0, "RAM writes require CPU reset")
        # MMIO.write accepts bytes on PYNQ. Bounded chunks avoid large temporary
        # transfers and preserve little-endian byte order on both PC and board.
        for start in range(0, len(words), 256):
            chunk = words[start:start + 256]
            self.mmio.write(offset + start * 4, struct.pack("<%dI" % len(chunk), *chunk))

    def _read_bytes(self, offset, count):
        require(offset % 4 == 0 and count >= 0 and offset + count <= RAM_BYTES,
                "RAM read outside aligned RAM region")
        return b"".join(struct.pack("<I", self._read(offset + word * 4))
                        for word in range((count + 3) // 4))[:count]

    def run_case(self, index, timeout=10.0, poll_interval=0.001):
        require(self.firmware_mode in MODES, "Select and verify paired firmware before running")
        require(type(index) is int and 0 <= index < CASE_COUNT, "Invalid official case index")
        require(timeout > 0 and poll_interval >= 0, "Invalid timeout or polling interval")
        case = self.vectors["cases"][index]
        started = time.perf_counter()
        record = dict(case_index=index, operation=case["operation"], op=case["op"],
            identity=deepcopy(case["identity"]), started_at_utc=utc_now(),
            measurement_kind="PYNQ_BOARD_AXI_LIVE", passed=False,
            firmware_mode=self.firmware_mode,
            input_sha256=hashlib.sha256(struct.pack("<%dI" % len(case["input_words"]),
                                                    *case["input_words"])).hexdigest(),
            historical_rtl_cpu_only=deepcopy(case["historical_rtl_cpu_only"]))
        try:
            self._verify_identity()
            self.reset()
            upload_start = time.perf_counter()
            self._write_words(INPUT, [0] * (WINDOW_BYTES // 4))
            self._write_words(OUTPUT, [0] * (WINDOW_BYTES // 4))
            self._write_words(INPUT, case["input_words"])
            record["upload_seconds"] = time.perf_counter() - upload_start
            wait_start = time.perf_counter()
            self.mmio.write(REG + 8, 1)
            while True:
                trap, status = self._read(REG + 0x10), self._read(REG + 0x0C)
                record.update(trap=trap, hardware_status=status)
                require(trap == 0, "PicoRV32 trap")
                require(status != FAILED, "Firmware reported KATF")
                elapsed = time.perf_counter() - wait_start
                if elapsed >= timeout:
                    raise TimeoutError("Timed out waiting for KATP completion")
                if status == COMPLETE:
                    break
                require(status in (0, RUNNING), "Unexpected firmware status")
                if poll_interval:
                    time.sleep(min(poll_interval, timeout - elapsed))
            record["run_wait_seconds"] = time.perf_counter() - wait_start
            read_start = time.perf_counter()
            header = struct.unpack("<8I", self._read_bytes(OUTPUT, 32))
            magic, version, op, retword, n1, n2, raw, empty = header
            require((magic, version, op) == (OUTPUT_MAGIC, ABI, case["op"]),
                    "Output magic, ABI, or operation mismatch")
            require([n1, n2] == case["output_lengths"] and n1 + n2 <= WINDOW_BYTES - 32,
                    "Output length mismatch")
            payload = self._read_bytes(OUTPUT + 32, n1 + n2)
            profile = [self._read(REG + 0x40 + 4 * i) for i in range(12)]
            hardware = dict(zip(("starts", "busy_cycles", "buffer_writes", "buffer_reads"),
                (self._read(REG + 0x80 + 4 * i) for i in range(4))))
            record.update(download_seconds=time.perf_counter() - read_start,
                return_code=signed32(retword), output_lengths=[n1, n2],
                output_hex=payload.hex(), output_sha256=hashlib.sha256(payload).hexdigest(),
                raw_cycles=raw, empty_cycles=empty, profile_words=profile, hardware=hardware,
                frequency_hz=FREQUENCY)
            verify_start = time.perf_counter()
            require(signed32(retword) == case["expected_return"], "Official return code mismatch")
            require(payload == bytes.fromhex(case["expected_hex"]), "Official output bytes mismatch")
            require(raw > empty > 0, "Invalid API rdcycle measurement")
            require(profile[3] == raw and profile[8] == empty and profile[9] == retword,
                    "Output/profile cycle or return mismatch")
            expected_hardware = (dict(starts=0, busy_cycles=0, buffer_writes=0, buffer_reads=0)
                                 if self.firmware_mode == "cpu_only" else case["expected_hardware"])
            require(all(hardware[name] == expected for name, expected in expected_hardware.items()),
                    "Hardware command or buffer transfer count mismatch")
            require((0 < hardware["busy_cycles"] < raw) if hardware["starts"] else
                    hardware["busy_cycles"] == 0, "Invalid hardware busy cycle count")
            record.update(passed=True, verification_seconds=time.perf_counter() - verify_start,
                algorithm_seconds=raw / FREQUENCY,
                algorithm_seconds_minus_empty=(raw - empty) / FREQUENCY)
        except Exception as exc:
            record.update(error_type=type(exc).__name__, error=str(exc))
            try:
                record["failure_profile_words"] = [self._read(REG + 0x40 + 4 * i)
                                                    for i in range(12)]
                record["firmware_error_code"] = record["failure_profile_words"][1]
            except Exception as diagnostic_error:
                record["diagnostic_error"] = str(diagnostic_error)
            try:
                self.reset()
            except Exception as reset_error:
                record["reset_error"] = str(reset_error)
            record["wall_seconds"] = time.perf_counter() - started
            raise CaseFailure(str(exc), record) from exc
        record["wall_seconds"] = time.perf_counter() - started
        return record

    def run_cases(self, indices=(0, 1, 115), timeout=10.0):
        indices = list(indices)
        require(indices and all(type(index) is int and 0 <= index < CASE_COUNT for index in indices)
                and len(indices) == len(set(indices)), "Select unique official indices in 0..144")
        report = dict(schema=1, status="INCOMPLETE", started_at_utc=utc_now(),
            measurement_kind="PYNQ_BOARD_AXI_LIVE", requested_indices=indices,
            artifacts=deepcopy(self.artifacts), overlay_loaded_at_utc=self.loaded_at_utc,
            firmware_mode=self.firmware_mode, firmware_load=deepcopy(self.firmware_load),
            runtime=dict(python=sys.version, platform=platform.platform(), machine=platform.machine()),
            clock_hz=FREQUENCY, case_count_required_for_full_pass=CASE_COUNT,
            metric_notes=dict(
                algorithm_seconds="raw rdcycle interval / hardware clock; API only",
                algorithm_seconds_minus_empty="(raw - empty bracket) / hardware clock",
                run_wait_seconds="CPU start to observed completion; includes boot, firmware work and polling",
                upload_seconds="clear input/output mailboxes and transfer one fixture",
                download_seconds="read output, profile and hardware counters",
                wall_seconds="entire host case, including reset, transport, waiting and verification",
                baseline="HISTORICAL_RTL_CPU_ONLY; not a live CPU-only board measurement",
                speedup="Compare matched live cpu_only and accelerated firmware on this same bitstream",
                firmware_load="Full RAM clear, image transfer and full readback excluded; reported separately"), cases=[])
        begin = time.perf_counter()
        for index in indices:
            try:
                report["cases"].append(self.run_case(index, timeout=timeout))
            except CaseFailure as exc:
                report["cases"].append(exc.record)
                break
        checked = [row["case_index"] for row in report["cases"] if row["passed"]]
        passed = len(checked) == len(indices)
        full = passed and len(checked) == CASE_COUNT and set(checked) == set(range(CASE_COUNT))
        report.update(status="FULL_PASS" if full else "SUBSET_PASS" if passed else "FAIL",
            passed=passed, full_pass=full, checked_indices=checked,
            unique_checked_cases=len(set(checked)),
            finished_at_utc=utc_now(), total_wall_seconds=time.perf_counter() - begin)
        return report

    @staticmethod
    def export(report, path):
        """Save complete evidence, including failed attempts, without overwriting."""
        path = Path(path)
        require(not path.exists(), "Evidence file already exists: " + str(path))
        write_json(path, report)
        return path

    def _save_stage(self, report, directory, label):
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
        return self.export(report, Path(directory) / (stamp + "_" + label + ".json"))

    def _reset_for_evidence(self, record):
        try:
            self.reset()
        except Exception as exc:
            record.update(passed=False, reset_error=str(exc))

    def run_paired(self, indices, evidence_dir, timeout=20.0, label="paired"):
        """Persist each load/run immediately; compare only two complete matched runs."""
        require(self.paired_firmware is not None, "Paired firmware release required")
        indices = list(indices)
        report = dict(schema=1, kind="PAIRED_BOARD_RUN", started_at_utc=utc_now(),
                      passed=False, status="FAIL", requested_indices=indices,
                      artifacts=deepcopy(self.artifacts), runs={}, evidence_paths=[])
        try:
            for mode in MODES:
                load = self.select_firmware(mode)
                report["evidence_paths"].append(str(self._save_stage(load, evidence_dir, label + "_load_" + mode)))
                run = self.run_cases(indices, timeout=timeout)
                report["runs"][mode] = run
                report["evidence_paths"].append(str(self._save_stage(run, evidence_dir, label + "_" + mode)))
                require(run["passed"], mode + " official validation failed")
            report["comparison"] = compare_paired(report["runs"]["cpu_only"], report["runs"]["accelerated"])
            report.update(passed=True, status="PAIRED_FULL_PASS" if
                          all(run["full_pass"] for run in report["runs"].values()) else "PAIRED_SUBSET_PASS")
        except Exception as exc:
            report.update(error_type=type(exc).__name__, error=str(exc))
            if isinstance(exc, CaseFailure):
                report["failure"] = exc.record
                report["evidence_paths"].append(str(self._save_stage(exc.record, evidence_dir, label + "_failure")))
            self._reset_for_evidence(report)
        report["finished_at_utc"] = utc_now()
        report["report_path"] = str(self._save_stage(report, evidence_dir, label))
        return report

    def run_repetitions(self, evidence_dir, indices=(0, 1, 115), repeats=10, timeout=20.0):
        require(self.paired_firmware is not None and type(repeats) is int and repeats > 0,
                "Repeated paired tests require a paired release and positive repeat count")
        report = dict(schema=1, kind="REPEATED_BOARD_RUN", started_at_utc=utc_now(),
                      passed=False, status="FAIL", repeats=repeats, requested_indices=list(indices),
                      artifacts=deepcopy(self.artifacts), runs={}, evidence_paths=[],
                      order_note="cpu_only block then accelerated block; no firmware loads inside case timing")
        try:
            for mode in MODES:
                load = self.select_firmware(mode)
                report["evidence_paths"].append(str(self._save_stage(load, evidence_dir, "repeat_load_" + mode)))
                report["runs"][mode] = []
                for repetition in range(repeats):
                    run = self.run_cases(report["requested_indices"], timeout=timeout)
                    run["repetition"] = repetition
                    report["runs"][mode].append(run)
                    report["evidence_paths"].append(str(self._save_stage(run, evidence_dir,
                                                       "repeat_%s_%02d" % (mode, repetition))))
                    require(run["passed"], "Repeated validation failed")
            report["comparisons"] = [compare_paired(a, b) for a, b in
                                     zip(report["runs"]["cpu_only"], report["runs"]["accelerated"])]
            summary = []
            for mode in MODES:
                for index in report["requested_indices"]:
                    rows = [next(row for row in run["cases"] if row["case_index"] == index)
                            for run in report["runs"][mode]]
                    summary.append(dict(mode=mode, case_index=index, operation=rows[0]["operation"],
                        samples=len(rows), raw_cycles=distribution([row["raw_cycles"] for row in rows]),
                        wall_seconds=distribution([row["wall_seconds"] for row in rows])))
            report.update(passed=True, status="REPEAT_PASS", statistics=summary,
                          percentile_definition="P95 = nearest rank ceil(0.95*n); with n=10, P95 is the maximum")
        except Exception as exc:
            report.update(error_type=type(exc).__name__, error=str(exc))
            if isinstance(exc, CaseFailure):
                report["failure"] = exc.record
            self._reset_for_evidence(report)
        report["finished_at_utc"] = utc_now()
        report["report_path"] = str(self._save_stage(report, evidence_dir, "repetitions"))
        return report

    def _bad_magic(self, timeout, detail):
        """Only mutate the input mailbox magic; require exact firmware ERR_MAGIC."""
        self.reset()
        words = list(self.vectors["cases"][0]["input_words"])
        words[0] ^= 1
        self._write_words(INPUT, [0] * (WINDOW_BYTES // 4))
        self._write_words(OUTPUT, [0] * (WINDOW_BYTES // 4))
        self._write_words(INPUT, words)
        self.mmio.write(REG + 8, 1)
        begin = time.perf_counter()
        while True:
            trap, status = self._read(REG + 0x10), self._read(REG + 0x0C)
            detail.update(trap=trap, status=status, elapsed_seconds=time.perf_counter() - begin)
            require(trap == 0 and status != COMPLETE, "Malformed input trapped or incorrectly completed")
            if status == FAILED:
                break
            require(time.perf_counter() - begin < timeout, "Malformed input did not report protocol failure")
            time.sleep(0.001)
        detail.update(firmware_error_code=self._read(REG + 0x44), output_magic=self._read(OUTPUT),
                      hardware=[self._read(REG + 0x80 + 4 * i) for i in range(4)])
        require(detail["firmware_error_code"] == 2 and detail["output_magic"] == 0
                and detail["hardware"] == [0, 0, 0, 0], "Malformed magic rejection evidence mismatch")
        self.reset()
        return detail

    def run_recovery_checks(self, evidence_dir, timeout=20.0,
                            checks=("reset", "bad_magic", "short_timeout")):
        """Controlled mailbox-only fault injection, then verify a fresh official case."""
        require(self.paired_firmware is not None, "Paired firmware release required")
        require(checks and len(checks) == len(set(checks)) and
                all(name in ("reset", "bad_magic", "short_timeout") for name in checks),
                "Unknown or duplicate recovery check")
        report = dict(schema=1, kind="CONTROLLED_RECOVERY", started_at_utc=utc_now(),
                      passed=False, status="FAIL", tests=[], evidence_paths=[],
                      artifacts=deepcopy(self.artifacts),
                      scope="Reset, invalid mailbox magic and host deadline recovery; distinct from official key-check negatives")
        try:
            for mode in MODES:
                load = self.select_firmware(mode)
                report["evidence_paths"].append(str(self._save_stage(load, evidence_dir, "recovery_load_" + mode)))
                for name in checks:
                    test = dict(mode=mode, name=name, passed=False, started_at_utc=utc_now())
                    report["tests"].append(test)
                    try:
                        if name == "reset":
                            test["before"] = self.run_case(0, timeout=timeout)
                            self.reset()
                            require(self._read(REG + 8) == 0 and self._read(REG + 0x0C) == 0 and
                                    all(self._read(REG + 0x80 + 4 * i) == 0 for i in range(4)),
                                    "Reset failed to clear run/status/hardware counters")
                        elif name == "bad_magic":
                            test["injection"] = {}
                            self._bad_magic(timeout, test["injection"])
                        else:
                            try:
                                self.run_case(0, timeout=1e-9, poll_interval=0)
                            except CaseFailure as exc:
                                test["injection"] = exc.record
                                require(exc.record.get("error_type") == "TimeoutError" and
                                        exc.record.get("hardware_status") != COMPLETE and
                                        self._read(REG + 8) == 0,
                                        "Short timeout did not abort an incomplete job into reset")
                            else:
                                raise ValueError("Short timeout did not trigger")
                        test["recovery"] = self.run_case(0, timeout=timeout)
                        test["passed"] = True
                    except Exception as exc:
                        test.update(error_type=type(exc).__name__, error=str(exc))
                        if isinstance(exc, CaseFailure):
                            test["failure"] = exc.record
                        raise
                    finally:
                        self._reset_for_evidence(test)
                        report["evidence_paths"].append(str(self._save_stage(test, evidence_dir,
                                                                           "recovery_" + mode + "_" + name)))
                    require(test["passed"], "Failed to leave recovered device in reset")
            report.update(passed=True, status="RECOVERY_PASS")
        except Exception as exc:
            report.update(error_type=type(exc).__name__, error=str(exc))
            if isinstance(exc, CaseFailure):
                report["failure"] = exc.record
            self._reset_for_evidence(report)
        report["finished_at_utc"] = utc_now()
        report["report_path"] = str(self._save_stage(report, evidence_dir, "recovery"))
        return report


def distribution(values):
    values = sorted(values)
    require(bool(values), "Cannot summarize an empty distribution")
    return dict(minimum=values[0], median=statistics.median(values),
                p95=values[(95 * len(values) + 99) // 100 - 1], maximum=values[-1])


def compare_paired(cpu, accelerated):
    """Reject historical/unmatched/incomplete evidence before calculating ratios."""
    require(cpu.get("passed") and accelerated.get("passed"), "Both paired runs must pass")
    require(cpu.get("firmware_mode") == "cpu_only" and
            accelerated.get("firmware_mode") == "accelerated", "Paired firmware modes mismatch")
    for report in (cpu, accelerated):
        require(report.get("measurement_kind") == "PYNQ_BOARD_AXI_LIVE" and
                report.get("clock_hz") == FREQUENCY and report.get("firmware_load", {}).get("passed"),
                "Paired comparison requires live verified firmware and clock")
        rows = report["cases"]
        require([row["case_index"] for row in rows] == report["requested_indices"] and
                len(rows) == len(set(row["case_index"] for row in rows)) and
                all(row["passed"] and row["firmware_mode"] == report["firmware_mode"] for row in rows),
                "Incomplete, duplicate, or mixed-mode paired cases")
        load = report["firmware_load"]
        files = report["artifacts"]["files_sha256"]
        require(load["mode"] == report["firmware_mode"] and files.get(load["file"]) == load["file_sha256"] and
                load["expected_ram_sha256"] == load["readback_ram_sha256"], "Firmware load identity mismatch")
    require(cpu["requested_indices"] == accelerated["requested_indices"] and
            cpu["artifacts"]["manifest_sha256"] == accelerated["artifacts"]["manifest_sha256"] and
            cpu["artifacts"]["files_sha256"] == accelerated["artifacts"]["files_sha256"] and
            cpu["overlay_loaded_at_utc"] == accelerated["overlay_loaded_at_utc"],
            "Paired overlay, vector manifest, session or case order mismatch")
    require(cpu["firmware_load"]["file_sha256"] != accelerated["firmware_load"]["file_sha256"],
            "CPU-only and accelerated firmware must differ")
    rows = []
    for a, b in zip(cpu["cases"], accelerated["cases"]):
        require(all(a[key] == b[key] for key in
                    ("case_index", "identity", "op", "input_sha256", "output_sha256", "return_code", "frequency_hz")),
                "Paired case identity, input, output, return or clock mismatch")
        require(a["hardware"] == dict(starts=0, busy_cycles=0, buffer_writes=0, buffer_reads=0),
                "CPU-only hardware counters must all be zero")
        rows.append(dict(case_index=a["case_index"], operation=a["operation"],
                         cpu_raw_cycles=a["raw_cycles"], accelerated_raw_cycles=b["raw_cycles"],
                         api_speedup=a["raw_cycles"] / b["raw_cycles"],
                         cpu_wall_seconds=a["wall_seconds"], accelerated_wall_seconds=b["wall_seconds"],
                         wall_speedup=a["wall_seconds"] / b["wall_seconds"]))
    totals = {}
    for mode, report in (("cpu_only", cpu), ("accelerated", accelerated)):
        totals[mode] = dict(raw_cycles=sum(row["raw_cycles"] for row in report["cases"]),
            net_cycles=sum(row["raw_cycles"] - row["empty_cycles"] for row in report["cases"]),
            case_wall_seconds=sum(row["wall_seconds"] for row in report["cases"]),
            batch_wall_seconds=report["total_wall_seconds"],
            firmware_load_seconds=report["firmware_load"]["load_seconds"])
    a, b = totals["cpu_only"], totals["accelerated"]
    return dict(kind="SAME_BITSTREAM_LIVE_FIRMWARE_COMPARISON", cases=rows, totals=totals,
        api_speedup=a["raw_cycles"] / b["raw_cycles"],
        api_minus_empty_speedup=a["net_cycles"] / b["net_cycles"],
        ps_wall_speedup=a["case_wall_seconds"] / b["case_wall_seconds"],
        batch_wall_speedup=a["batch_wall_seconds"] / b["batch_wall_seconds"],
        timing_note="API is raw rdcycle; PS wall includes reset, I/O, polling and exact verification. Firmware load/readback and JSON saving excluded.",
        hardware_note="Same bitstream retains Keccak in both modes; CPU-only firmware does not call it. No area/power comparison.")


def self_test():
    """Host protocol tests with a strict fake MMIO; this never touches hardware."""
    import tempfile
    import unittest

    class FakeMMIO:
        def __init__(self, case, mode="ok"):
            self.data = bytearray(SPAN)
            self.case, self.mode = case, mode
            self.chunks = []
            for offset, value in ((0, HARDWARE_ID), (4, ABI), (0x14, FREQUENCY), (0x18, RAM_BYTES)):
                self.put(REG + offset, value)

        def put(self, offset, value):
            struct.pack_into("<I", self.data, offset, value & 0xFFFFFFFF)

        def read(self, offset):
            if offset < RAM_BYTES and self.read(REG + 8) and self.read(REG + 12) not in (COMPLETE, FAILED):
                raise AssertionError("Host read RAM while CPU is active")
            return struct.unpack_from("<I", self.data, offset)[0]

        def write(self, offset, value):
            if isinstance(value, bytes):
                assert not self.read(REG + 8), "Host wrote RAM while CPU is active"
                self.chunks.append((offset, value))
                self.data[offset:offset + len(value)] = value
                return
            self.put(offset, value)
            if offset != REG + 8:
                return
            self.put(REG + 0x10, 0)
            self.put(REG + 12, 0)
            if not value:
                for i in range(4):
                    self.put(REG + 0x80 + 4 * i, 0)
                for i in range(12):
                    self.put(REG + 0x40 + 4 * i, 0)
                return
            if struct.unpack_from("<I", self.data, INPUT)[0] != 0x3254414B:
                self.put(REG + 12, FAILED)
                self.put(REG + 0x44, 2)
                return
            if self.mode == "timeout":
                self.put(REG + 12, RUNNING)
                return
            if self.mode == "trap":
                self.put(REG + 0x10, 1)
                return
            if self.mode == "fail":
                self.put(REG + 12, FAILED)
                return
            case = self.case
            ret = case["expected_return"] & 0xFFFFFFFF
            if self.mode == "wrong_return":
                ret = (ret + 1) & 0xFFFFFFFF
            header = [OUTPUT_MAGIC, ABI, case["op"], ret, *case["output_lengths"], 10000, 4]
            payload = bytes.fromhex(case["expected_hex"])
            if self.mode == "wrong_output":
                payload = bytes([payload[0] ^ 1]) + payload[1:]
            body = struct.pack("<8I", *header) + payload
            self.data[OUTPUT:OUTPUT + len(body)] = body
            for index, word in ((3, 10000), (8, 4), (9, ret)):
                self.put(REG + 0x40 + 4 * index, word)
            hw = (dict(starts=0, buffer_writes=0, buffer_reads=0)
                  if self.data[:4] == b"CPU0" else case["expected_hardware"])
            for i, value in enumerate((hw["starts"], 1 if hw["starts"] else 0,
                                       hw["buffer_writes"], hw["buffer_reads"])):
                self.put(REG + 0x80 + 4 * i, value)
            if self.mode == "wrong_count":
                self.put(REG + 0x80, hw["starts"] + 1)
            self.put(REG + 12, COMPLETE)

    class ProtocolTests(unittest.TestCase):
        @classmethod
        def setUpClass(cls):
            # Synthetic identities keep tests self-contained on a board or PC.
            cases = []
            for index in range(CASE_COUNT):
                op = 5 if index == 6 else 1
                inputs, outputs = SHAPES[op]
                words = [0x3254414B, 1, 1024, 1, 20 + sum(inputs) // 4, 0, 0, 0,
                         0, 1, 42, 3, index + 1, op, *inputs, *outputs, 0]
                words += [0x04030201] * (sum(inputs) // 4)
                payload = bytes(sum(outputs))
                cases.append(dict(case_index=index, op=op, operation=OPERATIONS[op],
                    identity=dict(dataset_id=1, dataset="synthetic", vsId=42, tgId=3, tcId=index + 1),
                    input_words=words, expected_return=-4 if op == 5 else 0,
                    output_lengths=outputs, expected_hex=payload.hex(),
                    expected_sha256=hashlib.sha256(payload).hexdigest(),
                    expected_hardware=dict(starts=0 if op == 5 else 1,
                                           buffer_writes=0 if op == 5 else 52,
                                           buffer_reads=0 if op == 5 else 52),
                    historical_rtl_cpu_only=dict(kind="HISTORICAL_RTL_CPU_ONLY", config="rv32im_fast",
                                                raw_cycles=20000, empty_cycles=4, frequency_hz=FREQUENCY)))
            cls.vectors = dict(schema=1, algorithm="ML-KEM-1024", case_count=CASE_COUNT, cases=cases)

        def device(self, index=0, mode="ok"):
            mmio = FakeMMIO(self.vectors["cases"][index], mode)
            return MLKEM1024(mmio, self.vectors), mmio

        def test_chunks_byte_order_and_exact_output(self):
            device, mmio = self.device()
            row = device.run_case(0)
            self.assertTrue(row["passed"])
            expected = struct.pack("<%dI" % len(mmio.case["input_words"]), *mmio.case["input_words"])
            self.assertEqual(mmio.data[INPUT:INPUT + len(expected)], expected)
            self.assertTrue(all(len(value) <= 1024 for _, value in mmio.chunks))
            self.assertEqual(row["algorithm_seconds"], 0.0001)

        def test_signed_negative_error_is_official_pass(self):
            device, _ = self.device(index=6)
            self.assertEqual(device.run_case(6)["return_code"], -4)

        def test_katp_alone_cannot_pass(self):
            for mode in ("wrong_output", "wrong_count", "wrong_return"):
                with self.subTest(mode=mode):
                    device, mmio = self.device(mode=mode)
                    with self.assertRaises(CaseFailure):
                        device.run_case(0)
                    self.assertEqual(mmio.read(REG + 8), 0)

        def test_timeout_trap_and_firmware_fail(self):
            for mode in ("timeout", "trap", "fail"):
                with self.subTest(mode=mode):
                    device, mmio = self.device(mode=mode)
                    with self.assertRaises(CaseFailure):
                        device.run_case(0, timeout=0.002, poll_interval=0)
                    self.assertEqual(mmio.read(REG + 8), 0)

        def test_wrong_id(self):
            mmio = FakeMMIO(self.vectors["cases"][0])
            mmio.put(REG, 0)
            with self.assertRaisesRegex(ValueError, "Wrong overlay"):
                MLKEM1024(mmio, self.vectors)

        def test_full_pass_requires_all_unique_cases(self):
            device, mmio = self.device()
            self.assertEqual(device.run_cases([0])["status"], "SUBSET_PASS")
            with self.assertRaises(ValueError):
                device.run_cases([0, 0])
            original = device.run_case
            def selected(index, **kwargs):
                mmio.case = self.vectors["cases"][index]
                return original(index, **kwargs)
            device.run_case = selected
            self.assertEqual(device.run_cases(range(CASE_COUNT))["status"], "FULL_PASS")
            mmio.mode = "wrong_output"
            report = device.run_cases([0, 1])
            self.assertEqual(report["status"], "FAIL")
            self.assertFalse(report["full_pass"])
            self.assertEqual(len(report["cases"]), 1)

        def test_bundle_hashes_hwh_mapping_and_pair(self):
            with tempfile.TemporaryDirectory() as temp:
                directory = Path(temp)
                bit, hwh = directory / "test.bit", directory / "test.hwh"
                bit.write_bytes(b"not a hardware bitstream")
                hwh.write_text('<ROOT><MEMRANGE BASEVALUE="0x40000000" HIGHVALUE="0x4003ffff"/></ROOT>')
                write_json(directory / "kat_vectors.json", self.vectors)
                manifest = dict(schema=1, overlay=dict(bitstream=bit.name, base_address=BASE,
                    address_range=SPAN, id=HARDWARE_ID, abi=ABI, frequency_hz=FREQUENCY, ram_bytes=RAM_BYTES),
                    files={name: sha256(directory / name) for name in
                           (bit.name, hwh.name, "kat_vectors.json")})
                path = directory / "release_manifest.json"
                write_json(path, manifest)
                verify_bundle(path)
                bit.write_bytes(b"changed")
                with self.assertRaisesRegex(ValueError, "SHA-256"):
                    verify_bundle(path)
                manifest["files"][bit.name] = sha256(bit)
                hwh.write_text('<ROOT><MEMRANGE BASEVALUE="0x41000000" HIGHVALUE="0x4103ffff"/></ROOT>')
                manifest["files"][hwh.name] = sha256(hwh)
                write_json(path, manifest)
                with self.assertRaisesRegex(ValueError, "HWH"):
                    verify_bundle(path)
                del manifest["files"][hwh.name]
                write_json(path, manifest)
                with self.assertRaisesRegex(ValueError, "matching"):
                    verify_bundle(path)

        def paired_device(self, directory, mode="ok"):
            device, mmio = self.device(mode=mode)
            firmware = {}
            for name, prefix in (("cpu_only", b"CPU0"), ("accelerated", b"ACC0")):
                words = [struct.unpack("<I", prefix)[0]] + [0] * (RAM_BYTES // 4 - 1)
                path = directory / (name + ".mem")
                path.write_text("".join("%08x\n" % word for word in words), encoding="ascii")
                firmware[name] = dict(file=path.name, sha256=sha256(path))
            artifacts = dict(manifest_sha256="test-manifest",
                             files_sha256={item["file"]: item["sha256"] for item in firmware.values()})
            device = MLKEM1024(mmio, self.vectors, artifacts=artifacts,
                              paired_firmware=firmware, bundle_directory=directory)
            return device, mmio

        def test_paired_full_ram_clear_upload_readback_and_zero_counters(self):
            with tempfile.TemporaryDirectory() as temp:
                device, mmio = self.paired_device(Path(temp))
                with self.assertRaisesRegex(ValueError, "Select"):
                    device.run_case(0)
                mmio.data[:RAM_BYTES] = b"\xff" * RAM_BYTES
                load = device.select_firmware("cpu_only")
                self.assertTrue(load["passed"])
                self.assertEqual(len(mmio.chunks), 256)  # full clear plus full load
                self.assertEqual(mmio.data[4:RAM_BYTES], bytes(RAM_BYTES - 4))
                row = device.run_case(0)
                self.assertEqual(set(row["hardware"].values()), {0})
                mmio.mode = "wrong_count"
                with self.assertRaises(CaseFailure):
                    device.run_case(0)
                mmio.mode = "ok"
                device.select_firmware("accelerated")
                self.assertGreater(device.run_case(0)["hardware"]["starts"], 0)

        def test_readback_mismatch_blocks_run_and_preserves_failure(self):
            with tempfile.TemporaryDirectory() as temp:
                device, mmio = self.paired_device(Path(temp))
                original = mmio.read
                mmio.read = lambda offset: original(offset) ^ (1 if offset == 4 else 0)
                result = device.run_paired([0], Path(temp) / "evidence")
                self.assertFalse(result["passed"])
                self.assertIn("readback", result["failure"]["error"])
                self.assertTrue(Path(result["report_path"]).is_file())
                self.assertEqual(mmio.read(REG + 8), 0)
                with self.assertRaisesRegex(ValueError, "Select"):
                    device.run_case(0)

        def test_paired_identity_mismatch_and_failed_run_never_compared(self):
            with tempfile.TemporaryDirectory() as temp:
                device, mmio = self.paired_device(Path(temp))
                result = device.run_paired([0], Path(temp) / "evidence")
                self.assertTrue(result["passed"])
                self.assertEqual(result["comparison"]["api_speedup"], 1)
                a, b = result["runs"]["cpu_only"], result["runs"]["accelerated"]
                for field, value in (("input_sha256", "changed"), ("identity", {}),
                                     ("firmware_mode", "cpu_only")):
                    altered = deepcopy(b)
                    altered["cases"][0][field] = value
                    with self.subTest(field=field), self.assertRaises(ValueError):
                        compare_paired(a, altered)
                altered = deepcopy(b)
                altered["artifacts"]["manifest_sha256"] = "other"
                with self.assertRaises(ValueError):
                    compare_paired(a, altered)
                mmio.mode = "wrong_output"
                failure = device.run_paired([0], Path(temp) / "evidence")
                self.assertFalse(failure["passed"])
                self.assertNotIn("comparison", failure)
                self.assertTrue(failure["runs"]["cpu_only"]["cases"][0]["error"])

        def test_repetitions_and_recovery_evidence(self):
            with tempfile.TemporaryDirectory() as temp:
                device, mmio = self.paired_device(Path(temp))
                result = device.run_repetitions(Path(temp) / "evidence", indices=[0], repeats=2)
                self.assertTrue(result["passed"])
                self.assertEqual(result["statistics"][0]["samples"], 2)
                recovery = device.run_recovery_checks(Path(temp) / "evidence", checks=("reset", "bad_magic"))
                self.assertTrue(recovery["passed"])
                self.assertEqual(len(recovery["tests"]), 4)
                self.assertEqual(mmio.read(REG + 8), 0)

        def test_short_timeout_recovery_and_no_false_pass(self):
            with tempfile.TemporaryDirectory() as temp:
                device, mmio = self.paired_device(Path(temp))
                original = device.run_case
                def controlled(index, **kwargs):
                    mmio.mode = "timeout" if kwargs.get("timeout", 1) < 1e-6 else "ok"
                    return original(index, **kwargs)
                device.run_case = controlled
                report = device.run_recovery_checks(Path(temp) / "evidence", checks=("short_timeout",))
                self.assertTrue(report["passed"])
                for test in report["tests"]:
                    self.assertEqual(test["injection"]["error_type"], "TimeoutError")
                    self.assertTrue(test["recovery"]["passed"])
                device.run_case = original  # instant fake completion must not count as an abort
                mmio.mode = "ok"
                rejected = device.run_recovery_checks(Path(temp) / "evidence", checks=("short_timeout",))
                self.assertFalse(rejected["passed"])
                self.assertTrue(Path(rejected["report_path"]).exists())

        def test_paired_manifest_must_bind_both_images_and_driver(self):
            with tempfile.TemporaryDirectory() as temp:
                directory = Path(temp)
                device, _ = self.paired_device(directory)
                (directory / "test.bit").write_bytes(b"synthetic")
                (directory / "test.hwh").write_text('<ROOT><MEMRANGE BASEVALUE="0x40000000" HIGHVALUE="0x4003ffff"/></ROOT>')
                (directory / "mlkem1024.py").write_bytes(Path(__file__).read_bytes())
                write_json(directory / "kat_vectors.json", self.vectors)
                manifest = dict(schema=1, paired_firmware=device.paired_firmware,
                    overlay=dict(bitstream="test.bit", base_address=BASE, address_range=SPAN,
                                 id=HARDWARE_ID, abi=ABI, frequency_hz=FREQUENCY, ram_bytes=RAM_BYTES),
                    files={file.name: sha256(file) for file in directory.iterdir()})
                path = directory / "release_manifest.json"
                write_json(path, manifest)
                verify_bundle(path)
                altered = deepcopy(manifest)
                del altered["paired_firmware"]["accelerated"]
                write_json(path, altered)
                with self.assertRaisesRegex(ValueError, "exactly"):
                    verify_bundle(path)
                altered = deepcopy(manifest)
                altered["paired_firmware"]["cpu_only"]["sha256"] = "wrong"
                write_json(path, altered)
                with self.assertRaisesRegex(ValueError, "firmware"):
                    verify_bundle(path)
                altered = deepcopy(manifest)
                del altered["files"]["mlkem1024.py"]
                write_json(path, altered)
                with self.assertRaisesRegex(ValueError, "driver"):
                    verify_bundle(path)

        def test_firmware_parser_rejects_truncated_or_addressed_images(self):
            with tempfile.TemporaryDirectory() as temp:
                path = Path(temp) / "bad.mem"
                for content in ("00000000\n", "@0\n" + "00000000\n" * 32767):
                    path.write_text(content, encoding="ascii")
                    with self.assertRaises(ValueError):
                        read_firmware(path)

    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ProtocolTests))
    return 0 if result.wasSuccessful() else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare", action="store_true", help="Create portable official vectors on a developer PC")
    mode.add_argument("--self-test", action="store_true", help="Run fake-MMIO tests without PYNQ or hardware")
    parser.add_argument("--root", type=Path, help="Repository root; otherwise discover from this file")
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parent,
                        help="Directory receiving kat_vectors.json")
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    target = prepare(args.root, args.output)
    print("PREPARED 145 official cases: " + str(target))
    print("SHA256 " + sha256(target))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
