# tests/contract/test_registry_authenticity.py
"""Authenticity: signature verification, expiry, monotonic sequence."""
from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from benchweave.content.json_document import JsonDocument, load_document
from benchweave.registry.authenticity import (
    AuthenticityRejected,
    TrustRoot,
    check_status,
    load_trust_root,
    verify_document,
)

REPO = Path(__file__).resolve().parents[2]
REG = REPO / "fixtures/registry"
NOW = int(datetime(2026, 9, 12, tzinfo=UTC).timestamp() * 1_000_000_000)


def _root(origin: str = "origin-main") -> TrustRoot:
    name = "main.pub.pem" if origin == "origin-main" else "originb.pub.pem"
    return load_trust_root(origin, REG / "keys" / name)


def _release(package: str) -> tuple[JsonDocument, bytes]:
    d = REG / "origin-main" / package / "1.0.0"
    raw = (d / "manifest.json").read_bytes()
    doc = load_document(raw, hashlib.sha256(raw).hexdigest(), max_bytes=1_000_000)
    return doc, (d / "manifest.sig").read_bytes()


def test_valid_manifest_signature_verifies() -> None:
    doc, sig = _release("benchweave/dc-psu-profile")
    verify_document(doc, sig, _root())  # no raise


def test_tampered_bytes_reject() -> None:
    doc, sig = _release("benchweave/dc-psu-profile")
    if b"dc-psu-profile" in doc.raw:
        raw2 = doc.raw.replace(b"dc-psu-profile", b"dc-psu-profileX", 1)
    else:
        raw2 = doc.raw[:-2] + b"X\n"
    doc2 = load_document(raw2, hashlib.sha256(raw2).hexdigest(), max_bytes=1_000_000)
    with pytest.raises(AuthenticityRejected) as exc:
        verify_document(doc2, sig, _root())
    assert exc.value.reason == "bad_signature"


def test_wrong_trust_root_rejects() -> None:
    doc, sig = _release("benchweave/dc-psu-profile")
    with pytest.raises(AuthenticityRejected) as exc:
        verify_document(doc, sig, _root("origin-b"))
    assert exc.value.reason == "bad_signature"


def test_malformed_trust_root_rejects() -> None:
    doc, sig = _release("benchweave/dc-psu-profile")
    bad_root = TrustRoot(origin_id="origin-main", verify_key_pem=b"not-a-pem\n")
    with pytest.raises(AuthenticityRejected) as exc:
        verify_document(doc, sig, bad_root)
    assert exc.value.reason == "unknown_trust"


def test_status_fresh_and_monotonic() -> None:
    root = _root()
    d = REG / "origin-main/benchweave/dc-psu-profile/1.0.0"
    sraw = (d / "status.json").read_bytes()
    status = load_document(sraw, hashlib.sha256(sraw).hexdigest(), max_bytes=100_000).content
    new_high = check_status(status, root=root, now_ns=NOW, high_water={})
    assert new_high == 1
    # same sequence again -> stale
    with pytest.raises(AuthenticityRejected) as exc:
        check_status(
            status,
            root=root,
            now_ns=NOW,
            high_water={("origin-main", "benchweave/dc-psu-profile", "1.0.0"): 1},
        )
    assert exc.value.reason == "stale_sequence"


def test_status_expired_rejects() -> None:
    root = _root()
    sraw = (REG / "faults/expired/benchweave/sim-psu-descriptor/1.0.0/status.json").read_bytes()
    status = load_document(sraw, hashlib.sha256(sraw).hexdigest(), max_bytes=100_000).content
    with pytest.raises(AuthenticityRejected) as exc:
        check_status(status, root=root, now_ns=NOW, high_water={})
    assert exc.value.reason == "expired_status"


def test_status_future_updated_at_rejects() -> None:
    root = _root()
    d = REG / "origin-main/benchweave/dc-psu-profile/1.0.0"
    sraw = (d / "status.json").read_bytes()
    status = load_document(sraw, hashlib.sha256(sraw).hexdigest(), max_bytes=100_000).content
    status = dict(status)
    future = datetime(2026, 9, 12, tzinfo=UTC) + timedelta(days=1)
    status["updated_at"] = future.isoformat().replace("+00:00", "Z")
    with pytest.raises(AuthenticityRejected) as exc:
        check_status(status, root=root, now_ns=NOW, high_water={})
    assert exc.value.reason == "future_updated_at"
