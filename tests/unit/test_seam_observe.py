"""WP07 Task 4: error model, tier gate, observe operations, bootstrap."""

from __future__ import annotations

import base64
import hashlib
import json
import shutil
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
from benchweave.vendoring import active_contract_family

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "execution"
# D1 (issue #450 §3-D1): the corpus family resolves through the vendoring
# helper (manifest-active), never a version literal.
CORPUS = active_contract_family("interface")
Seam = tuple[Operations, Store]
DEVICE_CONTROLLER = "dev.benchweave.sim-controller"  # bootstrap keys rows by descriptor id
BENCH = "sim-bench"  # the bootstrap bench (fixtures/execution/bench.json)


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
    assert data["interface_version"] == "0.1.1"
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
    page = ops.bench_list(OBSERVE, limit=10, cursor=None)
    items = page["items"]
    assert len(items) >= 1 and page["next_cursor"] is None
    bench_id = items[0]["bench_id"]
    devices = ops.device_list(OBSERVE, bench_id, limit=10, cursor=None)["items"]
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
    """The vendored interface schema (the manifest-active family — the
    0.1.1 revision; D1: derived, never a version literal) — the authority
    the licence verdict is decided by, read fresh so this suite pins the
    artifact."""
    path = active_contract_family("interface") / "interface.schema.json"
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
    items = ops.bench_list(OBSERVE, limit=10, cursor=None)["items"]
    assert items, "bootstrap admits the fixture bench"
    assert set(items[0]) == set(bench_def["properties"])
    bench = ops.bench_get(OBSERVE, items[0]["bench_id"])
    assert set(bench) == set(bench_def["properties"])
    devices = ops.device_list(OBSERVE, items[0]["bench_id"], limit=10, cursor=None)["items"]
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


# --- issue #450: the seam-level echo and the CON-10 conformance census --------


def test_paged_seam_returns_page_dicts_with_effective_limit(seam: Seam) -> None:
    """Row 3 (issue #450 §3.3) at the seam: the three paged operations
    return the page object itself — ``limit`` is the effective (clamped)
    value the seam received, emitted at one site shared by both adapters
    (A13; the adapters stop constructing the page)."""
    ops, _ = seam
    page = ops.bench_list(OBSERVE, limit=10, cursor=None)
    assert set(page) == {"items", "next_cursor", "limit"}, page
    assert page["limit"] == 10 and isinstance(page["limit"], int)
    devices = ops.device_list(OBSERVE, "sim-bench", limit=7, cursor=None)
    assert set(devices) == {"items", "next_cursor", "limit"}, devices
    assert devices["limit"] == 7
    events = ops.events_get(OBSERVE, "sim-bench", after=None, limit=3)
    assert events["limit"] == 3
    assert set(events) == {
        "events", "cursor", "stream_id", "oldest_sequence", "current_sequence",
        "limit",
    }, events


def _scratch_standards(tmp_path: Path) -> Path:
    """A copied standards tree for synthesized policy states (the in-tree
    pattern — test_range_narrowing's scratch corpus)."""
    corpus = tmp_path / "standards"
    shutil.copytree(Path(__file__).resolve().parents[2] / "standards", corpus)
    return corpus


def _rewrite_policy(
    corpus: Path, *, yank: str | None = None, retire: str | None = None, narrow: str | None = None
) -> None:
    """Edit the scratch copy's dependency-policy block (a working-tree edit
    on the copy only)."""
    path = corpus / "standards-manifest.json"
    manifest = json.loads(path.read_text())
    policy = manifest["dependency_policy"]["standards"]["otdp"]
    if yank is not None:
        policy["yanked"][yank] = {"reason": "synthetic census", "since": "2026-10-17"}
    if retire is not None:
        policy["retired"] = sorted(set(policy["retired"]) | {retire})
    if narrow is not None:
        policy["range"] = narrow
    path.write_text(json.dumps(manifest, indent=1))


@pytest.mark.parametrize(
    ("policy", "expected"),
    [
        # (scratch edit, then the conformance object the device must serve)
        (
            {"yank": "0.2.2"},
            {
                "otdp_version": "0.2.2",
                "status": "yanked",
                "conformance": "conforming",
                "deprecated": True,
                "acknowledged": False,
            },
        ),
        (
            {"retire": "0.2.2"},
            {
                "otdp_version": "0.2.2",
                "status": "retired",
                "conformance": "non-conforming",
                "deprecated": False,
                "acknowledged": False,
            },
        ),
        (
            {"narrow": ">=0.2.3,<0.3.0"},
            {
                "otdp_version": "0.2.2",
                "status": "nonconforming",
                "conformance": "non-conforming",
                "deprecated": False,
                "acknowledged": False,
            },
        ),
    ],
)
def test_device_conformance_serves_every_policy_class(
    seam: Seam,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    policy: dict[str, str],
    expected: dict[str, object],
) -> None:
    """F4 (issue #450 §3-F4): the wire conformance object is the Q6
    classification of the stored pin, one cell per synthesized policy state
    (the parity lattice carries only served pins — the denominator is
    completed here). ``note`` never rides the wire (VR-37 free-form text
    stays server-side)."""
    import benchweave.control.documents as documents_module

    ops, _ = seam
    corpus = _scratch_standards(tmp_path)
    _rewrite_policy(corpus, **policy)
    monkeypatch.setattr(documents_module, "_otdp_corpus", lambda: corpus)
    device = ops.device_get(OBSERVE, "sim-bench", DEVICE_CONTROLLER)
    assert device["conformance"] == expected, device
    assert "note" not in device["conformance"]


