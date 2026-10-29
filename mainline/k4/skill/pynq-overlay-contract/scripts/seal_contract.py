"""Hash reviewed artifacts into a contract; sealing is provenance, not hardware validation."""
import argparse
import json
from pathlib import Path
from overlay_contract import local_file, sha256, validate_contract, verify_bundle


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("template", type=Path)
    parser.add_argument("--bundle-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    spec = json.loads(args.template.read_text(encoding="utf-8-sig"))
    root = args.bundle_dir.resolve()
    names = set(spec.get("files", {})) | {spec["bitstream"], spec["hwh"]}
    spec["files"] = {name: sha256(local_file(root, name)) for name in sorted(names)}
    validate_contract(spec)
    # Check HWH before writing, so an invalid artifact set cannot look sealed.
    from overlay_contract import hwh_ranges, number
    base, span = number(spec["ip"]["base_address"]), number(spec["ip"]["address_range"])
    if (base, base + span - 1) not in hwh_ranges(local_file(root, spec["hwh"])):
        raise ValueError("HWH and declared address range differ")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(spec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    verify_bundle(args.output, root)
    print(str(args.output))


if __name__ == "__main__":
    main()
