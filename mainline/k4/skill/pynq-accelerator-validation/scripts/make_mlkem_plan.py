"""Generate a board validation plan from a verified project vector package; never programs PL."""
import argparse
import importlib.util
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--indices", type=int, nargs="+", default=[0, 1, 115])
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--mode", choices=["accelerated", "cpu_only"], default="accelerated")
    args = parser.parse_args()
    bundle = args.bundle.resolve()
    spec = importlib.util.spec_from_file_location("plan_mlkem1024", str(bundle / "mlkem1024.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    manifest, vectors, evidence = module.verify_bundle(bundle / "release_manifest.json")
    if not args.indices or len(set(args.indices)) != len(args.indices) or any(i < 0 or i >= len(vectors["cases"]) for i in args.indices):
        raise ValueError("Invalid or duplicate case indices")
    if args.repeats <= 0:
        raise ValueError("repeats must be positive")
    plan = {"schema": 1, "measurement_kind": "board-live", "warmup": 1,
            "repeats": args.repeats, "timeout_seconds": 20.0,
            "metadata": {"operation": "official ML-KEM vectors", "source_contract": evidence},
            "adapter_config": {"bundle_directory": str(bundle), "firmware_mode": args.mode},
            "cases": [{"id": str(i), "input": {"case_index": i},
                       "expected": {"hex": vectors["cases"][i]["expected_hex"],
                                    "return_code": vectors["cases"][i]["expected_return"]}} for i in args.indices]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
