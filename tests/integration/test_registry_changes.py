"""WP08 Task 7: the registry change kinds over a wired fixture resolver session.

The WP07 posture fail-closed both registry kinds ``not_ready`` (no resolver
session at bootstrap — ``test_seam_admin`` pins that boundary). This suite
pins the flip: ``package_admission`` and ``configuration_activation`` run
end-to-end — submit → apply with a valid independent approval → ``applied``
— over the REAL fixture registry (``fixtures/registry/``), the real store,
and the real registry surface (resolve → admit → activate), with no mocks.
The session comes from ``bootstrap.build_registry_session``, the same
builder the app composes, which mirrors ``test_registry_reuse.py``'s proven
construction: one signed origin-main, trust root ``keys/main.pub.pem``, the
``benchweave`` namespace routed, the same admission budgets.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from benchweave.content.store import ContentStore
from benchweave.interfaces.bootstrap import RegistrySession, build_registry_session
from benchweave.interfaces.identity import Identity, issue
from benchweave.interfaces.operations import Operations
from benchweave.interfaces.validation import SeamValidator
from benchweave.state.store import Store

REPO = Path(__file__).resolve().parents[2]
REG = REPO / "fixtures" / "registry"
CORPUS = REPO / "standards" / "interface/1.1.1"
NOW = "2026-09-12T00:00:00Z"
# The registry clock, verbatim from test_registry_reuse: inside every fixture
# status's validity window (expires 2027-09-11, updated_at not in the future).
NOW_NS = int(datetime(2026, 9, 12, tzinfo=UTC).timestamp() * 1_000_000_000)
SECRET = b"wp08-task-seven-secret"
ADMIN = Identity("admin-7", "stg", frozenset({"stg:admin"}), 2**31)
BENCH = "bench-reg"
LIMITS: dict[str, int] = {
    "max_json_bytes": 1048576,
    "max_page_size": 1000,
    "max_chunk_bytes": 65536,
    "max_lease_ms": 600000,
    "min_poll_ms": 100,
    "max_admission_ms": 5000,
}
SIM_PSU = "benchweave/sim-psu"
# The root release's manifest digest, pinned by the change target the same
# way test_registry_reuse pins the honest origin-main digest.
SIM_PSU_MANIFEST_SHA = hashlib.sha256(
    (REG / "origin-main" / SIM_PSU / "1.0.0" / "manifest.json").read_bytes()
).hexdigest()
TARGET_REF: dict[str, str] = {
    "id": SIM_PSU,
    "version": "1.0.0",
    "sha256": SIM_PSU_MANIFEST_SHA,
}


def _seed_bench(store: Store) -> None:
    """One admin bench at generation 1, mirroring the seam_admin seeding."""
    store.bump_generation(BENCH, NOW)
    store.put_bench(
        BENCH, 1, "observation", json.dumps({"id": BENCH, "version": "1"}), "", NOW
    )


def _store_approval(content: ContentStore, change_id: str) -> tuple[dict[str, str], str]:
    """A stored approval document + detached token binding one change at gen 1."""
    body = {
        "change_id": change_id,
        "expected_generation": 1,
        "approver_principal": "approver-7",
        "policy_version": "1",
    }
    raw = json.dumps(body, sort_keys=True).encode()
    sha = hashlib.sha256(raw).hexdigest()
    content.put_document(raw, sha, body, "urn:stg:approval", NOW)
    token = issue(
        SECRET,
        principal="approver-7",
        audience="gateway-admin",
        scopes=["stg:admin"],
        expires_at=2**31,
    )
    return {"id": f"approval-{change_id}", "version": "1", "sha256": sha}, token


@pytest.fixture()
def registry_seam(
    tmp_path: Path,
) -> Iterator[tuple[Operations, Store, ContentStore, RegistrySession]]:
    """The seam over the real store with bootstrap's fixture resolver session."""
    store = Store.open(tmp_path / "state.db")
    content = ContentStore(store)
    _seed_bench(store)
    session = build_registry_session(REG, tmp_path / "registry", now_ns=lambda: NOW_NS)
    ops = Operations(
        store,
        content,
        validator=SeamValidator(CORPUS),
        gateway_id="gw-registry-changes",
        limits=LIMITS,
        issuer_secret=SECRET,
        now_iso=lambda: NOW,
        now_epoch=lambda: 0,
        registry_session=session,
    )
    yield ops, store, content, session
    store.close()


def _apply_kind(
    ops: Operations, content: ContentStore, kind: str, target: dict[str, str]
) -> dict[str, Any]:
    """Submit one registry change and apply it with a valid independent approval."""
    submitted = ops.change_submit(
        ADMIN, f"req-{kind}", BENCH, kind, target, 1, "fixture registry change"
    )
    assert submitted["state"] == "proposed"
    change_id = str(submitted["change_id"])
    ref, token = _store_approval(content, change_id)
    return ops.change_apply(
        ADMIN, f"req-{kind}-apply", change_id, 1, ref, approver_token=token
    )


