"""Contract-driven PYNQ overlay verification; stdlib-only until connect(). Python 3.6+."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import sys
import time
import xml.etree.ElementTree as ET


def number(value):
    if isinstance(value, bool):
        raise ValueError("Boolean is not an integer")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return int(value, 0)
    raise ValueError("Expected integer or 0x-prefixed string: {!r}".format(value))


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def local_file(root, name):
    # The flat bundle is portable between Windows, Linux, and Jupyter.
    if not isinstance(name, str) or not name or name in (".", "..") or any(c in name for c in "/\\:"):
        raise ValueError("Expected a flat bundle filename: {!r}".format(name))
    path = (root / name).resolve()
    if path.parent != root.resolve():
        raise ValueError("Bundle file resolves outside its directory")
    return path


def validate_contract(contract):
    if type(contract.get("schema")) is not int or contract["schema"] != 1:
        raise ValueError("Unsupported contract schema")
    bit = contract.get("bitstream", "")
    if Path(bit).suffix != ".bit" or contract.get("hwh") != str(Path(bit).with_suffix(".hwh")):
        raise ValueError("Require a same-stem .bit/.hwh pair")
    for name in (bit, contract["hwh"]):
        local_file(Path.cwd(), name)
        if not re.fullmatch(r"[0-9a-f]{64}", contract.get("files", {}).get(name, "")):
            raise ValueError("Missing SHA-256 for " + name)
    ip = contract["ip"]
    base, span = number(ip["base_address"]), number(ip["address_range"])
    if base < 0 or base % 4 or span <= 0 or span % 4:
        raise ValueError("AXI base/span must be positive-sized and 32-bit aligned")
    if not isinstance(ip.get("name"), str) or not ip["name"]:
        raise ValueError("An IP hierarchy name is required")
    if type(ip.get("allow_mmio_fallback", False)) is not bool:
        raise ValueError("allow_mmio_fallback must be boolean")
    registers = contract.get("registers", {})
    if not registers or not isinstance(registers, dict):
        raise ValueError("Named registers are required")
    seen = set()
    for name, reg in registers.items():
        offset = number(reg["offset"])
        if not name or offset < 0 or offset % 4 or offset + 4 > span or offset in seen:
            raise ValueError("Invalid, overlapping, or out-of-range register " + name)
        seen.add(offset)
        if type(reg.get("snapshot", False)) is not bool:
            raise ValueError("snapshot must be boolean")
        if reg.get("access") not in ("ro", "rw", "wo", "w1c", "rc"):
            raise ValueError("Unknown register access for " + name)
    if not contract.get("identity"):
        raise ValueError("At least one stable read-only identity register is required")
    for check in contract["identity"]:
        reg = registers[check["register"]]
        expected = number(check["equals"])
        mask = number(check.get("mask", "0xffffffff"))
        if reg["access"] != "ro" or not 0 <= expected <= 0xffffffff or not 0 < mask <= 0xffffffff:
            raise ValueError("Identity requires a stable ro register and a valid value/mask")
    return contract


def read_contract(path):
    path = Path(path).resolve()
    return path, validate_contract(json.loads(path.read_text(encoding="utf-8-sig")))


def hwh_ranges(path):
    ranges = []
    for node in ET.parse(str(path)).iter():
        attrs = {k.upper(): v for k, v in node.attrib.items()}
        if "BASEVALUE" in attrs and "HIGHVALUE" in attrs:
            ranges.append((number(attrs["BASEVALUE"]), number(attrs["HIGHVALUE"])))
    return ranges


def verify_bundle(path, bundle_dir=None):
    path, contract = read_contract(path)
    bundle = Path(bundle_dir).resolve() if bundle_dir is not None else path.parent
    verified = {}
    for name, expected in contract["files"].items():
        file_path = local_file(bundle, name)
        if not re.fullmatch(r"[0-9a-f]{64}", expected) or sha256(file_path) != expected:
            raise ValueError("SHA-256 mismatch: " + name)
        verified[name] = expected
    base = number(contract["ip"]["base_address"])
    span = number(contract["ip"]["address_range"])
    ranges = hwh_ranges(local_file(bundle, contract["hwh"]))
    if (base, base + span - 1) not in ranges:
        raise ValueError("HWH does not contain the exact contract address range")
    return contract, {"contract_sha256": sha256(path), "files_sha256": verified,
                      "hwh_ranges": ranges, "hardware_verified": False}


class RegisterIO:
    """Single-caller, 32-bit register access. Offsets are IP-relative, including subwindows."""
    def __init__(self, backend, contract):
        self.backend, self.contract = backend, contract

    def _register(self, name):
        return self.contract["registers"][name]

    def read(self, name):
        reg = self._register(name)
        if reg["access"] in ("wo", "w1c"):
            raise ValueError("Register is not readable: " + name)
        return int(self.backend.read(number(reg["offset"]))) & 0xffffffff

    def write(self, name, value):
        reg = self._register(name)
        value = number(value)
        if reg["access"] not in ("rw", "wo", "w1c") or not 0 <= value <= 0xffffffff:
            raise ValueError("Register is not writable or value exceeds uint32: " + name)
        # Never read/modify/write command or W1C registers.
        self.backend.write(number(reg["offset"]), value)

    def snapshot(self):
        # Reading rc/ap_ctrl registers can acknowledge completion. Do not auto-read them.
        return {name: self.read(name) for name, reg in self.contract["registers"].items()
                if reg["access"] in ("ro", "rw") and reg.get("snapshot", False)}

    def verify_identity(self):
        actual = {}
        for check in self.contract["identity"]:
            name = check["register"]
            value, mask = self.read(name), number(check.get("mask", "0xffffffff"))
            actual[name] = value
            if value & mask != number(check["equals"]) & mask:
                raise ValueError("Hardware identity mismatch: {}={:#x}".format(name, value))
        return actual

    def poll(self, name, mask, expected, timeout=5.0, interval=0.001, error=None):
        mask, expected = number(mask), number(expected)
        if not 0 < mask <= 0xffffffff or not 0 <= expected <= 0xffffffff or expected & ~mask:
            raise ValueError("Invalid polling mask/expected")
        if not math.isfinite(timeout) or not math.isfinite(interval) or timeout <= 0 or interval < 0:
            raise ValueError("Invalid timeout or interval")
        if error:
            error_mask = number(error["mask"])
            if not 0 < error_mask <= 0xffffffff:
                raise ValueError("Invalid error mask")
        deadline = time.monotonic() + timeout
        while True:
            value = self.read(name)
            # Reuse destructive status reads if completion and errors share a register.
            if error:
                failure = value if error["register"] == name else self.read(error["register"])
                if failure & error_mask:
                    raise RuntimeError("Hardware failure: {}={:#x}".format(error["register"], failure))
            if time.monotonic() >= deadline:
                raise TimeoutError("Timeout: {}={:#x}, safe snapshot={}".format(name, value, self.snapshot()))
            if value & mask == expected:
                return value
            if interval:
                time.sleep(min(interval, max(0, deadline - time.monotonic())))


def connect(path, download=False, overlay_factory=None, mmio_factory=None, bundle_dir=None):
    """Validate artifacts before touching PL. Inject factories for offline testing."""
    contract, evidence = verify_bundle(path, bundle_dir)
    if overlay_factory is None or mmio_factory is None:
        from pynq import Overlay, MMIO
        overlay_factory = overlay_factory or Overlay
        mmio_factory = mmio_factory or MMIO
    bundle = Path(bundle_dir).resolve() if bundle_dir is not None else Path(path).resolve().parent
    bit_path = local_file(bundle, contract["bitstream"])
    overlay = overlay_factory(str(bit_path), download=False)
    spec = contract["ip"]
    ip_info = overlay.ip_dict.get(spec["name"])
    base, span = number(spec["base_address"]), number(spec["address_range"])
    if ip_info is not None:
        if number(ip_info["phys_addr"]) != base or number(ip_info["addr_range"]) != span:
            raise ValueError("PYNQ ip_dict address differs from contract/HWH")
    elif not spec.get("allow_mmio_fallback", False):
        raise ValueError("IP missing from ip_dict; confirm module-reference mapping before enabling MMIO fallback")
    if download:
        overlay.download()
    elif not overlay.is_loaded():
        raise RuntimeError("This overlay is not loaded; explicitly request download")
    backend = mmio_factory(base, span)
    registers = RegisterIO(backend, contract)
    evidence.update(hardware_identity=registers.verify_identity(), hardware_verified=True,
                    ip_dict_present=ip_info is not None, downloaded=bool(download))
    return overlay, registers, evidence


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("contract")
    parser.add_argument("--bundle-dir", type=Path, help="Artifact directory; defaults to contract directory")
    parser.add_argument("--download", action="store_true", help="Program PL and verify read-only hardware identity")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.download:
            _, _, evidence = connect(args.contract, download=True, bundle_dir=args.bundle_dir)
        else:
            _, evidence = verify_bundle(args.contract, args.bundle_dir)
        result, code = dict(passed=True, **evidence), 0
    except Exception as exc:
        result, code = dict(passed=False, error_type=type(exc).__name__, error=str(exc)), 1
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text)
    return code


if __name__ == "__main__":
    sys.exit(main())
