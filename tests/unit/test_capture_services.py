"""Composing capture services, the controller, and the permission gate.

Derivations (from primary sources, not the plan's restatement):

- The bundle shape is the SDK ``CaptureServices`` protocol (§8, eight
  members: monotonic/utc_now/transfer/close_transport/record_evidence plus
  the three capture methods); the permission-negative shape is plain
  ``HostServices`` (five members) — spec §8 line 216: "Only artifact_writer
  permission grants these services."
- ``adapter_permissions`` reads ``integration.adapter.permissions`` from a
  RAW full-form descriptor (the projected execution view drops
  ``integration`` — CON-10); shape: the active-version
  standards/otdp/<version>/examples/reference-capture.json
  carries ``["scoped_transport", "artifact_writer"]``.
- The fresh-clock rule is the record's Decision 3: "a fresh timestamp per
  call — never a construction-frozen now".
- The forensic mold is C1: put_artifact the JSON payload
  ``{capture_id, operation_id, reason, staged_bytes, reserved_bytes}``,
  then put_evidence(kind="event_log", content_ref={id: capture_id,
  version: "1", sha256: sha256(payload)}, artifact_id=payload artifact,
  context_key=host-minted session key, quota=None). The evidence kind
  enum in standards/interface/0.1.0/interface.schema.json
  ($defs.evidence_get_output) is exactly {document, dataset, artifact,
  event_log} — event_log is legal.
- QuotaLimits defaults are the owner-agreed fork-3 hints (16 MiB capture
  ceiling, 16 subscriptions), commissioned values come from bench
  qualification (A02); ``max_dataset_bytes`` stays REQUIRED — explicit at
  every construction site this slice creates (A18), and the term is an
  honest per-context CAPTURE-byte ceiling (evidence-lane artifact bytes
  are excluded).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

# Module-object access (the new-module RED convention): the test module
# must COLLECT against the parent commit's stubs, so every new name is
# resolved at call time rather than import time.
from benchweave.content import capture_services as services_module
from benchweave.content.store import ContentStore, EvidenceQuotaExceeded
from benchweave.control import documents as documents_module
from benchweave.host.services import QuotaLimits
from benchweave.state.store import Store


def adapter_permissions(descriptor: dict[str, Any]) -> frozenset[str]:
    return documents_module.adapter_permissions(descriptor)

NOW = "2026-09-22T00:00:00Z"
CONTEXT_KEY = "run-host-1/device-2/session-3"

RAW_DESCRIPTOR = {
    "id": "dev.local.reference-capture",
    "descriptor_version": "1.0.0",
    "integration": {
        "mode": "adapter",
        "adapter": {
            "entry_point": "reference_capture:create_plugin",
            "api_version": "1.1",
            "version": "1.0.0",
            "dependencies": [],
            "permissions": ["scoped_transport", "artifact_writer"],
        },
    },
}


@pytest.fixture()
def store(tmp_path: Path) -> Iterator[Store]:
    opened = Store.open(tmp_path / "services.db")
    yield opened
    opened.close()


class CounterClock:
    """A wall clock that advances one second per call — the frozen-``now``
    anti-pattern cannot hide behind it."""

    def __init__(self) -> None:
        self.ticks = 0

    def __call__(self) -> str:
        self.ticks += 1
        return f"2026-09-22T00:{self.ticks:02d}:00Z"


def a_factory(store: Store, **overrides: Any) -> Any:
    content = ContentStore(store)
    payload = json.dumps(RAW_DESCRIPTOR, sort_keys=True).encode()
    digest = hashlib.sha256(payload).hexdigest()
    content.put_document(payload, digest, RAW_DESCRIPTOR, "otdp-descriptor", NOW)
    from benchweave.content.capture_store import CaptureStagingStore

    writer = CaptureStagingStore(
        store, max_capture_bytes=1000, max_dataset_bytes=2000
    )
    settings: dict[str, Any] = {
        "descriptor_digest": digest,
        "content": content,
        "writer": writer,
        "clock": lambda: 1.0,
        "wall": CounterClock(),
        "quota": QuotaLimits(
            max_dataset_bytes=2000, max_evidence_entries=50, max_event_batch=10
        ),
        "context_key": CONTEXT_KEY,
    }
    settings.update(overrides)
    return services_module.build_capture_services(**settings)


# --- the permission read (G-D, A17) ---------------------------------------------


def test_adapter_permissions_reads_the_raw_full_form() -> None:
    assert adapter_permissions(RAW_DESCRIPTOR) == frozenset(
        {"scoped_transport", "artifact_writer"}
    )


@pytest.mark.parametrize(
    ("mutation", "label"),
    [
        ({"integration": None}, "absent integration"),
        ({"integration": {"mode": "declarative"}}, "declarative mode"),
        ({"integration": {"adapter": {}}}, "adapter without permissions"),
        ({"integration": {"adapter": {"permissions": "artifact_writer"}}}, "non-list"),
        ({"integration": {"adapter": {"permissions": [1, None]}}}, "non-string items"),
    ],
)
def test_adapter_permissions_defaults_to_empty_on_non_grant_shapes(
    mutation: dict[str, Any], label: str
) -> None:
    descriptor = dict(RAW_DESCRIPTOR)
    descriptor.update(mutation)
    assert adapter_permissions(descriptor) == frozenset(), label


def test_the_projected_view_carries_no_integration() -> None:
    """A17's premise: the CON-10 projection drops ``integration`` — the
    factory cannot read permissions from the projected view and must
    re-derive the raw form by pinned digest. Pinned against the in-tree
    corpus example (a schema-valid full-form descriptor with capture
    permissions), not a synthetic one."""
    example = json.loads(
        (
            Path(__file__).resolve().parents[2]
            / "standards/otdp/0.2.2/examples/reference-capture.json"
        ).read_text(encoding="utf-8")
    )
    view = documents_module._project_full_form("dev-capture", example)
    assert "integration" not in view
    assert adapter_permissions(example) == frozenset(
        {"scoped_transport", "artifact_writer"}
    )


def test_the_factory_re_derives_the_raw_descriptor_by_pinned_digest(
    store: Store,
) -> None:
    bundle, controller = a_factory(store)
    assert controller is not None  # the raw form carries artifact_writer
    assert hasattr(bundle, "artifact_append")


def test_an_absent_raw_descriptor_refuses_the_factory(store: Store) -> None:
    with pytest.raises(ValueError, match="raw descriptor"):
        a_factory(store, descriptor_digest="0" * 64)


# --- the bundle shapes (permission positive and negative) ------------------------


def test_with_permission_the_bundle_is_the_eight_member_shape(store: Store) -> None:
    bundle, controller = a_factory(store)
    assert controller is not None
    for member in (
        "monotonic",
        "utc_now",
        "transfer",
        "close_transport",
        "record_evidence",
    ):
        assert hasattr(bundle, member), member
    for member in ("artifact_append", "artifact_finalise", "artifact_abort"):
        assert hasattr(bundle, member), member
    import asyncio

    for member in (
        "transfer",
        "close_transport",
        "record_evidence",
        "artifact_append",
        "artifact_finalise",
        "artifact_abort",
    ):
        assert asyncio.iscoroutinefunction(getattr(type(bundle), member)), member


def test_without_permission_the_capture_members_are_structurally_absent(
    store: Store,
) -> None:
    negative = dict(
        RAW_DESCRIPTOR,
        integration={"mode": "adapter", "adapter": {
            "entry_point": "x:y", "api_version": "1.1", "version": "1.0.0",
            "dependencies": [], "permissions": ["scoped_transport"],
        }},
    )
    payload = json.dumps(negative, sort_keys=True).encode()
    digest = hashlib.sha256(payload).hexdigest()
    ContentStore(store).put_document(payload, digest, negative, "otdp-descriptor", NOW)
    bundle, controller = a_factory(store, descriptor_digest=digest)
    assert controller is None  # no capture writer exists at all
    for member in ("artifact_append", "artifact_finalise", "artifact_abort"):
        assert not hasattr(bundle, member), member  # structural absence
    for member in ("monotonic", "utc_now", "record_evidence"):
        assert hasattr(bundle, member), member  # the five-member shape stands


# --- the clocks: fresh per call (the frozen-now anti-test) ------------------------


def test_every_wall_read_is_fresh_never_construction_frozen(store: Store) -> None:
    bundle, _controller = a_factory(store)
    first = bundle.utc_now()
    second = bundle.utc_now()
    third = bundle.utc_now()
    assert len({first, second, third}) == 3  # three calls, three stamps


# --- evidence under the host-minted context key ------------------------------------


def test_record_evidence_writes_under_the_host_minted_context_key(
    store: Store,
) -> None:
    bundle, _controller = a_factory(store)
    entry = {"kind": "device_error", "entry": {"code": "E1", "message": "fault"}}
    import asyncio

    asyncio.run(bundle.record_evidence(entry, context=None))
    rows = store.connection.execute(
        "SELECT kind, context_key, artifact_id, content_ref_json FROM evidence"
    ).fetchall()
    assert len(rows) == 1
    kind, context_key, artifact_id, ref_json = rows[0]
    assert kind == "event_log"  # the contract-legal mold (C1's family)
    assert context_key == CONTEXT_KEY  # host-minted, never caller-supplied
    assert artifact_id is not None
    ref = json.loads(ref_json)
    assert set(ref) == {"id", "version", "sha256"}  # the closed doc-ref shape
    payload = store.connection.execute(
        "SELECT data FROM artifacts WHERE artifact_id = ?", (artifact_id,)
    ).fetchone()[0]
    assert hashlib.sha256(bytes(payload)).hexdigest() == ref["sha256"]
    assert json.loads(bytes(payload)) == entry  # the entry is preserved verbatim


def test_evidence_quota_exhaustion_refuses_with_the_bundle_stamp(store: Store) -> None:
    """B8: the bundle's record_evidence carries a named cap on its own
    kind-scoped accounting dimension (``(context_key, kind)`` — re-scoped at
    the streaming slice; every row this path writes is ``event_log``, so the
    arm's outcome is unchanged); exhaustion raises EvidenceQuotaExceeded
    through execute (joining the non-poisoning classification in the bridge)."""
    from benchweave.host.services import QuotaLimits as Limits

    bundle, _controller = a_factory(
        store,
        quota=Limits(max_dataset_bytes=2000, max_evidence_entries=1, max_event_batch=10),
    )
    import asyncio

    asyncio.run(
        bundle.record_evidence(
            {"kind": "device_error", "entry": {"code": "E1", "message": "one"}}, None
        )
    )
    with pytest.raises(EvidenceQuotaExceeded):
        asyncio.run(
            bundle.record_evidence(
                {"kind": "device_error", "entry": {"code": "E2", "message": "two"}}, None
            )
        )


def test_transport_delegates_or_refuses_loudly(store: Store) -> None:
    bundle, _controller = a_factory(store)  # no transport injected
    import asyncio

    with pytest.raises(NotImplementedError, match="transport"):
        asyncio.run(bundle.transfer({"kind": "x"}, context=None))
    with pytest.raises(NotImplementedError, match="transport"):
        asyncio.run(bundle.close_transport(context=None))


# --- the capture path through the bundle -------------------------------------------


def test_the_bundle_drives_the_writer_and_builds_the_manifest(store: Store) -> None:
    bundle, controller = a_factory(store)
    assert controller is not None
    controller.open_capture(
        capture_id="cap-1", fmt="waveform_f64le", sample_count=2, max_bytes=16
    )
    import asyncio

    asyncio.run(bundle.artifact_append("cap-1", b"\x01" * 8, context=None))
    asyncio.run(bundle.artifact_append("cap-1", b"\x02" * 8, context=None))
    manifest = asyncio.run(
        bundle.artifact_finalise(
            "cap-1",
            {
                "format": "waveform_f64le",
                "started_at": "2026-09-22T00:00:00Z",
                "sample_interval_s": 0.001,
                "unit": "V",
            },
            context=None,
        )
    )
    digest = hashlib.sha256(b"\x01" * 8 + b"\x02" * 8).hexdigest()
    assert manifest == {
        "capture_id": "cap-1",
        "format": "waveform_f64le",
        "artifact_id": "art-" + digest,
        "byte_length": 16,
        "sha256": digest,
        "started_at": "2026-09-22T00:00:00Z",
        "sample_count": 2,
        "sample_interval_s": 0.001,
        "unit": "V",
    }


def test_finalise_validates_the_adapter_metadata(store: Store) -> None:
    bundle, controller = a_factory(store)
    assert controller is not None
    controller.open_capture(
        capture_id="cap-1", fmt="raw_binary", sample_count=None, max_bytes=16
    )
    import asyncio

    asyncio.run(bundle.artifact_append("cap-1", b"\x01" * 16, context=None))
    for metadata, pattern in (
        ({"format": "csv", "started_at": "2026-09-22T00:00:00Z"}, "disagrees"),
        ({"format": "raw_binary"}, "started_at"),
        ({"format": "raw_binary", "started_at": ""}, "started_at"),
    ):
        with pytest.raises(ValueError, match=pattern):
            asyncio.run(bundle.artifact_finalise("cap-1", metadata, context=None))


# --- the controller: forensic mold, once-guard, sweep -------------------------------


def seeded_controller(store: Store) -> tuple[Any, Any, Store]:
    bundle, controller = a_factory(store)
    assert controller is not None
    controller.open_capture(
        capture_id="cap-1", fmt="raw_binary", sample_count=None, max_bytes=32
    )
    return bundle, controller, store


def forensic_rows(store: Store) -> list[tuple[str, str, str, str]]:
    return [
        (str(row[0]), str(row[1]), str(row[2]), str(row[3]))
        for row in store.connection.execute(
            "SELECT kind, content_ref_json, artifact_id, context_key FROM evidence"
            " WHERE kind = 'event_log'"
        ).fetchall()
    ]


def test_abort_reclaims_and_writes_exactly_one_forensic_row(store: Store) -> None:
    _bundle, controller, store = seeded_controller(store)
    import asyncio

    from benchweave.content.capture_store import CaptureStagingStore  # noqa: F401

    asyncio.run(_bundle.artifact_append("cap-1", b"\x01" * 8, context=None))
    assert controller.abort("cap-1", reason="dispatch failed", operation_id="op-1")
    rows = forensic_rows(store)
    assert len(rows) == 1  # exactly one forensic row (the once-guard)
    kind, ref_json, artifact_id, context_key = rows[0]
    assert kind == "event_log"
    assert context_key == CONTEXT_KEY
    ref = json.loads(ref_json)
    assert ref["id"] == "cap-1"  # the doc-ref names the capture
    assert ref["version"] == "1"
    payload = store.connection.execute(
        "SELECT data FROM artifacts WHERE artifact_id = ?", (artifact_id,)
    ).fetchone()[0]
    assert ref["sha256"] == hashlib.sha256(bytes(payload)).hexdigest()
    decoded = json.loads(bytes(payload))
    assert decoded == {
        "capture_id": "cap-1",
        "operation_id": "op-1",
        "artifact_id": None,  # nothing published: the plain-abort shape
        "reason": "dispatch failed",
        "staged_bytes": 8,
        "reserved_bytes": 32,
    }
    # R2's writer leg: zero staging rows.
    staged = store.connection.execute(
        "SELECT COUNT(*) FROM capture_staging WHERE capture_id = 'cap-1'"
    ).fetchone()[0]
    assert staged == 0
    # The once-guard: a second abort writes nothing.
    assert controller.abort("cap-1", reason="again", operation_id="op-2") is False
    assert len(forensic_rows(store)) == 1


def test_abort_of_an_unopened_capture_writes_nothing(store: Store) -> None:
    _bundle, controller, store = seeded_controller(store)
    assert controller.abort("cap-never", reason="gate refusal", operation_id="op-0") is False
    assert forensic_rows(store) == []  # no spurious markers (A8)


def test_sweep_open_aborts_still_open_captures(store: Store) -> None:
    bundle, controller = a_factory(store)
    assert controller is not None
    controller.open_capture(
        capture_id="cap-a", fmt="raw_binary", sample_count=None, max_bytes=16
    )
    controller.open_capture(
        capture_id="cap-b", fmt="raw_binary", sample_count=None, max_bytes=16
    )
    controller.open_capture(
        capture_id="cap-c", fmt="raw_binary", sample_count=None, max_bytes=16
    )
    import asyncio

    asyncio.run(bundle.artifact_append("cap-b", b"\x01" * 8, context=None))
    controller.abort("cap-b", reason="failed", operation_id="op-1")
    reclaimed = controller.sweep_open(reason="plugin_close")
    assert sorted(reclaimed) == ["cap-a", "cap-c"]  # cap-b already terminal
    rows = forensic_rows(store)
    assert {json.loads(ref)["id"] for _kind, ref, _aid, _ck in rows} == {
        "cap-a",
        "cap-b",
        "cap-c",
    }
    staged = store.connection.execute(
        "SELECT COUNT(*) FROM capture_staging"
    ).fetchone()[0]
    assert staged == 0


# --- QuotaLimits (A18/fork 3) --------------------------------------------------------


def test_quota_limits_grow_the_two_fields_with_hint_defaults() -> None:
    limits = QuotaLimits(
        max_dataset_bytes=2000, max_evidence_entries=50, max_event_batch=10
    )
    assert limits.max_capture_bytes == 16 * 1024 * 1024
    assert limits.max_subscriptions == 16


@pytest.mark.parametrize("field", ["max_capture_bytes", "max_subscriptions"])
def test_the_new_quota_fields_refuse_values_below_one(field: str) -> None:
    with pytest.raises(ValueError, match=field):
        QuotaLimits(
            max_dataset_bytes=2000,
            max_evidence_entries=50,
            max_event_batch=10,
            **{field: 0},
        )


def test_max_dataset_bytes_stays_required_and_explicit() -> None:
    with pytest.raises(TypeError):
        QuotaLimits(max_evidence_entries=50, max_event_batch=10)  # type: ignore[call-arg]
