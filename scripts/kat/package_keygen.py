#!/usr/bin/env python3
"""Package one or more official ACVP ML-KEM keyGen cases for PicoRV32.

The ACVP JSON files are intentionally kept out of a PicoRV32 firmware image.
This tool extracts the deterministic ``d || z`` input used by
``mlk_kem_keypair_derand`` and emits a small generated C header plus two
word-addressed .mem fixtures.  The firmware image consumes the C header; the
testbench consumes the expected-results fixture.  Keeping those artefacts
separate prevents a testbench oracle from becoming part of the measured code.

All multi-byte values in the .mem files are little-endian words, matching the
PicoRV32 byte-addressed RAM.  Byte strings in the generated C header retain
the byte order from ACVP.  In particular, the API coin buffer is d followed by
z, while the JSON prompt lists the fields as z and d.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Iterable

from validate_acvp_json import check_sha256_manifest, validate_pair


MAGIC = 0x3141544B  # bytes "KAT1" in a little-endian .mem word
VERSION = 1
OP_KEYGEN = 1
ACVP_COMMIT = "975de31eb83d87039ec88934fdc47d8c312b892d"
UPSTREAM_PATH = "gen-val/json-files/ML-KEM-keyGen-FIPS203"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_sources(root: Path) -> None:
    vector_root = root / "vectors/official_kat/acvp"
    errors = []
    check_sha256_manifest(vector_root, errors)
    keygen_root = vector_root / "fips203/ML-KEM-keyGen"
    _, _, pair_errors = validate_pair(
        keygen_root / "prompt.json", keygen_root / "expectedResults.json", vector_root
    )
    errors.extend(pair_errors)
    if errors:
        raise ValueError("ACVP source validation failed:\n" + "\n".join(str(e) for e in errors))


def parse_hex(name: str, value: str, size: int) -> bytes:
    if not isinstance(value, str) or len(value) != 2 * size:
        raise ValueError(f"{name}: expected {size} bytes, got {value!r}")
    try:
        out = bytes.fromhex(value)
    except ValueError as exc:
        raise ValueError(f"{name}: invalid hexadecimal value") from exc
    if len(out) != size:
        raise ValueError(f"{name}: expected {size} bytes, got {len(out)}")
    return out


def load_cases(root: Path, parameter_set: int, tc_ids: set[int]) -> list[dict]:
    prompt_path = root / "vectors/official_kat/acvp/fips203/ML-KEM-keyGen/prompt.json"
    expected_path = root / "vectors/official_kat/acvp/fips203/ML-KEM-keyGen/expectedResults.json"
    prompt = json.loads(prompt_path.read_text(encoding="utf-8"))
    expected = json.loads(expected_path.read_text(encoding="utf-8"))
    for label, data in (("prompt", prompt), ("expected", expected)):
        if (data["algorithm"], data["mode"], data["revision"]) != ("ML-KEM", "keyGen", "FIPS203"):
            raise ValueError(f"{label}: not a final FIPS203 ML-KEM keyGen vector")
    group_name = f"ML-KEM-{parameter_set}"
    groups = [g for g in prompt["testGroups"] if g["parameterSet"] == group_name]
    if len(groups) != 1:
        raise ValueError(f"expected one prompt group for {group_name}")
    if groups[0]["testType"] != "AFT":
        raise ValueError(f"{group_name}: only AFT keyGen cases are supported")
    ptests = {int(t["tcId"]): t for t in groups[0]["tests"]}
    egroups = [g for g in expected["testGroups"] if int(g["tgId"]) == int(groups[0]["tgId"])]
    if len(egroups) != 1:
        raise ValueError(f"expected one expected-results group for tgId={groups[0]['tgId']}")
    etests = {int(t["tcId"]): t for t in egroups[0]["tests"]}
    if not tc_ids:
        tc_ids = {min(ptests)}
    out = []
    for tc_id in sorted(tc_ids):
        if tc_id not in ptests or tc_id not in etests:
            raise ValueError(f"tcId={tc_id} is missing from {group_name}")
        p, e = ptests[tc_id], etests[tc_id]
        out.append(
            {
                "tc_id": tc_id,
                "tg_id": int(groups[0]["tgId"]),
                "vs_id": int(prompt["vsId"]),
                "d": parse_hex("d", p["d"], 32),
                "z": parse_hex("z", p["z"], 32),
                "ek": parse_hex("ek", e["ek"], {512: 800, 768: 1184, 1024: 1568}[parameter_set]),
                "dk": parse_hex("dk", e["dk"], {512: 1632, 768: 2400, 1024: 3168}[parameter_set]),
            }
        )
    return out


def words(data: bytes) -> Iterable[int]:
    padded = data + bytes((-len(data)) % 4)
    for offset in range(0, len(padded), 4):
        yield int.from_bytes(padded[offset : offset + 4], "little")


def write_mem(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(f"{word:08x}\n" for word in words(data)), encoding="ascii", newline="\n")


def append_u32(out: bytearray, value: int) -> None:
    out.extend(int(value).to_bytes(4, "little"))


def make_input(cases: list[dict], parameter_set: int) -> bytes:
    out = bytearray()
    # Header: magic, version, operation, parameter set, case count, then the
    # fixed d/z sizes and a reserved word.  Each case is tcId, d[32], z[32].
    for value in (MAGIC, VERSION, OP_KEYGEN, parameter_set, len(cases), 32, 32, 0):
        append_u32(out, value)
    for case in cases:
        append_u32(out, case["tc_id"])
        out.extend(case["d"])
        out.extend(case["z"])
    return bytes(out)


def make_expected(cases: list[dict], parameter_set: int) -> bytes:
    out = bytearray()
    ek_size = len(cases[0]["ek"])
    dk_size = len(cases[0]["dk"])
    # Header: magic, version, operation, parameter set, case count, ek bytes,
    # dk bytes, reserved.  Each case is tcId, ek, dk.
    for value in (MAGIC, VERSION, OP_KEYGEN, parameter_set, len(cases), ek_size, dk_size, 0):
        append_u32(out, value)
    for case in cases:
        append_u32(out, case["tc_id"])
        out.extend(case["ek"])
        out.extend(case["dk"])
    return bytes(out)


def c_bytes(value: bytes, indent: str = "    ") -> str:
    rows = []
    for offset in range(0, len(value), 16):
        rows.append(indent + ", ".join(f"0x{x:02x}" for x in value[offset : offset + 16]))
    return ",\n".join(rows)


def make_header(cases: list[dict], parameter_set: int) -> str:
    ek_size, dk_size = len(cases[0]["ek"]), len(cases[0]["dk"])
    lines = [
        "/* Generated by scripts/kat/package_keygen.py; do not edit. */",
        "#ifndef KAT_KEYGEN_VECTORS_H",
        "#define KAT_KEYGEN_VECTORS_H",
        "#include <stdint.h>",
        f"#define KAT_KEYGEN_PARAMETER_SET {parameter_set}u",
        f"#define KAT_KEYGEN_CASE_COUNT {len(cases)}u",
        "#define KAT_KEYGEN_SEED_BYTES 32u",
        f"#define KAT_KEYGEN_EK_BYTES {ek_size}u",
        f"#define KAT_KEYGEN_DK_BYTES {dk_size}u",
        "typedef struct { uint32_t tc_id; uint8_t d[32]; uint8_t z[32]; } kat_keygen_case_t;",
        "static const kat_keygen_case_t kat_keygen_cases[KAT_KEYGEN_CASE_COUNT] = {",
    ]
    for case in cases:
        lines.extend(
            [
                f"    {{ {case['tc_id']}u,",
                "      {",
                c_bytes(case["d"], "        "),
                "      },",
                "      {",
                c_bytes(case["z"], "        "),
                "      } },",
            ]
        )
    lines.extend(["};", "#endif /* KAT_KEYGEN_VECTORS_H */", ""])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--parameter-set", type=int, choices=(512, 768, 1024), default=512)
    parser.add_argument("--tc-id", type=int, action="append", default=[], help="repeat to select cases")
    parser.add_argument("--out-dir", type=Path, default=None)
    args = parser.parse_args()
    root = args.root.resolve()
    out_dir = (args.out_dir or root / "tb/software/mlkem_keygen").resolve()
    validate_sources(root)
    cases = load_cases(root, args.parameter_set, set(args.tc_id))
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"mlkem{args.parameter_set}_keygen"
    (out_dir / f"{stem}.h").write_text(make_header(cases, args.parameter_set), encoding="ascii", newline="\n")
    write_mem(out_dir / f"{stem}_input.mem", make_input(cases, args.parameter_set))
    write_mem(out_dir / f"{stem}_expected.mem", make_expected(cases, args.parameter_set))
    manifest = {
        "algorithm": "ML-KEM",
        "operation": "keyGen",
        "revision": "FIPS203",
        "parameterSet": f"ML-KEM-{args.parameter_set}",
        "vsId": cases[0]["vs_id"],
        "tgId": cases[0]["tg_id"],
        "source": {
            "repository": "https://github.com/usnistgov/ACVP-Server",
            "commit": ACVP_COMMIT,
            "manifest": "vectors/official_kat/acvp/SHA256SUMS",
            "manifest_sha256": sha256(root / "vectors/official_kat/acvp/SHA256SUMS"),
            "manifest_verified": True,
            "files": [
                {
                    "path": f"vectors/official_kat/acvp/fips203/ML-KEM-keyGen/{name}",
                    "url": f"https://raw.githubusercontent.com/usnistgov/ACVP-Server/{ACVP_COMMIT}/{UPSTREAM_PATH}/{name}",
                    "sha256": sha256(root / f"vectors/official_kat/acvp/fips203/ML-KEM-keyGen/{name}"),
                }
                for name in ("prompt.json", "expectedResults.json")
            ],
        },
        "generator": {"path": "scripts/kat/package_keygen.py", "sha256": sha256(Path(__file__))},
        "cases": [
            {"tcId": c["tc_id"], "dBytes": len(c["d"]), "zBytes": len(c["z"]),
             "ekBytes": len(c["ek"]), "dkBytes": len(c["dk"])}
            for c in cases
        ],
        "header": f"{stem}.h",
        "inputMem": f"{stem}_input.mem",
        "expectedMem": f"{stem}_expected.mem",
        "endianness": "little-endian 32-bit words; C arrays preserve ACVP byte order",
        "outputs": {
            name: {"bytes": (out_dir / name).stat().st_size, "sha256": sha256(out_dir / name)}
            for name in (f"{stem}.h", f"{stem}_input.mem", f"{stem}_expected.mem")
        },
    }
    (out_dir / f"{stem}.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"KAT_KEYGEN_PACK_PASS parameter_set={args.parameter_set} cases={len(cases)} output={out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
