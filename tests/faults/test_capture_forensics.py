"""Forensic-accountability fault arms (concurrency-lane refutation F1/F2).

Derivations (from the refuter's confirmed-executable probes, adapted):
- F1 (HIGH): the controller's abort must keep the capture RECLAIMABLE until
  the forensic writes complete durably — a suppressed forensic-write
  failure (real second-connection BEGIN IMMEDIATE contention, busy_timeout
  small so the INSERT fails fast) loses the record permanently when the
  once-guard marks recorded before put_artifact/put_evidence; the
  plugin_close sweep (B15-iii's designated in-process retry) then has
  nothing to retry. Fix shape: pop _open / add _recorded only AFTER
  put_evidence returns; the failing capture stays in _open for the sweep.
- F2 (MED-HIGH): the once-guard keys LIFECYCLE, not identity — a same-id
  retry (legal: the first abort deleted the staging row, so the writer
  re-opens it) whose second attempt also fails must be reclaimed with its
  own forensic record; a stale _recorded entry suppresses the second abort
  and sweep_open claims reclamation that never happened (row + reservation
  leak for the session's lifetime, no forensic trace for the second
  failure). Fix shape: open_capture discards the id from _recorded.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from benchweave.content.capture_services import build_capture_services
from benchweave.content.capture_store import CaptureStagingStore
from benchweave.content.store import ContentStore
from benchweave.control.clocking import SystemClock
from benchweave.host.otdp_bridge import OTDPBridge
from benchweave.host.plugin import SimulationInfo
from benchweave.host.services import QuotaLimits
from benchweave.host.types import (
    CaptureQuotaExceeded,
    ErrorCode,
    OperationRequest,
    OperationVerb,
)
from benchweave.state.store import Store


@pytest.fixture()
def store(tmp_path: Path) -> Iterator[Store]:
    opened = Store.open(tmp_path / "forensics.db", check_same_thread=False)
    yield opened
    opened.close()


def a_controller_harness(
    store: Store, *, busy_timeout: int | None = None
) -> tuple[OTDPBridge, CaptureStagingStore]:
    content = ContentStore(store)
    raw = {
        "id": "dev.local.forensics",
        "descriptor_version": "1.0.0",
        "integration": {"adapter": {"permissions": ["artifact_writer"]}},
    }
    blob = json.dumps(raw, sort_keys=True).encode()
    digest = hashlib.sha256(blob).hexdigest()
    content.put_document(blob, digest, raw, "otdp-descriptor", _now())
    writer = CaptureStagingStore(store, max_capture_bytes=64, max_dataset_bytes=8192)
    bundle, controller = build_capture_services(
        descriptor_digest=digest,
        content=content,
        writer=writer,
        clock=time.monotonic,
        wall=_now,
        quota=QuotaLimits(
            max_dataset_bytes=8192, max_evidence_entries=50, max_event_batch=10
        ),
        context_key="forensics",
    )
    assert controller is not None
    adapter = _OverAppend()
    bridge = OTDPBridge(
        adapter,
        descriptor={
            "capture_formats": ["waveform_f64le", "raw_binary"],
            "capture_limits": {"max_samples": 1024, "max_bytes": 8192},
        },
        services=bundle,
        simulation=SimulationInfo(True, "Synthetic"),
        capture=controller,
    )
    bridge.plugin_open(object())
    if busy_timeout is not None:
        store.connection.execute(f"PRAGMA busy_timeout={busy_timeout}")
    return bridge, writer


def _now() -> str:
    return SystemClock().now_iso()


def _deadline(seconds: float = 30.0) -> int:
    return int((time.monotonic() + seconds) * 1e9)


class _OverAppend:
    """Appends once, then past the reservation: a GENUINE writer-stamped
    quota refusal (the classification arm fires for real)."""

    def __init__(self) -> None:
        self.services: Any = None

    async def open(self, descriptor: dict[str, Any], services: Any, context: Any) -> None:
        self.services = services

    async def close(self, context: Any) -> None:
        pass

    async def execute(self, request: dict[str, Any], context: Any) -> dict[str, Any]:
        capture_id = request["arguments"]["capture_id"]
        await self.services.artifact_append(capture_id, b"\x01" * 8, context)
        try:
            await self.services.artifact_append(capture_id, b"\x01" * 4096, context)
        except CaptureQuotaExceeded:
            raise
        raise AssertionError("unreachable")  # pragma: no cover


def forensic_rows(store: Store, capture_id: str) -> int:
    return int(
        store.connection.execute(
            "SELECT COUNT(*) FROM evidence WHERE kind = 'event_log'"
            " AND content_ref_json LIKE ?",
            (f'%"{capture_id}"%',),
        ).fetchone()[0]
    )


def staged_rows(store: Store) -> int:
    return int(
        store.connection.execute(
            "SELECT COUNT(*) FROM capture_staging WHERE state = 'staged'"
        ).fetchone()[0]
    )


# --- F1: a failed forensic write must not lose the record -----------------------


def test_failed_forensic_write_is_retried_by_the_close_sweep(
    store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    """F1's mechanism, deterministic: the forensic put_artifact fails ONCE
    at its real call site (the refuter's real-lock reproduction — probe_forensic_loss
    — races the holder against the epilogue, so the arm pins the ORDERING
    defect directly: the once-guard marks recorded before the durable
    writes). On the unfixed tree the record is lost permanently; the fix
    keeps the capture in _open until put_evidence returns, and the
    plugin_close sweep (B15-iii's in-process retry) writes exactly one
    forensic row."""
    bridge, _writer = a_controller_harness(store)
    controller = bridge._capture
    assert controller is not None
    content = controller._content
    real_put_artifact = content.put_artifact
    calls = {"n": 0}

    def failing_first_put_artifact(data: bytes, now: str) -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            # The real condition class, at the real call site, once only.
            raise sqlite3.OperationalError("database is locked")
        recovered: str = real_put_artifact(data, now)
        return recovered

    monkeypatch.setattr(content, "put_artifact", failing_first_put_artifact)
    result = bridge.dispatch(
        OperationRequest(
            "op-f1",
            OperationVerb.CAPTURE,
            {
                "capture_id": "cap-f",
                "format": "waveform_f64le",
                "sample_count": 4,
                "max_bytes": 64,
            },
        ),
        deadline_ns=_deadline(),
    )
    assert result.error is not None
    assert result.error.code is ErrorCode.RESOURCE_LIMIT  # classified for real
    monkeypatch.undo()
    bridge.plugin_close()  # the in-process retry B15-iii names
    assert forensic_rows(store, "cap-f") == 1
    assert staged_rows(store) == 0


def test_no_dangling_forensic_payload_when_the_evidence_write_fails(
    store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    """F1's second half: if put_artifact succeeded and put_evidence failed,
    the unfixed tree leaks a dangling payload artifact with no evidence
    row. The retry must not double-write: after the close sweep there is
    exactly one payload artifact for the capture, one evidence row."""
    bridge, _writer = a_controller_harness(store)
    controller = bridge._capture
    assert controller is not None
    content = controller._content  # the harness's ContentStore
    real_put_evidence = content.put_evidence
    calls = {"n": 0}

    def failing_first_put_evidence(*args: Any, **kwargs: Any) -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            raise sqlite3.OperationalError("database is locked")
        recovered: str = real_put_evidence(*args, **kwargs)
        return recovered

    monkeypatch.setattr(content, "put_evidence", failing_first_put_evidence)
    result = bridge.dispatch(
        OperationRequest(
            "op-f1b",
            OperationVerb.CAPTURE,
            {
                "capture_id": "cap-fb",
                "format": "waveform_f64le",
                "sample_count": 4,
                "max_bytes": 64,
            },
        ),
        deadline_ns=_deadline(),
    )
    assert result.error is not None  # the dispatch failed (classified)
    monkeypatch.undo()
    bridge.plugin_close()  # the in-process retry
    assert forensic_rows(store, "cap-fb") == 1
    payload_rows = int(
        store.connection.execute(
            "SELECT COUNT(*) FROM artifacts WHERE artifact_id IN"
            " (SELECT artifact_id FROM evidence)"
        ).fetchone()[0]
    )
    assert payload_rows == 1  # no dangling duplicate payload artifact


# --- F2: the once-guard keys lifecycle, not identity -----------------------------


def test_a_same_id_retry_failure_is_reclaimed_with_its_own_record(
    store: Store,
) -> None:
    """The refuter's probe_retry_id shape: fail, retry with the SAME id
    (legal — abort deleted the row), fail again. The stale _recorded entry
    must not suppress the second abort: after the close sweep there are
    ZERO staged rows, the quota is refunded, and TWO forensic records exist
    (one per failed lifecycle)."""
    bridge, writer = a_controller_harness(store)
    request = OperationRequest(
        "op-f2",
        OperationVerb.CAPTURE,
        {
            "capture_id": "cap-r",
            "format": "waveform_f64le",
            "sample_count": 4,
            "max_bytes": 64,
        },
    )
    first = bridge.dispatch(request, deadline_ns=_deadline())
    assert first.error is not None
    assert forensic_rows(store, "cap-r") == 1
    # Same-id retry: the first abort deleted the staging row, so the gate
    # re-opens the id legally.
    second = bridge.dispatch(request, deadline_ns=_deadline())
    assert second.error is not None
    bridge.plugin_close()
    assert staged_rows(store) == 0
    assert writer.used_bytes("forensics") == 0  # the reservation refunded
    assert forensic_rows(store, "cap-r") == 2  # one record per failed lifecycle

