"""WP07 Task 7: two-phase changes, approval authentication, fail-closed apply.

Unit level over the seam (Task 8 wires the transports): the two-phase state
machine (proposed -> applied/failed/unknown), the two-principal approval
split (an admin applier + an independently authenticated approver token), the
canonical generation fence, the idle boundary, and the trip gate. Fixture
resolutions are disclosed in the fixtures' docstrings and the task report:

- ``seam_admin`` seeds the literal change rows (chg-1/chg-2/chg-ok) through
  the Task-2 store primitive — the seam derives §9-scoped opaque change ids
  (like run ids), so tests that name changes by literal id must seed them.
- ``approval_doc`` binds ``chg-ok`` (the happy-path change). The brief's
  snippet bound ``chg-1`` while its own note holds ``chg-ok`` as "matching
  the approval doc"; strict change binding (the trust requirement) makes the
  two incompatible, and the tests win.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from benchweave.content.store import ContentStore
from benchweave.interfaces import errors
from benchweave.interfaces.identity import Identity, issue
from benchweave.interfaces.operations import Operations
from benchweave.state.store import Store

ADMIN = Identity("admin-1", "stg", frozenset({"stg:admin"}), 2**31)
SECRET = b"test-issuer-secret"
NOW = "2026-09-12T00:00:00Z"
BENCH = "bench-1"
LIMITS = {
    "max_json_bytes": 1048576,
    "max_page_size": 1000,
    "max_chunk_bytes": 65536,
    "max_lease_ms": 600000,
    "min_poll_ms": 100,
    "max_admission_ms": 5000,
}
TARGET_REF = {"id": "t", "version": "1", "sha256": "0" * 64}


@pytest.fixture()
def seam_admin(tmp_path: Path) -> Iterator[tuple[Operations, Store, ContentStore]]:
    """Admin seam over a hand-seeded bench-1 at generation 1.

    The generations authority is bumped to 1 and the bench row mirrors it
    (Decision 4: the table is canonical, the row is the projection). Three
    literal proposed changes are seeded via ``put_change``.
    """
    store = Store.open(tmp_path / "state.db")
    content = ContentStore(store)
    store.bump_generation(BENCH, NOW)  # authority: 0 -> 1
    store.put_bench(
        BENCH, 1, "observation", json.dumps({"id": BENCH, "version": "1"}), "", NOW
    )
    for change_id in ("chg-1", "chg-2", "chg-ok"):
        store.put_change(
            change_id, BENCH, "trip_reset", json.dumps(TARGET_REF), 1, "fixture", NOW
        )
    ops = Operations(
        store,
        content,
        gateway_id="gw-admin-test",
        limits=LIMITS,
        issuer_secret=SECRET,
        now_epoch=lambda: 0,
        now_iso=lambda: NOW,
    )
    yield ops, store, content
    store.close()


@pytest.fixture()
def approval_doc(
    seam_admin: tuple[Operations, Store, ContentStore],
) -> tuple[dict[str, str], str, dict[str, Any]]:
    """A stored approval document + its detached token for change chg-ok gen 1."""
    _, _, content = seam_admin
    body = {
        "change_id": "chg-ok",
        "expected_generation": 1,
        "approver_principal": "approver-x",
        "policy_version": "1",
    }
    raw = json.dumps(body, sort_keys=True).encode()
    sha = hashlib.sha256(raw).hexdigest()
    content.put_document(raw, sha, body, "urn:stg:approval", NOW)
    token = issue(
        SECRET,
        principal="approver-x",
        audience="gateway-admin",
        scopes=["stg:admin"],
        expires_at=2**31,
    )
    return {"id": "approval-1", "version": "1", "sha256": sha}, token, body


def _put_approval(
    content: ContentStore, *, change_id: str, approver: str = "approver-x"
) -> tuple[dict[str, str], str]:
    """Store an approval document + detached token binding one change at gen 1."""
    body = {
        "change_id": change_id,
        "expected_generation": 1,
        "approver_principal": approver,
        "policy_version": "1",
    }
    raw = json.dumps(body, sort_keys=True).encode()
    sha = hashlib.sha256(raw).hexdigest()
    content.put_document(raw, sha, body, "urn:stg:approval", NOW)
    token = issue(
        SECRET,
        principal=approver,
        audience="gateway-admin",
        scopes=["stg:admin"],
        expires_at=2**31,
    )
    return {"id": f"approval-{change_id}", "version": "1", "sha256": sha}, token


# --- submit: records only ---------------------------------------------------------


def test_submit_records_only(seam_admin: tuple[Operations, Store, ContentStore]) -> None:
    ops, store, _ = seam_admin
    change = ops.change_submit(
        ADMIN,
        "req-1",
        BENCH,
        "trip_reset",
        {"id": "t", "version": "1", "sha256": "0" * 64},
        1,
        "operator reset",
    )
    assert change["state"] == "proposed"
    assert store.current_generation(BENCH) == 1  # untouched


def test_submit_is_idempotent_per_scoped_request(
    seam_admin: tuple[Operations, Store, ContentStore],
) -> None:
    ops, store, _ = seam_admin
    first = ops.change_submit(ADMIN, "dup-1", BENCH, "trip_reset", TARGET_REF, 1, "r")
    second = ops.change_submit(ADMIN, "dup-1", BENCH, "trip_reset", TARGET_REF, 1, "r")
    assert second["change_id"] == first["change_id"]  # replay: no second record
    assert store.get_change(str(first["change_id"])) is not None
    with pytest.raises(errors.OperationFailure) as exc:
        ops.change_submit(ADMIN, "dup-1", BENCH, "trip_reset", TARGET_REF, 2, "other")
    assert exc.value.failure.code == "conflict"


def test_submit_request_ids_are_principal_scoped(
    seam_admin: tuple[Operations, Store, ContentStore],
) -> None:
    ops, _, _ = seam_admin
    other = Identity("admin-2", "stg", frozenset({"stg:admin"}), 2**31)
    one = ops.change_submit(ADMIN, "same", BENCH, "trip_reset", TARGET_REF, 1, "r")
    two = ops.change_submit(other, "same", BENCH, "trip_reset", TARGET_REF, 1, "r")
    assert one["change_id"] != two["change_id"]  # separate §9 namespaces


def test_submit_rejects_unknown_kind(
    seam_admin: tuple[Operations, Store, ContentStore],
) -> None:
    ops, _, _ = seam_admin
    with pytest.raises(errors.OperationFailure) as exc:
        ops.change_submit(ADMIN, "k-req", BENCH, "firmware_flash", TARGET_REF, 1, "r")
    assert exc.value.failure.code == "invalid_request"


# --- apply: approval authentication -----------------------------------------------


def test_apply_without_authenticated_approval_fails_closed(
    seam_admin: tuple[Operations, Store, ContentStore],
    approval_doc: tuple[dict[str, str], str, dict[str, Any]],
) -> None:
    ops, store, _ = seam_admin
    ref, token, _ = approval_doc
    ops.change_submit(
        ADMIN, "req-2", "bench-1", "trip_reset",
        {"id": "t", "version": "1", "sha256": "0" * 64}, 1, "r",
    )
    with pytest.raises(errors.OperationFailure) as exc:
        ops.change_apply(ADMIN, "req-3", "chg-x-not-that-one", 1, ref)
    assert exc.value.failure.code in {"not_found", "forbidden"}
    # the authenticated happy path:
    change = ops.change_apply(ADMIN, "req-4", "chg-ok", 1, ref, approver_token=token)
    assert change["state"] == "applied"
    assert store.current_generation("bench-1") == 2


def test_apply_with_mismatched_generation_fails_and_records(
    seam_admin: tuple[Operations, Store, ContentStore],
    approval_doc: tuple[dict[str, str], str, dict[str, Any]],
) -> None:
    ops, store, _ = seam_admin
    ref, token, _ = approval_doc
    ops.change_submit(
        ADMIN, "req-5", "bench-1", "trip_reset",
        {"id": "t", "version": "1", "sha256": "0" * 64}, 1, "r",
    )
    with pytest.raises(errors.OperationFailure):
        ops.change_apply(ADMIN, "req-6", "chg-2", 999, ref, approver_token=token)
    failed = ops.change_get(ADMIN, "chg-2")
    assert failed["state"] == "failed" and failed["reasons"]


def test_apply_missing_token_is_forbidden_even_with_stored_doc(
    seam_admin: tuple[Operations, Store, ContentStore],
    approval_doc: tuple[dict[str, str], str, dict[str, Any]],
) -> None:
    """A stored approval document alone is not approval (contract §3)."""
    ops, _, _ = seam_admin
    ref, _, _ = approval_doc
    with pytest.raises(errors.OperationFailure) as exc:
        ops.change_apply(ADMIN, "req-mt", "chg-ok", 1, ref)
    assert exc.value.failure.code == "forbidden"
    assert ops.change_get(ADMIN, "chg-ok")["state"] == "failed"


def test_apply_with_detached_token_but_no_document(
    seam_admin: tuple[Operations, Store, ContentStore],
) -> None:
    """Token alone without the stored, sha-pinned document is not approval."""
    ops, _, _ = seam_admin
    token = issue(
        SECRET,
        principal="approver-x",
        audience="gateway-admin",
        scopes=["stg:admin"],
        expires_at=2**31,
    )
    with pytest.raises(errors.OperationFailure) as exc:
        ops.change_apply(
            ADMIN,
            "req-nd",
            "chg-ok",
            1,
            {"id": "a", "version": "1", "sha256": "f" * 64},
            approver_token=token,
        )
    assert exc.value.failure.code in {"not_found", "forbidden"}
    assert ops.change_get(ADMIN, "chg-ok")["state"] == "failed"


def test_apply_rejects_approval_authored_by_the_applier(
    seam_admin: tuple[Operations, Store, ContentStore],
) -> None:
    """Independence: the approver token must not be the applier's own."""
    ops, _, content = seam_admin
    ref, token = _put_approval(content, change_id="chg-1", approver=ADMIN.principal)
    with pytest.raises(errors.OperationFailure) as exc:
        ops.change_apply(ADMIN, "req-self", "chg-1", 1, ref, approver_token=token)
    assert exc.value.failure.code == "forbidden"
    assert ops.change_get(ADMIN, "chg-1")["state"] == "failed"


