#!/usr/bin/env python3
"""Generate deterministic ML-KEM-512 BaseMul MMIO simulation vectors.

The files are deliberately small, plain hexadecimal memories so the same
fixtures can be loaded by Vivado xsim and inspected by the Python oracle.
Each case contains two rows of A/B, two rows of mulcache, and the exact
signed-int16 output produced by the maintained HLS contract.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.mlkem512_interface.basemul_oracle import (  # noqa: E402
    N,
    K,
    Q,
    cached_base_mul_k2,
    direct_base_mul_k2,
    fixtures,
    montgomery_reduce,
    read_zetas,
)


def make_cache(b: list[list[int]], zetas: list[int]) -> list[list[int]]:
    cache = [[0] * (N // 2) for _ in range(K)]
    for k in range(K):
        for i in range(N // 4):
            zeta = zetas[64 + i]
            cache[k][2 * i] = montgomery_reduce(b[k][4 * i + 1] * zeta)
            cache[k][2 * i + 1] = montgomery_reduce(b[k][4 * i + 3] * (-zeta))
    return cache


def u16(value: int) -> str:
    return f"{value & 0xFFFF:04x}"


def write_mem(path: Path, values: list[int]) -> None:
    path.write_text("\n".join(u16(value) for value in values) + "\n", encoding="ascii", newline="\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "tb/accelerator/vectors",
        help="directory for xsim .mem files and manifest.json",
    )
    parser.add_argument("--seed", type=lambda value: int(value, 0), default=0x512BACE)
    args = parser.parse_args()

    zetas = read_zetas(ROOT / "third_party/mlkem-native/mlkem/src/zetas.inc", "mlk_zetas")
    cases = fixtures(args.seed)
    args.output.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, object] = {
        "schema_version": 1,
        "parameter_set": "ML-KEM-512",
        "k": K,
        "n": N,
        "q": Q,
        "seed": args.seed,
        "cases": [],
    }

    for case_index, case in enumerate(cases):
        name = str(case["name"])
        prefix = f"case_{case_index:03d}"
        operands_a = case["a"]
        operands_b = case["b"]
        assert isinstance(operands_a, list) and isinstance(operands_b, list)
        cache = make_cache(operands_b, zetas)
        expected = cached_base_mul_k2(operands_a, operands_b, zetas)
        direct = direct_base_mul_k2(operands_a, operands_b, zetas)
        assert all(x % Q == y % Q for x, y in zip(expected, direct)), name
        if name == "deterministic_random":
            values = operands_a[0] + operands_a[1] + operands_b[0] + operands_b[1] + cache[0] + cache[1] + expected
            packed = [((values[i+1] & 65535) << 16) | (values[i] & 65535) for i in range(0, len(values), 2)]
            (args.output / "basemul_bist.mem").write_text("".join(f"{x:08x}\n" for x in packed), encoding="ascii", newline="\n")

        paths = {
            "a0": args.output / f"{prefix}_a0.mem",
            "a1": args.output / f"{prefix}_a1.mem",
            "b0": args.output / f"{prefix}_b0.mem",
            "b1": args.output / f"{prefix}_b1.mem",
            "cache0": args.output / f"{prefix}_cache0.mem",
            "cache1": args.output / f"{prefix}_cache1.mem",
            "expected": args.output / f"{prefix}_expected.mem",
        }
        write_mem(paths["a0"], operands_a[0])
        write_mem(paths["a1"], operands_a[1])
        write_mem(paths["b0"], operands_b[0])
        write_mem(paths["b1"], operands_b[1])
        write_mem(paths["cache0"], cache[0])
        write_mem(paths["cache1"], cache[1])
        write_mem(paths["expected"], expected)

        manifest_case = {
            "index": case_index,
            "name": name,
            "files": {key: path.name for key, path in paths.items()},
            "sha256": {key: hashlib.sha256(path.read_bytes()).hexdigest() for key, path in paths.items()},
            "max_abs_a": max(abs(value) for row in operands_a for value in row),
            "max_abs_b": max(abs(value) for row in operands_b for value in row),
        }
        manifest["cases"].append(manifest_case)  # type: ignore[union-attr]

    manifest_path = args.output / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"BASEMUL_VECTOR_PASS cases={len(cases)} output={args.output}")


if __name__ == "__main__":
    main()
