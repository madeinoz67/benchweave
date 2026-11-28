# author: Stephen Eaton
"""Pinned local test inputs. Tests never download contracts and never touch
hardware: the explicit bootstrap (scripts/fetch_contracts.py) fetches the
pinned STANDARD documents once; this module refuses to run when they are
absent or altered."""

import hashlib
import json

from support import ROOT, contracts_dir


def pytest_sessionstart() -> None:
    lock = json.loads((ROOT / "contracts/lock.json").read_text())
    contracts = contracts_dir()
    for name, expected in lock["sha256"].items():
        path = contracts / name
        if not path.is_file():
            raise RuntimeError("Run python scripts/fetch_contracts.py before the offline tests")
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise RuntimeError(f"Pinned contract hash mismatch: {name}")