def test_apply_token_principal_must_match_the_documented_approver(
    seam_admin: tuple[Operations, Store, ContentStore],
) -> None:
    """A valid third-party token does not speak for the named approver."""
    ops, _, content = seam_admin
    ref, _ = _put_approval(content, change_id="chg-1", approver="approver-x")
    other_token = issue(
        SECRET,
        principal="someone-else",
        audience="gateway-admin",
        scopes=["stg:admin"],
        expires_at=2**31,
    )
    with pytest.raises(errors.OperationFailure) as exc:
        ops.change_apply(ADMIN, "req-px", "chg-1", 1, ref, approver_token=other_token)
    assert exc.value.failure.code == "forbidden"
    assert ops.change_get(ADMIN, "chg-1")["state"] == "failed"


# --- apply: fences and kind checks -------------------------------------------------


def test_apply_fences_against_the_canonical_generation(
    seam_admin: tuple[Operations, Store, ContentStore],
    approval_doc: tuple[dict[str, str], str, dict[str, Any]],
) -> None:
    """Decision 4: the generations table is the authority — a change whose
    expected generation the bench has moved past never applies."""
    ops, store, _ = seam_admin
    ref, token, _ = approval_doc
    store.bump_generation(BENCH, NOW)  # authority now 2; change + doc bind gen 1
    with pytest.raises(errors.OperationFailure) as exc:
        ops.change_apply(ADMIN, "req-fence", "chg-ok", 1, ref, approver_token=token)
    assert exc.value.failure.code == "conflict"
    assert ops.change_get(ADMIN, "chg-ok")["state"] == "failed"


