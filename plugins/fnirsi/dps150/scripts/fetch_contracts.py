"""Explicit development dependency bootstrap; never called by the plugin or tests.

Fetch immutable OTDP inputs with SHA-256 verification. No core checkout required.
Existing verified copies support offline use; mismatches fail without overwriting.
Corpus relocation 2026-09-15: the canonical tree is now standards/otdp-v0.3.0;
the next re-lock points lock directory there (old pinned revisions keep working).
"""

import argparse
import hashlib
import json
import re
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Verify local files without network")
    args = parser.parse_args()
    lock = json.loads((ROOT / "contracts/lock.json").read_text())
    revision = lock["revision"]
    if not re.fullmatch(r"[a-f0-9]{40}", revision):
        raise ValueError("An immutable full commit is required")
    base = f"https://raw.githubusercontent.com/madeinoz67/benchweave/{revision}/docs/otdp-v0.3.0/"
    destination = ROOT / "contracts/otdp-v0.3.0"
    for name, expected in lock["sha256"].items():
        if Path(name).name != name or not re.fullmatch(r"[a-f0-9]{64}", expected):
            raise ValueError("Invalid contract lock entry")
        path = destination / name
        if path.is_file():
            data = path.read_bytes()
        elif args.check:
            raise FileNotFoundError(f"Missing {name}; run scripts/fetch_contracts.py first")
        else:
            with urlopen(base + name, timeout=30) as response:
                data = response.read(2_000_001)
        if len(data) > 2_000_000 or hashlib.sha256(data).hexdigest() != expected:
            raise ValueError(f"Contract integrity mismatch: {name}")
        if not path.exists():
            destination.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
    print(f"Verified {len(lock['sha256'])} pinned OTDP contract inputs")


if __name__ == "__main__":
    main()