def test_device_conformance_acknowledgement_reads_the_row(
    seam: Seam,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """F4 presence-rule detail: ``acknowledged`` is the row's persisted
    acknowledgement naming THIS pin (the VR-18/issue #219 D11 record, the
    same predicate the log's warning suppression reads) — an ack naming a
    different pin does not apply."""
    import benchweave.control.documents as documents_module

    ops, store = seam
    corpus = _scratch_standards(tmp_path)
    _rewrite_policy(corpus, narrow=">=0.2.3,<0.3.0")
    monkeypatch.setattr(documents_module, "_otdp_corpus", lambda: corpus)

    row = store.get_device(DEVICE_CONTROLLER)
    assert row is not None
    store.put_device(
        row["device_id"], row["bench_id"], row["generation"], row["profiles_json"],
        row["descriptor_json"], row["identity_state"], "proprietary",
        row["updated_at"],
        acknowledgement_json=json.dumps(
            {"otdp_version": "0.2.2", "recorded_at": "2026-10-17T00:00:00Z"}
        ),
    )
    device = ops.device_get(OBSERVE, "sim-bench", DEVICE_CONTROLLER)
    assert device["conformance"]["acknowledged"] is True, device
    assert device["conformance"]["status"] == "nonconforming"

    # An ack naming a DIFFERENT pin does not apply (the R4 fold's rule).
    store.put_device(
        row["device_id"], row["bench_id"], row["generation"], row["profiles_json"],
        row["descriptor_json"], row["identity_state"], "proprietary",
        row["updated_at"],
        acknowledgement_json=json.dumps(
            {"otdp_version": "0.2.1", "recorded_at": "2026-10-17T00:00:00Z"}
        ),
    )
    device = ops.device_get(OBSERVE, "sim-bench", DEVICE_CONTROLLER)
    assert device["conformance"]["acknowledged"] is False, device


def test_device_conformance_unclassifiable_and_legacy_rows(
    seam: Seam,
) -> None:
    """F4's remaining cells: a stored row whose pin is not a parseable
    version serves ``unclassifiable``/``non-conforming`` (the Q6 table's
    fold — the schema's own const refused it at admission; this row was
    seeded at the store, bypassing admission), and a legacy pre-dialect row
    (no ``otdp_version``) OMITS the field entirely (R10 — nothing to
    classify)."""
    ops, store = seam
    bogus = {
        "id": "dev.benchweave.bogus-pin",
        "descriptor_version": "1.0.0",
        "otdp_version": "not-a-version",
    }
    store.put_device(
        "dev.benchweave.bogus-pin", "sim-bench", 1, "[]",
        json.dumps(bogus), "matched", "proprietary", "2026-09-12T00:00:00Z",
    )
    device = ops.device_get(OBSERVE, "sim-bench", "dev.benchweave.bogus-pin")
    assert device["conformance"] == {
        "otdp_version": "not-a-version",
        "status": "unclassifiable",
        "conformance": "non-conforming",
        "deprecated": False,
        "acknowledged": False,
    }, device

    legacy = {"id": "dev.benchweave.legacy", "version": "0.9.0"}
    store.put_device(
        "dev.benchweave.legacy", "sim-bench", 1, "[]",
        json.dumps(legacy), "matched", "proprietary", "2026-09-12T00:00:00Z",
    )
    device = ops.device_get(OBSERVE, "sim-bench", "dev.benchweave.legacy")
    assert "conformance" not in device, device


def test_device_conformance_malformed_governance_omits_the_field(
    seam: Seam,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """F4's degradation posture (the helper's own R10 precedent): malformed
    governance bytes never crash the devices read path — the field is
    omitted and the refusal rides the server-side log."""
    import benchweave.control.documents as documents_module

    ops, _ = seam
    corpus = _scratch_standards(tmp_path)
    (corpus / "corpus-manifest.json").write_text("{not json")
    monkeypatch.setattr(documents_module, "_otdp_corpus", lambda: corpus)
    device = ops.device_get(OBSERVE, "sim-bench", DEVICE_CONTROLLER)
    assert "conformance" not in device, device
    assert device["origin"] == {"kind": "plugin", "basis": "admitted-device-ref"}


def test_device_origin_is_served_on_list_and_get(seam: Seam) -> None:
    """D2 leg 1 at the seam: every device envelope carries the constant
    twin — one emission site (``_device_projection``) serves both
    ``device_list`` and ``device_get``; a device row served without the
    twin means a projection path bypasses it."""
    ops, _ = seam
    listed = ops.device_list(OBSERVE, "sim-bench", limit=10, cursor=None)
    assert listed["items"]
    for device in listed["items"]:
        assert device["origin"] == {"kind": "plugin", "basis": "admitted-device-ref"}
        assert "document" not in device["origin"]
    single = ops.device_get(OBSERVE, "sim-bench", listed["items"][0]["device_id"])
    assert single["origin"] == {"kind": "plugin", "basis": "admitted-device-ref"}