def test_apply_configuration_activation_refuses_live_lease(
    seam_admin: tuple[Operations, Store, ContentStore],
) -> None:
    """Idle boundary: a live bench lease refuses activation (not_ready)."""
    ops, _, content = seam_admin
    ops.lease_create(
        Identity("op", "stg", frozenset({"stg:control"}), 2**31),
        BENCH,
        "lease-req",
        1,
        60000,
    )
    store_put_configuration_activation(seam_admin, "chg-act")
    ref, token = _put_approval(content, change_id="chg-act")
    with pytest.raises(errors.OperationFailure) as exc:
        ops.change_apply(ADMIN, "req-act", "chg-act", 1, ref, approver_token=token)
    assert exc.value.failure.code == "not_ready"
    assert ops.change_get(ADMIN, "chg-act")["state"] == "failed"


def test_apply_package_admission_without_registry_session_not_ready(
    seam_admin: tuple[Operations, Store, ContentStore],
) -> None:
    """WP07 PoC: no registry session is configured, so the registry kinds
    record failed/not_ready rather than fabricating registry work."""
    ops, _, content = seam_admin
    store_put_configuration_activation(seam_admin, "chg-adm", kind="package_admission")
    ref, token = _put_approval(content, change_id="chg-adm")
    with pytest.raises(errors.OperationFailure) as exc:
        ops.change_apply(ADMIN, "req-adm", "chg-adm", 1, ref, approver_token=token)
    assert exc.value.failure.code == "not_ready"
    assert ops.change_get(ADMIN, "chg-adm")["state"] == "failed"


