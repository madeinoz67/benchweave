"""WP07 Task 4: error model, tier gate, observe operations, bootstrap."""

from __future__ import annotations

import base64
import hashlib
from collections.abc import Iterator
from pathlib import Path

import pytest

from benchweave.content.store import ContentStore
from benchweave.interfaces import errors, operations
from benchweave.interfaces.bootstrap import admit_startup_bench
from benchweave.interfaces.identity import Identity
from benchweave.interfaces.operations import Operations
from benchweave.state.store import Store

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "execution"
Seam = tuple[Operations, Store]


@pytest.fixture()
def seam(tmp_path: Path) -> Iterator[Seam]:
    store = Store.open(tmp_path / "state.db")
    content = ContentStore(store)
    admit_startup_bench(store, content, FIXTURES, now="2026-09-12T00:00:00Z")
    ops = operations.Operations(
        store, content, gateway_id="gw-test",
        limits={"max_json_bytes": 1048576, "max_page_size": 1000,
                "max_chunk_bytes": 65536, "max_lease_ms": 600000,
                "min_poll_ms": 100, "max_admission_ms": 5000},
    )
    yield ops, store
    store.close()


def _identity(scopes: frozenset[str]) -> Identity:
    return Identity(
        principal="tester", audience="stg", scopes=scopes, expires_at=2**31
    )


OBSERVE = _identity(frozenset({"stg:observe"}))
CONTROL = _identity(frozenset({"stg:control"}))
ADMIN = _identity(frozenset({"stg:admin"}))


def test_gateway_info_shape(seam: Seam) -> None:
    ops, _ = seam
    data = ops.gateway_info(OBSERVE)
    assert data["gateway_id"] == "gw-test"
    assert data["interface_version"] == "1.1.0"
    assert data["mcp_version"] == "2026-07-28"
    assert data["limits"]["max_chunk_bytes"] == 65536


def test_observe_rejects_unknown_scope(seam: Seam) -> None:
    ops, _ = seam
    with pytest.raises(errors.OperationFailure) as exc:
        ops.gateway_info(_identity(frozenset({"stg:other"})))
    assert exc.value.failure.code == "forbidden"
    assert exc.value.failure.message == "missing scope stg:observe"


def test_observe_permits_control_tier_identity(seam: Seam) -> None:
    ops, _ = seam
    data = ops.gateway_info(CONTROL)  # control tier satisfies observe permission
    assert data["gateway_id"] == "gw-test"


def test_observe_permits_admin_tier_identity(seam: Seam) -> None:
    ops, _ = seam
    assert ops.gateway_info(ADMIN)["gateway_id"] == "gw-test"


def test_permission_tiers_form_a_hierarchy() -> None:
    operations.require_permission(CONTROL, "control")
    operations.require_permission(ADMIN, "control")
    operations.require_permission(ADMIN, "admin")
    with pytest.raises(errors.OperationFailure):
        operations.require_permission(OBSERVE, "control")
    with pytest.raises(errors.OperationFailure):
        operations.require_permission(CONTROL, "admin")


def test_non_numeric_cursor_sequence_rejected(seam: Seam) -> None:
    ops, _ = seam
    token = operations.encode_cursor("benches", "not-a-number", "tester")
    with pytest.raises(errors.OperationFailure) as exc:
        ops.bench_list(OBSERVE, limit=10, cursor=token)
    assert exc.value.failure.code == "invalid_request"


def test_bootstrap_admitted_bench_and_devices(seam: Seam) -> None:
    ops, _ = seam
    items, next_cursor = ops.bench_list(OBSERVE, limit=10, cursor=None)
    assert len(items) >= 1 and next_cursor is None
    bench_id = items[0]["bench_id"]
    devices, _ = ops.device_list(OBSERVE, bench_id, limit=10, cursor=None)
    assert len(devices) >= 1
    assert devices[0]["descriptor"]["id"] or devices[0]["descriptor"]  # non-empty


def test_document_get_returns_exact_original_bytes(seam: Seam) -> None:
    ops, store = seam
    row = store.connection.execute(
        "SELECT sha256 FROM documents LIMIT 1"
    ).fetchone()
    data = ops.document_get(OBSERVE, row[0])
    raw = base64.b64decode(data["original_utf8_base64"])
    assert hashlib.sha256(raw).hexdigest() == row[0]
    assert data["document"]["sha256"] == row[0]


def test_not_found_maps_to_contract_failure(seam: Seam) -> None:
    ops, _ = seam
    with pytest.raises(errors.OperationFailure) as exc:
        ops.bench_get(OBSERVE, "no-such-bench")
    assert exc.value.failure.code == "not_found"


def test_artifact_read_round_trip(seam: Seam) -> None:
    ops, store = seam
    content = ContentStore(store)
    artifact_id = content.put_artifact(b"payload-bytes", "2026-09-12T00:00:00Z")
    chunk = ops.artifact_read(OBSERVE, artifact_id, 0, 16)
    assert chunk["eof"] and chunk["bytes"] == 13  # len(b"payload-bytes")


def test_failure_http_map_has_fourteen_codes() -> None:
    assert len(errors.FAILURE_HTTP) == 14
    assert errors.FAILURE_HTTP["unauthenticated"] == 401
    assert errors.FAILURE_HTTP["event_gap"] == 410
