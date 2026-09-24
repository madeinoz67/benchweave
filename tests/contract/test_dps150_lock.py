"""The dps150 contracts lock pins the standards corpus it names (review R2).

The design record's §11 risk-6 falsifier, made executable: the lock's eight
sha256 digests must equal the digests of the ``standards/otdp/0.2.2`` files
in THIS repository. Both sides are tracked, so the pin holds on a fresh
clone — the materialized ``contracts/otdp-*/`` dirs are gitignored local
artifacts and are deliberately NOT referenced here; the lock is the in-repo
anchor.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
LOCK = REPO / "plugins/fnirsi/dps150/contracts/lock.json"


def test_lock_pins_the_standards_corpus_bytes() -> None:
    lock = json.loads(LOCK.read_text())
    directory = (REPO / str(lock["directory"])).resolve()
    # The lock names a corpus directory inside the standards tree; refusing
    # anything else keeps the resolution bounded even if the lock is edited.
    assert directory.is_relative_to((REPO / "standards").resolve())
    assert directory.is_dir()
    for name, expected in lock["sha256"].items():
        digest = hashlib.sha256((directory / name).read_bytes()).hexdigest()
        assert digest == expected, f"{name}: lock pins {expected}, tree hashes {digest}"
