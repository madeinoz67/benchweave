"""WP07 Task 4: error model, tier gate, observe operations, bootstrap."""

from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from benchweave.content.store import ContentStore
from benchweave.interfaces import errors, operations
from benchweave.interfaces.bootstrap import admit_startup_bench
from benchweave.interfaces.identity import Identity
from benchweave.interfaces.operations import Operations
from benchweave.interfaces.validation import SeamValidator
from benchweave.state.store import Store

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "execution"
CORPUS = Path(__file__).resolve().parents[2] / "standards" / "interface/0.1.0"
Seam = tuple[Operations, Store]


@pytest.fixture()
def seam(tmp_path: Path) -> Iterator[Seam]:
    store = Store.open(tmp_path / "state.db")
    content = ContentStore(store)
    admit_startup_bench(store, content, FIXTURES, now="2026-09-12T00:00:00Z")
    ops = operations.Operations(
        store, content, gateway_id="gw-test",
        validator=SeamValidator(CORPUS),
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


# --- Task 12: licence display verdict (the schema decides) -------------------


def _vendored_interface_schema() -> dict[str, Any]:
    """The vendored interface schema (interface/0.1.0 errata revision; the
    schema file is a byte-copy of 1.1.0) — the authority the licence
    verdict is decided by, read fresh so this suite pins the artifact."""
    path = (
        FIXTURES.parents[1] / "standards" / "interface/0.1.0"
        / "interface.schema.json"
    )
    schema: dict[str, Any] = json.loads(path.read_text())
    return schema


def test_bench_projection_carries_licence_where_schema_permits(seam: Seam) -> None:
    """Task 12 licence verdict: the vendored schema decides, and it decides
    "nowhere". The bench and device $defs are closed
    (``additionalProperties: false``) with no licence field, so the wire
    projections stay schema-exact and licence is NOT served on either. The
    schema assertions below pin the $defs themselves — a future interface
    version that admits a licence field flips this test and then demands
    the projection carry it. The store assertions pin the documented
    fallback: the licence bootstrap admitted stays in the benches/devices
    rows — queryable at the store, not wire-exposed (the deviation recorded
    in docs/compatibility.md).
    """
    ops, store = seam
    schema = _vendored_interface_schema()
    bench_def = schema["$defs"]["bench"]
    device_def = schema["$defs"]["device"]
    assert bench_def["additionalProperties"] is False
    assert "licence" not in bench_def["properties"]
    assert device_def["additionalProperties"] is False
    assert "licence" not in device_def["properties"]

    # Wire: schema-exact — the projection key set IS the $def property set.
    items, _ = ops.bench_list(OBSERVE, limit=10, cursor=None)
    assert items, "bootstrap admits the fixture bench"
    assert set(items[0]) == set(bench_def["properties"])
    bench = ops.bench_get(OBSERVE, items[0]["bench_id"])
    assert set(bench) == set(bench_def["properties"])
    devices, _ = ops.device_list(OBSERVE, items[0]["bench_id"], limit=10, cursor=None)
    assert devices, "bootstrap admits the fixture devices"
    assert set(devices[0]) == set(device_def["properties"])

    # Store fallback: the admitted licence is retained and queryable, just
    # not wire-exposed. The fixture bench/descriptor docs declare no
    # licence, so the stored value is bootstrap's documented default.
    bench_row = store.get_bench(items[0]["bench_id"])
    device_row = store.get_device(devices[0]["device_id"])
    assert bench_row is not None and device_row is not None
    assert bench_row["licence"] == "proprietary"
    assert device_row["licence"] == "proprietary"


def test_evidence_and_document_surfaces_admit_no_licence(seam: Seam) -> None:
    """The brief's fallback landing is closed too: evidence_get's data
    object and document_get's document object admit no licence field, so
    licence is served on NO observe surface — the deviation register
    records it store-retained instead. Runtime shapes pinned alongside the
    schema shapes the same way.
    """
    ops, store = seam
    schema = _vendored_interface_schema()
    evidence_data = schema["$defs"]["evidence_get_output"]["oneOf"][0]["properties"][
        "data"
    ]
    assert evidence_data["additionalProperties"] is False
    assert "licence" not in evidence_data["properties"]
    document_data = schema["$defs"]["document_get_output"]["oneOf"][0]["properties"][
        "data"
    ]
    document_obj = document_data["properties"]["document"]
    assert document_obj["additionalProperties"] is False
    assert "licence" not in document_obj["properties"]

    row = store.connection.execute("SELECT sha256 FROM documents LIMIT 1").fetchone()
    data = ops.document_get(OBSERVE, row[0])
    assert set(data) == set(document_data["properties"])
    assert set(data["document"]) == set(document_obj["properties"])
