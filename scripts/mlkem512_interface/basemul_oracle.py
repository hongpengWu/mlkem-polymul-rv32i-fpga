#!/usr/bin/env python3
"""Cross-check ML-KEM-512 K=2 cached BaseMul with direct pair arithmetic.

Synthetic in-range test operands only. This is a software arithmetic sanity
check, not an official KAT intermediate trace and not an HLS/RTL integration
result. The official trace exporter is a separate follow-up task.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
Q = 3329
N = 256
K = 2
R_MASK = 0xFFFF
QINV = 62209


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def read_zetas(path: Path, symbol: str) -> list[int]:
    source = path.read_text(encoding="utf-8")
    match = re.search(rf"{re.escape(symbol)}\s*\[\s*128\s*\]\s*=\s*\{{(.*?)\}}", source, re.S)
    require(match is not None, f"Cannot parse {symbol} from {path}")
    values = [int(token) for token in re.findall(r"(?<![A-Za-z_])[-+]?\d+", match.group(1))]
    require(len(values) == 128, f"Expected 128 zetas in {path}, got {len(values)}")
    return values


def signed16(value: int) -> int:
    value &= R_MASK
    return value - 65536 if value & 0x8000 else value


def montgomery_reduce(value: int) -> int:
    low = value & R_MASK
    t = signed16((low * QINV) & R_MASK)
    return (value - t * Q) >> 16


def fqmul(a: int, b: int) -> int:
    return montgomery_reduce(a * b)


def canonical(value: int) -> int:
    return value % Q


def cached_base_mul_k2(a: list[list[int]], b: list[list[int]], zetas: list[int]) -> list[int]:
    """Mirror poly_k.c: raw 32-bit sum over K, then one RED per coefficient."""
    cache = [[0] * (N // 2) for _ in range(K)]
    for k in range(K):
        for i in range(N // 4):
            zeta = zetas[64 + i]
            cache[k][2 * i] = fqmul(b[k][4 * i + 1], zeta)
            cache[k][2 * i + 1] = fqmul(b[k][4 * i + 3], -zeta)

    result = [0] * N
    for i in range(N // 2):
        t0 = 0
        t1 = 0
        for k in range(K):
            t0 += a[k][2 * i + 1] * cache[k][i]
            t0 += a[k][2 * i] * b[k][2 * i]
            t1 += a[k][2 * i] * b[k][2 * i + 1]
            t1 += a[k][2 * i + 1] * b[k][2 * i]
        result[2 * i] = montgomery_reduce(t0)
        result[2 * i + 1] = montgomery_reduce(t1)
    return result


def direct_base_mul_k2(a: list[list[int]], b: list[list[int]], zetas: list[int]) -> list[int]:
    """Compute the two quadratic NTT products per four-coefficient block."""
    result = [0] * N
    for k in range(K):
        for i in range(N // 4):
            zeta = zetas[64 + i]
            base = 4 * i
            # First factor in F_q[X]/(X^2-zeta).
            result[base] += fqmul(a[k][base], b[k][base])
            result[base] += fqmul(zeta, fqmul(a[k][base + 1], b[k][base + 1]))
            result[base + 1] += fqmul(a[k][base], b[k][base + 1])
            result[base + 1] += fqmul(a[k][base + 1], b[k][base])
            # Adjacent factor uses -zeta.
            result[base + 2] += fqmul(a[k][base + 2], b[k][base + 2])
            result[base + 2] += fqmul(-zeta, fqmul(a[k][base + 3], b[k][base + 3]))
            result[base + 3] += fqmul(a[k][base + 2], b[k][base + 3])
            result[base + 3] += fqmul(a[k][base + 3], b[k][base + 2])
    return result


def fixtures(seed: int) -> list[dict]:
    rng = random.Random(seed)
    cases = []
    for name in ("zero", "signed_boundary", "deterministic_random"):
        a: list[list[int]] = []
        b: list[list[int]] = []
        for _ in range(K):
            if name == "zero":
                a.append([0] * N)
                b.append([0] * N)
            elif name == "signed_boundary":
                a.append([0 if i % 2 else 4095 for i in range(N)])
                b.append([(-8 * Q + 1) if i % 2 else (8 * Q - 1) for i in range(N)])
            else:
                a.append([rng.randrange(0, 4096) for _ in range(N)])
                b.append([rng.randrange(-(8 * Q) + 1, 8 * Q) for _ in range(N)])
        cases.append({"name": name, "a": a, "b": b})
    return cases


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=lambda x: int(x, 0), default=0x512BACE)
    parser.add_argument("--output", type=Path,
                        default=ROOT / "results/accelerator_interface/basemul_oracle.json")
    args = parser.parse_args()

    vendor_zetas_path = ROOT / "third_party/mlkem-native/mlkem/src/zetas.inc"
    hls_support_path = ROOT / "hls/src/mlkem_poly_mul256_v39e_unified_stream_support.cpp"
    vendor_zetas = read_zetas(vendor_zetas_path, "mlk_zetas")
    hls_zetas = read_zetas(hls_support_path, "zetas39c")
    require([x % Q for x in hls_zetas] == [x % Q for x in vendor_zetas],
            "HLS and portable software twiddle tables differ modulo q")

    cases = []
    for fixture in fixtures(args.seed):
        ref = direct_base_mul_k2(fixture["a"], fixture["b"], vendor_zetas)
        got = cached_base_mul_k2(fixture["a"], fixture["b"], vendor_zetas)
        mismatches = [i for i, (x, y) in enumerate(zip(ref, got)) if canonical(x) != canonical(y)]
        require(not mismatches, f"Cached/direct BaseMul mismatch in {fixture['name']}: {mismatches[:8]}")
        cases.append({
            **fixture,
            "expected_canonical": [canonical(x) for x in ref],
            "cached_signed_output": got,
            "coefficient_mod_q_match": True,
            "max_abs_a": max(abs(x) for poly in fixture["a"] for x in poly),
            "max_abs_b": max(abs(x) for poly in fixture["b"] for x in poly),
        })

    source_paths = [
        "scripts/mlkem512_interface/basemul_oracle.py",
        "third_party/mlkem-native/mlkem/src/poly.h",
        "third_party/mlkem-native/mlkem/src/poly_k.c",
        "third_party/mlkem-native/mlkem/src/poly_k.h",
        "third_party/mlkem-native/mlkem/src/zetas.inc",
        "hls/src/mlkem_poly_mul256_v39e_unified_stream_support.cpp",
        "hls/mlkem512_basemul_k2/src/mlkem512_basemul_acc_k2.h",
        "hls/mlkem512_basemul_k2/src/mlkem512_basemul_acc_k2.cpp",
    ]
    result = {
        "schema_version": 1,
        "status": "synthetic_software_oracle_pass_not_hardware",
        "parameter_set": "ML-KEM-512",
        "k": K,
        "n": N,
        "q": Q,
        "seed": args.seed,
        "scope": "Synthetic NTT-domain operands in stated coefficient bounds. Not official KAT intermediates and not an HLS/RTL result.",
        "comparison": "Direct two-factor quadratic BaseMul with +/- zeta versus portable cached K=2 vector accumulation; compare canonical residues modulo q.",
        "montgomery": {"radix": "2^16", "qinv": QINV},
        "twiddle_tables_equal_mod_q": True,
        "cases": cases,
        "source_sha256": {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
                          for path in source_paths},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"MLKEM512_BASEMUL_ORACLE_PASS cases={len(cases)} output={args.output}")


if __name__ == "__main__":
    main()
