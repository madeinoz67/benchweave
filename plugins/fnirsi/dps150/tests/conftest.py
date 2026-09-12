"""Validate pinned local test inputs; tests never download contracts."""

import hashlib
import json
from pathlib import Path


def pytest_sessionstart() -> None:
    root = Path(__file__).resolve().parents[1]
    lock = json.loads((root / "contracts/lock.json").read_text())
    for name, expected in lock["sha256"].items():
        path = root / "contracts/otdp-v0.3.0" / name
        if not path.is_file():
            raise RuntimeError("Run python scripts/fetch_contracts.py before the offline tests")
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise RuntimeError(f"Pinned contract hash mismatch: {name}")