# --- the flip: both registry kinds apply end-to-end -------------------------


def test_package_admission_applies_end_to_end_over_fixture_registry(
    registry_seam: tuple[Operations, Store, ContentStore, RegistrySession],
) -> None:
    ops, store, content, session = registry_seam
    applied = _apply_kind(ops, content, "package_admission", TARGET_REF)

    assert applied["state"] == "applied"
    assert store.current_generation(BENCH) == 2

    # The registry surface really admitted the closure: a schema-valid
    # package lock whose root is the pinned sim-psu release, the approval
    # recorded under the authenticated approver, both closure members in
    # the content-addressed cache, and the persisted high-water view.
    lock = json.loads(session.lock_path.read_bytes())
    assert lock["roots"] == [
        {
            "registry_id": "origin-main",
            "package_id": SIM_PSU,
            "version": "1.0.0",
            "manifest_sha256": SIM_PSU_MANIFEST_SHA,
        }
    ]
    # The closure the proven reuse suite pins: sim-psu + descriptor + profile.
    assert len(lock["packages"]) == 3
    assert lock["approval"]["principal_id"] == "approver-7"
    assert (session.cache_root / SIM_PSU_MANIFEST_SHA).is_dir()
    assert (session.cache_root / "high-water.json").is_file()

    # registry_status_changed emission: the contract's event-kind list
    # carries it for the registry change paths (interface.schema.json).
    events = store.read_events_after(f"bench.{BENCH}", None, 10)
    assert [event["kind"] for event in events] == ["registry_status_changed"]
    assert events[0]["evidence"]["change_id"] == applied["change_id"]
    assert events[0]["evidence"]["generation"] == 2


def test_configuration_activation_applies_end_to_end_over_fixture_registry(
    registry_seam: tuple[Operations, Store, ContentStore, RegistrySession],
) -> None:
    ops, store, content, session = registry_seam
    applied = _apply_kind(ops, content, "configuration_activation", TARGET_REF)

    assert applied["state"] == "applied"
    assert store.current_generation(BENCH) == 2

    # The activation record binds the admitted lock digest into the
    # generation this change creates (1 -> 2), per-bench under the
    # session's records directory.
    record_path = session.records_dir / BENCH / "activation-2.json"
    assert record_path.is_file()
    record = json.loads(record_path.read_bytes())
    lock_sha = hashlib.sha256(session.lock_path.read_bytes()).hexdigest()
    assert record["lock_sha256"] == lock_sha
    assert record["previous_generation"] == 1
    assert record["new_generation"] == 2
    assert record["activated_at"] == NOW

    events = store.read_events_after(f"bench.{BENCH}", None, 10)
    assert [event["kind"] for event in events] == ["registry_status_changed"]


def test_package_admission_digest_pin_mismatch_is_conflict(
    registry_seam: tuple[Operations, Store, ContentStore, RegistrySession],
) -> None:
    """The target ref's digest binds the change to one release: a pin the
    served registry does not match refuses at apply, before admission."""
    from benchweave.interfaces import errors

    ops, store, content, session = registry_seam
    mismatched = {**TARGET_REF, "sha256": "0" * 64}
    submitted = ops.change_submit(
        ADMIN, "req-mismatch", BENCH, "package_admission", mismatched, 1, "wrong pin"
    )
    change_id = str(submitted["change_id"])
    ref, token = _store_approval(content, change_id)
    with pytest.raises(errors.OperationFailure) as exc:
        ops.change_apply(
            ADMIN, "req-mismatch-apply", change_id, 1, ref, approver_token=token
        )
    assert exc.value.failure.code == "conflict"
    assert ops.change_get(ADMIN, change_id)["state"] == "failed"
    # Refused before admission: nothing was cached or locked.
    assert not session.lock_path.exists()
    assert not session.cache_root.exists()


def test_package_admission_without_session_still_fails_closed_not_ready(
    tmp_path: Path,
) -> None:
    """The WP07 boundary survives the wiring: a seam constructed without a
    registry session keeps failing closed rather than fabricating work."""
    from benchweave.interfaces import errors

    store = Store.open(tmp_path / "state.db")
    content = ContentStore(store)
    _seed_bench(store)
    ops = Operations(
        store,
        content,
        validator=SeamValidator(CORPUS),
        gateway_id="gw-unwired",
        limits=LIMITS,
        issuer_secret=SECRET,
        now_iso=lambda: NOW,
        now_epoch=lambda: 0,
    )
    try:
        submitted = ops.change_submit(
            ADMIN, "req-unwired", BENCH, "package_admission", TARGET_REF, 1, "unwired"
        )
        change_id = str(submitted["change_id"])
        ref, token = _store_approval(content, change_id)
        with pytest.raises(errors.OperationFailure) as exc:
            ops.change_apply(
                ADMIN, "req-unwired-apply", change_id, 1, ref, approver_token=token
            )
        assert exc.value.failure.code == "not_ready"
        assert ops.change_get(ADMIN, change_id)["state"] == "failed"
    finally:
        store.close()