def test_apply_success_refreshes_bench_row_and_emits_bench_changed(
    seam_admin: tuple[Operations, Store, ContentStore],
    approval_doc: tuple[dict[str, str], str, dict[str, Any]],
) -> None:
    """Task-5 mandate: bump the authority AND refresh the bench-row
    projection, then emit the kind's event (Task 6)."""
    ops, store, _ = seam_admin
    ref, token, _ = approval_doc
    ops.change_apply(ADMIN, "req-ev", "chg-ok", 1, ref, approver_token=token)
    assert store.current_generation(BENCH) == 2
    row = store.get_bench(BENCH)
    assert row is not None
    assert row["generation"] == 2  # projection is truthful
    events = store.read_events_after(f"bench:{BENCH}", None, 10)
    assert [event["kind"] for event in events] == ["bench_changed"]
    assert events[0]["evidence"]["change_id"] == "chg-ok"
    assert events[0]["evidence"]["generation"] == 2


def test_apply_crash_without_decision_records_unknown(
    seam_admin: tuple[Operations, Store, ContentStore],
    approval_doc: tuple[dict[str, str], str, dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ops, store, _ = seam_admin
    ref, token, _ = approval_doc

    def power_loss(bench_id: str, now: str) -> int:
        raise RuntimeError("power lost mid-apply")

    monkeypatch.setattr(store, "bump_generation", power_loss)
    with pytest.raises(errors.OperationFailure) as exc:
        ops.change_apply(ADMIN, "req-crash", "chg-ok", 1, ref, approver_token=token)
    assert exc.value.failure.code == "unavailable"
    assert ops.change_get(ADMIN, "chg-ok")["state"] == "unknown"


# --- change_get: admin-tier read ----------------------------------------------------


def test_change_get_unknown_change_not_found(
    seam_admin: tuple[Operations, Store, ContentStore],
) -> None:
    ops, _, _ = seam_admin
    with pytest.raises(errors.OperationFailure) as exc:
        ops.change_get(ADMIN, "chg-nope")
    assert exc.value.failure.code == "not_found"


def test_change_ops_reject_control_tier(
    seam_admin: tuple[Operations, Store, ContentStore],
    approval_doc: tuple[dict[str, str], str, dict[str, Any]],
) -> None:
    ops, _, _ = seam_admin
    ref, _, _ = approval_doc
    from benchweave.interfaces.identity import Identity as I

    control = I("op", "stg", frozenset({"stg:control"}), 2**31)
    with pytest.raises(errors.OperationFailure) as exc:
        ops.change_get(control, "chg-1")
    assert exc.value.failure.code == "forbidden"
    with pytest.raises(errors.OperationFailure) as exc:
        ops.change_submit(control, "c-sub", BENCH, "trip_reset", TARGET_REF, 1, "r")
    assert exc.value.failure.code == "forbidden"
    with pytest.raises(errors.OperationFailure) as exc:
        ops.change_apply(control, "c-app", "chg-ok", 1, ref, approver_token="x")
    assert exc.value.failure.code == "forbidden"


def store_put_configuration_activation(
    seam_admin: tuple[Operations, Store, ContentStore],
    change_id: str,
    *,
    kind: str = "configuration_activation",
) -> None:
    _, store, _ = seam_admin
    store.put_change(change_id, BENCH, kind, json.dumps(TARGET_REF), 1, "fixture", NOW)
