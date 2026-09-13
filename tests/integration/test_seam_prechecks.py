"""D9: §5 accept-time busy/binding-match pre-checks (spec Decision 3).

WP08 Task 2. The seam (``Operations.run_start``) must decide §5 contention
SYNCHRONOUSLY, before the request key is written: a bench with a live run
conflicts (catalog ``conflict`` — the 409 contention vehicle; the catalog
blesses no busy-specific code), and the binding document's own
``request_id`` must match the §9 request id (interface-contract §5:
"Binding document request_id must match the request"). §9 replay stays
AHEAD of the busy check: a retry of the same request id while its run is
active returns the existing run, never a conflict.

Bootstrap reuse, not duplication: these tests drive the seam in-process on
the ``seam_control`` fixture imported from tests/unit — the established
in-process seam bootstrap (real Store/ContentStore/startup admission +
the blocking FakeCoordinator that holds a run deterministically live). The
parity suite's gateway fixture boots the REAL worker, whose runs reach
terminal in milliseconds; busy-state assertions against it would be racy.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from test_seam_control import (  # noqa: E402  (path added by conftest)
    BENCH_ID,
    SeamControl,
    _await_coordinator,
    _control,
)

from benchweave.content.store import ContentStore
from benchweave.interfaces import errors

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "execution"
NOW = "2026-09-12T00:00:00Z"  # seam_control's frozen clock


def _variant_binding(fixture: SeamControl, request_id: str) -> dict[str, Any]:
    """A STORED binding variant: same pin lattice, a distinct document-level
    request_id (the event-recovery suite's SECOND_REF idiom — one binding
    document executes exactly once per database)."""
    document = json.loads((FIXTURES / "run-binding.json").read_bytes())
    document["request_id"] = request_id
    raw = json.dumps(document, indent=2).encode()
    sha = hashlib.sha256(raw).hexdigest()
    ContentStore(fixture.store).put_document(raw, sha, document, "urn:stg:binding", NOW)
    return {"id": request_id, "version": "1.0.0", "sha256": sha}


def _live_run(fixture: SeamControl, ref: dict[str, Any], request_id: str) -> str:
    """Start a run and wait until the FakeCoordinator is in-flight: the run
    is parked inside start_run, deterministically live (running)."""
    started = fixture.ops.run_start(_control("p1"), BENCH_ID, request_id, ref, 1, None)
    assert started["state"] in ("accepted", "running")
    _await_coordinator(fixture.coordinators)
    return str(started["run_id"])


# --- §5 busy bench: synchronous conflict before acceptance ----------------------


def test_run_start_on_busy_bench_conflicts_synchronously(
    seam_control: SeamControl,
) -> None:
    """A second run on a bench with a live run is a SYNCHRONOUS conflict,
    never a queued acceptance that surfaces asynchronously. The variant
    binding's request id MATCHES its §9 request id, so only the busy check
    can fire here."""
    variant = _variant_binding(seam_control, "req-prechecks-b")
    _live_run(seam_control, seam_control.binding_ref, str(seam_control.binding_ref["id"]))
    with pytest.raises(errors.OperationFailure) as ei:
        seam_control.ops.run_start(
            _control("p1"), BENCH_ID, "req-prechecks-b", variant, 1, None
        )
    assert ei.value.failure.code == "conflict"
    assert "busy" in ei.value.failure.message


# --- §5 binding identity: document request_id must match the request ------------


def test_binding_request_id_mismatch_is_conflict(seam_control: SeamControl) -> None:
    """Clean bench (no live run): the binding document names
    request_id 'req-voltage-check-1' while the §9 request id differs —
    only the binding-match check can fire."""
    with pytest.raises(errors.OperationFailure) as ei:
        seam_control.ops.run_start(
            _control("p1"),
            BENCH_ID,
            "req-c",
            seam_control.binding_ref,
            1,
            None,
        )
    assert ei.value.failure.code == "conflict"
    assert "req-voltage-check-1" in ei.value.failure.message


def test_unstored_binding_document_defers_to_async_path(
    seam_control: SeamControl,
) -> None:
    """Posture pin: the binding-match reads the content store exactly as
    run_check does; an UNSTORED digest is not decided at accept time (the
    worker's poison guard owns that failure asynchronously), so acceptance
    itself must not become a conflict."""
    ghost = dict(seam_control.binding_ref, sha256="f" * 64)
    result = seam_control.ops.run_start(
        _control("p1"), BENCH_ID, "req-ghost", ghost, 1, None
    )
    assert result["state"] in ("accepted", "running")


# --- §9 replay stays ahead of §5 contention --------------------------------------


def test_replay_of_same_request_id_beats_busy(seam_control: SeamControl) -> None:
    """Controller ruling: a retry of the SAME request id while its run is
    live returns the EXISTING run — the busy check must not turn a §9
    replay into a conflict."""
    ref = seam_control.binding_ref
    request_id = str(ref["id"])
    run_id = _live_run(seam_control, ref, request_id)
    replay = seam_control.ops.run_start(_control("p1"), BENCH_ID, request_id, ref, 1, None)
    assert replay["run_id"] == run_id
    assert replay["state"] in ("accepted", "running")
    assert seam_control.worker.submitted == 1  # replay never enqueues again


# --- clean bench still accepts ---------------------------------------------------


def test_clean_bench_still_accepts(seam_control: SeamControl) -> None:
    ref = seam_control.binding_ref
    result = seam_control.ops.run_start(
        _control("p1"), BENCH_ID, str(ref["id"]), ref, 1, None
    )
    assert result["state"] in ("accepted", "running")


# --- D9 lease-authority modeling (consumed by Task 3 takeover) -------------------


def test_run_row_records_gateway_authority_by_default(
    seam_control: SeamControl,
) -> None:
    run = seam_control.ops.run_start(
        _control("p1"), BENCH_ID, str(seam_control.binding_ref["id"]),
        seam_control.binding_ref, 1, None,
    )
    row = seam_control.store.get_run(str(run["run_id"]))
    assert row is not None
    assert row["authority"] == "gateway"  # lease_id=None ⇒ gateway-owned


def test_run_row_records_lease_authority_when_lease_id_present(
    seam_control: SeamControl,
) -> None:
    """D12 realignment: the named lease must be REAL — an active lease the
    caller holds, which the takeover validates and consumes. A bogus id no
    longer records lease authority; it fails closed ``not_found`` (pinned
    in test_takeover.py)."""
    lease = seam_control.ops.lease_create(
        _control("p1"), BENCH_ID, "lease-authority-1", 1, 600_000
    )
    run = seam_control.ops.run_start(
        _control("p1"), BENCH_ID, str(seam_control.binding_ref["id"]),
        seam_control.binding_ref, 1, str(lease["lease_id"]),
    )
    row = seam_control.store.get_run(str(run["run_id"]))
    assert row is not None
    assert row["authority"] == "lease"  # authority came from a validated lease
