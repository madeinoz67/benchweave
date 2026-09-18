"""D12: the commissioned takeover slice — ``run_start`` honors ``lease_id``
(WP08 Task 3, spec Decision 4).

WP07 shipped ``lease_id`` accepted-and-dropped; this suite pins the real
assertion. A run started against the caller's ACTIVE manual bench lease
takes over the bench: the lease is validated (resolvable, on THIS bench,
unexpired, §6 owner-or-admin) and CONSUMED at accept time — the store
transition that lets the worker's ``reserve`` see an idle bench (an active
lease would ``bench_busy`` the run into the poison guard) and that prevents
the lease from ever authorizing a second takeover. The authority handoff
and the manual-authority return both surface as ``authority_changed``
bench events shaped exactly like the vendored ``event`` def — whose
``evidence`` is a CLOSED ``{id, version, sha256}`` ref, not a free-form
dict, so the takeover event pins the binding document and the release
event pins the commissioned bench configuration.

Corpus anchors: interface-contract §5 ("The caller's own valid manual
lease is the required authority, not a conflicting busy owner; another
active controlling run or another owner still conflicts") and §6
(owner-or-admin, no generic override flag). Failure codes per the catalog
global 14-code set: unknown/expired/consumed lease ``not_found``;
wrong-bench lease and a still-live run ``conflict``; a non-holder control
principal ``forbidden``.

Bootstrap reuse, not duplication: the in-process ``seam_control`` fixture
from tests/unit (re-exported by this layer's conftest), exactly the
Task-2 pattern. Wire-level truth (real worker, real coordinator, real
``reserve``) is pinned separately in ``test_event_recovery.py``.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from test_seam_control import (
    BENCH_ID,
    SeamControl,
    _await_coordinator,
    _control,
)

from benchweave.content.store import ContentStore
from benchweave.interfaces import errors
from benchweave.interfaces.identity import Identity
from benchweave.interfaces.operations import scoped_request_key

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "execution"
CORPUS = Path(__file__).resolve().parents[2] / "standards" / "interface/0.1.0"
NOW = "2026-09-12T00:00:00Z"  # seam_control's frozen clock
OTHER_BENCH = "sim-bench-two"  # a wrong-bench lease target (store-seeded)

# The vendored event def, VERBATIM: its ``evidence`` is a closed ref, and
# its ``stream_id`` pattern admits the seam's "bench.{bench_id}" naming
# (the fix-wave rename). The def is never patched here.
_EVENT_DEF = json.loads((CORPUS / "interface.schema.json").read_bytes())["$defs"]["event"]
_EVENT_VALIDATOR = Draft202012Validator(_EVENT_DEF)


def _admin(principal: str) -> Identity:
    return Identity(principal, "stg", frozenset({"stg:admin"}), 2**31)


def _variant_binding(fixture: SeamControl, request_id: str) -> dict[str, Any]:
    """A STORED binding variant (the event-recovery suite's SECOND_REF
    idiom): same pin lattice, a distinct document-level request id."""
    document = json.loads((FIXTURES / "run-binding.json").read_bytes())
    document["request_id"] = request_id
    raw = json.dumps(document, indent=2).encode()
    sha = hashlib.sha256(raw).hexdigest()
    ContentStore(fixture.store).put_document(raw, sha, document, "urn:stg:binding", NOW)
    return {"id": request_id, "version": "1.0.0", "sha256": sha}


def _bench_events(fixture: SeamControl) -> list[dict[str, Any]]:
    page = fixture.ops.events_get(_control("p1"), BENCH_ID, after=None, limit=1000)
    return list(page["events"])


def _live_run(fixture: SeamControl, ref: dict[str, Any], request_id: str) -> str:
    """Start a run and wait until the FakeCoordinator is in-flight: the run
    is parked inside start_run, deterministically live (running)."""
    started = fixture.ops.run_start(_control("p1"), BENCH_ID, request_id, ref, 1, None)
    assert started["state"] in ("accepted", "running")
    _await_coordinator(fixture.coordinators)
    return str(started["run_id"])


# --- the sanctioned takeover ------------------------------------------------------


def test_takeover_with_active_lease_accepted_run_proceeds_authority_changed(
    seam_control: SeamControl,
) -> None:
    """The caller's own ACTIVE lease on THIS bench commissions the run:
    accepted, ``authority='lease'`` on the run row, the lease CONSUMED
    (nothing holds the bench — the exact precondition the worker's
    ``reserve`` reads), and one contract-shaped ``authority_changed``
    before the ``run_changed`` announcement."""
    lease = seam_control.ops.lease_create(
        _control("p1"), BENCH_ID, "lease-take-1", 1, 600_000
    )
    variant = _variant_binding(seam_control, "req-take-1")
    run = seam_control.ops.run_start(
        _control("p1"), BENCH_ID, "req-take-1", variant, 1, str(lease["lease_id"])
    )
    assert run["state"] in ("accepted", "running")
    row = seam_control.store.get_run(str(run["run_id"]))
    assert row is not None
    assert row["authority"] == "lease"

    # Consumed: no active lease remains on the bench (the reserve()
    # precondition), and the lease row itself is closed out.
    assert seam_control.store.get_active_lease(BENCH_ID) is None
    rows = [
        item for item in seam_control.store.list_leases(BENCH_ID)
        if item.lease_id == str(lease["lease_id"])
    ]
    assert rows and all(item.state == "released" for item in rows)

    events = _bench_events(seam_control)
    assert [event["kind"] for event in events] == [
        "lease_changed",  # lease_create
        "authority_changed",  # the commissioned handoff
        "run_changed",  # the run announcement
    ]
    event = events[1]
    assert event["stream_id"] == f"bench.{BENCH_ID}"
    assert event["run_id"] == run["run_id"]
    assert event["evidence"] == {
        "id": variant["id"],
        "version": variant["version"],
        "sha256": variant["sha256"],
    }
    assert not list(_EVENT_VALIDATOR.iter_errors(event))


# --- unvalidated leases fail closed -----------------------------------------------


def test_unknown_lease_fails_not_found_nothing_persisted(
    seam_control: SeamControl,
) -> None:
    """A lease id that resolves to nothing is ``not_found`` — decided
    BEFORE the request key is written (no dangling §9 tombstone) and
    before anything is enqueued. The default binding + its own request id
    keep every other §5 check quiet, so only the lease check can fire."""
    with pytest.raises(errors.OperationFailure) as ei:
        seam_control.ops.run_start(
            _control("p1"),
            BENCH_ID,
            str(seam_control.binding_ref["id"]),
            seam_control.binding_ref,
            1,
            "lease-ghost",
        )
    assert ei.value.failure.code == "not_found"
    assert seam_control.worker.submitted == 0
    key = scoped_request_key(
        "p1", "run_start", str(seam_control.binding_ref["id"])
    )
    assert seam_control.store.find_request(key) is None


def test_wrong_bench_lease_fails_conflict(seam_control: SeamControl) -> None:
    """A real ACTIVE lease held by the caller — on a DIFFERENT bench — is
    a ``conflict`` (the takeover asserts authority over THIS bench)."""
    seam_control.store.bump_generation(OTHER_BENCH, NOW)
    seam_control.store.put_bench(OTHER_BENCH, 1, "none", "{}", "", NOW)
    foreign = seam_control.ops.lease_create(
        _control("p1"), OTHER_BENCH, "lease-other-1", 1, 600_000
    )
    with pytest.raises(errors.OperationFailure) as ei:
        seam_control.ops.run_start(
            _control("p1"),
            BENCH_ID,
            str(seam_control.binding_ref["id"]),
            seam_control.binding_ref,
            1,
            str(foreign["lease_id"]),
        )
    assert ei.value.failure.code == "conflict"
    assert seam_control.worker.submitted == 0


def test_expired_lease_fails_not_found(seam_control: SeamControl) -> None:
    """An active row whose deadline has passed is expired authority:
    ``not_found`` (a late takeover cannot revive it, mirroring §6's
    late-renewal rule). Seeded through the store so the clock stays frozen."""
    seam_control.store.next_lease(
        BENCH_ID, "lease-expired-1", holder="p1", expires_at="2026-09-11T23:59:59Z"
    )
    with pytest.raises(errors.OperationFailure) as ei:
        seam_control.ops.run_start(
            _control("p1"),
            BENCH_ID,
            str(seam_control.binding_ref["id"]),
            seam_control.binding_ref,
            1,
            "lease-expired-1",
        )
    assert ei.value.failure.code == "not_found"
    assert seam_control.worker.submitted == 0


# --- §6 non-holder semantics (owner-or-admin, shared with run_cancel) --------------


def test_non_holder_takeover_forbidden_admin_allowed(seam_control: SeamControl) -> None:
    """A control-tier principal who is not the holder is ``forbidden``
    (§6 owner-or-admin — the SAME predicate run_cancel's scoping uses);
    an admin-tier principal may take over on the holder's lease."""
    lease = seam_control.ops.lease_create(
        _control("p1"), BENCH_ID, "lease-hold-1", 1, 600_000
    )
    variant = _variant_binding(seam_control, "req-take-admin")

    with pytest.raises(errors.OperationFailure) as ei:
        seam_control.ops.run_start(
            _control("p2"), BENCH_ID, "req-take-admin", variant, 1, str(lease["lease_id"])
        )
    assert ei.value.failure.code == "forbidden"
    assert seam_control.worker.submitted == 0
    # the refused attempt must not have consumed the holder's authority
    active = seam_control.store.get_active_lease(BENCH_ID)
    assert active is not None and active.lease_id == str(lease["lease_id"])

    run = seam_control.ops.run_start(
        _admin("p2"), BENCH_ID, "req-take-admin", variant, 1, str(lease["lease_id"])
    )
    assert run["state"] in ("accepted", "running")
    row = seam_control.store.get_run(str(run["run_id"]))
    assert row is not None
    assert row["authority"] == "lease"


# --- the takeover never waives §5 contention ---------------------------------------


def test_takeover_on_bench_with_live_run_still_conflicts(
    seam_control: SeamControl,
) -> None:
    """Corpus §5: ``another active controlling run ... still conflicts`` —
    the lease overrides the CALLER'S OWN manual authority (consumed at
    acceptance), never another live run; and a refused attempt leaves the
    lease untouched."""
    variant = _variant_binding(seam_control, "req-take-b")
    lease = seam_control.ops.lease_create(
        _control("p1"), BENCH_ID, "lease-busy-1", 1, 600_000
    )
    _live_run(seam_control, seam_control.binding_ref, str(seam_control.binding_ref["id"]))
    with pytest.raises(errors.OperationFailure) as ei:
        seam_control.ops.run_start(
            _control("p1"), BENCH_ID, "req-take-b", variant, 1, str(lease["lease_id"])
        )
    assert ei.value.failure.code == "conflict"
    active = seam_control.store.get_active_lease(BENCH_ID)
    assert active is not None and active.lease_id == str(lease["lease_id"])


# --- the consume→reserve window (§6 "rejects conflicts with existing authority") ---


def test_unrelated_lease_create_in_takeover_window_is_refused(
    seam_control: SeamControl,
) -> None:
    """D12's disclosed consume→reserve window, CLOSED (§6, D13 batch B):
    once a takeover has consumed the caller's lease and its run is live,
    an UNRELATED lease_create on the bench is refused with ``conflict`` —
    the run's live state IS the gateway-owned authority §6 protects.
    Pre-fix this mint succeeded and the worker's ``reserve`` then found
    the bench busy (bench_busy → poison guard ⇒ an outcome_unknown death
    for a valid takeover); the refusal keeps the takeover's path clear."""
    lease = seam_control.ops.lease_create(
        _control("p1"), BENCH_ID, "lease-window-1", 1, 600_000
    )
    variant = _variant_binding(seam_control, "req-window-1")
    run = seam_control.ops.run_start(
        _control("p1"), BENCH_ID, "req-window-1", variant, 1, str(lease["lease_id"])
    )
    assert run["state"] in ("accepted", "running")
    _await_coordinator(seam_control.coordinators)
    with pytest.raises(errors.OperationFailure) as exc:
        seam_control.ops.lease_create(
            _control("p2"), BENCH_ID, "lease-window-2", 1, 1000
        )
    assert exc.value.failure.code == "conflict"
    assert "run" in exc.value.failure.message


# --- a consumed lease is single-shot; §9 replay stays ahead ------------------------


def test_consumed_lease_replay_returns_run_reuse_fails(
    seam_control: SeamControl,
) -> None:
    """Ruling 3's two halves: a §9 replay of the SAME request returns the
    existing run (never re-validates the now-consumed lease, never
    re-enqueues); a NEW request re-presenting the consumed lease fails
    closed ``not_found``."""
    lease = seam_control.ops.lease_create(
        _control("p1"), BENCH_ID, "lease-once-1", 1, 600_000
    )
    first = seam_control.ops.run_start(
        _control("p1"),
        BENCH_ID,
        "req-take-r",
        _variant_binding(seam_control, "req-take-r"),
        1,
        str(lease["lease_id"]),
    )
    replay = seam_control.ops.run_start(
        _control("p1"),
        BENCH_ID,
        "req-take-r",
        _variant_binding(seam_control, "req-take-r"),
        1,
        str(lease["lease_id"]),
    )
    assert replay["run_id"] == first["run_id"]
    assert seam_control.worker.submitted == 1

    with pytest.raises(errors.OperationFailure) as ei:
        seam_control.ops.run_start(
            _control("p1"),
            BENCH_ID,
            "req-take-r2",
            _variant_binding(seam_control, "req-take-r2"),
            1,
            str(lease["lease_id"]),
        )
    assert ei.value.failure.code == "not_found"


# --- the release path emits authority_changed --------------------------------------


def test_lease_release_emits_authority_changed(seam_control: SeamControl) -> None:
    """Releasing manual authority is an authority transition: the release
    carries ``lease_changed`` (the fact) then ``authority_changed`` (the
    return), the latter contract-shaped with the commissioned bench
    configuration as its closed evidence ref and no run attached."""
    lease = seam_control.ops.lease_create(
        _control("p1"), BENCH_ID, "lease-rel-1", 1, 600_000
    )
    seam_control.ops.lease_release(
        _control("p1"), str(lease["lease_id"]), "lease-rel-1", "manual work done"
    )
    events = _bench_events(seam_control)
    assert [event["kind"] for event in events] == [
        "lease_changed",
        "lease_changed",
        "authority_changed",
    ]
    event = events[2]
    assert event["run_id"] is None
    assert event["stream_id"] == f"bench.{BENCH_ID}"
    bench = seam_control.ops.bench_get(_control("p1"), BENCH_ID)
    assert event["evidence"] == bench["configuration"]
    assert not list(_EVENT_VALIDATOR.iter_errors(event))
