"""WP07 Task 3: content-addressed documents/artifacts/evidence + retention."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterator
from pathlib import Path

import pytest

from benchweave.content.store import (
    ContentStore,
    EvidenceQuotaExceeded,
    RetainingServices,
)
from benchweave.state.store import Store


@pytest.fixture()
def content(tmp_path: Path) -> Iterator[tuple[ContentStore, Store]]:
    store = Store.open(tmp_path / "state.db")
    yield ContentStore(store), store
    store.close()


def test_document_roundtrip_is_byte_exact(content: tuple[ContentStore, Store]) -> None:
    cs, store = content
    raw = b'{"id": "doc-1", "version": "1.0.0"}'
    sha = hashlib.sha256(raw).hexdigest()
    cs.put_document(raw, sha, {"id": "doc-1"}, "urn:x:doc", "2026-09-12T00:00:00Z")
    got = cs.get_document(sha)
    assert got is not None and got["raw_bytes"] == raw and got["schema_id"] == "urn:x:doc"


def test_put_document_rejects_digest_mismatch(content: tuple[ContentStore, Store]) -> None:
    cs, _ = content
    raw = b'{"id": "doc-x", "version": "1.0.0"}'
    wrong_sha = hashlib.sha256(b"other").hexdigest()  # not the digest of raw
    with pytest.raises(ValueError):
        cs.put_document(
            raw, wrong_sha, {"id": "doc-x"}, "urn:x:doc", "2026-09-12T00:00:00Z"
        )
    assert cs.get_document(wrong_sha) is None


def test_artifact_chunk_reassembly_reproduces_digest(
    content: tuple[ContentStore, Store],
) -> None:
    cs, _ = content
    data = bytes(range(256)) * 100  # 25,600 bytes
    artifact_id = cs.put_artifact(data, "2026-09-12T00:00:00Z")
    out = bytearray()
    offset = 0
    while True:
        chunk = cs.artifact_chunk(artifact_id, offset, 65536)
        out += chunk["data"]
        assert chunk["sha256"] == hashlib.sha256(data).hexdigest()
        if chunk["eof"]:
            break
        offset += chunk["bytes"]
    assert bytes(out) == data


def test_artifact_chunk_length_is_clamped(content: tuple[ContentStore, Store]) -> None:
    cs, _ = content
    artifact_id = cs.put_artifact(b"x" * 10, "2026-09-12T00:00:00Z")
    chunk = cs.artifact_chunk(artifact_id, 0, 100000)
    assert chunk["bytes"] == 10 and chunk["eof"]


def test_evidence_quota_raises(content: tuple[ContentStore, Store]) -> None:
    cs, _ = content
    for _ in range(2):
        cs.put_evidence("dataset", {"id": "e", "version": "1", "sha256": "0" * 64},
                        None, "run:r1", "2026-09-12T00:00:00Z", quota=2)
    with pytest.raises(EvidenceQuotaExceeded):
        cs.put_evidence("dataset", {"id": "e", "version": "1", "sha256": "0" * 64},
                        None, "run:r1", "2026-09-12T00:00:00Z", quota=2)


def test_evidence_quota_counts_per_kind_dimension(
    content: tuple[ContentStore, Store],
) -> None:
    """Issue #43 slice 2 (the quota stack): the accounting dimension is
    ``(context_key, kind)`` — one row of each kind lands under a quota of 1,
    and only a SECOND row of the same kind refuses. The re-scope is invisible
    on pre-slice-2 data (the bases differ only once ``event_log`` and
    ``dataset`` rows coexist under one context key, which streaming
    introduces), so no published quota decision is repriced."""
    cs, _ = content
    ref = {"id": "e", "version": "1", "sha256": "0" * 64}
    cs.put_evidence("dataset", ref, None, "run:r1", "2026-09-12T00:00:00Z", quota=1)
    cs.put_evidence("event_log", ref, None, "run:r1", "2026-09-12T00:00:00Z", quota=1)
    with pytest.raises(EvidenceQuotaExceeded):
        cs.put_evidence("event_log", ref, None, "run:r1", "2026-09-12T00:00:00Z", quota=1)


def test_artifact_and_evidence_ids_match_contract_pattern(
    content: tuple[ContentStore, Store],
) -> None:
    cs, _ = content
    artifact_id = cs.put_artifact(b"contract", "2026-09-12T00:00:00Z")
    evidence_id = cs.put_evidence(
        "dataset",
        {"id": "e", "version": "1", "sha256": "0" * 64},
        None,
        "run:r1",
        "2026-09-12T00:00:00Z",
    )
    pattern = r"^[a-z][a-z0-9_.-]*$"
    assert re.fullmatch(pattern, artifact_id) is not None
    assert re.fullmatch(pattern, evidence_id) is not None


def test_retaining_services_implements_host_protocol(
    content: tuple[ContentStore, Store],
) -> None:
    cs, _ = content
    services = RetainingServices(cs, quota=10, now="2026-09-12T00:00:00Z")
    evidence_id = services.retain_evidence("run:r1:tick:1", {"v": 3.3})
    got = cs.get_evidence(evidence_id)
    assert got is not None and got["context_key"] == "run:r1:tick:1"
