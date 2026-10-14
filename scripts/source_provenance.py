"""Verify historical source hashes after directory/launcher maintenance.

The small source_before archive was preserved during reorganization, AFTER the
historical executions. It is not a new claim of an execution-before snapshot.
Only exact bytes matching a hash already recorded in an original run qualify.
"""
from functools import lru_cache
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRESERVED = ROOT / "results/reorganization/source_before"


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@lru_cache(maxsize=1)
def _manifest():
    return json.loads((PRESERVED / "manifest.json").read_text(encoding="utf-8"))


def verified_source(path, recorded_sha256):
    """Return current or preserved source only if it matches the recorded hash.

    Preservation fallback is restricted to explicitly archived source files.
    It cannot excuse missing/changed output logs, firmware images or vectors.
    """
    path = Path(path).resolve()
    if path.is_file() and _sha(path) == recorded_sha256:
        return path
    if not path.is_relative_to(ROOT):
        raise ValueError(f"Changed or missing input: {path}")
    name = path.relative_to(ROOT).as_posix()
    entry = _manifest()["files"].get(name)
    if entry and entry["sha256"] == recorded_sha256:
        preserved = (ROOT / entry["preserved_path"]).resolve()
        if (preserved.is_relative_to(PRESERVED) and preserved.is_file()
                and _sha(preserved) == recorded_sha256):
            return preserved
    raise ValueError(f"Changed or missing input, including preserved original source: {name}")
