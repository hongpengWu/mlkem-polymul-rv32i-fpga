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


def prepare(root, output):
    """Freeze public vectors and historical references on the developer PC."""
    require(sys.version_info >= (3, 10), "Run --prepare on the developer PC with Python 3.10+")
    root, output = Path(root).resolve(), Path(output).resolve()
    sys.path[:0] = [str(root / "scripts/kat"), str(root / "scripts/mlkem1024_keccak")]
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
                        "scripts/mlkem1024_keccak/collect_kat.py",
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


class CaseFailure(RuntimeError):
    def __init__(self, message, record):
        super().__init__(message)
        self.record = record


class MLKEM1024:
    """One reset/run/verify transaction at a time; no concurrent callers."""

    def __init__(self, mmio, vectors, artifacts=None, overlay=None):
        self.mmio = mmio
        self.vectors = validate_vectors(vectors)
        self.artifacts = artifacts or {}
        self.overlay = overlay
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
        return cls(MMIO(BASE, SPAN), vectors, artifacts=artifacts, overlay=overlay)

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
        require(type(index) is int and 0 <= index < CASE_COUNT, "Invalid official case index")
        require(timeout > 0 and poll_interval >= 0, "Invalid timeout or polling interval")
        case = self.vectors["cases"][index]
        started = time.perf_counter()
        record = dict(case_index=index, operation=case["operation"], op=case["op"],
            identity=deepcopy(case["identity"]), started_at_utc=utc_now(),
            measurement_kind="PYNQ_BOARD_AXI_LIVE", passed=False,
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
            require(all(hardware[name] == expected for name, expected in case["expected_hardware"].items()),
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
                speedup="No measured board speedup until both overlays are measured"), cases=[])
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
            if offset < RAM_BYTES and self.read(REG + 8) and self.read(REG + 12) != COMPLETE:
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
            hw = case["expected_hardware"]
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

    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ProtocolTests))
    return 0 if result.wasSuccessful() else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare", action="store_true", help="Create portable official vectors on a developer PC")
    mode.add_argument("--self-test", action="store_true", help="Run fake-MMIO tests without PYNQ or hardware")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
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
