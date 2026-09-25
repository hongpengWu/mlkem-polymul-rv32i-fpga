#!/usr/bin/env python3
"""Audit current ML-KEM software/accelerator interface facts read-only."""

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
    parser.add_argument("--output", type=Path,
                        default=ROOT / "results/accelerator_interface/current_contract.json")
    args = parser.parse_args()

    paths = [
        "rtl/axi/mlkem_polymul_axi_wrapper.v",
        "hls/src/mlkem_poly_mul256_v39e_true_one_dsp.cpp",
        "hls/src/mlkem_poly_mul256_v39e_unified_stream_support.cpp",
        "hls/mlkem512_basemul_k2/src/mlkem512_basemul_acc_k2.h",
        "hls/mlkem512_basemul_k2/src/mlkem512_basemul_acc_k2.cpp",
        "third_party/mlkem-native/mlkem/src/poly.h",
        "third_party/mlkem-native/mlkem/src/poly.c",
        "third_party/mlkem-native/mlkem/src/poly_k.h",
        "third_party/mlkem-native/mlkem/src/poly_k.c",
        "third_party/mlkem-native/mlkem/src/indcpa.c",
        "third_party/mlkem-native/mlkem/src/params.h",
    ]
    text = {path: read(path) for path in paths}
    wrapper = text[paths[0]]
    hls = text[paths[1]]
    support = text[paths[2]]
    new_hls_h = text[paths[3]]
    new_hls = text[paths[4]]
    poly_h = text[paths[5]]
    poly_c = text[paths[6]]
    poly_k_h = text[paths[7]]
    poly_k_c = text[paths[8]]
    indcpa = text[paths[9]]
    params = text[paths[10]]

    for name, value in {
        "REG_CONTROL": "16'h0000", "REG_CYCLES": "16'h0004",
        "REG_ID": "16'h0008", "MEM_A_BASE": "16'h1000",
        "MEM_B_BASE": "16'h1200", "MEM_O_BASE": "16'h1400",
    }.items():
        has(wrapper, f"{name} = {value}", f"wrapper {name}")
    has(wrapper, "if (busy) begin", "busy protection")
    has(wrapper, "cycle_count <= cycle_count + 1'b1", "cycle counter")
    has(wrapper, "if (commit_strb[0] && commit_data[0])", "start command")
    has(wrapper, "s_axi_rdata <= {27'b0, access_error, busy, ap_idle, done_sticky, 1'b0}",
        "control status layout")

    has(hls, "void mlkem_poly_mul256_v39e_true_one_dsp(", "HLS top signature")
    for needle, label in [
        ("const coeff_t a[256]", "HLS operand A"),
        ("const coeff_t b[256]", "HLS operand B"),
        ("coeff_t output[256]", "HLS output"),
        ("MODE_FNTT39C", "HLS FNTT stage"),
        ("MODE_BM39C", "HLS BaseMul stage"),
        ("MODE_INTT39C", "HLS INTT stage"),
        ("MODE_SCALE39C", "HLS scale stage"),
        ("batch39d(pong,ping,ant,bnt,dummy,bm,bm_final,output,MODE_SCALE39C",
         "HLS final scale stage"),
    ]:
        has(hls, needle, label)
    for needle, label in [
        ("typedef ap_int<16> coeff_t", "HLS signed coefficient type"),
        ("typedef ap_uint<12> residue_t", "HLS residue type"),
        ("static const int Q39C = 3329", "HLS modulus"),
        ("static residue_t norm39c", "HLS input normalization"),
        ("xw<<10)+(xw<<8)", "HLS 1441 scale expression"),
    ]:
        has(support, needle, label)

    for needle, label in [
        ("void mlkem512_basemul_acc_k2(", "new HLS top signature"),
        ("const int16_t a[2][256]", "new HLS operand A"),
        ("const int16_t b[2][256]", "new HLS operand B"),
        ("const int16_t b_cache[2][128]", "new HLS mulcache input"),
        ("int16_t result[256]", "new HLS result"),
        ("#pragma HLS PIPELINE II=1", "new HLS coefficient-pair pipeline"),
        ("#pragma HLS UNROLL", "new HLS K=2 unroll"),
    ]:
        has(new_hls_h + new_hls, needle, label)

    for needle, label in [
        ("where R=2^16", "Montgomery radix"),
        ("const uint32_t QINV = 62209", "Montgomery inverse"),
    ]:
        has(poly_h, needle, label)
    has(poly_c, "const int16_t f = 1353", "poly_tomont factor")
    has(params, "#if MLK_CONFIG_PARAMETER_SET == 512", "ML-KEM-512 parameter branch")
    has(params, "#define MLKEM_K 2", "ML-KEM-512 K parameter")
    has(poly_c, "const int16_t f = 1441", "inverse NTT factor")
    has(poly_k_h, "in NTT domain", "polyvec NTT-domain contract")
    has(poly_k_h, "mulcache", "polyvec mulcache contract")
    has(poly_k_c, "int32_t t[2] = {0}", "K=2 vector accumulation")
    has(poly_k_c, "mlk_montgomery_reduce(t[0])", "vector output reduction")
    has(indcpa, "The public matrix is generated in NTT domain", "matrix NTT-domain contract")
    has(indcpa, "mlk_polyvec_basemul_acc_montgomery_cached(&out->vec[i]",
        "matrix-vector BaseMul call")
    has(indcpa, "mlk_polyvec_tomont(pkpv)", "KeyGen post-matvec scaling")
    has(indcpa, "mlk_polyvec_invntt_tomont(b)", "Encaps inverse NTT")

    contract = {
        "schema_version": 1,
        "status": "audited_legacy_and_new_interface_not_drop_in",
        "audited_at": "2026-09-25",
        "scope": "Read-only source audit before adapter and stage-oracle work.",
        "register_map": {
            "control": 0, "cycles": 4, "id": 8,
            "a_base": 0x1000, "b_base": 0x1200, "output_base": 0x1400,
            "a_bytes": 0x200, "b_bytes": 0x200, "output_bytes": 0x200,
            "word_bytes": 4, "coefficients_per_word": 2,
        },
        "control_bits": {
            "write_start": 0, "write_clear_done": 1,
            "write_clear_access_error": 2, "read_done": 1,
            "read_idle": 2, "read_busy": 3, "read_access_error": 4,
        },
        "current_hls_top": {
            "input_domain": "normal_time_domain_coefficients",
            "output_domain": "canonical_time_domain_coefficients",
            "coefficient_type": "signed_ap_int_16_at_top_unsigned_12_internal",
            "operation": "FNTT(A), FNTT(B), BaseMul, INTT, scale",
            "scale_constant_observed": 1441,
            "top_is_stage_configurable": False,
        },
        "new_hls_top": {
            "path": "hls/mlkem512_basemul_k2/src/mlkem512_basemul_acc_k2.cpp",
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
            "parameter_set": "ML-KEM-512", "k": 2, "q": 3329,
            "polynomial_coefficients": 256, "ntt_matrix_input": True,
            "ntt_vector_input": True, "mulcache_coefficients_per_polynomial": 128,
            "base_mul": "K=2 vector dot product with Montgomery reduction per output pair",
            "montgomery_radix": "2^16", "montgomery_qinv": 62209,
            "poly_tomont_factor": 1353, "invntt_initial_factor": 1441,
            "standard_coefficients": "signed int16 with lazy bounds; not always canonical [0,q)",
        },
        "integration_decision": {
            "direct_drop_in": False,
            "reason": "The current top consumes ordinary polynomials and returns a complete product, while standard matrix/vector BaseMul consumes NTT-domain operands and a reusable mulcache.",
            "next_boundary": "stage_oracle_then_ntt_domain_vector_base_mul_adapter",
            "preserve_original_sources": True,
        },
        "source_sha256": {path: sha(ROOT / path) for path in paths},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(contract, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"MLKEM512_INTERFACE_AUDIT_PASS output={args.output} sources={len(paths)}")


if __name__ == "__main__":
    main()
