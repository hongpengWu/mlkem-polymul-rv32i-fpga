#!/usr/bin/env python3
"""Audit the maintained ML-KEM-512 BaseMul interface read-only."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def read(rel: str) -> str:
    path = ROOT / rel
    require(path.is_file(), f"Missing source: {rel}")
    return path.read_text(encoding="utf-8")


def has(text: str, needle: str, label: str) -> None:
    compact = re.sub(r"\s+", " ", text)
    wanted = re.sub(r"\s+", " ", needle).strip()
    require(wanted in compact, f"Missing {label}: {needle}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "results/accelerator_interface/current_contract.json",
    )
    args = parser.parse_args()

    paths = [
        "hls/mlkem512_basemul_k2/src/mlkem512_basemul_acc_k2.h",
        "hls/mlkem512_basemul_k2/src/mlkem512_basemul_acc_k2.cpp",
        "third_party/mlkem-native/mlkem/src/poly.h",
        "third_party/mlkem-native/mlkem/src/poly.c",
        "third_party/mlkem-native/mlkem/src/poly_k.h",
        "third_party/mlkem-native/mlkem/src/poly_k.c",
        "third_party/mlkem-native/mlkem/src/indcpa.c",
        "third_party/mlkem-native/mlkem/src/params.h",
        "third_party/mlkem-native/mlkem/src/zetas.inc",
    ]
    text = {path: read(path) for path in paths}
    hls_h = text[paths[0]]
    hls = text[paths[1]]
    poly_h = text[paths[2]]
    poly_c = text[paths[3]]
    poly_k_h = text[paths[4]]
    poly_k_c = text[paths[5]]
    indcpa = text[paths[6]]
    params = text[paths[7]]
    zetas = text[paths[8]]

    for needle, label in [
        ("void mlkem512_basemul_acc_k2(", "HLS top signature"),
        ("const int16_t a[2][256]", "HLS operand A"),
        ("const int16_t b[2][256]", "HLS operand B"),
        ("const int16_t b_cache[2][128]", "HLS mulcache input"),
        ("int16_t result[256]", "HLS result"),
        ("#pragma HLS PIPELINE II=1", "coefficient-pair pipeline"),
        ("#pragma HLS UNROLL", "K=2 unroll"),
        ("constexpr int kQ = 3329", "HLS modulus"),
        ("constexpr uint32_t kQInv = 62209", "HLS Montgomery inverse"),
    ]:
        has(hls_h + hls, needle, label)

    for needle, label in [
        ("where R=2^16", "Montgomery radix"),
        ("const uint32_t QINV = 62209", "software Montgomery inverse"),
        ("const int16_t f = 1353", "forward-domain conversion factor"),
        ("const int16_t f = 1441", "inverse NTT factor"),
    ]:
        has(poly_h + poly_c, needle, label)
    for needle, label in [
        ("in NTT domain", "polyvec NTT-domain contract"),
        ("mulcache", "polyvec mulcache contract"),
    ]:
        has(poly_k_h, needle, label)
    for needle, label in [
        ("int32_t t[2] = {0}", "K=2 vector accumulation"),
        ("mlk_montgomery_reduce(t[0])", "vector output reduction"),
    ]:
        has(poly_k_c, needle, label)
    has(indcpa, "The public matrix is generated in NTT domain", "matrix NTT-domain contract")
    has(indcpa, "mlk_polyvec_basemul_acc_montgomery_cached(&out->vec[i]", "matrix-vector BaseMul call")
    has(indcpa, "mlk_polyvec_tomont(pkpv)", "KeyGen post-matvec scaling")
    has(indcpa, "mlk_polyvec_invntt_tomont(b)", "Encaps inverse NTT")
    has(params, "#if MLK_CONFIG_PARAMETER_SET == 512", "ML-KEM-512 branch")
    has(params, "#define MLKEM_K 2", "ML-KEM-512 K parameter")
    require("mlk_zetas" in zetas, "Missing portable zeta table")

    contract = {
        "schema_version": 2,
        "status": "audited_new_hls_interface",
        "audited_at": "2026-09-25",
        "scope": "Maintained K=2 NTT-domain BaseMul HLS and portable ML-KEM boundary.",
        "new_hls_top": {
            "path": paths[1],
            "input_domain": "NTT_domain",
            "operation": "K=2 cached vector BaseMul with one Montgomery reduction per output coefficient",
            "output_domain": "NTT_domain",
            "mulcache_is_explicit_input": True,
            "pipeline_granularity": "one coefficient pair",
            "k_unrolled": 2,
            "direct_drop_in": False,
            "requires_axilite_or_axi_adapter": True,
        },
        "standard_mlkem512_contract": {
            "parameter_set": "ML-KEM-512",
            "k": 2,
            "q": 3329,
            "polynomial_coefficients": 256,
            "base_mul": "K=2 vector dot product with Montgomery reduction per output pair",
            "montgomery_radix": "2^16",
            "montgomery_qinv": 62209,
            "poly_tomont_factor": 1353,
            "invntt_initial_factor": 1441,
            "standard_coefficients": "signed int16 with lazy bounds; not always canonical [0,q)",
        },
        "integration_decision": {
            "direct_drop_in": False,
            "reason": "The maintained HLS block consumes NTT-domain operands and an explicit mulcache; it does not perform NTT, inverse NTT, compression, or scaling.",
            "next_boundary": "stage_oracle_then_axi_bram_adapter",
            "legacy_complete_polymul_removed": True,
        },
        "source_sha256": {path: sha(ROOT / path) for path in paths},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(contract, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"MLKEM512_INTERFACE_AUDIT_PASS output={args.output} sources={len(paths)}")


if __name__ == "__main__":
    main()
